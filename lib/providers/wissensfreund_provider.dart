import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:just_audio/just_audio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/audio_package_service.dart';
import '../services/hires_image_service.dart';
import '../services/image_library_service.dart';
import '../services/license_cache_db.dart';
import '../services/network_service.dart';
import '../services/professor_response_service.dart';
import '../services/profile_service.dart';
import '../services/json_article_service.dart';
import '../services/subscription_service.dart';
import '../services/wikimedia_license_checker.dart';
import '../services/zim_update_service.dart';
import '../models/wf_article.dart';

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
enum _QueryType { fullRead, targeted, comparison, followUp, unknown }

const _kFullReadPrefixes = [
  'was ist', 'was sind', 'erzähl mir', 'erzähl', 'erkläre', 'erkläre mir',
  'wer ist', 'wer war', 'was war',
];
const _kTargetedPrefixes = [
  'warum', 'wie', 'wann', 'wo ', 'woher', 'wohin', 'wozu',
  'ist es wahr', 'stimmt es', 'wieso', 'weshalb', 'welche', 'welcher',
];
const _kCompareWords = [
  'größer', 'kleiner', 'schneller', 'langsamer', 'schwerer', 'leichter',
  'stärker', 'schwächer', 'älter', 'jünger', 'länger', 'kürzer',
  'gefährlicher', 'sicherer', 'schlauer', 'schöner', 'oder ', 'versus', 'verglichen',
];

