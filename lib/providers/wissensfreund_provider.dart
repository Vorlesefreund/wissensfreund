import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:just_audio/just_audio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/audio_package_service.dart';
import '../services/wikimedia_license_checker.dart';

class ArticleImageInfo {
  final String filename;
  final String? caption;
  // true = Bild stammt nachweislich aus der Klexikon-ZIM (CC BY-SA 3.0).
  // false = Herkunft unklar → Bild wird nicht angezeigt.
  final bool fromKlexikon;
  const ArticleImageInfo({
    required this.filename,
    this.caption,
    this.fromKlexikon = false,
  });
}

// Unified media item for the thumbnail bar (image or audio).
class ArticleMediaItem {
  final String filename;
  final String? caption;
  final bool isAudio;
  final int posInHtml;    // for ordering images + audio by document position
  final String? localPath; // absolute path for locally downloaded audio files
  const ArticleMediaItem({
    required this.filename,
    this.caption,
    required this.isAudio,
    this.posInHtml = 0,
    this.localPath,
  });
}

// just_audio source backed by raw bytes (avoids temp file on disk).
class _BytesAudioSource extends StreamAudioSource {
  final Uint8List _bytes;
  final String _contentType;
  _BytesAudioSource(this._bytes, this._contentType) : super(tag: 'ZimAudio');

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: end - start,
      offset: start,
      stream: Stream.value(_bytes.sublist(start, end)),
      contentType: _contentType,
    );
  }
}

enum AppState { idle, listening, thinking, speaking }
enum ArticleViewMode { a, b, c }

// ── Frage-Typ-Erkennung (Keyword-Matching, keine KI) ──────────────────────────
enum _QueryType { fullRead, targeted }

const _kFullReadPrefixes = [
  'was ist', 'was sind', 'erzähl mir', 'erzähl', 'erkläre', 'erkläre mir',
  'wer ist', 'wer war', 'was war',
];
const _kTargetedPrefixes = [
  'warum', 'wie', 'wann', 'wo ', 'woher', 'wohin', 'wozu',
  'ist es wahr', 'stimmt es', 'wieso', 'weshalb', 'welche', 'welcher',
];

_QueryType _detectQueryType(String query) {
  final q = query.trim().toLowerCase();
  for (final p in _kFullReadPrefixes) {
    if (q.startsWith(p)) return _QueryType.fullRead;
  }
  for (final p in _kTargetedPrefixes) {
    if (q.startsWith(p)) return _QueryType.targeted;
  }
  return _QueryType.fullRead; // default: Artikel vorlesen
}

// ── Mindest-Score damit ein Artikel akzeptiert wird ───────────────────────────
const _kMinScore = 3;
// Score-Differenz unter der zwei Treffer als "gleichwertig" gelten
const _kAmbiguityDelta = 1;

const _noSpeechMessage =
    'Ich habe dich leider nicht verstanden — versuch es nochmal!';
const _noArticleMessage =
    'Dazu habe ich leider noch keinen Artikel. Frag mich nach einem anderen Thema!';
const _zimNotReadyMessage =
    'Mein Wissensspeicher wird gerade geladen — versuch es gleich nochmal!';
const _parentReferralMessage =
    'Das ist eine tolle Frage — die können Mama oder Papa dir noch viel besser erklären!';

class WissensfreundProvider extends ChangeNotifier {
  static const _speechChannel       = MethodChannel('wissensfreund/speech');
  static const _zimChannel          = MethodChannel('wissensfreund/zim');
  static const _zimProgressChannel  = EventChannel('wissensfreund/zim_progress');

  final _tts = FlutterTts();

  AppState _state        = AppState.idle;
  String _recognizedText = '';
  String _articleText    = '';
  String _articleTitle   = '';
  String _articlePath    = '';  // raw ZIM url field for Klexikon link
  int _ttsCursor         = 0;
  int _resumeOffset      = 0;
  bool _isPaused         = false;
  ArticleViewMode _viewMode = ArticleViewMode.a;

  // ZIM state
  bool   _zimReady        = false;
  bool   _zimNotFound     = false;
  int    _zimArticleCount = 0;
  double _zimProgress     = 0.0;  // 0.0..1.0 during loading

