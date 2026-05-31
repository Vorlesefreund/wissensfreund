import 'dart:convert';
import 'dart:io';

import 'package:convert/convert.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/asset_config.dart';
import 'license_cache_db.dart';
import 'network_service.dart';
import 'storage_manager.dart';
import 'subscription_service.dart';

const _ua               = 'Wissensfreund/1.0';
const _downloadTimeout  = Duration(seconds: 15);
const _originalMaxBytes = 5 * 1024 * 1024;  // originals ≥ 5 MB → use thumb instead
const _maxCacheBytes    = 500 * 1024 * 1024;
const _targetCacheBytes = 400 * 1024 * 1024;

const _wikimediaBase      = 'https://upload.wikimedia.org/wikipedia/commons';
const _wikimediaThumbBase = '$_wikimediaBase/thumb';

class _ImageMeta {
  final String filename;
  final String sourceUrl;
  final String author;
  final String license;
  const _ImageMeta({
    required this.filename,
    required this.sourceUrl,
    required this.author,
    required this.license,
  });
}

/// Downloads on-demand high-res images from Wikimedia Commons.
///
/// Step 1: HEAD the original file — load if < 5 MB, else fall through.
/// Step 2: Request 2048px thumbnail.
/// 404 at either step → negative in-memory cache (skips future attempts).
/// On null: caller falls back to offline ZIP or ZIM.
class HiResImageService {
  HiResImageService._();
  static final HiResImageService instance = HiResImageService._();

  bool _loading = false;

  // image_index.json: ZIM hash key → image metadata (v1: String, v2: object)
  Map<String, _ImageMeta>? _index;
  bool _indexLoading = false;

  // Commons filenames confirmed 404 at both steps — skip on next request.
  final Set<String> _hiResFailed = {};

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Returns the best available image bytes for [filename] (_assets_/ path), or null.
  Future<Uint8List?> getHiResImage(String filename) async {
    final cached = await _fromCache(filename);
    if (cached != null) return cached;

    if (!SubscriptionService.instance.canUseHighResOnDemand) return null;

    final commonsFilename = await _lookupCommonsFilename(filename);
    if (commonsFilename == null) return null;

    if (_hiResFailed.contains(commonsFilename)) return null;

    if (_loading) return null;

    final check = await NetworkService.instance.canUseNetwork(
      estimatedBytes: _originalMaxBytes,
    );
    if (!check.allowed) return null;

    _loading = true;
    try {
      return await _download(filename, commonsFilename);
    } catch (e) {
      debugPrint('HiRes: error for $commonsFilename: $e');
      return null;
    } finally {
      _loading = false;
    }
  }

  // ── Index ─────────────────────────────────────────────────────────────────────

  Future<String?> _lookupCommonsFilename(String zimFilename) async {
    final meta = await lookupMeta(zimFilename);
    return meta?.filename.isNotEmpty == true ? meta!.filename : null;
  }

  /// Returns full metadata for [zimFilename], or null if not found.
  Future<_ImageMeta?> lookupMeta(String zimFilename) async {
    final index = await _loadIndex();
    if (index == null) return null;
    final key = zimFilename.replaceFirst(RegExp(r'^_assets_[/\\]'), '');
    return index[key];
  }

  Future<Map<String, _ImageMeta>?> _loadIndex() async {
    if (_index != null) return _index;
    if (_indexLoading) return null;
    _indexLoading = true;
    try {
      final client = http.Client();
      try {
        final resp = await client
            .get(Uri.parse(AssetConfig.imageIndexUrl), headers: {'User-Agent': _ua})
            .timeout(const Duration(seconds: 20));
        if (resp.statusCode != 200) {
          debugPrint('HiRes: index fetch failed (${resp.statusCode})');
          return null;
        }
        final raw = json.decode(resp.body) as Map<String, dynamic>;
        _index = raw.map((k, v) {
          if (v is String) {
            return MapEntry(k, _ImageMeta(filename: v, sourceUrl: '', author: '', license: ''));
          }
          final m = v as Map<String, dynamic>;
          return MapEntry(k, _ImageMeta(
            filename:  m['filename']   as String? ?? '',
            sourceUrl: m['source_url'] as String? ?? '',
            author:    m['author']     as String? ?? '',
            license:   m['license']    as String? ?? '',
          ));
        });
        debugPrint('HiRes: index loaded (${_index!.length} entries)');
        return _index;
      } finally {
        client.close();
      }
    } catch (e) {
      debugPrint('HiRes: index load error: $e');
      return null;
    } finally {
      _indexLoading = false;
    }
  }

  // ── URL helpers ───────────────────────────────────────────────────────────────

  static ({String h0, String h2, String encoded}) _urlParts(String commonsFilename) {
    final md5Hash = hex.encode(md5.convert(utf8.encode(commonsFilename)).bytes);
    return (
      h0:      md5Hash[0],
      h2:      md5Hash.substring(0, 2),
      encoded: Uri.encodeComponent(commonsFilename),
    );
  }

  static String _originalUrl(String commonsFilename) {
    final p = _urlParts(commonsFilename);
    return '$_wikimediaBase/${p.h0}/${p.h2}/${p.encoded}';
  }

  static String _thumbUrl(String commonsFilename) {
    final p = _urlParts(commonsFilename);
    final isSvg   = commonsFilename.toLowerCase().endsWith('.svg');
    final suffix  = isSvg ? '2048px-${p.encoded}.png' : '2048px-${p.encoded}';
    return '$_wikimediaThumbBase/${p.h0}/${p.h2}/${p.encoded}/$suffix';
  }

