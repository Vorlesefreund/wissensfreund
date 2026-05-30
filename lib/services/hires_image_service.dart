import 'dart:convert';
import 'dart:io';;

import 'package:convert/convert.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/asset_config.dart';
import 'license_cache_db.dart';
import 'network_service.dart';
import 'storage_manager.dart';
import 'subscription_service.dart';

const _ua              = 'Wissensfreund/1.0';
const _downloadTimeout = Duration(seconds: 15);
const _maxBytes        = 8 * 1024 * 1024;   // 8 MB per image (2048px can be large)
const _maxCacheBytes   = 500 * 1024 * 1024; // 500 MB LRU cache limit
const _targetCacheBytes = 400 * 1024 * 1024;

const _wikimediaThumbBase =
    'https://upload.wikimedia.org/wikipedia/commons/thumb';

/// Downloads on-demand 2048px images from Wikimedia Commons.
///
/// - Plus/Premium only.
/// - Only on WiFi (or allowed mobile connection).
/// - One download at a time; further requests silently return null.
/// - LRU cache in StorageManager.imageCacheDir, max 500 MB.
/// - Uses image_index.json (hash → Commons filename) loaded from R2.
class HiResImageService {
  HiResImageService._();
  static final HiResImageService instance = HiResImageService._();

  bool _loading = false;

  // image_index.json: ZIM hash (e.g. "d772913a.jpg") → Commons filename
  Map<String, String>? _index;
  bool _indexLoading = false;

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Returns 2048px image bytes for [filename] (ZIM _assets_/ path), or null.
  Future<Uint8List?> getHiResImage(String filename) async {
    // Local cache hit.
    final cached = await _fromCache(filename);
    if (cached != null) return cached;

    // Feature gate — Plus or Premium only.
    if (!SubscriptionService.instance.canUseHighResOnDemand) return null;

    // Resolve Commons filename from index.
    final commonsFilename = await _lookupCommonsFilename(filename);
    if (commonsFilename == null) return null;

    // Only one concurrent download.
    if (_loading) return null;

    // Network gate — enforces WiFi/mobile settings and data limits.
    final check = await NetworkService.instance.canUseNetwork(
      estimatedBytes: _maxBytes,
    );
    if (!check.allowed) return null;

    _loading = true;
    try {
      return await _download(filename, commonsFilename);
    } catch (e) {
      debugPrint('HiRes: error for $filename: $e');
      return null;
    } finally {
      _loading = false;
    }
  }

  // ── Index ─────────────────────────────────────────────────────────────────────

  /// Looks up the Commons filename for a ZIM _assets_/ path.
  Future<String?> _lookupCommonsFilename(String zimFilename) async {
    final index = await _loadIndex();
    if (index == null) return null;
    // Strip _assets_/ prefix to get the hash key (e.g. "d772913a.jpg").
    final key = zimFilename.replaceFirst(RegExp(r'^_assets_[/\\]'), '');
    return index[key];
  }

  /// Loads image_index.json from R2 on first call, then returns cached map.
  Future<Map<String, String>?> _loadIndex() async {
    if (_index != null) return _index;
    if (_indexLoading) return null;
    _indexLoading = true;
    try {
      final client = http.Client();
      try {
        final resp = await client
            .get(
              Uri.parse(AssetConfig.imageIndexUrl),
              headers: {'User-Agent': _ua},
            )
            .timeout(const Duration(seconds: 20));
        if (resp.statusCode != 200) {
          debugPrint('HiRes: image_index.json fetch failed (${resp.statusCode})');
          return null;
        }
        final raw = json.decode(resp.body) as Map<String, dynamic>;
        _index = raw.map((k, v) => MapEntry(k, v as String));
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

  // ── URL computation ───────────────────────────────────────────────────────────

  /// Builds the Wikimedia thumb URL for [commonsFilename] at 2048px.
  ///
  /// Format: .../thumb/{md5[0]}/{md5[0..1]}/{encoded}/2048px-{encoded}
  /// SVG: suffix becomes 2048px-{encoded}.png
  static String _thumbUrl(String commonsFilename) {
    final md5Hash = hex.encode(md5.convert(utf8.encode(commonsFilename)).bytes);
    final encoded = Uri.encodeComponent(commonsFilename);
    final suffix  = commonsFilename.toLowerCase().endsWith('.svg')
        ? '2048px-$encoded.png'
        : '2048px-$encoded';
    return '$_wikimediaThumbBase/${md5Hash[0]}/${md5Hash.substring(0, 2)}/$encoded/$suffix';
  }

  // ── Download + cache ─────────────────────────────────────────────────────────

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

  Future<Uint8List?> _download(String zimFilename, String commonsFilename) async {
    final url = _thumbUrl(commonsFilename);
    final client = http.Client();
    try {
      final resp = await client
          .get(Uri.parse(url), headers: {'User-Agent': _ua})
          .timeout(_downloadTimeout);

      if (resp.statusCode != 200) {
        debugPrint('HiRes: $commonsFilename → HTTP ${resp.statusCode}');
        return null;
      }

      final bytes = resp.bodyBytes;
      if (bytes.isEmpty || bytes.length > _maxBytes) {
        debugPrint('HiRes: $commonsFilename size ${bytes.length ~/ 1024} KB — skipped');
        return null;
      }

      await _saveToCache(zimFilename, bytes);
      await NetworkService.instance.recordUsage(bytes.length);
      debugPrint('HiRes: cached $commonsFilename (${bytes.length ~/ 1024} KB)');
      return bytes;
    } finally {
      client.close();
    }
  }

  Future<void> _saveToCache(String filename, Uint8List bytes) async {
    final dir = StorageManager.instance.imageCacheDir;
    if (!dir.existsSync()) await dir.create(recursive: true);

    final file = _cacheFile(filename);
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

  /// LRU eviction: if cache exceeds 500 MB, delete oldest files until ~400 MB.
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

  /// Clears the in-memory index (forces re-fetch on next request).
  void resetIndex() {
    _index = null;
    _indexLoading = false;
  }
}