_QueryType _detectQueryType(String query) {
  final q = query.trim().toLowerCase();
  for (final p in _kFullReadPrefixes) {
    if (q.startsWith(p)) return _QueryType.fullRead;
  }
  for (final p in _kTargetedPrefixes) {
    if (q.startsWith(p)) return _QueryType.targeted;
  }
  return _QueryType.unknown; // default: Typ 5
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
  final JsonArticleService _jsonArticleService = JsonArticleService.instance;

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

  // Screen idle management
  Timer? _screenDimTimer;
  Timer? _screenOffTimer;
  static const _dimAfter = Duration(minutes: 1);
  static const _offAfter = Duration(minutes: 5);

  // Caption-resume state (Vollbild-Modus: Lautsprecher-Tap oder Wisch-Settle)
  bool   _isCaptionPlaying        = false;
  bool   _isPromptPlaying         = false;
  bool   _showCaptionResumePrompt = false;
  bool   _wasPlayingBeforeCaption = false; // true nur wenn Professor beim Caption-Tap aktiv sprach
  Timer? _captionResumeTimer;
  Timer? _captionPromptDelayTimer;

  // Mid-article mic interrupt: saves article context so reading can resume after answer
  bool   _hasInterruptedForMic      = false;
  String _savedArticleTextForMic    = '';
  String _savedArticleTitleForMic   = '';
  String _savedArticlePathForMic    = '';
  int    _savedResumeOffsetForMic   = 0;

  // Article-switch confirmation: professor asks before leaving the current article
  bool                   _awaitingArticleSwitch   = false;
  Map<String, dynamic>?  _pendingArticleCandidate;

  // Professor Response Catalog — failure counters
  int    _misserfolgZaehler = 0; // consecutive no-speech + no-article failures
  int    _technischZaehler  = 0; // consecutive technical errors
  String _lastFailedQuery   = ''; // for k4 (same topic repeated)

  // Rest mode — professor goes to sleep after extended idle
  bool   _isRestMode  = false;

  // ZIM update — set in background after license-cache sync
  ZimVersionInfo? _pendingZimUpdate;

  // Data-limit overlay: completer for awaiting the handoff phrase
  Completer<void>? _handoffCompleter;
  // Warning phrase interleaving: article chunk deferred until warning phrase is done
  String? _deferredArticleChunk;
  // After "Kein Problem" cancel phrase: resume article automatically
  bool _resumeAfterHandoff = false;
  bool _ttsStopPending = false; // guard against stop()-induced onDone race

  // Internal link navigation
  List<Map<String, dynamic>> _articleLinks = [];
  int _currentUrlIndex = -1;
  final _navStack = <({String title, int urlIndex, int charOffset})>[];
  bool _awaitingLinkConfirmation = false;
  String? _pendingLinkTarget;
  bool _isLinkNavigation = false;
  bool _awaitingNavStackResume = false;

  bool   _isInBackground = false; // app is paused/backgrounded

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
  bool                   get isRestMode        => _isRestMode;
  ZimVersionInfo?        get pendingZimUpdate  => _pendingZimUpdate;
  List<Map<String, dynamic>> get articleLinks  => List.unmodifiable(_articleLinks);
  bool get canGoBack => _navStack.isNotEmpty;

  WissensfreundProvider() {
    _initTts();
    _loadViewMode();
    _initZim();
    _initLicenseCache();
    unawaited(ProfessorResponseService.instance.initialize());
    unawaited(SubscriptionService.instance.initialize());
  }

  // ── License cache initialisation ─────────────────────────────────────────

  Future<void> _initLicenseCache() async {
    if (!await WikimediaLicenseChecker.instance.isSynced()) {
      await WikimediaLicenseChecker.instance.syncLicenses();
    }
    unawaited(_checkZimUpdateInBackground());
  }

  Future<void> _checkZimUpdateInBackground() async {
    final info = await ZimUpdateService.instance.checkForUpdate();
    if (info != null) {
      _pendingZimUpdate = info;
      notifyListeners();
    }
  }

  void clearPendingZimUpdate() {
    _pendingZimUpdate = null;
    notifyListeners();
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
      // Discard onDone that was triggered by an explicit stop() call.
      if (_ttsStopPending) { _ttsStopPending = false; return; }
      // Deferred article chunk after a limit-warning phrase — resume article reading.
      if (_deferredArticleChunk != null) {
        final chunk = _deferredArticleChunk!;
        _deferredArticleChunk = null;
        _tts.speak(chunk);
        return;
      }
      // Caption fertig → Professor bleibt pausiert; Nutzer resumt manuell über Play.
      if (_isCaptionPlaying) {
        _isCaptionPlaying = false;
        notifyListeners();
        return;
      }
      // Prompt finished → timer is already running, nothing more to do
      if (_isPromptPlaying) {
        _isPromptPlaying = false;
        return;
      }
      // After disambiguation question, auto-start listening — no mic tap needed.
      // TTS is already done here, so skip the Dart-side lead delay (Kotlin warmup suffices).
      if (_awaitingDisambiguation && _state == AppState.idle) {
        Future.delayed(
          const Duration(milliseconds: 80),
          () => startListening(skipLeadDelay: true),
        );
        return;
      }
      // After article-switch confirmation question, auto-start listening.
      if (_awaitingArticleSwitch && _state == AppState.idle) {
        Future.delayed(
          const Duration(milliseconds: 80),
          () => startListening(skipLeadDelay: true),
        );
        return;
      }
      // After link-tap confirmation question, auto-start listening.
      if (_awaitingLinkConfirmation && _state == AppState.idle) {
        Future.delayed(
          const Duration(milliseconds: 80),
          () => startListening(skipLeadDelay: true),
        );
        return;
      }
      // After article-end nav-stack prompt, auto-start listening.
      if (_awaitingNavStackResume && _state == AppState.idle) {
        Future.delayed(
          const Duration(milliseconds: 80),
          () => startListening(skipLeadDelay: true),
        );
        return;
      }
      // Mid-article mic interrupt: restore saved article + show resume prompt.
      // Fires after any TTS (error msg, no-match, etc.) when flag is still set.
      // _handleArticleSwitchConfirmation clears the flag when user confirms switch.
      if (_hasInterruptedForMic && _savedArticleTextForMic.isNotEmpty) {
        _restoreInterruptedArticle();
        return;
      }
      if (_state != AppState.speaking || _isPaused) {
        resetScreenTimer();
        // Drain data-limit handoff completer (professor phrase just finished).
        final completer = _handoffCompleter;
        if (completer != null) {
          _handoffCompleter = null;
          completer.complete();
        }
        // Resume article after "Kein Problem" cancel phrase.
        if (_resumeAfterHandoff) {
          _resumeAfterHandoff = false;
          if (_isPaused && _articleText.isNotEmpty) unawaited(resumeSpeaking());
        }
        return;
      }
      _currentChunk++;
      if (_currentChunk < _speechChunks.length) {
        // Snap cursor to start of new chunk so any rebuild triggered between
        // chunks (e.g. mode switch) highlights the correct sentence rather
        // than the stale end-of-previous-chunk position.
        _ttsCursor = _chunkOffsets[_currentChunk];
        // Check for a pending 80%/90% limit warning between chunks.
        final warning = NetworkService.instance.consumePendingWarning();
        if (warning != null && warning != LimitWarningLevel.limitReached) {
          _deferredArticleChunk = _speechChunks[_currentChunk];
          _tts.speak(_randomLimitWarningPhrase(warning));
          return;
        }
        _tts.speak(_speechChunks[_currentChunk]);
      } else {
        _speechChunks  = [];
        _chunkOffsets  = [];
        _currentChunk  = 0;
        _isPaused      = false;
        _resumeOffset  = 0;
        _ttsCursor     = 0;
        unawaited(ProfileService.instance.clearLastArticle());
        _state         = AppState.idle;
        notifyListeners();
        resetScreenTimer(); // Artikel fertig → Idle-Timer starten
        _onArticleEnd();
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
    _pauseScreenTimer(); // Während Vorlesen kein Idle-Timeout
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

  // skipLeadDelay: true when called right after TTS completion (Kotlin warmup is enough).
  // false (default) when TTS may still be running (user-initiated mic tap).
  Future<void> startListening({bool skipLeadDelay = false}) async {
    if (_state != AppState.idle) return;
    _cancelIdleTimers();
    _captionPromptDelayTimer?.cancel();
    _captionPromptDelayTimer = null;
    _captionResumeTimer?.cancel();
    _captionResumeTimer = null;
    _isCaptionPlaying = false;
    _isPromptPlaying  = false;
    _showCaptionResumePrompt = false;
    _state = AppState.listening;
    _recognizedText = '';
    if (!_awaitingLinkConfirmation) {
      _articleText = '';
      _articleTitle = '';
      _articlePath = '';
      _articleImages = [];
      _selectedImageIndex = -1;
      _imageBytesCache.clear();
      _isPaused = false;
      _resumeOffset = 0;
    }
    notifyListeners();

    await _tts.stop();
    await Future.delayed(Duration(milliseconds: skipLeadDelay ? 80 : 500));
    if (_state != AppState.listening) return;

    try {
      final text =
          await _speechChannel.invokeMethod<String>('startSpeech') ?? '';
      debugPrint('Speech result: "$text"');
      if (text.isNotEmpty) {
        _recognizedText = text;
        notifyListeners();
        if (_awaitingArticleSwitch) {
          await _handleArticleSwitchConfirmation(text);
        } else if (_awaitingLinkConfirmation) {
          await _handleLinkConfirmation(text);
        } else if (_awaitingNavStackResume) {
          await _handleNavStackResume(text);
        } else if (!_awaitingDisambiguation && !_hasInterruptedForMic &&
                   _isGoodbyeKeyword(text)) {
          await _handleKeyword('k8');
        } else if (!_awaitingDisambiguation && !_hasInterruptedForMic &&
                   _isThankKeyword(text)) {
          await _handleKeyword('k7');
        } else {
          await _processQuery(text);
        }
      } else {
        unawaited(_handleNoSpeech());
      }
    } on PlatformException catch (e) {
      debugPrint('Speech channel error: ${e.message}');
      _handleNoSpeech();
    }
  }

  Future<void> _handleNoSpeech() async {
    if (_awaitingArticleSwitch) {
      _awaitingArticleSwitch = false;
      _pendingArticleCandidate = null;
      _state = AppState.idle;
      notifyListeners();
      _tts.speak('Ok, ich lese weiter.');
      return;
    }
    if (_awaitingLinkConfirmation) {
      _awaitingLinkConfirmation = false;
      _pendingLinkTarget = null;
      _state = AppState.idle;
      notifyListeners();
      _resumeAfterHandoff = _isPaused;
      _tts.speak('Ok, ich lese weiter.');
      return;
    }
    if (_awaitingNavStackResume) {
      _awaitingNavStackResume = false;
      _navStack.clear();
      _state = AppState.idle;
      notifyListeners();
      return;
    }
    if (_hasInterruptedForMic) {
      _state = AppState.idle;
      notifyListeners();
      final msg = await _catalogOrFallback('k1', _noSpeechMessage);
      if (_state == AppState.idle) _tts.speak(msg);
      return;
    }
    _misserfolgZaehler++;
    _state = AppState.idle;
    notifyListeners();
    final katalogId = _noSpeechKatalogId();
    final msg = await _catalogOrFallback(katalogId, _noSpeechMessage);
    if (_state == AppState.idle) _tts.speak(msg);
  }

  String _noSpeechKatalogId() {
    if (_misserfolgZaehler == 1) return 'k1';
    if (_misserfolgZaehler == 2) return 'k3_s1';
    if (_misserfolgZaehler <= 4) return 'k3_s2';
    _misserfolgZaehler = 0;
    return 'k3_s3';
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
    _misserfolgZaehler = 0;
    _technischZaehler  = 0;
    _lastFailedQuery   = '';
    _cancelIdleTimers();
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
    // Capture followUp context BEFORE state changes clear article
    final isFollowUp = _hasInterruptedForMic && _savedArticleTextForMic.isNotEmpty;
    final queryType  = _detectQueryType(query);

    _state = AppState.thinking;
    notifyListeners();

    if (!_zimReady) {
      await _speakAndIdle(_zimNotReadyMessage);
      return;
    }

    // Typ 4: Folgefrage — Artikel bereits geladen, Gemini-Platzhalter
    // Only genuine questions (targeted prefix: Warum/Wie/Wann/...) count as follow-ups.
    // Plain nouns/names (unknown type) are always a new article search, never a follow-up.
    if (isFollowUp && queryType == _QueryType.targeted) {
      _state = AppState.idle;
      notifyListeners();
      await _handleGeminiPlaceholder(query);
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
        if (queryType != _QueryType.fullRead) {
          // Typen 2, 3, 5 ohne Artikel → Eltern-Verweis (eiserne Regel)
          _state = AppState.idle;
          notifyListeners();
          unawaited(_tts.speak(_parentReferralMessage));
          return;
        }
        _misserfolgZaehler++;
        final nq = query.toLowerCase().trim();
        final isRepeat = nq.isNotEmpty && nq == _lastFailedQuery;
        _lastFailedQuery = nq;
        final katalogId = _noArticleKatalogId(isRepeat: isRepeat);
        final msg = await _catalogOrFallback(katalogId, _noArticleMessage);
        _state = AppState.idle;
        notifyListeners();
        await _tts.speak(msg);
        // TTS completion → if _hasInterruptedForMic → _restoreInterruptedArticle
        return;
      }

      final best   = results.first;
      final second = results.length > 1 ? results[1] : null;
      final bestScore   = best['score']   as int;
      final secondScore = second != null ? second['score'] as int : 0;

      // Typ 3: Vergleichsfrage — zwei gute Treffer + Vergleichswort → Gemini-Platzhalter
      if (queryType != _QueryType.fullRead &&
          second != null &&
          secondScore >= _kMinScore &&
          _kCompareWords.any((w) => query.toLowerCase().contains(w))) {
        _state = AppState.idle;
        notifyListeners();
        await _handleGeminiPlaceholder(query);
        return;
      }

      // Typ 2: targeted → Gemini-Platzhalter (Artikel gefunden, aber Gemini antwortet)
      if (queryType == _QueryType.targeted) {
        _state = AppState.idle;
        notifyListeners();
        await _handleGeminiPlaceholder(query);
        return;
      }

      // Two equally good results → ask once (fullRead + unknown)
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

      // Clear winner → direkt laden, ohne Rückfrage (auch bei Mic-Interrupt)
      await _loadAndSpeak(best['urlIndex'] as int, best['title'] as String);
    } on PlatformException catch (e) {
      debugPrint('ZIM search error: ${e.message}');
      _technischZaehler++;
      final katalogId = _technischZaehler == 1 ? 'k5_s1'
          : _technischZaehler == 2 ? 'k5_s2'
          : 'k5_s3';
      final msg = await _catalogOrFallback(katalogId, _noArticleMessage);
      await _speakAndIdle(msg);
    }
  }

  Future<void> _loadAndSpeak(int urlIndex, String title) async {
    try {
      final raw = await _zimChannel.invokeMethod<Map>('article', {
        'urlIndex': urlIndex,
      });
      if (raw == null) { await _speakAndIdle(_noArticleMessage); return; }

      // Clear nav stack for user-initiated searches; preserve for link navigation.
      if (!_isLinkNavigation) _navStack.clear();
      _isLinkNavigation = false;
      _currentUrlIndex = urlIndex;

      _awaitingDisambiguation = false;
      _pendingCandidates = [];
      _hasInterruptedForMic    = false;
      _savedArticleTextForMic  = '';
      _misserfolgZaehler = 0;
      _technischZaehler  = 0;
      _lastFailedQuery   = '';
      _cancelIdleTimers();
      _articleTitle = raw['title'] as String? ?? title;
      _articleText  = raw['text']  as String? ?? '';
      _articlePath  = raw['url']   as String? ?? '';
      _articleLinks = [];
      _articleImages = [];
      _selectedImageIndex = -1;
      _imageBytesCache.clear();
      _ttsCursor    = 0;
      _resumeOffset = 0;
      _isPaused     = false;
      unawaited(ProfileService.instance.clearLastArticle());
      _startSpeakingFrom(0);
      loadMedia(urlIndex); // fire-and-forget — updates UI via notifyListeners
      unawaited(_loadLinks(urlIndex));
      _trackArticleListened();
    } on PlatformException catch (e) {
      debugPrint('ZIM article error: ${e.message}');
      _technischZaehler++;
      final katalogId = _technischZaehler == 1 ? 'k5_s1'
          : _technischZaehler == 2 ? 'k5_s2'
          : 'k5_s3';
      final msg = await _catalogOrFallback(katalogId, _noArticleMessage);
      await _speakAndIdle(msg);
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
      final ch = _articleText[i];
      if ('.!?'.contains(ch)) {
        // Skip period between digits (German thousands separator: 1.000, 1.000.000)
        if (ch == '.' && i > 0 && i + 1 < _articleText.length) {
          final before = _articleText.codeUnitAt(i - 1);
          final after  = _articleText.codeUnitAt(i + 1);
          if (before >= 48 && before <= 57 && after >= 48 && after <= 57) continue;
        }
        int start = i + 1;
        while (start < _articleText.length && _articleText[start] == ' ') start++;
        return start;
      }
    }
    return 0;
  }

  /// Saves current reading position for "Weiterhören" (back button / background).
  Future<void> saveCurrentArticlePosition() async {
    if (_articleTitle.isEmpty) return;
    final offset = _state == AppState.speaking
        ? _sentenceStartOffset()
        : (_isPaused ? _resumeOffset : _ttsCursor);
    await ProfileService.instance.saveLastArticle(_articleTitle, offset);
  }

  /// Clears the saved "Weiterhören" position for the active profile.
  Future<void> clearLastArticle() async {
    await ProfileService.instance.clearLastArticle();
  }

  // ── JSON article access (Schritt A — kein Rendering) ────────────────────────

  Future<WfArticle?> loadJsonArticle(String articleId) async {
    return _jsonArticleService.loadArticle(articleId);
  }

  /// Resumes a previously saved article from [charOffset] with an intro phrase.
  Future<void> resumeLastArticle(String title, int charOffset) async {
    if (!_zimReady) return;
    _state = AppState.thinking;
    notifyListeners();
    try {
      final rawResults = await _zimChannel.invokeMethod<List>('search', {
        'query': title,
        'maxResults': 1,
      });
      final results = (rawResults ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      if (results.isEmpty) {
        await ProfileService.instance.clearLastArticle();
        _state = AppState.idle;
        notifyListeners();
        return;
      }
      await _loadAndSpeakFrom(results.first['urlIndex'] as int, title, charOffset);
    } catch (_) {
      _state = AppState.idle;
      notifyListeners();
    }
  }

  /// Loads an article and starts reading from [charOffset] after an intro phrase.
  Future<void> _loadAndSpeakFrom(int urlIndex, String title, int charOffset) async {
    try {
      final raw = await _zimChannel.invokeMethod<Map>('article', {'urlIndex': urlIndex});
      if (raw == null) {
        await ProfileService.instance.clearLastArticle();
        _state = AppState.idle;
        notifyListeners();
        return;
      }
      _awaitingDisambiguation = false;
      _pendingCandidates      = [];
      _hasInterruptedForMic   = false;
      _savedArticleTextForMic = '';
      _misserfolgZaehler      = 0;
      _technischZaehler       = 0;
      _lastFailedQuery        = '';
      _cancelIdleTimers();
      _currentUrlIndex = urlIndex;
      _articleTitle = raw['title'] as String? ?? title;
      _articleText  = raw['text']  as String? ?? '';
      _articlePath  = raw['url']   as String? ?? '';
      _articleImages      = [];
      _selectedImageIndex = -1;
      _imageBytesCache.clear();
      final safeOffset = charOffset.clamp(0, _articleText.length);
      _ttsCursor      = safeOffset;
      _resumeOffset   = safeOffset;
      _isPaused       = true;
      _resumeAfterHandoff = true;
      _state = AppState.idle;
      notifyListeners();
      loadMedia(urlIndex);
      unawaited(_loadLinks(urlIndex));
      unawaited(_tts.speak('Weiter mit $_articleTitle!'));
      // TTS completion → non-article branch → _resumeAfterHandoff → resumeSpeaking()
    } on PlatformException catch (e) {
      debugPrint('ZIM article error (resume): ${e.message}');
      _state = AppState.idle;
      notifyListeners();
    }
  }

  // ── Gemini-Platzhalter (Typen 2, 3, 4) ────────────────────────────────────

  static const _kGeminiUpgradePhrases = [
    'Das ist eine kluge Frage! Für solche Antworten brauche ich einen Premium-Pass — frag deine Eltern darum!',
    'Ooh, gute Frage! Das kann ich mit Premium-Zugang beantworten — frag Mama oder Papa!',
    'Interessante Frage! Mit einem Premium-Pass könnte ich dir das erklären — deine Eltern wissen wie!',
  ];
  static const _kGeminiPlaceholderPhrases = [
    'Gute Frage! Diese Fähigkeit lerne ich gerade noch — frag mich bald nochmal!',
    'Hmm, lass mich überlegen ... das kann ich dir bald beantworten. Bleib gespannt!',
    'Das ist spannend! Ich arbeite daran, solche Fragen zu beantworten — frag mich später nochmal!',
  ];

  Future<void> _handleGeminiPlaceholder(String query) async {
    final idx = DateTime.now().millisecondsSinceEpoch % 3;
    if (!SubscriptionService.instance.canAskQuestions) {
      unawaited(_tts.speak(_kGeminiUpgradePhrases[idx]));
      return;
    }
    // Premium: Platzhalter-Phrase (TODO: hier Gemini-API-Aufruf einsetzen)
    unawaited(_tts.speak(_kGeminiPlaceholderPhrases[idx]));
  }

  // ── Internal link navigation ─────────────────────────────────────────────

  Future<void> onLinkTapped(String target) async {
    if (_state == AppState.speaking) {
      _resumeOffset = _sentenceStartOffset(); // snap to sentence start before state changes
      _isPaused = true;
      _state    = AppState.idle;
      notifyListeners();
      await _tts.stop();
    }
    await _followLink(target);
  }

  Future<void> _handleLinkConfirmation(String text) async {
    _awaitingLinkConfirmation = false;
    final lc = text.toLowerCase();
    final isYes = lc.contains('ja') || lc.contains('yes') || lc.contains('okay') ||
                  lc.contains('ok') || lc.contains('klar') || lc.contains('gerne') ||
                  lc.contains('natürlich') || lc.contains('erzähl') || lc.contains('bitte') ||
                  lc.contains('weiter');
    if (isYes && _pendingLinkTarget != null) {
      final target = _pendingLinkTarget!;
      _pendingLinkTarget = null;
      await _followLink(target);
    } else {
      _pendingLinkTarget = null;
      _resumeAfterHandoff = _isPaused;
      _state = AppState.idle;
      notifyListeners();
      await _tts.speak('Ok, ich lese weiter.');
    }
  }

  Future<void> _followLink(String target) async {
    final savedTitle    = _articleTitle;
    final savedUrlIndex = _currentUrlIndex;
    final savedOffset   = _state == AppState.speaking
        ? _sentenceStartOffset()
        : (_isPaused ? _resumeOffset : _ttsCursor);

    _state = AppState.thinking;
    notifyListeners();
    try {
      // 1. Direkter URL-Lookup — folgt Weiterleitungen (z.B. Stausee → Staudamm).
      final direct = await _zimChannel.invokeMethod<Map>('articleByName', {'name': target});
      if (direct != null) {
        if (savedTitle.isNotEmpty && savedUrlIndex >= 0) {
          _navStack.add((title: savedTitle, urlIndex: savedUrlIndex, charOffset: savedOffset));
          if (_navStack.length > 2) _navStack.removeAt(0);
        }
        _isLinkNavigation = true;
        await _loadAndSpeak(direct['urlIndex'] as int, direct['title'] as String);
        return;
      }

      // 2. Fallback: Fuzzy-Suche (falls URL-Lookup nichts findet)
      final rawResults = await _zimChannel.invokeMethod<List>('search', {
        'query': target,
        'maxResults': 1,
      });
      final results = (rawResults ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      if (results.isEmpty || (results.first['score'] as int) < _kMinScore) {
        _state = AppState.idle;
        notifyListeners();
        _resumeAfterHandoff = _isPaused;
        await _tts.speak('Dazu habe ich leider noch keinen Artikel.');
        return;
      }
      if (savedTitle.isNotEmpty && savedUrlIndex >= 0) {
        _navStack.add((title: savedTitle, urlIndex: savedUrlIndex, charOffset: savedOffset));
        if (_navStack.length > 2) _navStack.removeAt(0);
      }
      _isLinkNavigation = true;
      final best = results.first;
      await _loadAndSpeak(best['urlIndex'] as int, best['title'] as String);
    } on PlatformException catch (e) {
      debugPrint('_followLink error: ${e.message}');
      _state = AppState.idle;
      notifyListeners();
      _resumeAfterHandoff = _isPaused;
      await _tts.speak('Da ist leider etwas schiefgelaufen.');
    }
  }

  Future<void> goBack() async {
    if (_navStack.isEmpty) return;
    _awaitingNavStackResume = false;
    _awaitingLinkConfirmation = false;
    final entry = _navStack.removeLast();

    _state = AppState.thinking;
    _isPaused = false;
    _resumeAfterHandoff = false;
    notifyListeners();

    _ttsStopPending = true;
    unawaited(_tts.stop());

    try {
      final raw = await _zimChannel.invokeMethod<Map>('article', {'urlIndex': entry.urlIndex});
      if (raw == null) {
        _ttsStopPending = false;
        _state = AppState.idle;
        notifyListeners();
        return;
      }

      _currentUrlIndex      = entry.urlIndex;
      _articleTitle         = raw['title'] as String? ?? entry.title;
      _articleText          = raw['text']  as String? ?? '';
      _articlePath          = raw['url']   as String? ?? '';
      _articleLinks         = [];
      _articleImages        = [];
      _selectedImageIndex   = -1;
      _imageBytesCache.clear();
      _awaitingDisambiguation = false;
      _pendingCandidates    = [];
      _hasInterruptedForMic  = false;
      _savedArticleTextForMic = '';
      _misserfolgZaehler    = 0;
      _technischZaehler     = 0;
      _lastFailedQuery      = '';
      _cancelIdleTimers();
      _resumeAfterHandoff   = false;

      notifyListeners();
      loadMedia(entry.urlIndex);
      unawaited(_loadLinks(entry.urlIndex));

      final safeOffset = entry.charOffset.clamp(0, _articleText.length);
      _startSpeakingFrom(safeOffset);

    } on PlatformException catch (e) {
      _ttsStopPending = false;
      debugPrint('goBack: ${e.message}');
      _state = AppState.idle;
      notifyListeners();
    }
  }

  void _onArticleEnd() {
    // Article stays displayed; screen timer (started in caller) handles dim/off.
    // No prompt, no mic, no k6 — user reads/swipes at their own pace.
    _navStack.clear();
  }

  Future<void> _speakArticleEndWithStack() async {
    _awaitingNavStackResume = true;
    final String msg;
    if (_navStack.length == 1) {
      msg = 'Soll ich mit ${_navStack[0].title} weitermachen oder möchtest du etwas anderes hören?';
    } else {
      msg = 'Soll ich mit ${_navStack.last.title} oder mit ${_navStack[0].title} weitermachen oder etwas anderes erzählen?';
    }
    await _tts.speak(msg);
    // TTS completion → auto-start listening (via _awaitingNavStackResume check)
  }

  Future<void> _handleNavStackResume(String text) async {
    _awaitingNavStackResume = false;
    final lc = text.toLowerCase();

    // Check if user mentioned one of the nav stack titles (most recent first).
    for (int i = _navStack.length - 1; i >= 0; i--) {
      final entry = _navStack[i];
      if (lc.contains(entry.title.toLowerCase())) {
        final title  = entry.title;
        final offset = entry.charOffset;
        _navStack.removeRange(i, _navStack.length);
        _isLinkNavigation = true;
        _state = AppState.thinking;
        notifyListeners();
        await _loadAndSpeakFrom(entry.urlIndex, title, offset);
        return;
      }
    }

    // No nav stack title matched → treat as a new query, clear stack.
    _navStack.clear();
    await _processQuery(text);
  }

  Future<void> _loadLinks(int urlIndex) async {
    try {
      final rawList = await _zimChannel.invokeMethod<List>('listLinks', {'urlIndex': urlIndex});
      if (_currentUrlIndex != urlIndex) return; // stale — article changed while loading
      _articleLinks = (rawList ?? []).cast<Map>().map((m) => Map<String, dynamic>.from(m)).toList();
    } catch (e) {
      debugPrint('_loadLinks error: $e');
      if (_currentUrlIndex != urlIndex) return;
      _articleLinks = [];
    }
    notifyListeners();
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

    _wasPlayingBeforeCaption = (_state == AppState.speaking);
    if (_wasPlayingBeforeCaption) {
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

  // ── Usage tracking ───────────────────────────────────────────────────────────

  void _trackArticleListened() {
    final date = DateTime.now().toIso8601String().substring(0, 10);
    unawaited(LicenseCacheDb.instance.recordArticleListened(date));
    if (_articleTitle.isNotEmpty) {
      unawaited(ProfileService.instance.recordArticleOpened(_articleTitle));
    }
  }

  static const int kMonthlyQuestionLimit = 5000;

  String get _currentMonth => DateTime.now().toIso8601String().substring(0, 7);

  /// Returns true if a Premium question can be sent, false if limit reached.
  Future<bool> canSendPremiumQuestion() async {
    if (!SubscriptionService.instance.canAskQuestions) return false;
    final count = await LicenseCacheDb.instance.getQuestionCount(_currentMonth);
    return count < kMonthlyQuestionLimit;
  }

  Future<void> trackQuestionAsked() async {
    final today = DateTime.now().toIso8601String().substring(0, 10);
    await LicenseCacheDb.instance.incrementQuestionCount(_currentMonth);
    await LicenseCacheDb.instance.recordQuestionAsked(today);
  }

  Future<int> questionCountThisMonth() =>
      LicenseCacheDb.instance.getQuestionCount(_currentMonth);

  Future<List<Map<String, dynamic>>> recentStats(int days) =>
      LicenseCacheDb.instance.getRecentStats(days);

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
      final bytes = await _resolveImageBytes(filename);
      if (bytes != null && bytes.length <= 2 * 1024 * 1024) {
        _imageBytesCache[filename] = bytes;
      }
      return bytes;
    } catch (_) {
      return null;
    }
  }

  /// Routing logic depending on subscription tier and WiFi setting.
  ///
  /// Free:              offline ZIP (300px)        → ZIM
  /// Plus, WiFi on:     HiRes (best, WiFi-gated)   → offline ZIP (800px) → ZIM
  /// Plus, WiFi off:    offline ZIP (800px)         → ZIM
  Future<Uint8List?> _resolveImageBytes(String filename) async {
    if (!SubscriptionService.instance.isPlus) {
      return await ImageLibraryService.instance.getImage(filename)
          ?? await _zimBytes(filename);
    }

    final hiresWifi = await ImageLibraryService.hiresOnWifiEnabled();
    if (hiresWifi) {
      return await HiResImageService.instance.getHiResImage(filename)
          ?? await ImageLibraryService.instance.getImage(filename)
          ?? await _zimBytes(filename);
    }
    return await ImageLibraryService.instance.getImage(filename)
        ?? await _zimBytes(filename);
  }

  Future<Uint8List?> _zimBytes(String filename) async {
    try {
      return await _zimChannel.invokeMethod<Uint8List>(
        'getImageBytes', {'filename': filename},
      );
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

  /// App geht in den Hintergrund: Timer stoppen, TTS sofort beenden.
  Future<void> enterBackground() async {
    _isInBackground = true;
    _cancelIdleTimers();
    if (_state == AppState.speaking) {
      _resumeOffset = _ttsCursor;
      _isPaused = true;
      _state = AppState.idle;
      notifyListeners();
    }
    await _tts.stop(); // auch laufende Idle-Ansagen abbrechen
  }

  /// App kommt in den Vordergrund zurück.
  void exitBackground() {
    _isInBackground = false;
  }

  // ── Screen idle management ────────────────────────────────────────────────

  /// Startet/resettet den Idle-Timer. Wird bei jedem Touch und bei Sprechbeginn aufgerufen.
  void resetScreenTimer() {
    _screenDimTimer?.cancel();
    _screenOffTimer?.cancel();
    _zimChannel.invokeMethod<void>('setScreenMode', {'mode': 'awake'});
    _screenDimTimer = Timer(_dimAfter, () {
      _zimChannel.invokeMethod<void>('setScreenMode', {'mode': 'dim'});
      _screenOffTimer = Timer(_offAfter - _dimAfter, () {
        _zimChannel.invokeMethod<void>('setScreenMode', {'mode': 'off'});
      });
    });
  }

  /// Pausiert den Idle-Timer während der Professor spricht.
  void _pauseScreenTimer() {
    _screenDimTimer?.cancel();
    _screenOffTimer?.cancel();
    _zimChannel.invokeMethod<void>('setScreenMode', {'mode': 'awake'});
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
    _isPaused     = false;
    _resumeOffset = 0;
    _ttsCursor    = 0;
    _articleText  = '';
    _articleTitle = '';
    _articlePath  = '';
    _articleImages      = [];
    _selectedImageIndex = -1;
    _mediaItems         = [];
    _selectedMediaIndex = -1;
    _state = AppState.idle;
    notifyListeners();
  }

  /// Stellt den unterbrochenen Artikel wieder her und zeigt "Weiterlesen?"-Prompt.
  void _restoreInterruptedArticle() {
    if (!_hasInterruptedForMic || _savedArticleTextForMic.isEmpty) return;
    _hasInterruptedForMic    = false;
    _awaitingArticleSwitch   = false;
    _pendingArticleCandidate = null;
    _articleText   = _savedArticleTextForMic;
    _articleTitle  = _savedArticleTitleForMic;
    _articlePath   = _savedArticlePathForMic;
    _resumeOffset  = _savedResumeOffsetForMic;
    _isPaused      = true;
    _savedArticleTextForMic = '';
    _state = AppState.idle;
    notifyListeners();
    _showCaptionResumePrompt = true;
    _captionPromptDelayTimer?.cancel();
    _captionPromptDelayTimer = Timer(const Duration(seconds: 5), () {
      if (!_showCaptionResumePrompt) return;
      _isPromptPlaying = true;
      _captionResumeTimer?.cancel();
      _captionResumeTimer = Timer(const Duration(seconds: 5), resumeAfterCaption);
      _tts.speak('Soll ich weiterlesen?');
    });
  }

  /// Verarbeitet die Ja/Nein-Antwort auf die Artikel-Wechsel-Frage des Professors.
  Future<void> _handleArticleSwitchConfirmation(String text) async {
    _awaitingArticleSwitch = false;
    final lc = text.toLowerCase();
    final isYes = lc.contains('ja') || lc.contains('yes') ||
                  lc.contains('okay') || lc.contains('ok') ||
                  lc.contains('klar') || lc.contains('gerne') ||
                  lc.contains('natürlich') || lc.contains('wechsel') ||
                  lc.contains('erzähl') || lc.contains('bitte');

    if (isYes && _pendingArticleCandidate != null) {
      final candidate = _pendingArticleCandidate!;
      _pendingArticleCandidate = null;
      _hasInterruptedForMic   = false;
      _savedArticleTextForMic = '';
      await _loadAndSpeak(candidate['urlIndex'] as int, candidate['title'] as String);
    } else {
      _pendingArticleCandidate = null;
      _restoreInterruptedArticle();
    }
  }

  /// Mic-Tap im Artikel-Screen: Professor pausieren, Position merken, STT starten.
  /// Nach der Antwort wird der Artikel wiederhergestellt und "Weiterlesen?" angezeigt.
  Future<void> interruptAndStartListening() async {
    final wasSpeaking = _state == AppState.speaking;
    final wasPaused   = _isPaused;
    if (!wasSpeaking && !wasPaused) return;

    _savedArticleTextForMic  = _articleText;
    _savedArticleTitleForMic = _articleTitle;
    _savedArticlePathForMic  = _articlePath;
    _savedResumeOffsetForMic = wasSpeaking ? _sentenceStartOffset() : _resumeOffset;
    _hasInterruptedForMic    = true;

    if (wasSpeaking) {
      _isPaused = false;
      _state    = AppState.idle;
      await _tts.stop();
      notifyListeners();
    }
    // startListening() will clear _articleText etc. — saved copies are preserved above.
    await startListening();
  }

  // ── Professor Response Catalog helpers ───────────────────────────────────

  Future<String> _catalogOrFallback(String katalogId, String fallback) async {
    try {
      final msg = await ProfessorResponseService.instance.getResponse(katalogId);
      return msg.isNotEmpty ? msg : fallback;
    } catch (_) {
      return fallback;
    }
  }

  // katalogId for no-article failures (k2 → k3 escalation, k4 for repeats)
  String _noArticleKatalogId({required bool isRepeat}) {
    if (isRepeat) return 'k4';
    if (_misserfolgZaehler == 1) return 'k2';
    if (_misserfolgZaehler == 2) return 'k3_s1';
    if (_misserfolgZaehler <= 4) return 'k3_s2';
    _misserfolgZaehler = 0;
    return 'k3_s3';
  }

  // ── Keyword detection ─────────────────────────────────────────────────────

  bool _isThankKeyword(String text) {
    final lc = text.toLowerCase();
    return lc.contains('danke') || lc.contains('toll') || lc.contains('super') ||
           lc.contains('klasse') || lc.contains('prima') || lc.contains('cool') ||
           lc.contains('schön') || lc.contains('gefällt mir') || lc.contains('du bist');
  }

  bool _isGoodbyeKeyword(String text) {
    final lc = text.toLowerCase();
    return lc.contains('tschüss') || lc.contains('auf wiedersehen') ||
           lc.contains('bye') || lc.contains('ich muss gehen') ||
           lc.contains('ich gehe jetzt') || lc.contains('bis später');
  }

  Future<void> _handleKeyword(String katalogId) async {
    _misserfolgZaehler = 0;
    _technischZaehler  = 0;
    _lastFailedQuery   = '';
    _cancelIdleTimers();
    _state = AppState.idle;
    notifyListeners();
    final msg = await _catalogOrFallback(katalogId, '');
    if (msg.isNotEmpty) _tts.speak(msg);
  }

  // ── Idle / pause / rest mode ──────────────────────────────────────────────

  void _checkStartIdleTimer() {}

  void _cancelIdleTimers() {}

  void _enterRestMode() {}

  Future<void> wakeFromRest() async {}

  // ── Data-limit overlay support ────────────────────────────────────────────

  static const _kHandoffPhrases = [
    'Ich brauche kurz Hilfe von Mama oder Papa!',
    'Dafür brauche ich kurz die Erlaubnis deiner Eltern!',
    'Moment — das müssen kurz deine Eltern freigeben!',
  ];

  static const _kWarning80Phrases = [
    'Übrigens — ich habe heute schon viel geladen. Deine Eltern können mir mehr erlauben!',
    'Ich merke, ich habe heute schon einiges heruntergeladen. Frag deine Eltern falls du mehr möchtest!',
    'Psst — ich habe heute fast mein Limit erreicht. Deine Eltern können das anpassen!',
  ];

  static const _kWarning90Phrases = [
    'Ich kann heute nur noch wenige Bilder laden. Deine Eltern können mir mehr erlauben!',
    'Fast am Limit — deine Eltern können mir mehr Spielraum geben!',
    'Noch ein bisschen — dann brauche ich Hilfe von Mama oder Papa!',
  ];

  String _randomLimitWarningPhrase(LimitWarningLevel level) {
    final idx = DateTime.now().millisecond % 3;
    return level == LimitWarningLevel.warning80
        ? _kWarning80Phrases[idx]
        : _kWarning90Phrases[idx];
  }

  /// Pauses article reading, speaks a random handoff phrase, and returns a
  /// Future that completes when the phrase finishes.
  /// Call this before showing the data-limit overlay.
  Future<void> pauseForDataLimit() async {
    if (_state == AppState.speaking) {
      _resumeOffset = _sentenceStartOffset();
      _isPaused     = true;
      _state        = AppState.idle;
      await _tts.stop();
    }
    // Set completer before speaking so the completion handler can drain it.
    _handoffCompleter = Completer<void>();
    final phrase = _kHandoffPhrases[DateTime.now().millisecond % 3];
    unawaited(_tts.speak(phrase));
    return _handoffCompleter!.future;
  }

  /// Resumes article reading after the data-limit overlay was dismissed (retry).
  void resumeAfterDataLimit() {
    if (_isPaused && _articleText.isNotEmpty) {
      unawaited(resumeSpeaking());
    }
  }

  /// Speaks "Kein Problem" and then automatically resumes article reading.
  /// Call this when the user cancels the data-limit overlay.
  void speakDataLimitCancelled() {
    _resumeAfterHandoff = _isPaused && _articleText.isNotEmpty;
    unawaited(_tts.speak('Kein Problem — wir machen einfach weiter!'));
  }

  @override
  void dispose() {
    _cancelIdleTimers();
    _tts.stop();
    _audioPlayer.dispose();
    super.dispose();
  }
}