  // TTS chunking — Android TTS has a ~3976 char/call limit
  List<String> _speechChunks  = [];
  List<int>    _chunkOffsets  = [];  // absolute char offset of each chunk in _articleText
  int          _currentChunk  = 0;

  // Disambiguation state: when two results are equally good, store them
  // and ask the user once before auto-picking
  List<Map<String, dynamic>> _pendingCandidates = [];
  bool _awaitingDisambiguation = false;

  // Image state
  List<ArticleImageInfo> _articleImages = [];
  int _selectedImageIndex = -1;
  final Map<String, Uint8List> _imageBytesCache = {};

  // Media state — unified thumbnail list (images + audio in document order)
  List<ArticleMediaItem> _mediaItems = [];
  int _selectedMediaIndex = -1;

  // Audio playback
  final _audioPlayer = AudioPlayer();
  bool _isPlayingAudio = false;
  int _activeAudioIndex = -1; // index in _mediaItems

  // Caption-resume state (Vollbild-Modus: Lautsprecher-Tap oder Wisch-Settle)
  bool   _isCaptionPlaying        = false;
  bool   _isPromptPlaying         = false;
  bool   _showCaptionResumePrompt = false;
  Timer? _captionResumeTimer;
  Timer? _captionPromptDelayTimer;

  AppState get state          => _state;
  String get recognizedText   => _recognizedText;
  String get articleText      => _articleText;
  String get articleTitle     => _articleTitle;
  String get articleUrl {
    final path = _articlePath.isNotEmpty
        ? _articlePath
        : _articleTitle.replaceAll(' ', '_');
    if (path.isEmpty) return 'https://klexikon.zum.de';
    return Uri(scheme: 'https', host: 'klexikon.zum.de', pathSegments: ['wiki', path]).toString();
  }
  int get ttsCursor           => _ttsCursor;
  bool get isPaused                  => _isPaused;
  bool get showCaptionResumePrompt  => _showCaptionResumePrompt;
  ArticleViewMode get viewMode => _viewMode;
  bool   get zimReady        => _zimReady;
  bool   get zimNotFound     => _zimNotFound;
  int    get zimArticleCount => _zimArticleCount;
  double get zimProgress     => _zimProgress;

  List<ArticleImageInfo> get articleImages     => List.unmodifiable(_articleImages);
  int                    get selectedImageIndex => _selectedImageIndex;

  List<ArticleMediaItem> get mediaItems        => List.unmodifiable(_mediaItems);
  int                    get selectedMediaIndex => _selectedMediaIndex;
  bool                   get isPlayingAudio    => _isPlayingAudio;
  int                    get activeAudioIndex  => _activeAudioIndex;

  WissensfreundProvider() {
    _initTts();
    _loadViewMode();
    _initZim();
    _initLicenseCache();
  }

  // ── License cache initialisation ─────────────────────────────────────────

  Future<void> _initLicenseCache() async {
    if (!await WikimediaLicenseChecker.instance.isSynced()) {
      await WikimediaLicenseChecker.instance.syncLicenses();
    }
  }

  // ── ZIM initialisation ────────────────────────────────────────────────────

  Future<void> _initZim() async {
    // Subscribing triggers onListen in Kotlin, which starts ZIM loading.
    // Progress events are Doubles (0.0..1.0); the final event is a Map with status/articleCount.
    _zimProgressChannel.receiveBroadcastStream().listen((event) {
      if (event is double) {
        _zimProgress = event.clamp(0.0, 1.0);
        notifyListeners();
      } else if (event is Map) {
        final status = event['status'] as String? ?? 'error';
        if (status == 'ok') {
          _zimReady        = true;
          _zimArticleCount = (event['articleCount'] as int?) ?? 0;
          _zimProgress     = 1.0;
          debugPrint('ZIM ready: $_zimArticleCount articles');
          // Download audio package in background (parallel to normal use).
          unawaited(AudioPackageService.instance.initialize());
        } else {
          _zimNotFound = true;
          debugPrint('ZIM not found — running without offline knowledge base');
        }
        notifyListeners();
      }
    });
  }

  // ── TTS ───────────────────────────────────────────────────────────────────

