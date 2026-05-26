import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'license_cache_db.dart';
import 'network_service.dart';
import 'storage_manager.dart';
import 'subscription_service.dart';

const _commonsFilePath = 'https://commons.wikimedia.org/wiki/Special:FilePath';
const _ua              = 'Wissensfreund/1.0';
const _downloadTimeout = Duration(seconds: 8);
const _maxBytes        = 3 * 1024 * 1024;   // 3 MB per image
const _maxCacheBytes   = 500 * 1024 * 1024; // 500 MB LRU cache limit
const _targetCacheBytes = 400 * 1024 * 1024; // evict down to 400 MB

/// Downloads on-demand 1200px images from Wikimedia Commons.
///
/// - Plus/Premium only.
/// - Only on WiFi (or allowed mobile connection).
/// - One download at a time; further requests silently return null.
/// - LRU cache in StorageManager.imageCacheDir, max 500 MB.
/// - Max 3 MB per image, 8 s download timeout.
class HiResImageService {
  HiResImageService._();
  static final HiResImageService instance = HiResImageService._();

  bool _loading = false;

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Returns 1200px image bytes for [filename] (ZIM filename), or null.
  Future<Uint8List?> getHiResImage(String filename) async {
    // Local cache hit.
    final cached = await _fromCache(filename);
    if (cached != null) return cached;

    // Feature gate — Plus or Premium only.
    if (!SubscriptionService.instance.canUseHighResOnDemand) return null;

    // Resolve the Commons filename from the ZIM thumbnail path.
    final commonsFilename = _extractCommonsFilename(filename);
    if (commonsFilename == null) return null; // ZIM-only image, no Commons source

    // Only one concurrent download.
    if (_loading) return null;

    // Network gate — enforces WiFi/mobile settings and data limits.
    final check = await NetworkService.instance.canUseNetwork(estimatedBytes: _maxBytes);
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

  // ── Internal ─────────────────────────────────────────────────────────────────

  /// Extracts the original Commons filename from a ZIM thumbnail path.
  ///
  /// ZIM stores MediaWiki thumbnails as `langde-{size}px-{original}`.
  /// SVGs are rendered to PNG in the ZIM, producing a double extension (.svg.png).
  static String? _extractCommonsFilename(String zimFilename) {
    final basename = zimFilename.split('/').last;
    final m = RegExp(r'^[a-z]+-\d+px-(.+)', caseSensitive: false).firstMatch(basename);
    if (m == null) return null;
    String original = m.group(1)!;
    if (original.toLowerCase().endsWith('.svg.png')) {
      original = original.substring(0, original.length - 4);
    }
    return original;
  }

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
    final url = '$_commonsFilePath/${Uri.encodeComponent(commonsFilename)}?width=1200';
    final client = http.Client();
    try {
      final resp = await client
          .get(Uri.parse(url), headers: {'User-Agent': _ua})
          .timeout(_downloadTimeout);

      if (resp.statusCode != 200) return null;

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

  File _cacheFile(String filename) =>
      File('${StorageManager.instance.imageCacheDir.path}/$filename');

  Future<int> cacheSizeBytes() => LicenseCacheDb.instance.imageCacheTotalBytes();

  Future<void> clearCache() async {
    final dir = StorageManager.instance.imageCacheDir;
    if (dir.existsSync()) {
      await dir.delete(recursive: true);
      await dir.create(recursive: true);
    }
    await LicenseCacheDb.instance.clearImageCacheIndex();
  }
}
