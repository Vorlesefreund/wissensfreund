import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/asset_config.dart';
import 'asset_download_service.dart';

/// Ein Wort der Vertonung: Zeichen-Offsets im gerenderten Artikeltext + ms-Zeitfenster.
class NarrationWord {
  final int cs; // char start
  final int ce; // char end
  final int t0; // ms start
  final int t1; // ms end
  const NarrationWord(this.cs, this.ce, this.t0, this.t1);
}

/// Ein Satz der Vertonung (für Bild-Weiterschaltung, Karaoke-Modus B, Pausen).
class NarrationSentence {
  final int cs;
  final int ce;
  final int t0;
  final int t1;
  const NarrationSentence(this.cs, this.ce, this.t0, this.t1);
}

/// Zeitleiste einer Vertonung — treibt Cursor/Bild/Pausen synchron zum Ton.
class NarrationTiming {
  final int durMs;
  final List<NarrationWord> words;
  final List<NarrationSentence> sentences;
  const NarrationTiming({
    required this.durMs,
    required this.words,
    required this.sentences,
  });

  /// Wort-Index für eine Abspielposition (ms) via Binärsuche; -1 vor dem ersten Wort.
  int wordIndexAt(int posMs) {
    if (words.isEmpty) return -1;
    int lo = 0, hi = words.length - 1, res = -1;
    while (lo <= hi) {
      final mid = (lo + hi) >> 1;
      if (words[mid].t0 <= posMs) {
        res = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return res;
  }
}

/// Streamt die Premium-Vertonung (Gemini-Mehrsprecher / Nico-Stimme) pro Artikel/Stufe
/// von R2 und cached sie on-device. NICHT das kostenlose On-Device-flutter_tts — das
/// bleibt der Fallback (offline / Nicht-Plus). Diese Klasse liefert nur Bausteine
/// (Audio-Quelle + Timing); den Vorlese-Flow orchestriert der Provider.
class NarrationService {
  NarrationService._();
  static final NarrationService instance = NarrationService._();

  static const String _capPrefKey = 'narration_cache_cap_mb';
  static const int _defaultCapMb = 200; // vom Nutzer im Menü einstellbar

  // articleId → { stufe → {file, dur_s, bytes} }
  Map<String, Map<String, Map<String, dynamic>>> _index = {};
  String? _cacheDir;
  bool _initialized = false;

  // ── Public API ──────────────────────────────────────────────────────────────

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    final appDir = await getApplicationDocumentsDirectory();
    _cacheDir = '${appDir.path}/narration_cache';
    Directory(_cacheDir!).createSync(recursive: true);

    final indexFile = File('${appDir.path}/narration_index.json');
    if (indexFile.existsSync()) _loadIndex(indexFile.readAsStringSync());

    unawaited(_syncIfNeeded(indexFile));
  }

  /// Gibt es eine Vertonung für diesen Artikel + Stufe (1/2/3)?
  bool hasNarration(String articleId, int stufe) =>
      _index[articleId]?[stufe.toString()]?['file'] != null;

  /// Streaming-Audioquelle mit Disk-Cache (zweites Abspielen offline). Respektiert
  /// den Nutzer-Cap per LRU-Eviction. null, wenn keine Vertonung existiert.
  Future<AudioSource?> audioSourceFor(String articleId, int stufe) async {
    final file = _index[articleId]?[stufe.toString()]?['file'] as String?;
    if (file == null || _cacheDir == null) return null;
    unawaited(_evictIfOverCap());
    return LockCachingAudioSource(
      Uri.parse(AssetConfig.narrationFileUrl(file)),
      cacheFile: File('$_cacheDir/$file'),
    );
  }

  /// Wort-/Satz-Zeitleiste zur Vertonung (für die synchrone Markierung). Wird
  /// gecacht. null, wenn kein Sidecar existiert oder das Parsen scheitert.
  Future<NarrationTiming?> timingFor(String articleId, int stufe) async {
    final file = _index[articleId]?[stufe.toString()]?['file'] as String?;
    if (file == null || _cacheDir == null) return null;
    final timingName = file.replaceFirst(RegExp(r'\.m4a$'), '.timing.json');
    final localPath = '$_cacheDir/$timingName';
    final local = File(localPath);

    String? body;
    if (local.existsSync()) {
      body = local.readAsStringSync();
    } else {
      final res = await AssetDownloadService.instance.downloadAsset(
        url: AssetConfig.narrationFileUrl(timingName),
        destinationPath: localPath,
      );
      if (!res.success) return null;
      try { body = local.readAsStringSync(); } catch (_) { return null; }
    }
    return _parseTiming(body);
  }

  Future<int> cacheCapMb() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_capPrefKey) ?? _defaultCapMb;
  }

  Future<void> setCacheCapMb(int mb) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_capPrefKey, mb);
    unawaited(_evictIfOverCap());
  }

  int get cacheBytes {
    if (_cacheDir == null) return 0;
    final dir = Directory(_cacheDir!);
    if (!dir.existsSync()) return 0;
    return dir.listSync(recursive: true).whereType<File>().fold(0, (s, f) {
      try { return s + f.lengthSync(); } catch (_) { return s; }
    });
  }

  Future<void> clearCache() async {
    if (_cacheDir == null) return;
    final dir = Directory(_cacheDir!);
    if (dir.existsSync()) {
      dir.deleteSync(recursive: true);
      dir.createSync(recursive: true);
    }
  }

  // ── Internal ─────────────────────────────────────────────────────────────────

  void _loadIndex(String body) {
    try {
      final data = jsonDecode(body) as Map<String, dynamic>;
      final nar = data['narration'] as Map<String, dynamic>? ?? {};
      final result = <String, Map<String, Map<String, dynamic>>>{};
      for (final e in nar.entries) {
        final byStufe = (e.value as Map<String, dynamic>).map(
          (k, v) => MapEntry(k, (v as Map<String, dynamic>)),
        );
        result[e.key] = byStufe;
      }
      _index = result;
      debugPrint('Narration: index loaded — ${_index.length} Themen');
    } catch (e) {
      debugPrint('Narration: index parse failed: $e');
      _index = {};
    }
  }

  NarrationTiming? _parseTiming(String body) {
    try {
      final d = jsonDecode(body) as Map<String, dynamic>;
      final words = ((d['words'] as List?) ?? [])
          .cast<Map<String, dynamic>>()
          .map((w) => NarrationWord(
                w['cs'] as int, w['ce'] as int, w['t0'] as int, w['t1'] as int))
          .toList();
      final sents = ((d['sentences'] as List?) ?? [])
          .cast<Map<String, dynamic>>()
          .map((s) => NarrationSentence(
                s['cs'] as int, s['ce'] as int, s['t0'] as int, s['t1'] as int))
          .toList();
      return NarrationTiming(
        durMs: (d['dur_ms'] as num?)?.toInt() ?? 0,
        words: words,
        sentences: sents,
      );
    } catch (e) {
      debugPrint('Narration: timing parse failed: $e');
      return null;
    }
  }

  Future<void> _syncIfNeeded(File indexFile) async {
    try {
      final appDir = await getApplicationDocumentsDirectory();
      final tmp = '${appDir.path}/narration_index.json.tmp';
      final res = await AssetDownloadService.instance.downloadAsset(
        url: AssetConfig.narrationIndexUrl,
        destinationPath: tmp,
      );
      if (!res.success) {
        debugPrint('Narration: index fetch skipped (${res.error})');
        return;
      }
      final remoteBody = await File(tmp).readAsString();
      final remoteGen = (jsonDecode(remoteBody) as Map<String, dynamic>)['generated'];
      String? localGen;
      if (indexFile.existsSync()) {
        try {
          localGen = (jsonDecode(indexFile.readAsStringSync())
              as Map<String, dynamic>)['generated'] as String?;
        } catch (_) {}
      }
      if (remoteGen == localGen && indexFile.existsSync()) {
        try { File(tmp).deleteSync(); } catch (_) {}
        return;
      }
      indexFile.writeAsStringSync(remoteBody);
      _loadIndex(remoteBody);
      try { File(tmp).deleteSync(); } catch (_) {}
      debugPrint('Narration: index synced ($remoteGen)');
    } catch (e) {
      debugPrint('Narration: sync error: $e');
    }
  }

  /// LRU-Eviction bis unter den Nutzer-Cap (älteste zuletzt genutzte Dateien zuerst).
  Future<void> _evictIfOverCap() async {
    if (_cacheDir == null) return;
    final dir = Directory(_cacheDir!);
    if (!dir.existsSync()) return;
    final capBytes = (await cacheCapMb()) * 1024 * 1024;
    final files = dir.listSync(recursive: true).whereType<File>().toList();
    var total = files.fold<int>(0, (s, f) {
      try { return s + f.lengthSync(); } catch (_) { return s; }
    });
    if (total <= capBytes) return;
    files.sort((a, b) {
      try {
        return a.statSync().accessed.compareTo(b.statSync().accessed);
      } catch (_) { return 0; }
    });
    for (final f in files) {
      if (total <= capBytes) break;
      try {
        total -= f.lengthSync();
        f.deleteSync();
      } catch (_) {}
    }
  }
}