  // ── Download logic ────────────────────────────────────────────────────────────

  Future<Uint8List?> _download(String zimFilename, String commonsFilename) async {
    final client = http.Client();
    try {
      // Step 1 — probe the original file via HEAD.
      final headResp = await client
          .head(Uri.parse(_originalUrl(commonsFilename)), headers: {'User-Agent': _ua})
          .timeout(_downloadTimeout);

      if (headResp.statusCode == 404) {
        debugPrint('HiRes: original 404 → $commonsFilename');
        _hiResFailed.add(commonsFilename);
        return null;
      }

      if (headResp.statusCode == 200) {
        final contentLength = int.tryParse(
          headResp.headers['content-length'] ?? '',
        );

        if (contentLength == null || contentLength < _originalMaxBytes) {
          // No Content-Length or small enough → fetch original.
          final bytes = await _get(client, _originalUrl(commonsFilename));
          if (bytes != null) {
            if (bytes.length < _originalMaxBytes) {
              await _cache(zimFilename, commonsFilename, bytes);
              return bytes;
            }
            // Unexpectedly large despite HEAD → fall through to thumb.
          }
          // GET failed with non-404 → fall through to thumb.
        }
        // Content-Length ≥ 5 MB → fall through to thumb.
      }
      // Any non-200/404 HEAD status → fall through to thumb.

      // Step 2 — 2048px thumbnail.
      final thumbBytes = await _get(client, _thumbUrl(commonsFilename));
      if (thumbBytes != null) {
        await _cache(zimFilename, commonsFilename, thumbBytes);
        return thumbBytes;
      }
      return null;
    } finally {
      client.close();
    }
  }

  /// GET [url], returns bytes on 200, null otherwise.
  /// Adds to negative cache on 404.
  Future<Uint8List?> _get(http.Client client, String url) async {
    try {
      final resp = await client
          .get(Uri.parse(url), headers: {'User-Agent': _ua})
          .timeout(_downloadTimeout);

      if (resp.statusCode == 200 && resp.bodyBytes.isNotEmpty) {
        return resp.bodyBytes;
      }
      if (resp.statusCode == 404) {
        // Caller decides whether to add to negative cache.
        debugPrint('HiRes: GET 404 $url');
      } else {
        debugPrint('HiRes: GET ${resp.statusCode} $url');
      }
      return null;
    } catch (e) {
      debugPrint('HiRes: GET error $url — $e');
      return null;
    }
  }

  Future<void> _cache(
    String zimFilename,
    String commonsFilename,
    Uint8List bytes,
  ) async {
    await _saveToCache(zimFilename, bytes);
    await NetworkService.instance.recordUsage(bytes.length);
    debugPrint('HiRes: cached $commonsFilename (${bytes.length ~/ 1024} KB)');
  }

  // ── Negative cache: mark 404 from thumb step ──────────────────────────────────
  //
  // _get() returns null for 404 but does not mutate _hiResFailed — _download()
  // adds to the set only when *both* steps fail with a definitive 404, inferred
  // from _get() returning null after the thumb URL. We cannot distinguish 404
  // from network errors here, so we only add when the original HEAD was 404
  // (handled above) or when the caller wants an explicit mark.
  //
  // For the thumb step: a null return may mean 404 or a transient error.
  // We do NOT add to negative cache here — a transient failure should be
  // retried next time the user opens the article.

  // ── Cache storage ─────────────────────────────────────────────────────────────

  Future<Uint8List?> _fromCache(String filename) async {
    final file = _cacheFile(filename);
    if (!file.existsSync()) return null;
    try {
      await LicenseCacheDb.instance.touchImageCache(filename);
      return file.readAsBytesSync();
    } catch (_) {
      return null;
    }
  }

  Future<void> _saveToCache(String filename, Uint8List bytes) async {
    final dir = StorageManager.instance.imageCacheDir;
    if (!dir.existsSync()) await dir.create(recursive: true);

    final file   = _cacheFile(filename);
    final parent = file.parent;
    if (!parent.existsSync()) await parent.create(recursive: true);
    await file.writeAsBytes(bytes);

    await LicenseCacheDb.instance.upsertImageCache(
      filename:  filename,
      localPath: file.path,
      fileSize:  bytes.length,
    );

    await _evictIfNeeded();
  }

  Future<void> _evictIfNeeded() async {
    final total = await cacheSizeBytes();
    if (total <= _maxCacheBytes) return;

    final dir = StorageManager.instance.imageCacheDir;
    if (!dir.existsSync()) return;

    final files = dir
        .listSync(recursive: false)
        .whereType<File>()
        .toList()
      ..sort((a, b) => a.statSync().modified.compareTo(b.statSync().modified));

    int remaining = total;
    for (final file in files) {
      if (remaining <= _targetCacheBytes) break;
      try {
        final size = file.statSync().size;
        file.deleteSync();
        remaining -= size;
      } catch (_) {}
    }
  }

  File _cacheFile(String filename) {
    final key = filename.replaceFirst(RegExp(r'^_assets_[/\\]'), '');
    return File('${StorageManager.instance.imageCacheDir.path}/$key');
  }

  Future<int> cacheSizeBytes() => LicenseCacheDb.instance.imageCacheTotalBytes();

  Future<void> clearCache() async {
    final dir = StorageManager.instance.imageCacheDir;
    if (dir.existsSync()) {
      await dir.delete(recursive: true);
      await dir.create(recursive: true);
    }
    await LicenseCacheDb.instance.clearImageCacheIndex();
  }

  void resetIndex() {
    _index = null;
    _indexLoading = false;
  }
}
