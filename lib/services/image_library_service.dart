import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/foundation.dart';

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

  /// Downloads images_medium.zip from R2, extracts it into image_library/.
  /// Returns null on success, or an error code string on failure.
  /// No-op (returns 'already_downloading') if already downloading.
  Future<String?> downloadLibrary({
    void Function(int received, int total, Duration eta)? onProgress,
  }) async {
    if (_downloading) return 'already_downloading';
    _downloading = true;

    try {
      final tmpZip = '${StorageManager.instance.imageLibraryDir.path}.zip.tmp';

      final result = await AssetDownloadService.instance.downloadAsset(
        url:             AssetConfig.imageLibraryUrl,
        destinationPath: tmpZip,
        onProgress:      onProgress,
      );

      if (!result.success) {
        debugPrint('ImageLibrary: download failed (${result.error})');
        return result.error ?? 'unknown';
      }

      await _extractZip(tmpZip);
      try { File(tmpZip).deleteSync(); } catch (_) {}

      debugPrint('ImageLibrary: ready (${totalSizeBytes ~/ 1024} KB)');
      return null; // success
    } finally {
      _downloading = false;
    }
  }

  /// Removes all files from image_library/.
  Future<void> clear() async {
    final dir = StorageManager.instance.imageLibraryDir;
    if (dir.existsSync()) {
      await dir.delete(recursive: true);
      await dir.create(recursive: true);
    }
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

  File _fileFor(String filename) =>
      File('${StorageManager.instance.imageLibraryDir.path}/$filename');

  Future<void> _extractZip(String zipPath) async {
    final dir = StorageManager.instance.imageLibraryDir;
    if (!dir.existsSync()) await dir.create(recursive: true);

    final stream  = InputFileStream(zipPath);
    final archive = ZipDecoder().decodeBuffer(stream);

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
