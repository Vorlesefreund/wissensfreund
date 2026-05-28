import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/asset_config.dart';
import 'asset_download_service.dart';
import 'storage_manager.dart';

/// Manages the offline image library (medium quality, ~800px wide).
///
/// Images are stored in StorageManager.imageLibraryDir.
/// Download is triggered from the onboarding quality dialog.
class ImageLibraryService {
  ImageLibraryService._();
  static final ImageLibraryService instance = ImageLibraryService._();

  bool _downloading = false;
  double _downloadProgress = 0;
  int _downloadedBytes = 0;
  int _downloadTotalBytes = 0;
  Duration? _downloadEta;

  // ── Public API ───────────────────────────────────────────────────────────────

  /// Returns image bytes from the offline library, or null if not available.
  Future<Uint8List?> getImage(String filename) async {
    final file = _fileFor(filename);
    if (!file.existsSync()) return null;
    try {
      return file.readAsBytesSync();
    } catch (_) {
      return null;
    }
  }

  bool hasImage(String filename) => _fileFor(filename).existsSync();

  /// Total size of image_library/ in bytes.
  int get totalSizeBytes {
    final dir = StorageManager.instance.imageLibraryDir;
    if (!dir.existsSync()) return 0;
    return dir
        .listSync(recursive: true)
        .whereType<File>()
        .fold(0, (s, f) {
      try { return s + f.lengthSync(); } catch (_) { return s; }
    });
  }

  bool get isDownloading => _downloading;
  double get downloadProgress => _downloadProgress;
  int get downloadedBytes => _downloadedBytes;
  int get downloadTotalBytes => _downloadTotalBytes;
  Duration? get downloadEta => _downloadEta;

  /// Returns true if thumb tier (300px), false if standard (600px), null if unknown.
  static Future<bool?> getStoredTier() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('image_library_thumb_tier');
  }

  /// Downloads the image library ZIP from R2, extracts it into image_library/.
  /// [thumbTier] = true → 300px Free tier; false → 600px Plus/Premium tier.
  /// Returns null on success, or an error code string on failure.
  /// No-op (returns 'already_downloading') if already downloading.
  Future<String?> downloadLibrary({
    bool thumbTier = false,
    void Function(int received, int total, Duration eta)? onProgress,
  }) async {
    if (_downloading) return 'already_downloading';
    _downloading = true;

    try {
      await StorageManager.instance.initialize();
      final tmpZip = '${StorageManager.instance.imageLibraryDir.path}.zip.tmp';

      final result = await AssetDownloadService.instance.downloadAsset(
        url:             thumbTier ? AssetConfig.imageThumbLibraryUrl : AssetConfig.imageLibraryUrl,
        destinationPath: tmpZip,
        onProgress: (received, total, eta) {
          _downloadedBytes = received;
          _downloadTotalBytes = total;
          _downloadProgress = total > 0 ? received / total : 0;
          _downloadEta = eta;
          onProgress?.call(received, total, eta);
        },
      );

      if (!result.success) {
        debugPrint('ImageLibrary: download failed (${result.error})');
        return result.error ?? 'unknown';
      }

      // Extract into staging dir — old library stays intact and usable during extraction
      final libDir = StorageManager.instance.imageLibraryDir;
      final stagingDir = Directory('${libDir.path}.new');
      if (stagingDir.existsSync()) await stagingDir.delete(recursive: true);

      await _extractZipTo(tmpZip, stagingDir);
      try { File(tmpZip).deleteSync(); } catch (_) {}

      // Atomic swap: only now replace old library (takes milliseconds)
      if (libDir.existsSync()) await libDir.delete(recursive: true);
      await stagingDir.rename(libDir.path);

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('image_library_thumb_tier', thumbTier);

      debugPrint('ImageLibrary: ready (${totalSizeBytes ~/ 1024} KB)');
      return null; // success
    } finally {
      _downloading = false;
      _downloadProgress = 0;
      _downloadedBytes = 0;
      _downloadTotalBytes = 0;
      _downloadEta = null;
    }
  }

  /// Removes all files from image_library/.
  Future<void> clear() async {
    final dir = StorageManager.instance.imageLibraryDir;
    if (dir.existsSync()) {
      await dir.delete(recursive: true);
      await dir.create(recursive: true);
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('image_library_thumb_tier');
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

  File _fileFor(String filename) =>
      File('${StorageManager.instance.imageLibraryDir.path}/$filename');

  Future<void> _extractZipTo(String zipPath, Directory dir) async {
    if (!dir.existsSync()) await dir.create(recursive: true);

    final stream  = InputFileStream(zipPath);
    final archive = ZipDecoder().decodeStream(stream);

    for (final entry in archive.files) {
      if (!entry.isFile) continue;
      final filename = entry.name.replaceFirst(RegExp(r'^images/'), '');
      if (filename.isEmpty) continue;
      final out = OutputFileStream('${dir.path}/$filename');
      entry.writeContent(out);
      out.close();
    }
    stream.close();
  }
}