  Future<void> _initTts() async {
    await _tts.setLanguage('de-DE');
    await _tts.setSpeechRate(0.45);
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    _tts.setCompletionHandler(() {
      // Caption fertig → 5s Pause → "Soll ich weiterlesen?" → weitere 5s → Auto-Resume
      if (_isCaptionPlaying) {
        _isCaptionPlaying = false;
        _showCaptionResumePrompt = true;
        notifyListeners();
        _captionPromptDelayTimer?.cancel();
        _captionPromptDelayTimer = Timer(const Duration(seconds: 5), () {
          if (!_showCaptionResumePrompt) return;
          _isPromptPlaying = true;
          _captionResumeTimer?.cancel();
          _captionResumeTimer = Timer(const Duration(seconds: 5), resumeAfterCaption);
          _tts.speak('Soll ich weiterlesen?');
        });
        return;
      }
      // Prompt finished → timer is already running, nothing more to do
      if (_isPromptPlaying) {
        _isPromptPlaying = false;
        return;
      }
      // After disambiguation question, auto-start listening — no mic tap needed.
      if (_awaitingDisambiguation && _state == AppState.idle) {
        Future.delayed(const Duration(milliseconds: 500), startListening);
        return;
      }
      if (_state != AppState.speaking || _isPaused) return;
      _currentChunk++;
      if (_currentChunk < _speechChunks.length) {
        _tts.speak(_speechChunks[_currentChunk]);
      } else {
        _speechChunks  = [];
        _chunkOffsets  = [];
        _currentChunk  = 0;
        _isPaused      = false;
        _resumeOffset  = 0;
        _ttsCursor     = 0;
        _state         = AppState.idle;
        notifyListeners();
      }
    });
    _tts.setProgressHandler((_, start, __, ___) {
      final base = _currentChunk < _chunkOffsets.length ? _chunkOffsets[_currentChunk] : 0;
      _ttsCursor = base + start;
      notifyListeners();
    });
  }

  // Split text at sentence boundaries so each chunk stays under Android's TTS limit.
  List<String> _splitIntoChunks(String text, {int maxLen = 3000}) {
    final chunks = <String>[];
    int start = 0;
    while (start < text.length) {
      if (text.length - start <= maxLen) {
        chunks.add(text.substring(start));
        break;
      }
      int end = start + maxLen;
      int splitAt = text.lastIndexOf('. ', end);
      if (splitAt <= start) splitAt = end;
      else splitAt += 2;
      chunks.add(text.substring(start, splitAt));
      start = splitAt;
    }
    return chunks;
  }

  void _startSpeakingFrom(int offset) {
    final remaining = _articleText.substring(offset);
    _speechChunks = _splitIntoChunks(remaining);
    _chunkOffsets = [];
    int pos = offset;
    for (final chunk in _speechChunks) {
      _chunkOffsets.add(pos);
      pos += chunk.length;
    }
    _currentChunk = 0;
    _state = AppState.speaking;
    notifyListeners();
    if (_speechChunks.isNotEmpty) {
      _tts.speak(_speechChunks[0]);
    }
  }

  // ── View mode ─────────────────────────────────────────────────────────────

  Future<void> _loadViewMode() async {
    final prefs = await SharedPreferences.getInstance();
    final idx = (prefs.getInt('viewMode') ?? 0).clamp(0, 2);
    _viewMode = ArticleViewMode.values[idx];
    notifyListeners();
  }

  Future<void> cycleViewMode() async {
    _viewMode = ArticleViewMode.values[(_viewMode.index + 1) % 3];
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    prefs.setInt('viewMode', _viewMode.index);
  }

  // ── STT ───────────────────────────────────────────────────────────────────

