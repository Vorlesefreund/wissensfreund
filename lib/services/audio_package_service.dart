import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

const _indexUrl =
    'https://github.com/Vorlesefreund/wissensfreund/releases/download/wissensfreund-audio/audio_index.json';
const _zipUrl =
    'https://github.com/Vorlesefreund/wissensfreund/releases/download/wissensfreund-audio/wissensfreund_audio.zip';

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

/// Downloads the Wissensfreund audio package from the GitHub release,
/// extracts it, and provides per-article audio refs for offline playback.
class AudioPackageService {
  AudioPackageService._();
  static final AudioPackageService instance = AudioPackageService._();

  Map<String, List<AudioRef>> _index = {};
  String? _audioDir;
  bool _initialized = false;

  static const _httpTimeout = Duration(seconds: 20);
  static const _zipTimeout  = Duration(minutes: 5);

  // ── Public API ──────────────────────────────────────────────────────────────

  /// Call once after ZIM is ready. Loads the local index immediately,
  /// then checks for updates in the background.
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    final appDir = await getApplicationDocumentsDirectory();
    _audioDir = '${appDir.path}/audio';

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
    final result = <String, List<AudioRef>>{};
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
      // Fetch the small index file to check version.
      final idxResponse = await http
          .get(Uri.parse(_indexUrl))
          .timeout(_httpTimeout);
      if (idxResponse.statusCode != 200) return;

      final remoteData      = jsonDecode(idxResponse.body) as Map<String, dynamic>;
      final remoteGenerated = remoteData['generated'] as String? ?? '';

      // Compare with locally stored version.
      String? localGenerated;
      if (indexFile.existsSync()) {
        try {
          final local = jsonDecode(indexFile.readAsStringSync()) as Map<String, dynamic>;
          localGenerated = local['generated'] as String?;
        } catch (_) {}
      }
      if (remoteGenerated == localGenerated && indexFile.existsSync()) {
        debugPrint('AudioPackage: already up to date ($remoteGenerated)');
        return;
      }

      debugPrint('AudioPackage: updating to $remoteGenerated ...');

      // Download ZIP.
      final zipResponse = await http
          .get(Uri.parse(_zipUrl))
          .timeout(_zipTimeout);
      if (zipResponse.statusCode != 200) {
        debugPrint('AudioPackage: ZIP download failed (${zipResponse.statusCode})');
        return;
      }

      // Extract.
      final audioDir = Directory(_audioDir!);
      if (!audioDir.existsSync()) audioDir.createSync(recursive: true);

      final archive = ZipDecoder().decodeBytes(zipResponse.bodyBytes);
      for (final entry in archive) {
        if (!entry.isFile) continue;
        // Paths inside ZIP: "audio/Beethoven_Moonlight.ogg"
        final filename = entry.name.replaceFirst(RegExp(r'^audio/'), '');
        if (filename.isEmpty) continue;
        final outFile = File('${_audioDir!}/$filename');
        outFile.writeAsBytesSync(entry.content as List<int>);
      }
      debugPrint('AudioPackage: extracted ${archive.length} files');

      // Save index and reload.
      indexFile.writeAsStringSync(idxResponse.body);
      _index = _parseIndex(remoteData);
      debugPrint('AudioPackage: sync done — ${_index.length} articles with audio');
    } catch (e) {
      debugPrint('AudioPackage: sync error: $e');
    }
  }
}
