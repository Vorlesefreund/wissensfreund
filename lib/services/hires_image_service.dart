import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'license_cache_db.dart';
import 'storage_manager.dart';

const _wikimediaApiBase = 'https://api.wikimedia.org/core/v1/commons/file';
const _ua               = 'Wissensfreund/1.0';
const _apiTimeout        = Duration(seconds: 5);
const _downloadTimeout   = Duration(seconds: 8);
const _maxBytes          = 3 * 1024 * 1024; // 3 MB

/// Downloads on-demand high-resolution images (1600px) from Wikimedia Commons.
///
/// - Only on WiFi.
/// - One download at a time (further requests silently return null).
/// - Caches result in StorageManager.imageCacheDir + SQLite index.
/// - Max 3 MB per image, 8s download timeout.
class HiResImageService {
  HiResImageService._();
  static final HiResImageService instance = HiResImageService._();

  bool _loading = false;

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Returns 1600px image bytes for [filename], or null on any error.
  /// Checks local cache first; downloads from Wikimedia otherwise.
  Future<Uint8List?> getHiResImage(String filename) async {
    // Local cache hit.
    final cached = await _fromCache(filename);
    if (cached != null) return cached;

    // Only one concurrent download.
    if (_loading) return null;

    // WiFi required.
    final conn = await Connectivity().checkConnectivity();
    if (!conn.contains(ConnectivityResult.wifi)) return null;

    _loading = true;
    try {
      return await _download(filename);
    } catch (e) {
      debugPrint('HiRes: error for $filename: $e');
      return null;
    } finally {
      _loading = false;
    }
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

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

  Future<Uint8List?> _download(String filename) async {
    final client = http.Client();
    try {
      // Step 1: resolve 1600px URL via Wikimedia REST API.
      final encodedName = Uri.encodeComponent(filename.replaceAll(' ', '_'));
      final apiResp = await client
          .get(
            Uri.parse('$_wikimediaApiBase/File:$encodedName'),
            headers: {'User-Agent': _ua},
          )
          .timeout(_apiTimeout);

      if (apiResp.statusCode != 200) return null;

      final data      = jsonDecode(apiResp.body) as Map<String, dynamic>;
      final preferred = data['preferred'] as Map<String, dynamic>?;
      final original  = data['original']  as Map<String, dynamic>?;
      final baseUrl   = preferred?['url'] as String? ?? original?['url'] as String?;
      if (baseUrl == null) return null;

      final url1600 = '$baseUrl?width=1600';

      // Step 2: download image.
      final imgResp = await client
          .get(Uri.parse(url1600), headers: {'User-Agent': _ua})
          .timeout(_downloadTimeout);

      if (imgResp.statusCode != 200) return null;

      final bytes = imgResp.bodyBytes;
      if (bytes.length > _maxBytes) {
        debugPrint('HiRes: $filename too large (${bytes.length ~/ 1024} KB) — skipped');
        return null;
      }

      // Step 3: save to cache.
      await _saveToCache(filename, bytes);
      debugPrint('HiRes: cached $filename (${bytes.length ~/ 1024} KB)');
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