  Future<void> startListening() async {
    if (_state != AppState.idle) return;
    _captionPromptDelayTimer?.cancel();
    _captionPromptDelayTimer = null;
    _captionResumeTimer?.cancel();
    _captionResumeTimer = null;
    _isCaptionPlaying = false;
    _isPromptPlaying  = false;
    _showCaptionResumePrompt = false;
    _state = AppState.listening;
    _recognizedText = '';
    _articleText = '';
    _articleTitle = '';
    _articlePath = '';
    _articleImages = [];
    _selectedImageIndex = -1;
    _imageBytesCache.clear();
    _isPaused = false;
    _resumeOffset = 0;
    notifyListeners();

    await _tts.stop();
    await Future.delayed(const Duration(milliseconds: 500));
    if (_state != AppState.listening) return;

    try {
      final text =
          await _speechChannel.invokeMethod<String>('startSpeech') ?? '';
      debugPrint('Speech result: "$text"');
      if (text.isNotEmpty) {
        _recognizedText = text;
        notifyListeners();
        await _processQuery(text);
      } else {
        _handleNoSpeech();
      }
    } on PlatformException catch (e) {
      debugPrint('Speech channel error: ${e.message}');
      _handleNoSpeech();
    }
  }

  void _handleNoSpeech() {
    _state = AppState.idle;
    notifyListeners();
    _tts.speak(_noSpeechMessage);
  }

  Future<void> stopListening() async {
    _state = AppState.idle;
    notifyListeners();
  }

  Future<void> submitText(String query) async {
    if (query.trim().isEmpty) return;
    _recognizedText = query.trim();
    _articleText = '';
    _articleTitle = '';
    notifyListeners();
    await _processQuery(_recognizedText);
  }

  // ── Disambiguation: user picked one of two candidates ─────────────────────

  Future<void> pickDisambiguation(int candidateIndex) async {
    if (!_awaitingDisambiguation ||
        candidateIndex >= _pendingCandidates.length) return;
    _awaitingDisambiguation = false;
    final chosen = _pendingCandidates[candidateIndex];
    _pendingCandidates = [];
    await _loadAndSpeak(chosen['urlIndex'] as int, chosen['title'] as String);
  }

  // ── Core query processing ─────────────────────────────────────────────────

