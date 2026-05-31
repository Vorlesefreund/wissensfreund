import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/asset_config.dart';
import 'asset_download_service.dart';
import 'storage_manager.dart';

class _CancelledException implements Exception {
  const _CancelledException();
}

/// Manages the offline image library (medium quality, ~800px wide).
///
/// Images are stored in StorageManager.imageLibraryDir.
/// Download is triggered from the onboarding quality dialog.
class ImageLibraryService {
  ImageLibraryService._();
  static final ImageLibraryService instance = ImageLibraryService._();

  bool _downloading = false;
  bool _cancelRequested = false;
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

  /// Bricht einen laufenden Download ab. Keine Wirkung wenn kein Download läuft.
  void cancel() => _cancelRequested = true;
  double get downloadProgress => _downloadProgress;
  int get downloadedBytes => _downloadedBytes;
  int get downloadTotalBytes => _downloadTotalBytes;
  Duration? get downloadEta => _downloadEta;

  /// Returns true if thumb tier (300px), false if standard (800px), null if unknown.
  static Future<bool?> getStoredTier() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('image_library_thumb_tier');
  }

  /// Whether to auto-load best available image on WiFi (default: true).
  static Future<bool> hiresOnWifiEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool('hires_on_wifi_enabled') ?? true;
  }

  static Future<void> setHiresOnWifi(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('hires_on_wifi_enabled', enabled);
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
    _cancelRequested = false;

    try {
      await StorageManager.instance.initialize();
      final libDir = StorageManager.instance.imageLibraryDir;
      final tmpZip = '${libDir.path}.zip.tmp';

      final result = await AssetDownloadService.instance.downloadAsset(
        url:             thumbTier ? AssetConfig.imageThumbLibraryUrl : AssetConfig.imageLibraryUrl,
        destinationPath: tmpZip,
        onProgress: (received, total, eta) {
          if (_cancelRequested) throw const _CancelledException();
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
      final stagingDir = Directory('${libDir.path}.new');
      if (stagingDir.existsSync()) await stagingDir.delete(recursive: true);

      await _extractZipTo(tmpZip, stagingDir, onExtractProgress: (done, total) {
        _downloadProgress = 1.0 + (done / total); // >1.0 signals extraction phase
        onProgress?.call(_downloadedBytes, _downloadTotalBytes, Duration.zero);
      });
      try { File(tmpZip).deleteSync(); } catch (_) {}

      // Swap: ersetze alte Library durch neue.
      // Directory.rename() schlägt auf Android external storage fehl →
      // stattdessen alte Library löschen und Staging-Dir umbenennen mit
      // Fallback auf manuelles Kopieren.
      if (libDir.existsSync()) await libDir.delete(recursive: true);
      try {
        await stagingDir.rename(libDir.path);
      } catch (_) {
        // Fallback: manuell kopieren wenn rename fehlschlägt
        await _copyDir(stagingDir, libDir);
        await stagingDir.delete(recursive: true);
      }

      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('image_library_thumb_tier', thumbTier);

      debugPrint('ImageLibrary: ready (${totalSizeBytes ~/ 1024} KB)');
      return null; // success
    } on _CancelledException {
      // Staging-Dir aufräumen falls Extraktion schon begonnen hatte
      try {
        final stagingDir = Directory('${StorageManager.instance.imageLibraryDir.path}.new');
        if (stagingDir.existsSync()) await stagingDir.delete(recursive: true);
      } catch (_) {}
      debugPrint('ImageLibrary: download cancelled');
      return 'cancelled';
    } finally {
      _downloading = false;
      _cancelRequested = false;
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

  File _fileFor(String filename) {
    // New hash-based ZIPs store entries as "{hash}.jpg".
    // ZimReader passes "_assets_/{hash}.jpg" from the ZIM HTML src attribute.
    final key = filename.replaceFirst(RegExp(r'^_assets_[/\\]'), '');
    return File('${StorageManager.instance.imageLibraryDir.path}/$key');
  }

  Future<void> _extractZipTo(String zipPath, Directory dir,
      {void Function(int done, int total)? onExtractProgress}) async {
    if (!dir.existsSync()) await dir.create(recursive: true);

    final stream  = InputFileStream(zipPath);
    final archive = ZipDecoder().decodeStream(stream);

    final files = archive.files.where((e) => e.isFile).toList();
    int done = 0;
    for (final entry in files) {
      final filename = entry.name.replaceFirst(RegExp(r'^images/'), '');
      if (filename.isEmpty) continue;
      final outPath = '${dir.path}/$filename';
      final parent = File(outPath).parent;
      if (!parent.existsSync()) await parent.create(recursive: true);
      final out = OutputFileStream(outPath);
      entry.writeContent(out);
      out.close();
      done++;
      onExtractProgress?.call(done, files.length);
    }
    stream.close();
  }

  Future<void> _copyDir(Directory src, Directory dst) async {
    await dst.create(recursive: true);
    await for (final entity in src.list(recursive: false)) {
      final name = entity.path.split(RegExp(r'[\\/]')).last;
      if (entity is Directory) {
        await _copyDir(entity, Directory('${dst.path}/$name'));
      } else if (entity is File) {
        await entity.copy('${dst.path}/$name');
      }
    }
  }
}
