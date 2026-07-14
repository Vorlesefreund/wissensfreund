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

  /// Abspielzeit (ms) für einen Zeichen-Offset — erstes Wort, dessen Bereich den
  /// Offset enthält oder danach beginnt. Für Seek/Resume ab einer Textstelle.
  int timeForChar(int charOffset) {
    if (words.isEmpty) return 0;
    for (final w in words) {
      if (w.ce > charOffset) return w.t0;
    }
    return words.last.t0;
  }

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

  // articleId ("{slug}_l{level}", = App _articleId) → {file, dur_s, bytes}
  Map<String, Map<String, dynamic>> _index = {};
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

  /// Gibt es eine Vertonung für diese Artikel-ID (z. B. "vulkan_l1")?
  bool hasNarration(String articleId) => _index[articleId]?['file'] != null;

  /// Streaming-Audioquelle mit Disk-Cache (zweites Abspielen offline). Nutzt eine
  /// bereits vollständig lokal vorhandene Datei direkt (Offline-Paket/Test), sonst
  /// LockCachingAudioSource (streamt + cached). null, wenn keine Vertonung existiert.
  Future<AudioSource?> audioSourceFor(String articleId) async {
    final file = _index[articleId]?['file'] as String?;
    if (file == null || _cacheDir == null) return null;
    final local = File('$_cacheDir/$file');
    // Vollständig vorliegende Datei (z. B. vorab per Offline-Paket geladen) direkt
    // abspielen — kein Netz. LockCachingAudioSource verwaltet sonst ihren eigenen
    // Cache-Container, daher der getrennte lokale Pfad für „fertige" Dateien.
    final full = File('$_cacheDir/full/$file');
    if (full.existsSync() && full.lengthSync() > 0) {
      return AudioSource.uri(Uri.file(full.path));
    }
    unawaited(_evictIfOverCap());
    return LockCachingAudioSource(
      Uri.parse(AssetConfig.narrationFileUrl(file)),
      cacheFile: local,
    );
  }

  /// Wort-/Satz-Zeitleiste zur Vertonung (für die synchrone Markierung). Wird
  /// gecacht. null, wenn kein Sidecar existiert oder das Parsen scheitert.
  Future<NarrationTiming?> timingFor(String articleId) async {
    final file = _index[articleId]?['file'] as String?;
    if (file == null || _cacheDir == null) return null;
    final timingName = file.replaceFirst(RegExp(r'\.m4a$'), '.timing.json');
    final fullPath = '$_cacheDir/full/$timingName';
    final localPath = '$_cacheDir/$timingName';
    final full = File(fullPath);
    final local = File(localPath);

    String? body;
    if (full.existsSync()) {
      body = full.readAsStringSync();
    } else if (local.existsSync()) {
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
      _index = nar.map((k, v) => MapEntry(k, (v as Map<String, dynamic>)));
      debugPrint('Narration: index loaded — ${_index.length} Artikel');
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
