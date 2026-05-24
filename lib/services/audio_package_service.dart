import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive_io.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../config/asset_config.dart';
import 'asset_download_service.dart';

class AudioRef {
  final String filename;
  final String? caption;
  final String localPath;   // absolute path to the audio file on device
  final int posInHtml;      // document position for thumbnail ordering

  const AudioRef({
    required this.filename,
    this.caption,
    required this.localPath,
    this.posInHtml = 999999,
  });
}

/// Downloads the Wissensfreund audio package from Cloudflare R2,
/// extracts it, and provides per-article audio refs for offline playback.
class AudioPackageService {
  AudioPackageService._();
  static final AudioPackageService instance = AudioPackageService._();

  Map<String, List<AudioRef>> _index = {};
  String? _audioDir;
  bool _initialized = false;

  // ── Public API ──────────────────────────────────────────────────────────────

  /// Call once after ZIM is ready. Loads the local index immediately,
  /// then checks for updates in the background.
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    final appDir = await getApplicationDocumentsDirectory();
    _audioDir    = '${appDir.path}/audio';

    final indexFile = File('${appDir.path}/audio_index.json');
    if (indexFile.existsSync()) {
      _loadIndexFromFile(indexFile);
    }

    // Run update check in background — never blocks app start.
    unawaited(_syncIfNeeded(indexFile));
  }

  /// Returns audio refs for [articleTitle] that have a local file present.
  List<AudioRef> getAudioRefs(String articleTitle) {
    if (_audioDir == null) return [];
    return (_index[articleTitle] ?? [])
        .where((ref) => File(ref.localPath).existsSync())
        .toList();
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  void _loadIndexFromFile(File file) {
    try {
      final data = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      _index = _parseIndex(data);
      debugPrint('AudioPackage: loaded ${_index.length} articles from local index');
    } catch (e) {
      debugPrint('AudioPackage: failed to load local index: $e');
      _index = {};
    }
  }

  Map<String, List<AudioRef>> _parseIndex(Map<String, dynamic> data) {
    final result  = <String, List<AudioRef>>{};
    final audioMap = data['audio'] as Map<String, dynamic>? ?? {};
    for (final entry in audioMap.entries) {
      final items = (entry.value as List).cast<Map<String, dynamic>>();
      result[entry.key] = items.map((item) {
        final fn = item['filename'] as String;
        return AudioRef(
          filename:  fn,
          caption:   item['caption'] as String?,
          localPath: '$_audioDir/$fn',
          posInHtml: item['position'] as int? ?? 999999,
        );
      }).toList();
    }
    return result;
  }

  Future<void> _syncIfNeeded(File indexFile) async {
    try {
      final appDir    = await getApplicationDocumentsDirectory();
      final tmpIndex  = '${appDir.path}/audio_index.json.tmp_check';

      // Download index to check version (small file).
      final idxResult = await AssetDownloadService.instance.downloadAsset(
        url:             AssetConfig.audioIndexUrl,
        destinationPath: tmpIndex,
      );
      if (!idxResult.success) {
        debugPrint('AudioPackage: index fetch skipped (${idxResult.error})');
        return;
      }

      final remoteBody      = await File(tmpIndex).readAsString();
      final remoteData      = jsonDecode(remoteBody) as Map<String, dynamic>;
      final remoteGenerated = remoteData['generated'] as String? ?? '';

      String? localGenerated;
      if (indexFile.existsSync()) {
        try {
          final local = jsonDecode(indexFile.readAsStringSync()) as Map<String, dynamic>;
          localGenerated = local['generated'] as String?;
        } catch (_) {}
      }

      if (remoteGenerated == localGenerated && indexFile.existsSync()) {
        debugPrint('AudioPackage: already up to date ($remoteGenerated)');
        try { File(tmpIndex).deleteSync(); } catch (_) {}
        return;
      }

      debugPrint('AudioPackage: updating to $remoteGenerated ...');

      // Download ZIP to a temp file — streams to disk, no memory spike.
      final tmpZip = '${appDir.path}/audio_package.zip.tmp';
      final zipResult = await AssetDownloadService.instance.downloadAsset(
        url:             AssetConfig.audioZipUrl,
        destinationPath: tmpZip,
        onProgress: (received, total, eta) {
          if (total > 0) {
            final pct = (received / total * 100).round();
            debugPrint('AudioPackage: $pct% (ETA ${eta.inSeconds}s)');
          }
        },
      );

      if (!zipResult.success) {
        debugPrint('AudioPackage: ZIP download failed (${zipResult.error})');
        try { File(tmpIndex).deleteSync(); } catch (_) {}
        return;
      }

      // Extract ZIP from file — streaming via InputFileStream avoids loading
      // the entire archive into RAM (important for files up to 50 MB).
      final audioDir = Directory(_audioDir!);
      if (!audioDir.existsSync()) audioDir.createSync(recursive: true);

      final inputStream = InputFileStream(tmpZip);
      final archive     = ZipDecoder().decodeStream(inputStream);
      var extracted     = 0;

      for (final entry in archive.files) {
        if (!entry.isFile) continue;
        final filename = entry.name.replaceFirst(RegExp(r'^audio/'), '');
        if (filename.isEmpty) continue;
        final outStream = OutputFileStream('${_audioDir!}/$filename');
        entry.writeContent(outStream);
        outStream.close();
        extracted++;
      }
      inputStream.close();
      debugPrint('AudioPackage: extracted $extracted files');

      try { zipFile.deleteSync(); } catch (_) {}

      // Persist index and update in-memory map.
      indexFile.writeAsStringSync(remoteBody);
      _index = _parseIndex(remoteData);
      debugPrint('AudioPackage: sync done — ${_index.length} articles with audio');

      try { File(tmpIndex).deleteSync(); } catch (_) {}
    } catch (e) {
      debugPrint('AudioPackage: sync error: $e');
    }
  }
}