  Future<void> _processQuery(String query) async {
    _state = AppState.thinking;
    notifyListeners();

    if (!_zimReady) {
      await _speakAndIdle(_zimNotReadyMessage);
      return;
    }

    try {
      final rawResults = await _zimChannel.invokeMethod<List>('search', {
        'query': query,
        'maxResults': 3,
      });

      final results = (rawResults ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();

      // No match at all
      if (results.isEmpty || (results.first['score'] as int) < _kMinScore) {
        await _speakAndIdle(_noArticleMessage);
        return;
      }

      final best   = results.first;
      final second = results.length > 1 ? results[1] : null;
      final bestScore   = best['score']   as int;
      final secondScore = second != null ? second['score'] as int : 0;

      // Two equally good results → ask once
      if (second != null &&
          bestScore - secondScore <= _kAmbiguityDelta &&
          !_awaitingDisambiguation) {
        _awaitingDisambiguation = true;
        _pendingCandidates = [best, second];
        _state = AppState.idle;
        notifyListeners();
        final t1 = best['title']   as String;
        final t2 = second['title'] as String;
        await _tts.speak('Meinst du $t1 oder $t2?');
        return;
      }

      // Clear winner (or second disambiguation call)
      await _loadAndSpeak(best['urlIndex'] as int, best['title'] as String);
    } on PlatformException catch (e) {
      debugPrint('ZIM search error: ${e.message}');
      await _speakAndIdle(_noArticleMessage);
    }
  }

  Future<void> _loadAndSpeak(int urlIndex, String title) async {
    try {
      final raw = await _zimChannel.invokeMethod<Map>('article', {
        'urlIndex': urlIndex,
      });
      if (raw == null) { await _speakAndIdle(_noArticleMessage); return; }

      _awaitingDisambiguation = false;
      _pendingCandidates = [];
      _articleTitle = raw['title'] as String? ?? title;
      _articleText  = raw['text']  as String? ?? '';
      _articlePath  = raw['url']   as String? ?? '';
      _articleImages = [];
      _selectedImageIndex = -1;
      _imageBytesCache.clear();
      _ttsCursor    = 0;
      _resumeOffset = 0;
      _isPaused     = false;
      _startSpeakingFrom(0);
      loadMedia(urlIndex); // fire-and-forget — updates UI via notifyListeners
    } on PlatformException catch (e) {
      debugPrint('ZIM article error: ${e.message}');
      await _speakAndIdle(_noArticleMessage);
    }
  }

  Future<void> _speakAndIdle(String message) async {
    _awaitingDisambiguation = false;
    _pendingCandidates = [];
    _state = AppState.idle;
    notifyListeners();
    await _tts.speak(message);
  }

  // ── Image handling ────────────────────────────────────────────────────────

  void selectImage(int index) {
    _selectedImageIndex = (_selectedImageIndex == index) ? -1 : index;
    notifyListeners();
  }

  /// Thumbnail-Tap: nur Bild wechseln, kein TTS.
  void onThumbnailTap(int index) {
    _selectedImageIndex = index;
    notifyListeners();
  }

  /// Liefert den Zeichen-Offset des ANFANGS des aktuellen Satzes.
  int _sentenceStartOffset() {
    if (_articleText.isEmpty) return 0;
    final pos = _ttsCursor.clamp(0, _articleText.length - 1);
    for (int i = pos - 1; i >= 0; i--) {
      if ('.!?'.contains(_articleText[i])) {
        int start = i + 1;
        while (start < _articleText.length && _articleText[start] == ' ') start++;
        return start;
      }
    }
    return 0;
  }

  /// Professor unterbricht sich, liest Caption vor, fragt danach "Soll ich weiterlesen?".
  /// Wird vom Vollbild-Lautsprecher-Button oder nach Wisch-Settle aufgerufen.
  Future<void> interruptForCaption(String caption) async {
    if (caption.isEmpty) return;
    _captionPromptDelayTimer?.cancel();
    _captionResumeTimer?.cancel();
    _isCaptionPlaying = false;
    _isPromptPlaying  = false;
    _showCaptionResumePrompt = false;

    // Immer zum Satzanfang zurückspringen — gilt sowohl für sprechenden als auch pausierten Professor
    final sentStart = _sentenceStartOffset();

    if (_state == AppState.speaking) {
      _isPaused = true;
      _state    = AppState.idle;
      await _tts.stop();
    }

    _resumeOffset     = sentStart;
    _isCaptionPlaying = true;
    notifyListeners();
    await _tts.speak(caption);
    // Completion handler adds 1s delay → prompt → 5s auto-resume
  }

  /// Sofortiges Resume nach Caption (Tap auf "Weiterlesen" oder 5s-Timer).
  void resumeAfterCaption() {
    _captionPromptDelayTimer?.cancel();
    _captionPromptDelayTimer = null;
    _captionResumeTimer?.cancel();
    _captionResumeTimer = null;
    _isCaptionPlaying = false;
    _isPromptPlaying  = false;
    _showCaptionResumePrompt = false;
    notifyListeners();
    resumeSpeaking();
  }

  Future<void> loadImages(int urlIndex) async {
    try {
      final rawList =
          await _zimChannel.invokeMethod<List>('listImages', {'urlIndex': urlIndex});
      if (rawList == null) return;
      // All Klexikon images are CC-licensed — no per-image gate.
      // License info (author/URL) is fetched on-demand by the ⓘ overlay.
      _articleImages = rawList.cast<Map>().map((ref) {
        return ArticleImageInfo(
          filename:     ref['filename'] as String? ?? '',
          caption:      ref['caption']  as String?,
          fromKlexikon: true, // einzige Quelle in dieser App = Klexikon-ZIM (CC BY-SA 3.0)
        );
      }).where((img) => img.filename.isNotEmpty && img.fromKlexikon).toList();
    } catch (e) {
      debugPrint('loadImages error: $e');
    }
    notifyListeners();
  }

  // Loads images from ZIM + audio from local package, merges by document position.
  Future<void> loadMedia(int urlIndex) async {
    _mediaItems = [];
    _selectedMediaIndex = -1;
    _activeAudioIndex = -1;
    _isPlayingAudio = false;

    final rawImages =
        await _zimChannel.invokeMethod<List>('listImages', {'urlIndex': urlIndex}) ?? [];

    final items = <ArticleMediaItem>[];
    for (final ref in rawImages.cast<Map>()) {
      final filename = ref['filename'] as String? ?? '';
      if (filename.isEmpty) continue;
      items.add(ArticleMediaItem(
        filename:  filename,
        caption:   ref['caption'] as String?,
        isAudio:   false,
        posInHtml: ref['posInHtml'] as int? ?? 0,
      ));
    }

    // Audio refs come from the locally downloaded package (not the ZIM).
    final audioRefs = AudioPackageService.instance.getAudioRefs(_articleTitle);
    for (final ref in audioRefs) {
      items.add(ArticleMediaItem(
        filename:  ref.filename,
        caption:   ref.caption,
        isAudio:   true,
        posInHtml: ref.posInHtml,
        localPath: ref.localPath,
      ));
    }

    items.sort((a, b) => a.posInHtml.compareTo(b.posInHtml));
    _mediaItems = items;

    // Keep _articleImages in sync for the main image display.
    _articleImages = rawImages.cast<Map>().map((ref) {
      return ArticleImageInfo(
        filename:     ref['filename'] as String? ?? '',
        caption:      ref['caption']  as String?,
        fromKlexikon: true,
      );
    }).where((img) => img.filename.isNotEmpty).toList();

    if (_mediaItems.isNotEmpty) _selectedMediaIndex = 0;
    notifyListeners();
  }

  // Thumbnail tap — handles image selection AND audio playback (Fall A, B, C).
  Future<void> onMediaTap(int index) async {
    final item = _mediaItems[index];
    if (!item.isAudio) {
      // Image tap: just select it (mirrors existing onThumbnailTap behaviour).
      _selectedMediaIndex = index;
      // Also sync _selectedImageIndex for the main image display.
      final imgIdx = _mediaItems
          .take(index + 1)
          .where((m) => !m.isAudio)
          .length - 1;
      _selectedImageIndex = imgIdx;
      notifyListeners();
      return;
    }

    // ── Audio thumbnail tapped ────────────────────────────────────────────────

    // Fall C: Sound läuft gerade → stoppen, Professor weiter ab gespeicherter Position.
    if (_isPlayingAudio && _activeAudioIndex == index) {
      await _stopAudio();
      if (_isPaused && _articleText.isNotEmpty) {
        resumeSpeaking();
      }
      return;
    }

    // Stoppe laufenden Sound falls ein anderer Sound angetippt wird.
    if (_isPlayingAudio) await _stopAudio();

    // Fall A: Professor liest gerade → Position merken, Professor pausieren.
    final wasReadingArticle = _state == AppState.speaking;
    if (wasReadingArticle) {
      _resumeOffset = _sentenceStartOffset();
      _isPaused = true;
      _state = AppState.idle;
      notifyListeners();
      await _tts.stop();
    } else if (_isPaused) {
      // Professor war bereits pausiert — Resume-Position bleibt erhalten.
    }

    _selectedMediaIndex = index;
    _activeAudioIndex   = index;
    _isPlayingAudio     = true;
    notifyListeners();

    await _playAudioItem(item, wasReadingArticle: wasReadingArticle);
  }

  Future<void> _playAudioItem(ArticleMediaItem item, {required bool wasReadingArticle}) async {
    try {
      if (item.localPath != null && File(item.localPath!).existsSync()) {
        await _audioPlayer.setFilePath(item.localPath!);
      } else {
        // Fallback: try loading from ZIM (will be empty for Klexikon, kept for completeness).
        final bytes = await _getAudioBytes(item.filename);
        if (bytes == null || bytes.isEmpty) {
          debugPrint('_playAudioItem: no audio for ${item.filename}');
          await _onAudioFinished(item, wasReadingArticle: wasReadingArticle);
          return;
        }
        final mimeType = item.filename.toLowerCase().endsWith('.ogg') ? 'audio/ogg' : 'audio/mpeg';
        await _audioPlayer.setAudioSource(_BytesAudioSource(bytes, mimeType));
      }

      // Listen for completion once.
      late StreamSubscription<PlayerState> sub;
      sub = _audioPlayer.playerStateStream.listen((ps) async {
        if (ps.processingState == ProcessingState.completed) {
          sub.cancel();
          await _onAudioFinished(item, wasReadingArticle: wasReadingArticle);
        }
      });
      await _audioPlayer.play();
    } catch (e) {
      debugPrint('_playAudioItem error: $e');
      await _onAudioFinished(item, wasReadingArticle: wasReadingArticle);
    }
  }

  Future<void> _onAudioFinished(ArticleMediaItem item, {required bool wasReadingArticle}) async {
    _isPlayingAudio  = false;
    _activeAudioIndex = -1;
    notifyListeners();

    final caption = item.caption ?? '';

    if (caption.isNotEmpty) {
      // Erklärtext vorlesen — danach "Soll ich weiterlesen?" (wie bei Bild-Caption).
      _isCaptionPlaying = true;
      notifyListeners();
      await _tts.speak(caption);
      // Completion handler übernimmt ab hier (5s → "Soll ich weiterlesen?" → Auto-Resume).
    } else if (wasReadingArticle || _isPaused) {
      // Kein Erklärtext: 2s Pause, dann automatisch ab gespeicherter Position weiter.
      await Future.delayed(const Duration(seconds: 2));
      if (!_isPlayingAudio) resumeSpeaking();
    }
    // Fall B (idle, kein Erklärtext): nichts — Professor schweigt.
  }

  Future<void> _stopAudio() async {
    _isPlayingAudio   = false;
    _activeAudioIndex = -1;
    try { await _audioPlayer.stop(); } catch (_) {}
    notifyListeners();
  }

  final Map<String, Uint8List> _audioBytesCache = {};

  Future<Uint8List?> _getAudioBytes(String filename) async {
    if (_audioBytesCache.containsKey(filename)) return _audioBytesCache[filename];
    try {
      final bytes = await _zimChannel.invokeMethod<Uint8List>('getAudioBytes', {'filename': filename});
      if (bytes != null && bytes.isNotEmpty) _audioBytesCache[filename] = bytes;
      return bytes;
    } catch (e) {
      debugPrint('getAudioBytes error: $e');
      return null;
    }
  }

  Future<Uint8List?> getImageBytes(String filename) async {
    if (_imageBytesCache.containsKey(filename)) return _imageBytesCache[filename];
    try {
      final bytes =
          await _zimChannel.invokeMethod<Uint8List>('getImageBytes', {'filename': filename});
      if (bytes != null && bytes.length <= 2 * 1024 * 1024) {
        _imageBytesCache[filename] = bytes;
      }
      return bytes;
    } catch (_) {
      return null;
    }
  }

  // ── Playback controls ─────────────────────────────────────────────────────

  /// Unterbricht den Artikel-Vortrag, spricht einen einmaligen Satz (z.B. Rückfrage),
  /// und speichert den Satzanfang als Resume-Punkt. Kein Auto-Resume-Timer.
  Future<void> speakInterrupt(String text) async {
    if (_state == AppState.speaking) {
      _resumeOffset = _sentenceStartOffset();
      _isPaused = true;
      _state = AppState.idle;
      notifyListeners();
      await _tts.stop();
    }
    await _tts.speak(text);
  }

  Future<void> pauseSpeaking() async {
    if (_state != AppState.speaking) return;
    _resumeOffset = _ttsCursor;
    _isPaused = true;  // guard completion handler before stop()
    _state = AppState.idle;
    await _tts.stop();
    notifyListeners();
  }

  Future<void> resumeSpeaking() async {
    if (!_isPaused || _articleText.isEmpty) return;
    final offset = _resumeOffset;
    if (offset >= _articleText.length) {
      _isPaused = false;
      _state = AppState.idle;
      notifyListeners();
      return;
    }
    _isPaused = false;
    _startSpeakingFrom(offset);
  }

  Future<void> stopSpeaking() async {
    _captionPromptDelayTimer?.cancel();
    _captionPromptDelayTimer = null;
    _captionResumeTimer?.cancel();
    _captionResumeTimer = null;
    _isCaptionPlaying = false;
    _isPromptPlaying  = false;
    _showCaptionResumePrompt = false;
    await _tts.stop();
    _isPaused = false;
    _resumeOffset = 0;
    _state = AppState.idle;
    notifyListeners();
  }

  @override
  void dispose() {
    _tts.stop();
    _audioPlayer.dispose();
    super.dispose();
  }
}
