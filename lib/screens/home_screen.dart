import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/asset_config.dart';
import '../providers/wissensfreund_provider.dart';
import '../services/image_library_service.dart';
import '../services/license_cache_db.dart';
import '../services/network_service.dart';
import '../services/network_settings_service.dart';
import '../services/parental_lock_service.dart';
import '../services/profile_service.dart';
import '../services/reward_service.dart';
import '../services/storage_manager.dart';
import '../services/subscription_service.dart';
import '../services/zim_update_service.dart';
import '../utils/responsive.dart';
import '../widgets/professor_widget.dart';
import 'article_screen.dart';
import 'card_album_screen.dart';
import 'profile_management_screen.dart';
import 'room_screen.dart';
import 'trophy_screen.dart';
import 'profile_selection_screen.dart';
import 'wf_article_list_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  final _scrollController = ScrollController();
  WissensfreundProvider? _provider;
  AppState _lastState = AppState.idle;
  bool _navigatingToArticle = false;

  // Breathing animation for rest mode
  late final AnimationController _breathCtrl;
  late final Animation<double> _breathScale;

  // ZIM status bar: visible while loading, briefly after ready, hidden otherwise
  bool _lastZimReady        = false;
  bool _zimStatusVisible    = true;  // shown until dismissed
  bool _zimStatusFading     = false; // true while fading out
  Timer? _zimFadeTimer;

  bool _zimUpdateDialogShown = false;

  // Weiterhören state
  ({String title, int offset})? _lastArticle;

  @override
  void initState() {
    super.initState();
    _breathCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3000),
    )..repeat(reverse: true);
    _breathScale = Tween<double>(begin: 1.0, end: 1.04).animate(
      CurvedAnimation(parent: _breathCtrl, curve: Curves.easeInOut),
    );
    ProfileService.instance.addListener(_onProfileChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _loadLastArticle();
      await StorageManager.instance.initialize();
      unawaited(StorageManager.instance.evictOldCache());
      await _checkOnboarding();
      if (mounted) await _checkImageQuality();
      if (mounted) await _checkNetworkSettings();
    });
  }

  Future<void> _loadLastArticle() async {
    final last = await ProfileService.instance.getLastArticle();
    if (mounted) setState(() => _lastArticle = last);
  }

  void _onProfileChanged() => _loadLastArticle();

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final p = context.read<WissensfreundProvider>();
    if (p != _provider) {
      _provider?.removeListener(_onProviderChanged);
      _provider = p;
      _provider?.addListener(_onProviderChanged);
    }
  }

  Future<void> _checkOnboarding() async {
    if (!mounted) return;
    final ps = context.read<ParentalLockService>();
    if (ps.onboardingDone) return;
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => _ParentalOnboardingDialog(ps: ps),
    );
    // Accessibility-Status nach Rückkehr aus Einstellungen aktualisieren
    if (mounted) await ps.refreshAdminStatus();
  }

  Future<void> _checkImageQuality() async {
    if (!mounted) return;
    if (ImageLibraryService.instance.totalSizeBytes > 0) return;
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool('image_quality_offered') ?? false) return;
    await prefs.setBool('image_quality_offered', true);
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const _ImageQualityDialog(),
    );
  }

  Future<void> _checkNetworkSettings() async {
    if (!mounted) return;
    final settings = NetworkSettingsService.instance;
    if (await settings.networkSettingsOffered) return;
    await settings.setNetworkSettingsOffered(true);

    final ps = context.read<ParentalLockService>();
    final ok = await ps.authenticate(
      'Eltern: Bitte bestätigen um Internet-Einstellungen einzurichten.',
    );
    if (!mounted) return;
    if (!ok) return; // skip silently if auth fails

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const _NetworkSettingsOnboardingDialog(),
    );
  }

  Future<void> _onBackPressed(bool didPop, dynamic result) async {
    if (didPop) return;
    final provider = context.read<WissensfreundProvider>();
    final ps = context.read<ParentalLockService>();

    // Professor spricht die Rückfrage (unterbricht Artikel am Satzanfang)
    await provider.speakInterrupt('Möchtest du Wissensfreund wirklich verlassen?');

    if (!mounted) return;
    final exit = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Wissensfreund verlassen?'),
        content: const Text(
          'Möchtest du wirklich aufhören zu lernen?',
          style: TextStyle(fontSize: 16),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Nein, weiterlernen'),
          ),
          TextButton(
            style: TextButton.styleFrom(
                foregroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Ja, beenden'),
          ),
        ],
      ),
    );

    if (exit != true) {
      provider.resumeSpeaking();
      return;
    }

    if (!mounted) return;

    // Biometrie nur wenn Kinderschutz (Kiosk) aktiv ist
    if (ps.isKioskMode) {
      final authenticated = await ps.authenticate(
        'Zum Beenden der App bitte authentifizieren.',
      );
      if (!authenticated) {
        provider.resumeSpeaking();
        return;
      }
      await ps.stopKioskMode();
    }

    SystemNavigator.pop();
  }

  void _onProviderChanged() {
    // ZIM became ready → start fade-out timer
    final zimReady = _provider!.zimReady;
    if (zimReady && !_lastZimReady) {
      _lastZimReady = true;
      _zimFadeTimer?.cancel();
      _zimFadeTimer = Timer(const Duration(seconds: 2), () {
        if (mounted) setState(() => _zimStatusFading = true);
        Timer(const Duration(milliseconds: 600), () {
          if (mounted) setState(() => _zimStatusVisible = false);
        });
      });
    }

    // ZIM update available → show dialog once
    if (_provider!.pendingZimUpdate != null && !_zimUpdateDialogShown) {
      _zimUpdateDialogShown = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final info = _provider!.pendingZimUpdate;
        if (info == null) return;
        _showZimUpdateDialog(info);
      });
    }

    // Limit warning (80% / 90%) → SnackBar
    final warning = NetworkService.instance.consumePendingWarning();
    if (warning != null &&
        warning != LimitWarningLevel.limitReached &&
        mounted) {
      final pct = warning == LimitWarningLevel.warning80 ? '80 %' : '90 %';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$pct des Datenlimits erreicht!'),
          duration: const Duration(seconds: 4),
        ),
      );
    }

    final newState = _provider!.state;

    // Navigate to ArticleScreenA when speaking starts (only once per article)
    if (!_navigatingToArticle &&
        _lastState != AppState.speaking &&
        newState == AppState.speaking &&
        _provider!.articleText.isNotEmpty) {
      _navigatingToArticle = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        // Guard: don't push if an article screen is already on top
        final route = ModalRoute.of(context);
        if (route == null || !route.isCurrent) return;
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const ArticleScreen()),
        ).then((_) {
          if (mounted) {
            _navigatingToArticle = false;
            _loadLastArticle(); // reload Weiterhören card after returning
          }
        });
      });
    }

    // Scroll to top after TTS finishes (fallback if user stays on home screen)
    if (_lastState == AppState.speaking && newState == AppState.idle) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients && _scrollController.offset > 0) {
          _scrollController.animateTo(
            0,
            duration: const Duration(milliseconds: 600),
            curve: Curves.easeOut,
          );
        }
      });
    }

    _lastState = newState;
  }

  void _showZimUpdateDialog(ZimVersionInfo info) {
    showDialog<void>(
      context: context,
      builder: (_) => _ZimUpdateDialog(
        info: info,
        onDone: () => context.read<WissensfreundProvider>().clearPendingZimUpdate(),
      ),
    );
  }

  @override
  void dispose() {
    _breathCtrl.dispose();
    _zimFadeTimer?.cancel();
    _provider?.removeListener(_onProviderChanged);
    ProfileService.instance.removeListener(_onProfileChanged);
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToRatio(double ratio) {
    if (!_scrollController.hasClients) return;
    final max = _scrollController.position.maxScrollExtent;
    if (max <= 0) return;
    _scrollController.animateTo(
      (ratio * max).clamp(0.0, max),
      duration: const Duration(milliseconds: 200),
      curve: Curves.linear,
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: _onBackPressed,
      child: Consumer<WissensfreundProvider>(
        builder: (context, provider, _) {
        final isSpeaking = provider.state == AppState.speaking;

        if (isSpeaking && provider.articleText.isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            final text = provider.articleText;
            if (text.isEmpty) return;
            final ratio =
                (provider.ttsCursor / text.length).clamp(0.0, 1.0);
            _scrollToRatio(ratio);
          });
        }

        return Scaffold(
          backgroundColor: const Color(0xFFFFF8EE),
          body: SafeArea(
            minimum: const EdgeInsets.only(bottom: 8),
            child: Column(
              children: [
                _AppHeader(),
                if (_zimStatusVisible || provider.zimNotFound)
                  AnimatedOpacity(
                    opacity: _zimStatusFading && !provider.zimNotFound ? 0.0 : 1.0,
                    duration: const Duration(milliseconds: 600),
                    child: _ZimStatusBar(
                      ready: provider.zimReady,
                      notFound: provider.zimNotFound,
                      articleCount: provider.zimArticleCount,
                      progress: provider.zimProgress,
                    ),
                  ),
                Expanded(
                  child: Stack(
                    children: [
                      // Scrollable text content
                      Positioned.fill(
                        child: SingleChildScrollView(
                          controller: _scrollController,
                          padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
                          child: Column(
                            children: [
                              AnimatedContainer(
                                duration: const Duration(milliseconds: 500),
                                curve: Curves.easeInOut,
                                height: isSpeaking ? 8 : 290,
                              ),
                              _StateLabel(state: provider.state),
                              const SizedBox(height: 12),
                              if (_lastArticle != null &&
                                  provider.state == AppState.idle &&
                                  provider.articleText.isEmpty)
                                _WeiterhoerenCard(
                                  title: _lastArticle!.title,
                                  onTap: () {
                                    final last = _lastArticle!;
                                    setState(() => _lastArticle = null);
                                    provider.resumeLastArticle(last.title, last.offset);
                                  },
                                ),
                              if (provider.recognizedText.isNotEmpty &&
                                  provider.articleText.isEmpty)
                                _RecognizedText(text: provider.recognizedText),
                              if (provider.articleText.isNotEmpty)
                                _ArticleCard(
                                  title: provider.articleTitle,
                                  text: provider.articleText,
                                ),
                              // TODO: TEMP TEST — auskommentiert, durch Artikelliste ersetzt
                              // if (provider.state == AppState.idle)
                              //   _JsonTestButton(provider: provider),
                              if (provider.state == AppState.idle)
                                _ArticleListButton(),
                              if (provider.state == AppState.idle)
                                _CardAlbumButton(),
                              if (provider.state == AppState.idle)
                                _TrophyButton(),
                              if (provider.state == AppState.idle)
                                _RoomButton(),
                              const SizedBox(height: 16),
                            ],
                          ),
                        ),
                      ),
                      // Professor: topCenter → bottomRight when speaking
                      Positioned.fill(
                        child: AnimatedAlign(
                          duration: const Duration(milliseconds: 500),
                          curve: Curves.easeInOut,
                          alignment: isSpeaking
                              ? Alignment.bottomRight
                              : Alignment.topCenter,
                          child: Padding(
                            padding: isSpeaking
                                ? const EdgeInsets.only(bottom: 4)
                                : EdgeInsets.zero,
                            child: GestureDetector(
                              onTap: provider.isRestMode
                                  ? () => provider.wakeFromRest()
                                  : null,
                              child: provider.isRestMode
                                  ? AnimatedBuilder(
                                      animation: _breathCtrl,
                                      builder: (_, child) => Transform.scale(
                                        scale: _breathScale.value,
                                        child: Opacity(opacity: 0.65, child: child),
                                      ),
                                      child: AnimatedContainer(
                                        duration: const Duration(milliseconds: 500),
                                        curve: Curves.easeInOut,
                                        height: 268,
                                        width: 240,
                                        child: ProfessorWidget(
                                          state: AppState.idle,
                                          compact: false,
                                        ),
                                      ),
                                    )
                                  : AnimatedContainer(
                                      duration: const Duration(milliseconds: 500),
                                      curve: Curves.easeInOut,
                                      height: isSpeaking ? 160 : 268,
                                      width: isSpeaking ? 120.0 : 240.0,
                                      child: ProfessorWidget(
                                        state: provider.state,
                                        compact: isSpeaking,
                                      ),
                                    ),
                            ),
                          ),
                        ),
                      ),
                      // Rest mode: "Tippe mich an" badge below professor
                      if (provider.isRestMode)
                        const Positioned(
                          top: 270,
                          left: 0,
                          right: 0,
                          child: Center(child: _RestModeBadge()),
                        ),
                    ],
                  ),
                ),
                // Bottom bar: menu icon + dominant mic FAB
                _BottomBar(provider: provider),
              ],
            ),
          ),
        );
      },
    ),   // Consumer
    );   // PopScope
  }
}

// ── ZIM Status Bar ─────────────────────────────────────────────────────────────

class _ZimStatusBar extends StatelessWidget {
  final bool ready;
  final bool notFound;
  final int articleCount;
  final double progress; // 0.0..1.0
  const _ZimStatusBar({
    required this.ready,
    required this.notFound,
    required this.articleCount,
    required this.progress,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 6),
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 400),
        child: ready
            // ── Fertig ────────────────────────────────────────────────────
            ? Row(
                key: const ValueKey('ready'),
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.check_circle_rounded,
                      size: 13, color: Color(0xFF388E3C)),
                  const SizedBox(width: 5),
                  Text(
                    '$articleCount Artikel geladen',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF388E3C),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              )
            : notFound
            // ── Nicht gefunden ────────────────────────────────────────────
            ? Row(
                key: const ValueKey('notfound'),
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.warning_amber_rounded,
                      size: 13, color: Colors.orange.shade700),
                  const SizedBox(width: 5),
                  Text(
                    'klexikon.zim nicht gefunden',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.orange.shade700,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              )
            // ── Lädt ──────────────────────────────────────────────────────
            : Column(
                key: const ValueKey('loading'),
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Wissensspeicher lädt...',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade500,
                        ),
                      ),
                      Text(
                        '${(progress * 100).round()} %',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade500,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 5),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: progress > 0 ? progress : null,
                      minHeight: 5,
                      backgroundColor: Colors.grey.shade200,
                      valueColor: AlwaysStoppedAnimation(Colors.grey.shade400),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

// ── App Header ─────────────────────────────────────────────────────────────────

class _AppHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 4),
      child: Row(
        children: [
          // Left flex balances the ⭐ badge so the title stays visually centered.
          const Expanded(child: SizedBox()),
          const Text('🎓', style: TextStyle(fontSize: 28)),
          const SizedBox(width: 10),
          Text(
            'Wissensfreund',
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w900,
              color: const Color(0xFF2E7D32),
              letterSpacing: 0.5,
              shadows: [
                Shadow(
                  color: Colors.green.withValues(alpha: 0.2),
                  offset: const Offset(0, 2),
                  blurRadius: 6,
                ),
              ],
            ),
          ),
          const Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: _StarBadge(),
            ),
          ),
        ],
      ),
    );
  }
}

/// ⭐ balance pill in the header. Reactive to [RewardService]; hidden when no
/// profile is active (rewards are per profile).
class _StarBadge extends StatelessWidget {
  const _StarBadge();

  @override
  Widget build(BuildContext context) {
    final hasProfile = context.watch<ProfileService>().activeProfile != null;
    if (!hasProfile) return const SizedBox.shrink();
    final stars = context.watch<RewardService>().stars;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3D6),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFF0C36D), width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.amber.withValues(alpha: 0.18),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('⭐', style: TextStyle(fontSize: 15)),
          const SizedBox(width: 4),
          Text(
            '$stars',
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: Color(0xFF9A6B00),
            ),
          ),
        ],
      ),
    );
  }
}

// ── State Label ────────────────────────────────────────────────────────────────

class _StateLabel extends StatelessWidget {
  final AppState state;
  const _StateLabel({required this.state});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (state) {
      AppState.idle => ('Stell mir eine Frage!', const Color(0xFF555555)),
      AppState.listening => ('Ich höre zu...', const Color(0xFF388E3C)),
      AppState.thinking => ('Ich denke nach...', const Color(0xFFF57C00)),
      AppState.speaking => ('Ich erkläre dir...', const Color(0xFF1565C0)),
    };
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: Text(
        label,
        key: ValueKey(state),
        style: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: color,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}

// ── Weiterhören Card ──────────────────────────────────────────────────────────

class _WeiterhoerenCard extends StatelessWidget {
  final String title;
  final VoidCallback onTap;
  const _WeiterhoerenCard({required this.title, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: const Color(0xFF2D6A4F),
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.15),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              const Icon(Icons.play_circle_fill_rounded,
                  color: Colors.white, size: 36),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Weiterhören',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    const Text(
                      'Weitermachen wo du aufgehört hast',
                      style: TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Recognized Text ────────────────────────────────────────────────────────────

class _RecognizedText extends StatelessWidget {
  final String text;
  const _RecognizedText({required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Text(
        '"$text"',
        style: TextStyle(
          fontSize: 16,
          color: Colors.grey.shade600,
          fontStyle: FontStyle.italic,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}

// ── Article Card ───────────────────────────────────────────────────────────────

class _ArticleCard extends StatelessWidget {
  final String title;
  final String text;
  const _ArticleCard({required this.title, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.07),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
        border: Border.all(color: const Color(0xFFE8F5E9), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title.isNotEmpty) ...[
            Text(
              title,
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2E7D32),
              ),
            ),
            const SizedBox(height: 10),
            const Divider(height: 1, color: Color(0xFFE8F5E9)),
            const SizedBox(height: 10),
          ],
          Text(
            text,
            style: const TextStyle(
              fontSize: 16,
              height: 1.65,
              color: Color(0xFF333333),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Bottom Bar ─────────────────────────────────────────────────────────────────

class _BottomBar extends StatelessWidget {
  final WissensfreundProvider provider;
  const _BottomBar({required this.provider});

  void _openMenu(BuildContext context) {
    final navBarHeight = MediaQuery.of(context).viewPadding.bottom;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => _AppMenu(
        provider: provider,
        outerContext: context,
        navBarHeight: navBarHeight,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 12,
            offset: Offset(0, -3),
          ),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(24, 4, 24, 12),
      child: provider.isRestMode
          // Rest mode: only menu button, centered
          ? SizedBox(
              height: 96,
              child: Center(
                child: _MenuIconButton(onTap: () => _openMenu(context)),
              ),
            )
          : Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                _MenuIconButton(onTap: () => _openMenu(context)),
                SizedBox(
                  width: 96,
                  height: 96,
                  child: Stack(
                    clipBehavior: Clip.none,
                    alignment: Alignment.center,
                    children: [
                      _PulsingRings(active: provider.state == AppState.listening),
                      _MicButtonCore(
                        isListening: provider.state == AppState.listening,
                        isSpeaking: provider.state == AppState.speaking,
                        isThinking: provider.state == AppState.thinking,
                        onTap: () {
                          if (provider.state == AppState.speaking) {
                            provider.stopSpeaking();
                          } else if (provider.state == AppState.listening) {
                            provider.stopListening();
                          } else if (provider.state != AppState.thinking) {
                            provider.startListening();
                          }
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 48),
              ],
            ),
    );
  }
}

class _MenuIconButton extends StatelessWidget {
  final VoidCallback onTap;
  const _MenuIconButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 48,
        height: 48,
        decoration: const BoxDecoration(
          shape: BoxShape.circle,
          color: Color(0xFFE8F5E9),
        ),
        child: const Icon(
          Icons.menu_rounded,
          color: Color(0xFF2E7D32),
          size: 24,
        ),
      ),
    );
  }
}

// ── App Menu (Bottom Sheet) ────────────────────────────────────────────────────

class _AppMenu extends StatefulWidget {
  final WissensfreundProvider provider;
  final BuildContext outerContext;
  final double navBarHeight;
  const _AppMenu({
    required this.provider,
    required this.outerContext,
    required this.navBarHeight,
  });

  @override
  State<_AppMenu> createState() => _AppMenuState();
}

class _AppMenuState extends State<_AppMenu> {
  bool _parentUnlocked = false;

  WissensfreundProvider get provider => widget.provider;
  BuildContext get outerContext => widget.outerContext;

  @override
  Widget build(BuildContext context) {
    final profile = context.watch<ProfileService>().activeProfile;

    return Container(
      margin: EdgeInsets.fromLTRB(16, 0, 16, 16 + widget.navBarHeight + 8),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8EE),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── Drag handle ─────────────────────────────────────────────
          const SizedBox(height: 12),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey.shade300,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 12),

          // ── Profile header ───────────────────────────────────────────
          if (profile != null)
            GestureDetector(
              onTap: () {
                Navigator.pop(context);
                Navigator.of(outerContext).push(
                  MaterialPageRoute(
                    builder: (_) => const ProfileSelectionScreen(),
                  ),
                );
              },
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Row(
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: const BoxDecoration(
                        color: Color(0xFFE8F5E9),
                        shape: BoxShape.circle,
                      ),
                      child: Center(
                        child: Text(
                          profile.avatarId,
                          style: const TextStyle(fontSize: 26),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            profile.name,
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1B5E20),
                            ),
                          ),
                          Text(
                            '${profile.age} Jahre · ${_levelLabel(profile.languageLevel)}',
                            style: const TextStyle(
                              fontSize: 13,
                              color: Color(0xFF888888),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const Icon(
                      Icons.chevron_right_rounded,
                      color: Color(0xFF4CAF50),
                      size: 24,
                    ),
                  ],
                ),
              ),
            ),
          const Divider(height: 1, indent: 20, endIndent: 20),

          // ── Für Kinder ───────────────────────────────────────────────
          const _MenuSectionHeader(label: 'Für Kinder'),
          _MenuItem(
            icon: Icons.home_rounded,
            label: 'Hauptmenü',
            onTap: () => Navigator.pop(context),
          ),
          _MenuItem(
            icon: Icons.keyboard_rounded,
            label: 'Texteingabe',
            onTap: () {
              Navigator.pop(context);
              _showTextInput(outerContext);
            },
          ),
          _MenuItem(
            icon: Icons.history_rounded,
            label: 'Verlauf',
            onTap: () {
              Navigator.pop(context);
              _showHistory(outerContext);
            },
          ),
          _MenuItem(
            icon: Icons.star_rounded,
            label: 'Favoriten',
            onTap: () {
              Navigator.pop(context);
              _showFavorites(outerContext);
            },
          ),
          const Divider(height: 1, indent: 20, endIndent: 20),

          // ── Für Eltern ───────────────────────────────────────────────
          _MenuSectionHeader(
            label: 'Für Eltern',
            locked: !_parentUnlocked,
          ),
          if (_parentUnlocked) ...[
            _MenuItem(
              icon: Icons.wifi_rounded,
              label: 'Internet & Daten',
              onTap: () => Navigator.of(outerContext).push(
                MaterialPageRoute(
                  fullscreenDialog: true,
                  builder: (_) => const _InternetDataScreen(),
                ),
              ),
            ),
            _MenuItem(
              icon: Icons.shield_rounded,
              label: 'Kinderschutz',
              onTap: () => Navigator.of(outerContext).push(
                MaterialPageRoute(
                  fullscreenDialog: true,
                  builder: (_) => const _ParentalScreen(),
                ),
              ),
            ),
            _MenuItem(
              icon: Icons.storage_rounded,
              label: 'Speicher & Qualität',
              onTap: () => _showStorageDialog(outerContext),
            ),
            _MenuItem(
              icon: Icons.people_rounded,
              label: 'Profile verwalten',
              onTap: () => Navigator.of(outerContext).push(
                MaterialPageRoute(
                  builder: (_) => const ProfileManagementScreen(),
                  fullscreenDialog: true,
                ),
              ),
            ),
            _MenuItem(
              icon: Icons.workspace_premium_rounded,
              label: 'Plus & Premium',
              onTap: () => Navigator.of(outerContext).push(
                MaterialPageRoute(
                  fullscreenDialog: true,
                  builder: (_) => const _SubscriptionScreen(),
                ),
              ),
            ),
          ] else
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
              child: OutlinedButton.icon(
                icon: const Icon(Icons.fingerprint_rounded, size: 20),
                label: const Text('Mit Fingerabdruck / PIN entsperren'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF2E7D32),
                  side: const BorderSide(color: Color(0xFF4CAF50)),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(50),
                  ),
                ),
                onPressed: _unlockParentSection,
              ),
            ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Future<void> _unlockParentSection() async {
    final ps = outerContext.read<ParentalLockService>();
    final ok = await ps.authenticate(
      'Bitte authentifizieren um die Eltern-Einstellungen zu öffnen.',
    );
    if (ok && mounted) setState(() => _parentUnlocked = true);
  }

  static String _levelLabel(String level) => switch (level) {
    'easy'     => 'Einfach',
    'advanced' => 'Fortgeschritten',
    _          => 'Mittel',
  };

  void _showHistory(BuildContext ctx) async {
    final ps = ctx.read<ProfileService>();
    final articles = await ps.getRecentArticles(limit: 30);
    if (!ctx.mounted) return;
    showDialog<void>(
      context: ctx,
      builder: (_) => _ArticleListDialog(
        title: 'Verlauf',
        icon: Icons.history_rounded,
        articles: articles,
        emptyMessage: 'Noch keine Artikel angeschaut.',
        onTap: (title) => ctx.read<WissensfreundProvider>().submitText(title),
      ),
    );
  }

  void _showFavorites(BuildContext ctx) async {
    final ps = ctx.read<ProfileService>();
    final articles = await ps.getFavorites();
    if (!ctx.mounted) return;
    showDialog<void>(
      context: ctx,
      builder: (_) => _ArticleListDialog(
        title: 'Favoriten',
        icon: Icons.star_rounded,
        articles: articles,
        emptyMessage: 'Noch keine Favoriten gespeichert.',
        onTap: (title) => ctx.read<WissensfreundProvider>().submitText(title),
      ),
    );
  }


  void _showParentalDashboard(BuildContext ctx) {
    Navigator.of(ctx).push(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => const _ParentalScreen(),
      ),
    );
  }

  void _showStorageDialog(BuildContext ctx) {
    Navigator.of(ctx).push(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => const _StorageScreen(),
      ),
    );
  }

  void _showTextInput(BuildContext context) {
    final controller = TextEditingController();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: Container(
          margin: const EdgeInsets.all(16),
          padding: const EdgeInsets.fromLTRB(16, 16, 8, 16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  autofocus: true,
                  textInputAction: TextInputAction.search,
                  style: const TextStyle(fontSize: 15),
                  decoration: InputDecoration(
                    hintText: 'Deine Frage...',
                    hintStyle:
                        TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    prefixIcon: Icon(Icons.search_rounded,
                        color: Colors.grey.shade400),
                    filled: true,
                    fillColor: const Color(0xFFF5F5F5),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(28),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                        vertical: 12, horizontal: 16),
                  ),
                  onSubmitted: (q) {
                    Navigator.pop(ctx);
                    if (q.trim().isNotEmpty) provider.submitText(q);
                  },
                ),
              ),
              IconButton(
                icon:
                    const Icon(Icons.send_rounded, color: Color(0xFF2E7D32)),
                onPressed: () {
                  final q = controller.text;
                  Navigator.pop(ctx);
                  if (q.trim().isNotEmpty) provider.submitText(q);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool comingSoon;

  const _MenuItem({
    required this.icon,
    required this.label,
    required this.onTap,
    this.comingSoon = false,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        icon,
        color: comingSoon ? Colors.grey.shade400 : const Color(0xFF2E7D32),
      ),
      title: Text(
        label,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w500,
          color: comingSoon ? Colors.grey.shade400 : const Color(0xFF333333),
        ),
      ),
      trailing: comingSoon
          ? Text('bald',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade400))
          : null,
      onTap: comingSoon ? null : onTap,
    );
  }
}

// ── Menu Section Header ────────────────────────────────────────────────────────

class _MenuSectionHeader extends StatelessWidget {
  final String label;
  final bool locked;
  const _MenuSectionHeader({required this.label, this.locked = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 2),
      child: Row(
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Color(0xFF888888),
              letterSpacing: 0.8,
            ),
          ),
          if (locked) ...[
            const SizedBox(width: 6),
            const Icon(Icons.lock_rounded, size: 13, color: Color(0xFF888888)),
          ],
        ],
      ),
    );
  }
}

// ── Article List Dialog (History / Favorites) ──────────────────────────────────

class _ArticleListDialog extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<String> articles;
  final String emptyMessage;
  final void Function(String title) onTap;

  const _ArticleListDialog({
    required this.title,
    required this.icon,
    required this.articles,
    required this.emptyMessage,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(children: [
        Icon(icon, color: const Color(0xFF2E7D32), size: 22),
        const SizedBox(width: 8),
        Text(title),
      ]),
      content: SizedBox(
        width: double.maxFinite,
        child: articles.isEmpty
            ? Text(
                emptyMessage,
                style: const TextStyle(color: Color(0xFF888888), fontSize: 15),
              )
            : ListView.separated(
                shrinkWrap: true,
                itemCount: articles.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) => ListTile(
                  dense: true,
                  title: Text(
                    articles[i],
                    style: const TextStyle(fontSize: 15),
                  ),
                  trailing: const Icon(Icons.play_arrow_rounded,
                      color: Color(0xFF4CAF50), size: 20),
                  onTap: () {
                    Navigator.pop(context);
                    onTap(articles[i]);
                  },
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Schließen'),
        ),
      ],
    );
  }
}

// ── Mic Button Core ────────────────────────────────────────────────────────────

class _MicButtonCore extends StatelessWidget {
  final bool isListening;
  final bool isSpeaking;
  final bool isThinking;
  final VoidCallback onTap;

  const _MicButtonCore({
    required this.isListening,
    required this.isSpeaking,
    required this.isThinking,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final Color color;
    final IconData icon;

    if (isListening) {
      color = const Color(0xFFE53935);
      icon = Icons.stop_rounded;
    } else if (isSpeaking) {
      color = const Color(0xFFF57C00);
      icon = Icons.volume_off_rounded;
    } else if (isThinking) {
      color = Colors.grey.shade400;
      icon = Icons.hourglass_top_rounded;
    } else {
      color = const Color(0xFF2E7D32);
      icon = Icons.mic_rounded;
    }

    return GestureDetector(
      onTap: isThinking ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: 88,
        height: 88,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color,
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: isListening ? 0.5 : 0.3),
              blurRadius: isListening ? 24 : 12,
              spreadRadius: isListening ? 3 : 0,
            ),
          ],
        ),
        child: isThinking
            ? const Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(
                    color: Colors.white, strokeWidth: 3),
              )
            : Icon(icon, size: 44, color: Colors.white),
      ),
    );
  }
}

// ── Pulsing Rings ──────────────────────────────────────────────────────────────

class _PulsingRings extends StatefulWidget {
  final bool active;
  const _PulsingRings({required this.active});

  @override
  State<_PulsingRings> createState() => _PulsingRingsState();
}

class _PulsingRingsState extends State<_PulsingRings>
    with TickerProviderStateMixin {
  static const _ringCount = 3;
  static const _ringDelay = 550;

  final List<AnimationController> _ctrls = [];
  final List<Animation<double>> _scales = [];
  final List<Animation<double>> _opacities = [];

  @override
  void initState() {
    super.initState();
    for (int i = 0; i < _ringCount; i++) {
      final ctrl = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1700),
      );
      _ctrls.add(ctrl);
      _scales.add(Tween<double>(begin: 1.0, end: 2.4).animate(
        CurvedAnimation(parent: ctrl, curve: Curves.easeOut),
      ));
      _opacities.add(Tween<double>(begin: 0.55, end: 0.0).animate(
        CurvedAnimation(parent: ctrl, curve: Curves.easeOut),
      ));
    }
    if (widget.active) _startRings();
  }

  void _startRings() {
    for (int i = 0; i < _ringCount; i++) {
      Future.delayed(Duration(milliseconds: i * _ringDelay), () {
        if (mounted && widget.active) _ctrls[i].repeat();
      });
    }
  }

  void _stopRings() {
    for (final c in _ctrls) {
      c.stop();
      c.reset();
    }
  }

  @override
  void didUpdateWidget(_PulsingRings old) {
    super.didUpdateWidget(old);
    if (widget.active && !old.active) {
      _startRings();
    } else if (!widget.active && old.active) {
      _stopRings();
    }
  }

  @override
  void dispose() {
    for (final c in _ctrls) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: List.generate(_ringCount, (i) {
        return AnimatedBuilder(
          animation: _ctrls[i],
          builder: (_, __) => Transform.scale(
            scale: _scales[i].value,
            child: Container(
              width: 88,
              height: 88,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: Colors.green.withValues(alpha: _opacities[i].value),
                  width: 2.5,
                ),
              ),
            ),
          ),
        );
      }),
    );
  }
}

// ── Dashboard-Hilfswidget ──────────────────────────────────────────────────

class _DashboardRow extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;
  const _DashboardRow({
    required this.icon,
    required this.color,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            label,
            style: TextStyle(
                fontWeight: FontWeight.bold, color: color, fontSize: 14),
          ),
        ),
      ],
    );
  }
}

// ── Onboarding-Dialog (Schritt-für-Schritt-Einrichtung) ────────────────────

class _ParentalOnboardingDialog extends StatefulWidget {
  final ParentalLockService ps;
  const _ParentalOnboardingDialog({required this.ps});

  @override
  State<_ParentalOnboardingDialog> createState() =>
      _ParentalOnboardingDialogState();
}

class _ParentalOnboardingDialogState extends State<_ParentalOnboardingDialog>
    with WidgetsBindingObserver {
  // 0 = Willkommen, 1 = Wartet auf Berechtigung, 2 = Fertig
  int _step = 0;
  bool _permissionDenied = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _step == 1) {
      _checkPermissionAndActivate();
    }
  }

  Future<void> _checkPermissionAndActivate() async {
    await widget.ps.refreshAdminStatus();
    if (!mounted) return;
    if (widget.ps.hasOverlayPermission) {
      await widget.ps.startKioskMode();
      if (!mounted) return;
      setState(() { _step = 2; _permissionDenied = false; });
    } else {
      setState(() => _permissionDenied = true);
    }
  }

  Future<void> _openSettings() async {
    setState(() { _step = 1; _permissionDenied = false; });
    await widget.ps.requestOverlayPermission();
  }

  Future<void> _dismiss() async {
    await widget.ps.markOnboardingDone();
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        contentPadding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
        actionsPadding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
        content: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          child: _buildContent(),
        ),
        actions: [_buildActions()],
      ),
    );
  }

  Widget _buildContent() {
    if (_step == 0) {
      return Column(
        key: const ValueKey(0),
        mainAxisSize: MainAxisSize.min,
        children: const [
          Text('🎓', style: TextStyle(fontSize: 40)),
          SizedBox(height: 10),
          Text(
            'Kinderschutz einrichten',
            style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2E7D32)),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: 16),
          Text(
            'Wissensfreund benötigt einmalig die Berechtigung, über anderen Apps '
            'angezeigt zu werden — wie Messenger oder Chat-Bubbles.\n\n'
            'So erscheint ein Sperr-Bildschirm, wenn dein Kind die App verlässt.',
            style: TextStyle(fontSize: 15, height: 1.55),
            textAlign: TextAlign.center,
          ),
        ],
      );
    }
    if (_step == 1) {
      return Column(
        key: const ValueKey(1),
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_permissionDenied ? '⚠️' : '🔐',
              style: const TextStyle(fontSize: 40)),
          const SizedBox(height: 10),
          Text(
            _permissionDenied
                ? 'Berechtigung nicht erteilt'
                : 'Fast geschafft!',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: _permissionDenied
                  ? Colors.red.shade700
                  : const Color(0xFF2E7D32),
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            _permissionDenied
                ? 'Ohne diese Berechtigung kann kein Sperr-Bildschirm erscheinen. '
                  'Bitte erteile sie, um dein Kind zu schützen.'
                : 'Bitte aktiviere in den Einstellungen den Schalter für '
                  'Wissensfreund und kehre dann zurück.',
            style: const TextStyle(fontSize: 15, height: 1.55),
            textAlign: TextAlign.center,
          ),
        ],
      );
    }
    // _step == 2
    return const Column(
      key: ValueKey(2),
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('✅', style: TextStyle(fontSize: 40)),
        SizedBox(height: 10),
        Text(
          'Kinderschutz ist aktiv!',
          style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: Color(0xFF2E7D32)),
          textAlign: TextAlign.center,
        ),
        SizedBox(height: 16),
        Text(
          'Ab jetzt erscheint ein Sperr-Bildschirm, wenn dein Kind Wissensfreund '
          'verlässt. Du kannst ihn jederzeit mit Fingerabdruck oder PIN entsperren.',
          style: TextStyle(fontSize: 15, height: 1.55),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  Widget _buildActions() {
    final btnStyle = FilledButton.styleFrom(
      backgroundColor: const Color(0xFF2E7D32),
      padding: const EdgeInsets.symmetric(vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(50)),
    );

    if (_step == 0) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          FilledButton(
            style: btnStyle,
            onPressed: _openSettings,
            child: const Text('Jetzt einrichten — empfohlen',
                style: TextStyle(fontSize: 16)),
          ),
          const SizedBox(height: 10),
          TextButton(
            onPressed: _dismiss,
            child: Text('Später / Ohne Kinderschutz',
                style: TextStyle(color: Colors.grey.shade600)),
          ),
        ],
      );
    }
    if (_step == 1) {
      if (_permissionDenied) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            FilledButton(
              style: btnStyle,
              onPressed: _openSettings,
              child: const Text('Berechtigung erteilen',
                  style: TextStyle(fontSize: 16)),
            ),
            const SizedBox(height: 10),
            TextButton(
              onPressed: _dismiss,
              child: Text('Ohne Kinderschutz fortfahren',
                  style: TextStyle(color: Colors.grey.shade600)),
            ),
          ],
        );
      }
      return TextButton(
        onPressed: _dismiss,
        child:
            Text('Überspringen', style: TextStyle(color: Colors.grey.shade600)),
      );
    }
    // _step == 2
    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        style: btnStyle,
        onPressed: _dismiss,
        child: const Text('Alles klar!', style: TextStyle(fontSize: 16)),
      ),
    );
  }
}

// ── Image Quality Dialog ───────────────────────────────────────────────────────

class _ImageQualityDialog extends StatefulWidget {
  const _ImageQualityDialog();

  @override
  State<_ImageQualityDialog> createState() => _ImageQualityDialogState();
}

class _ImageQualityDialogState extends State<_ImageQualityDialog> {
  bool _downloading = false;
  double _progress = 0;
  Duration? _eta;
  String? _error;
  int _freeBytes = -1; // -1 = noch nicht geladen

  // peak = ZIP + extracted (both ~same size, ZIP_STORED)
  static int get _requiredBytes => SubscriptionService.instance.isPlus
      ? AssetConfig.imageLibrarySizeBytes * 2   // ~6.6 GB
      : AssetConfig.imageThumbLibrarySizeBytes * 2; // ~1.1 GB

  @override
  void initState() {
    super.initState();
    StorageManager.instance.getFreeStorageBytes().then((b) {
      if (mounted) setState(() => _freeBytes = b);
    });
  }

  bool get _hasEnoughSpace => _freeBytes < 0 || _freeBytes >= _requiredBytes;

  Future<void> _startDownload() async {
    setState(() { _downloading = true; _error = null; });
    final thumbTier = !SubscriptionService.instance.isPlus;
    final error = await ImageLibraryService.instance.downloadLibrary(
      thumbTier: thumbTier,
      onProgress: (received, total, eta) {
        if (mounted) setState(() {
          _progress = total > 0 ? received / total : 0;
          _eta = eta;
        });
      },
    );
    if (!mounted) return;
    if (error == null) {
      Navigator.pop(context);
    } else {
      setState(() {
        _downloading = false;
        _error = _downloadErrorMessage(error);
      });
    }
  }

  static String _downloadErrorMessage(String code) {
    if (code.startsWith('http_404')) {
      return 'Bildpaket noch nicht verfügbar — bitte in einigen Tagen erneut versuchen.';
    }
    if (code == 'no_network' || code == 'wifi_lost') {
      return 'Keine WLAN-Verbindung. Bitte WLAN prüfen.';
    }
    if (code == 'mobile_not_allowed') {
      return 'Mobile Daten nicht erlaubt. Bitte WLAN verwenden.';
    }
    if (code == 'limit_reached') {
      return 'Datenlimit erreicht. Bitte Internet-Einstellungen prüfen.';
    }
    return 'Download fehlgeschlagen ($code). Bitte WLAN prüfen.';
  }

  String _fmtEta(Duration d) =>
      d.inMinutes >= 1 ? '~${d.inMinutes} min' : '~${d.inSeconds}s';

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_downloading,
      child: AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: const Row(children: [
          Text('🖼️', style: TextStyle(fontSize: 22)),
          SizedBox(width: 8),
          Text('Bildqualität wählen'),
        ]),
        content: _downloading
            ? Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  LinearProgressIndicator(
                    value: _progress > 0 ? _progress : null,
                    backgroundColor: const Color(0xFFE8F5E9),
                    valueColor: const AlwaysStoppedAnimation(Color(0xFF2E7D32)),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    _progress > 0
                        ? '${(_progress * 100).round()} %'
                            '${_eta != null ? "  —  ${_fmtEta(_eta!)}" : ""}'
                        : 'Verbinde…',
                    style: const TextStyle(fontSize: 13),
                  ),
                ],
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _QualityRow(
                    icon: Icons.image_outlined,
                    title: 'Variabel (aus Wissensspeicher)',
                    subtitle: 'Kein Download — Qualität je nach Artikel',
                    highlight: !_hasEnoughSpace,
                  ),
                  const SizedBox(height: 12),
                  Builder(builder: (ctx) {
                    final isPlus = SubscriptionService.instance.isPlus;
                    return _QualityRow(
                      icon: Icons.hd_outlined,
                      title: isPlus
                          ? 'Gut  (~${AssetConfig.imageLibrarySizeLabel} · 800px)'
                          : 'Einheitlich 300px  (~${AssetConfig.imageThumbLibrarySizeLabel})',
                      subtitle: 'Offline-Bilderbibliothek · ca. 1–3 min im WLAN',
                      highlight: _hasEnoughSpace,
                    );
                  }),
                  if (_freeBytes >= 0 && !_hasEnoughSpace) ...[
                    const SizedBox(height: 10),
                    Row(children: [
                      Icon(Icons.warning_amber_rounded,
                          size: 15, color: Colors.orange.shade700),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          'Wenig Speicherplatz (${(_freeBytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB frei). '
                          'Download nicht empfohlen.',
                          style: TextStyle(
                              fontSize: 12, color: Colors.orange.shade800),
                        ),
                      ),
                    ]),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 10),
                    Text(
                      _error!,
                      style: TextStyle(color: Colors.red.shade700, fontSize: 13),
                    ),
                  ],
                ],
              ),
        actions: _downloading
            ? null
            : [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: Text('Standard',
                      style: TextStyle(color: Colors.grey.shade600)),
                ),
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32)),
                  onPressed: _hasEnoughSpace ? _startDownload : null,
                  child: Text(SubscriptionService.instance.isPlus ? 'Herunterladen (800px)' : 'Herunterladen (300px)'),
                ),
              ],
      ),
    );
  }
}

class _QualityRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool highlight;
  const _QualityRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: highlight
            ? const Color(0xFFE8F5E9)
            : const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(12),
        border: highlight
            ? Border.all(color: const Color(0xFF2E7D32), width: 1.5)
            : null,
      ),
      child: Row(
        children: [
          Icon(icon,
              color: highlight ? const Color(0xFF2E7D32) : Colors.grey.shade600,
              size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: highlight
                          ? const Color(0xFF1B5E20)
                          : const Color(0xFF333333),
                    )),
                Text(subtitle,
                    style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey.shade600,
                        height: 1.3)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Storage Screen ─────────────────────────────────────────────────────────────

class _StorageScreen extends StatefulWidget {
  const _StorageScreen();

  @override
  State<_StorageScreen> createState() => _StorageScreenState();
}

class _StorageScreenState extends State<_StorageScreen> {
  int _libraryBytes = 0;
  int _libraryCount = 0; // Anzahl offline gespeicherter Bilder
  int _freeBytes = 0; // freier Gerätespeicher (0 = unbekannt)
  bool? _libraryIsThumb; // true=300px, false=800px, null=unbekannt
  bool _hiresOnWifi = true;
  bool _loadingLibrary = false;
  bool _loadingStats = true;

  // Download state
  bool _downloading = false;
  bool _bgDownloading = false; // ongoing background download from onboarding
  double _dlProgress = 0;   // 0..1 = download; >1 = extraction phase
  Duration? _dlEta;
  String? _dlError;
  bool? _downloadingThumbTier; // tier being downloaded: true=300px, false=600px
  bool _downloadComplete = false;

  @override
  void initState() {
    super.initState();
    _loadStats();
  }

  Future<void> _loadStats({bool silent = false}) async {
    if (!mounted) return;
    if (!silent) setState(() => _loadingStats = true);
    try {
      await StorageManager.instance.initialize();
      final bgDl = ImageLibraryService.instance.isDownloading && !_downloading;
      if (!mounted) return;
      final tier     = await ImageLibraryService.getStoredTier();
      final hiresWifi = await ImageLibraryService.hiresOnWifiEnabled();
      final freeBytes = await StorageManager.instance.getFreeStorageBytes();
      if (!mounted) return;
      setState(() {
        _libraryBytes   = ImageLibraryService.instance.totalSizeBytes;
        _libraryCount   = ImageLibraryService.instance.totalImageCount;
        _freeBytes      = freeBytes;
        _libraryIsThumb = tier;
        _hiresOnWifi    = hiresWifi;
        _bgDownloading  = bgDl;
        if (bgDl) {
          _dlProgress = ImageLibraryService.instance.downloadProgress;
          _dlEta = ImageLibraryService.instance.downloadEta;
          _downloadingThumbTier = !SubscriptionService.instance.isPlus;
        }
      });
      if (bgDl) {
        Future.delayed(const Duration(seconds: 3), () {
          if (mounted && _bgDownloading) _loadStats(silent: true);
        });
      }
    } catch (_) {
    } finally {
      if (!silent && mounted) setState(() => _loadingStats = false);
    }
  }

  Future<void> _clearLibrary() async {
    setState(() => _loadingLibrary = true);
    await ImageLibraryService.instance.clear();
    if (!mounted) return;
    setState(() {
      _libraryBytes = 0;
      _loadingLibrary = false;
    });
  }

  Future<void> _downloadLibrary() async {
    final thumbTier = !SubscriptionService.instance.isPlus;
    setState(() {
      _downloading = true;
      _bgDownloading = false;
      _dlError = null;
      _dlProgress = 0;
      _downloadingThumbTier = thumbTier;
    });
    final error = await ImageLibraryService.instance.downloadLibrary(
      thumbTier: thumbTier,
      onProgress: (received, total, eta) {
        if (mounted) {
          setState(() {
            _dlProgress = total > 0 ? received / total : 0;
            _dlEta = eta;
          });
        }
      },
    );
    if (!mounted) return;
    if (error == null) {
      setState(() {
        _downloading = false;
        _dlProgress = 0;
        _libraryBytes = ImageLibraryService.instance.totalSizeBytes;
        _libraryCount = ImageLibraryService.instance.totalImageCount;
        _downloadComplete = true;
      });
      // Freien Speicher neu lesen, damit die Übersicht nach dem Download stimmt.
      final freeBytes = await StorageManager.instance.getFreeStorageBytes();
      if (mounted && freeBytes > 0) setState(() => _freeBytes = freeBytes);
    } else if (error == 'cancelled') {
      setState(() { _downloading = false; _dlProgress = 0; _downloadComplete = false; });
    } else {
      setState(() {
        _downloading = false;
        _dlError = _mapDlError(error);
      });
    }
  }

  String _mapDlError(String code) {
    if (code.startsWith('http_404')) return 'Bildpaket noch nicht verfügbar.';
    if (code == 'no_network' || code == 'wifi_lost') return 'Keine WLAN-Verbindung.';
    if (code == 'limit_reached') return 'Datenlimit erreicht.';
    return 'Download fehlgeschlagen ($code).';
  }

  String _fmtSize(int bytes) {
    if (bytes <= 0) return '0 MB';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).round()} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).round()} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  String _fmtEta(Duration d) =>
      d.inMinutes >= 1 ? '~${d.inMinutes} min' : '~${d.inSeconds}s';

  /// Zahl mit deutschem Tausenderpunkt: 15234 → „15.234".
  String _fmtCount(int n) => n.toString().replaceAllMapped(
      RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]}.');

  /// Kompakte Speicher-Übersicht: was liegt offline auf dem Gerät und wie viel
  /// Platz ist noch frei. Warnt farblich, wenn es eng wird. Handy + Tablet gleich.
  Widget _buildStorageOverview() {
    final hasLib = _libraryBytes > 0;
    final knowFree = _freeBytes > 0;
    // „Knapp" ab < 1,5 GB frei — dann reicht ein 800px-Upgrade (~3,3 GB) nicht
    // mehr, und auch das kleine Paket wird eng.
    const lowThreshold = 1500 * 1024 * 1024;
    final low = knowFree && _freeBytes < lowThreshold;

    Widget row(String label, String value, {Color? valueColor}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style: const TextStyle(fontSize: 14, color: Color(0xFF555555))),
              Text(value,
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: valueColor ?? const Color(0xFF2E7D32))),
            ],
          ),
        );

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF6FAF6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8F5E9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.sd_storage_rounded, color: Color(0xFF2E7D32), size: 18),
            SizedBox(width: 6),
            Text('Speicherplatz',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF1B5E20))),
          ]),
          const SizedBox(height: 8),
          row(
            'Bilder offline',
            hasLib
                ? '${_fmtCount(_libraryCount)} Bilder · ${_fmtSize(_libraryBytes)}'
                : 'Noch keine',
          ),
          if (knowFree)
            row('Frei auf dem Gerät', _fmtSize(_freeBytes),
                valueColor: low ? const Color(0xFFC62828) : const Color(0xFF2E7D32)),
          if (low) ...[
            const SizedBox(height: 8),
            Text(
              'Der Speicher wird knapp. Für das große Bildpaket '
              '(~${AssetConfig.imageLibrarySizeLabel}) könnte der Platz nicht reichen.',
              style: const TextStyle(fontSize: 12, color: Color(0xFFC62828)),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildUpgradeTeaser(BuildContext ctx) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F7F2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFA5D6A7)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.star_rounded, color: Color(0xFF2E7D32), size: 18),
            SizedBox(width: 6),
            Text('Mit Plus: Bilder in guter Qualität',
                style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    color: Color(0xFF1B5E20))),
          ]),
          const SizedBox(height: 6),
          Text(
            '800px statt 300px offline (~${AssetConfig.imageLibrarySizeLabel}) '
            'und automatisch beste Qualität bei WLAN.',
            style: const TextStyle(fontSize: 12, color: Color(0xFF555555)),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF2E7D32)),
              onPressed: () => Navigator.of(ctx).push(
                MaterialPageRoute(
                  fullscreenDialog: true,
                  builder: (_) => const _SubscriptionScreen(),
                ),
              ),
              child: const Text('Zu Plus upgraden'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProgressBar() {
    if (_downloadComplete) {
      final tierLabel = _downloadingThumbTier == true ? '300px' : '600px';
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFE8F5E9),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            const Icon(Icons.check_circle_rounded, color: Color(0xFF2E7D32), size: 24),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Fertig — $tierLabel-Bilder sind jetzt verfügbar.',
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Color(0xFF2E7D32)),
              ),
            ),
          ],
        ),
      );
    }

    final extracting = _dlProgress > 1.0;
    final tierLabel = _downloadingThumbTier == true
        ? '300px (Free-Qualität)'
        : _downloadingThumbTier == false
            ? '800px (Plus-Qualität)'
            : 'Bilder';
    final extractPct = extracting ? ((_dlProgress - 1.0) * 100).round() : 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          extracting ? 'Bilder werden entpackt…' : '$tierLabel wird heruntergeladen…',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Color(0xFF2E7D32)),
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: extracting ? (_dlProgress - 1.0) : (_dlProgress > 0 ? _dlProgress : null),
          minHeight: 8,
          borderRadius: BorderRadius.circular(4),
          backgroundColor: const Color(0xFFE8F5E9),
          valueColor: const AlwaysStoppedAnimation(Color(0xFF2E7D32)),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: Text(
                extracting
                    ? '$extractPct % entpackt'
                    : _dlProgress > 0
                        ? '${(_dlProgress * 100).round()} %${_dlEta != null ? "  —  noch ${_fmtEta(_dlEta!)}" : ""}'
                        : 'Verbindung wird aufgebaut…',
                style: const TextStyle(fontSize: 14, color: Color(0xFF555555)),
              ),
            ),
            if (!extracting)
              TextButton(
                onPressed: () {
                  ImageLibraryService.instance.cancel();
                  setState(() { _downloading = false; _bgDownloading = false; _dlProgress = 0; });
                },
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  foregroundColor: Colors.red.shade600,
                  textStyle: const TextStyle(fontSize: 12),
                ),
                child: const Text('Abbrechen'),
              ),
          ],
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isPlus = SubscriptionService.instance.isPlus;
    final hasLib = _libraryBytes > 0;
    final isDl   = _downloading || _bgDownloading;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('Speicher & Qualität'),
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF2E7D32),
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(height: 1, color: Colors.grey.shade200),
        ),
      ),
      body: _loadingStats
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF4CAF50)))
          : TabletMaxWidth(child: SafeArea(
              top: false,
              minimum: const EdgeInsets.only(bottom: 8),
              child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildStorageOverview(),
                  const SizedBox(height: 20),
                  // ── Bildqualität-Status ──────────────────────────────
                  if (!isPlus && !hasLib) ...[
                    _InfoRow(
                      label: 'Bildqualität',
                      value: isDl ? 'Wird heruntergeladen…' : 'Noch nicht gespeichert',
                    ),
                    const SizedBox(height: 4),
                    if (!isDl)
                      Text(
                        'Lokal speichern für einheitlich 300px (~${AssetConfig.imageThumbLibrarySizeLabel})',
                        style: const TextStyle(fontSize: 12, color: Color(0xFF888888)),
                      ),
                    const SizedBox(height: 12),
                    if (isDl)
                      _buildProgressBar()
                    else ...[
                      if (_dlError != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Text(_dlError!,
                              style: TextStyle(fontSize: 12, color: Colors.red.shade700)),
                        ),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          icon: const Icon(Icons.download_rounded, size: 18),
                          label: Text('Bilder herunterladen (300px, ~${AssetConfig.imageThumbLibrarySizeLabel})'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFF2E7D32),
                            side: const BorderSide(color: Color(0xFF2E7D32)),
                            textStyle: const TextStyle(fontSize: 13),
                          ),
                          onPressed: _downloadLibrary,
                        ),
                      ),
                      const SizedBox(height: 16),
                      _buildUpgradeTeaser(context),
                    ],
                  ] else if (!isPlus && hasLib) ...[
                    _InfoRow(
                      label: 'Offline-Bilder',
                      value: '300px (Free) — ${_fmtSize(_libraryBytes)}',
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: _loadingLibrary
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.delete_outline_rounded, size: 18),
                        label: const Text('Offline-Bilder löschen'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.red.shade700,
                          side: BorderSide(color: Colors.red.shade300),
                          textStyle: const TextStyle(fontSize: 13),
                        ),
                        onPressed: _loadingLibrary ? null : _clearLibrary,
                      ),
                    ),
                    const SizedBox(height: 16),
                    _buildUpgradeTeaser(context),
                  ] else if (!hasLib) ...[
                    _InfoRow(
                      label: 'Offline-Bibliothek',
                      value: isDl ? 'Wird heruntergeladen…' : 'Nicht heruntergeladen',
                    ),
                    const SizedBox(height: 4),
                    if (!isDl)
                      Text(
                        'Lade alle Bilder für schnelle Offline-Anzeige (~${AssetConfig.imageLibrarySizeLabel})',
                        style: const TextStyle(fontSize: 12, color: Color(0xFF888888)),
                      ),
                    const SizedBox(height: 12),
                    if (isDl)
                      _buildProgressBar()
                    else ...[
                      if (_dlError != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Text(_dlError!,
                              style: TextStyle(fontSize: 12, color: Colors.red.shade700)),
                        ),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          icon: const Icon(Icons.download_rounded, size: 18),
                          label: Text('Bilder herunterladen (800px, ~${AssetConfig.imageLibrarySizeLabel})'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFF2E7D32),
                            side: const BorderSide(color: Color(0xFF2E7D32)),
                            textStyle: const TextStyle(fontSize: 13),
                          ),
                          onPressed: _downloadLibrary,
                        ),
                      ),
                    ],
                  ] else ...[
                    _InfoRow(
                      label: 'Offline-Bilder',
                      value: '${_libraryIsThumb == true ? "300px (Free)" : _libraryIsThumb == false ? "800px (Plus)" : "Unbekannte Qualität"} — ${_fmtSize(_libraryBytes)}',
                    ),
                    if (_libraryIsThumb != false) ...[
                      const SizedBox(height: 4),
                      Text(
                        'Mit Plus kannst du auf 800px upgraden (~${AssetConfig.imageLibrarySizeLabel})',
                        style: const TextStyle(fontSize: 12, color: Color(0xFF888888)),
                      ),
                      const SizedBox(height: 12),
                      if (isDl)
                        _buildProgressBar()
                      else ...[
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            icon: const Icon(Icons.upgrade_rounded, size: 18),
                            label: Text('Auf 800px upgraden (~${AssetConfig.imageLibrarySizeLabel})'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: const Color(0xFF2E7D32),
                              side: const BorderSide(color: Color(0xFF2E7D32)),
                              textStyle: const TextStyle(fontSize: 13),
                            ),
                            onPressed: _downloadLibrary,
                          ),
                        ),
                        const SizedBox(height: 8),
                      ],
                    ] else
                      const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: _loadingLibrary
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.delete_outline_rounded, size: 18),
                        label: const Text('Offline-Bilder löschen'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.red.shade700,
                          side: BorderSide(color: Colors.red.shade300),
                          textStyle: const TextStyle(fontSize: 13),
                        ),
                        onPressed: _loadingLibrary ? null : _clearLibrary,
                      ),
                    ),
                    const SizedBox(height: 20),
                    _buildWifiSwitch(),
                  ],
                ],
              ),
            ),
            )),
    );
  }

  Widget _buildWifiSwitch() {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: SwitchListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        title: const Text(
          'Bei WLAN automatisch höchste Qualität laden',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
        ),
        subtitle: const Text(
          'Hochaufgelöste Bilder direkt von Wikipedia',
          style: TextStyle(fontSize: 12, color: Color(0xFF666666), height: 1.4),
        ),
        value: _hiresOnWifi,
        activeColor: const Color(0xFF2E7D32),
        onChanged: (val) async {
          setState(() => _hiresOnWifi = val);
          await ImageLibraryService.setHiresOnWifi(val);
        },
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 13, color: Color(0xFF555555))),
        Flexible(
          child: Text(
            value,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            textAlign: TextAlign.end,
          ),
        ),
      ],
    );
  }
}

// ── Network Settings Onboarding Dialog ────────────────────────────────────────

class _NetworkSettingsOnboardingDialog extends StatefulWidget {
  const _NetworkSettingsOnboardingDialog();

  @override
  State<_NetworkSettingsOnboardingDialog> createState() =>
      _NetworkSettingsOnboardingDialogState();
}

class _NetworkSettingsOnboardingDialogState
    extends State<_NetworkSettingsOnboardingDialog> {
  final _settings = NetworkSettingsService.instance;

  bool _wifiUnlimited  = true;
  int  _wifiDailyMb    = 0;
  int  _wifiMonthlyMb  = 0;
  bool _mobileAllowed  = false;
  int  _mobileDailyMb  = 100;
  int  _mobileMonthlyMb = 500;
  bool _loading = true;
  bool _saving  = false;

  static const _wifiDailyOptions    = [0, 250, 500, 1024, 2048];
  static const _wifiMonthlyOptions  = [0, 1024, 5120, 10240, 51200];
  static const _mobileDailyOptions  = [25, 50, 100, 250, 500];
  static const _mobileMonthlyOptions = [100, 250, 500, 1024, 5120];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    _wifiUnlimited   = await _settings.wifiUnlimited;
    _wifiDailyMb     = await _settings.wifiDailyLimitMb;
    _wifiMonthlyMb   = await _settings.wifiMonthlyLimitMb;
    _mobileAllowed   = await _settings.mobileAllowed;
    _mobileDailyMb   = await _settings.mobileDailyLimitMb;
    _mobileMonthlyMb = await _settings.mobileMonthlyLimitMb;
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    await _settings.setWifiUnlimited(_wifiUnlimited);
    await _settings.setWifiDailyLimitMb(_wifiDailyMb);
    await _settings.setWifiMonthlyLimitMb(_wifiMonthlyMb);
    await _settings.setMobileAllowed(_mobileAllowed);
    await _settings.setMobileDailyLimitMb(_mobileDailyMb);
    await _settings.setMobileMonthlyLimitMb(_mobileMonthlyMb);
    if (mounted) Navigator.pop(context);
  }

  String _mbLabel(int mb) {
    if (mb == 0) return 'Unbegrenzt';
    if (mb >= 1024) return '${(mb / 1024).round()} GB';
    return '$mb MB';
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      title: const Row(children: [
        Icon(Icons.wifi_rounded, color: Color(0xFF2E7D32), size: 22),
        SizedBox(width: 8),
        Text('Internet-Einstellungen'),
      ]),
      content: _loading
          ? const SizedBox(
              height: 60, child: Center(child: CircularProgressIndicator()))
          : SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Lege fest, wann und wie viele Daten Wissensfreund '
                    'herunterladen darf.',
                    style: TextStyle(fontSize: 13, height: 1.45),
                  ),
                  const SizedBox(height: 20),

                  // ── WiFi ─────────────────────────────────────────────
                  _SectionHeader('WLAN'),
                  SwitchListTile(
                    value: _wifiUnlimited,
                    onChanged: (v) => setState(() => _wifiUnlimited = v),
                    title: const Text('Unbegrenzt',
                        style: TextStyle(fontSize: 14)),
                    subtitle: const Text('Kein Datenlimit im WLAN',
                        style: TextStyle(fontSize: 12)),
                    dense: true,
                    activeColor: const Color(0xFF2E7D32),
                  ),
                  if (!_wifiUnlimited) ...[
                    _LimitDropdown(
                      label: 'Tageslimit',
                      value: _wifiDailyMb,
                      options: _wifiDailyOptions,
                      fmt: _mbLabel,
                      onChanged: (v) => setState(() => _wifiDailyMb = v),
                    ),
                    _LimitDropdown(
                      label: 'Monatslimit',
                      value: _wifiMonthlyMb,
                      options: _wifiMonthlyOptions,
                      fmt: _mbLabel,
                      onChanged: (v) => setState(() => _wifiMonthlyMb = v),
                    ),
                  ],
                  const SizedBox(height: 12),

                  // ── Mobile ───────────────────────────────────────────
                  _SectionHeader('Mobilfunk'),
                  SwitchListTile(
                    value: _mobileAllowed,
                    onChanged: (v) => setState(() => _mobileAllowed = v),
                    title: const Text('Downloads erlaubt',
                        style: TextStyle(fontSize: 14)),
                    subtitle: const Text('Standardmäßig deaktiviert',
                        style: TextStyle(fontSize: 12)),
                    dense: true,
                    activeColor: const Color(0xFF2E7D32),
                  ),
                  if (_mobileAllowed) ...[
                    _LimitDropdown(
                      label: 'Tageslimit',
                      value: _mobileDailyMb,
                      options: _mobileDailyOptions,
                      fmt: _mbLabel,
                      onChanged: (v) => setState(() => _mobileDailyMb = v),
                    ),
                    _LimitDropdown(
                      label: 'Monatslimit',
                      value: _mobileMonthlyMb,
                      options: _mobileMonthlyOptions,
                      fmt: _mbLabel,
                      onChanged: (v) => setState(() => _mobileMonthlyMb = v),
                    ),
                  ],
                ],
              ),
            ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Überspringen'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
          onPressed: _saving || _loading ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 16, height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : const Text('Speichern'),
        ),
      ],
    );
  }
}

// ── Internet & Daten Settings Dialog (from menu) ───────────────────────────────

// ── Parental Screen ────────────────────────────────────────────────────────────

class _ParentalScreen extends StatelessWidget {
  const _ParentalScreen();

  static AppBar _appBar(BuildContext context) => AppBar(
        title: const Text('Kinderschutz'),
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF2E7D32),
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(height: 1, color: Colors.grey.shade200),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: _appBar(context),
      body: Consumer<ParentalLockService>(
        builder: (ctx, ps, _) => SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _DashboardRow(
                icon: ps.hasOverlayPermission
                    ? Icons.layers_rounded
                    : Icons.layers_clear_rounded,
                color: ps.hasOverlayPermission
                    ? const Color(0xFF2E7D32)
                    : Colors.red.shade700,
                label: ps.hasOverlayPermission
                    ? 'Overlay-Berechtigung erteilt'
                    : 'Overlay-Berechtigung fehlt',
              ),
              const SizedBox(height: 6),
              Text(
                ps.hasOverlayPermission
                    ? 'Wissensfreund kann ein Sperr-Bildschirm über anderen Apps anzeigen.'
                    : 'Ohne diese Berechtigung kann kein Overlay erscheinen. Bitte unten einrichten.',
                style: const TextStyle(fontSize: 13, height: 1.45),
              ),
              const SizedBox(height: 20),
              _DashboardRow(
                icon: ps.isKioskMode
                    ? Icons.lock_outline_rounded
                    : Icons.lock_open_rounded,
                color: ps.isKioskMode
                    ? const Color(0xFF2E7D32)
                    : Colors.orange.shade700,
                label: ps.isKioskMode ? 'Kindermodus aktiv' : 'Kindermodus inaktiv',
              ),
              const SizedBox(height: 6),
              Text(
                ps.isKioskMode
                    ? 'Home- und Recents-Taste führen direkt zum Eltern-Bildschirm.'
                    : 'Wenn aktiviert, kehrt das Gerät bei Home- oder Recents-Taste sofort zurück.',
                style: const TextStyle(fontSize: 13, height: 1.45),
              ),
              const SizedBox(height: 20),
              _DashboardRow(
                icon: ps.isAdminActive
                    ? Icons.verified_rounded
                    : Icons.info_outline_rounded,
                color: ps.isAdminActive
                    ? const Color(0xFF2E7D32)
                    : Colors.orange.shade700,
                label: ps.isAdminActive
                    ? 'Gerätesperre beim Beenden'
                    : 'Eltern-Bildschirm (Fallback)',
              ),
              const SizedBox(height: 6),
              Text(
                ps.isAdminActive
                    ? 'Beim Verlassen der App sperrt sich das Gerät.'
                    : 'Beim Zurückkehren zur App erscheint der Eltern-Bildschirm.',
                style: const TextStyle(fontSize: 13, height: 1.45),
              ),
              const SizedBox(height: 28),
              if (!ps.hasOverlayPermission) ...[
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
                    onPressed: () async {
                      await ps.requestOverlayPermission();
                      await ps.refreshAdminStatus();
                    },
                    child: const Text('Overlay-Berechtigung einrichten'),
                  ),
                ),
                const SizedBox(height: 8),
              ],
              if (!ps.isAdminActive) ...[
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () async {
                      await ps.requestDeviceAdmin();
                      await ps.refreshAdminStatus();
                    },
                    child: const Text('Gerätesperre aktivieren'),
                  ),
                ),
                const SizedBox(height: 8),
              ],
              SizedBox(
                width: double.infinity,
                child: ps.isKioskMode
                    ? FilledButton(
                        style: FilledButton.styleFrom(
                            backgroundColor: Colors.grey.shade600),
                        onPressed: () async {
                          final ok = await ps.authenticate(
                            'Kindersicherung deaktivieren — bitte authentifizieren.',
                          );
                          if (ok) await ps.stopKioskMode();
                        },
                        child: const Text('Kindersicherung deaktivieren'),
                      )
                    : FilledButton(
                        style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF2E7D32)),
                        onPressed: () async => ps.startKioskMode(),
                        child: const Text('Kindermodus aktivieren'),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Internet & Daten Screen ────────────────────────────────────────────────────

class _InternetDataScreen extends StatefulWidget {
  const _InternetDataScreen();

  @override
  State<_InternetDataScreen> createState() => _InternetDataScreenState();
}

class _InternetDataScreenState extends State<_InternetDataScreen> {
  final _settings = NetworkSettingsService.instance;

  bool _wifiUnlimited   = true;
  int  _wifiDailyMb     = 0;
  int  _wifiMonthlyMb   = 0;
  bool _mobileAllowed   = false;
  int  _mobileDailyMb   = 100;
  int  _mobileMonthlyMb = 500;
  bool _loading = true;
  bool _saving  = false;

  int _wifiDailyUsed    = 0;
  int _wifiMonthlyUsed  = 0;
  int _mobileDailyUsed  = 0;
  int _mobileMonthlyUsed = 0;

  static const _wifiDailyOptions    = [0, 250, 500, 1024, 2048];
  static const _wifiMonthlyOptions  = [0, 1024, 5120, 10240, 51200];
  static const _mobileDailyOptions  = [25, 50, 100, 250, 500];
  static const _mobileMonthlyOptions = [100, 250, 500, 1024, 5120];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    _wifiUnlimited    = await _settings.wifiUnlimited;
    _wifiDailyMb      = await _settings.wifiDailyLimitMb;
    _wifiMonthlyMb    = await _settings.wifiMonthlyLimitMb;
    _mobileAllowed    = await _settings.mobileAllowed;
    _mobileDailyMb    = await _settings.mobileDailyLimitMb;
    _mobileMonthlyMb  = await _settings.mobileMonthlyLimitMb;

    final today       = DateTime.now().toIso8601String().substring(0, 10);
    final monthPrefix = DateTime.now().toIso8601String().substring(0, 7);
    final db          = LicenseCacheDb.instance;
    _wifiDailyUsed    = await db.getDailyUsage(today, 'wifi');
    _wifiMonthlyUsed  = await db.getMonthlyUsage(monthPrefix, 'wifi');
    _mobileDailyUsed  = await db.getDailyUsage(today, 'mobile');
    _mobileMonthlyUsed = await db.getMonthlyUsage(monthPrefix, 'mobile');

    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    await _settings.setWifiUnlimited(_wifiUnlimited);
    await _settings.setWifiDailyLimitMb(_wifiDailyMb);
    await _settings.setWifiMonthlyLimitMb(_wifiMonthlyMb);
    await _settings.setMobileAllowed(_mobileAllowed);
    await _settings.setMobileDailyLimitMb(_mobileDailyMb);
    await _settings.setMobileMonthlyLimitMb(_mobileMonthlyMb);
    if (mounted) Navigator.pop(context);
  }

  String _mbLabel(int mb) {
    if (mb == 0) return 'Unbegrenzt';
    if (mb >= 1024) return '${(mb / 1024).round()} GB';
    return '$mb MB';
  }

  String _bytesLabel(int bytes) {
    if (bytes <= 0) return '0 MB';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).round()} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).round()} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  // Einheitliche Typografie für diesen Screen (behebt die Größen-Mischung).
  static const _label = TextStyle(fontSize: 15, color: Color(0xFF333333));
  static const _value = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w700, color: Color(0xFF2E7D32));
  static const _hint =
      TextStyle(fontSize: 13, height: 1.4, color: Color(0xFF888888));
  static const _cardTitle = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w800, color: Color(0xFF2E7D32));

  /// Abgesetzte Karte mit Icon-Titel — trennt WLAN / Mobilfunk / Wissensspeicher klar.
  Widget _card({
    required IconData icon,
    required String title,
    required List<Widget> children,
  }) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE8F5E9), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, size: 20, color: const Color(0xFF2E7D32)),
            const SizedBox(width: 8),
            Text(title, style: _cardTitle),
          ]),
          const SizedBox(height: 6),
          ...children,
        ],
      ),
    );
  }

  /// Schalter-Zeile mit Erklärung darunter (einheitlich für beide Schalter).
  Widget _switchRow({
    required String label,
    required String hint,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(label, style: _label)),
            Switch(
              value: value,
              onChanged: onChanged,
              activeColor: const Color(0xFF2E7D32),
            ),
          ],
        ),
        Text(hint, style: _hint),
      ],
    );
  }

  /// "klexikon_de_all_maxi_2026-05" → "Mai 2026" — ohne interne Kennung/URL.
  String _friendlyZimVersion(String? raw) {
    if (raw == null || raw.isEmpty) return '—';
    final m = RegExp(r'(\d{4})-(\d{2})').firstMatch(raw);
    if (m == null) return raw;
    const months = [
      '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
      'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
    ];
    final mon = int.tryParse(m.group(2)!) ?? 0;
    if (mon < 1 || mon > 12) return raw;
    return '${months[mon]} ${m.group(1)}';
  }

  /// Tablet: Formular auf angenehme Breite begrenzen und zentrieren.
  /// Handy (isTablet == false): unverändert der bestehende Baum.
  Widget _tabletConstrain(Widget child) => context.isTablet
      ? Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: child,
          ),
        )
      : child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        title: const Text('Internet & Daten'),
        backgroundColor: const Color(0xFFFFF8EE),
        foregroundColor: const Color(0xFF2E7D32),
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(height: 1, color: Colors.grey.shade200),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF4CAF50)))
          : _tabletConstrain(Column(
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Kurz-Erklärung ganz oben
                        Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: Text(
                            'Für manche Artikel lädt die App Bilder aus dem '
                            'Internet. Hier legst du fest, wie viel Datenvolumen '
                            'sie dafür verwenden darf. Alle Artikeltexte und '
                            'die Vorschaubilder sind bereits offline gespeichert '
                            'und zählen nie mit.',
                            style: _hint,
                          ),
                        ),

                        // ── WLAN ─────────────────────────────────────────────
                        _card(
                          icon: Icons.wifi_rounded,
                          title: 'WLAN',
                          children: [
                            _switchRow(
                              label: 'Unbegrenzt',
                              hint: _wifiUnlimited
                                  ? 'Bilder laden im WLAN ohne Begrenzung. '
                                      'Empfohlen, wenn dein WLAN kein Datenlimit hat.'
                                  : 'Es gilt ein WLAN-Budget. Ist es erreicht, '
                                      'werden weitere Bilderdownloads pausiert. '
                                      'Texte und bereits heruntergeladene Bilder '
                                      'sind weiterhin offline verfügbar.',
                              value: _wifiUnlimited,
                              onChanged: (v) =>
                                  setState(() => _wifiUnlimited = v),
                            ),
                            if (!_wifiUnlimited) ...[
                              const _CardDivider(),
                              _LimitDropdown(
                                label: 'Tageslimit',
                                value: _wifiDailyMb,
                                options: _wifiDailyOptions,
                                fmt: _mbLabel,
                                onChanged: (v) =>
                                    setState(() => _wifiDailyMb = v),
                              ),
                              _LimitDropdown(
                                label: 'Monatslimit',
                                value: _wifiMonthlyMb,
                                options: _wifiMonthlyOptions,
                                fmt: _mbLabel,
                                onChanged: (v) =>
                                    setState(() => _wifiMonthlyMb = v),
                              ),
                            ],
                            const _CardDivider(),
                            _UsageProgressRow(
                              label: 'Heute',
                              used: _bytesLabel(_wifiDailyUsed),
                              limit: _wifiUnlimited || _wifiDailyMb == 0
                                  ? null
                                  : _mbLabel(_wifiDailyMb),
                              pct: _wifiDailyMb == 0
                                  ? 0
                                  : (_wifiDailyUsed /
                                          (_wifiDailyMb * 1024 * 1024))
                                      .clamp(0.0, 1.0),
                            ),
                            _UsageProgressRow(
                              label: 'Dieser Monat',
                              used: _bytesLabel(_wifiMonthlyUsed),
                              limit: _wifiUnlimited || _wifiMonthlyMb == 0
                                  ? null
                                  : _mbLabel(_wifiMonthlyMb),
                              pct: _wifiMonthlyMb == 0
                                  ? 0
                                  : (_wifiMonthlyUsed /
                                          (_wifiMonthlyMb * 1024 * 1024))
                                      .clamp(0.0, 1.0),
                            ),
                          ],
                        ),

                        // ── Mobilfunk ────────────────────────────────────────
                        _card(
                          icon: Icons.signal_cellular_alt_rounded,
                          title: 'Mobilfunk',
                          children: [
                            _switchRow(
                              label: 'Downloads erlaubt',
                              hint: _mobileAllowed
                                  ? 'Bilder dürfen auch übers Mobilnetz laden – '
                                      'im Rahmen der Limits unten.'
                                  : 'Unterwegs werden keine neuen Bilder geladen. '
                                      'Das schont dein Datenvolumen.',
                              value: _mobileAllowed,
                              onChanged: (v) =>
                                  setState(() => _mobileAllowed = v),
                            ),
                            if (_mobileAllowed) ...[
                              const _CardDivider(),
                              _LimitDropdown(
                                label: 'Tageslimit',
                                value: _mobileDailyMb,
                                options: _mobileDailyOptions,
                                fmt: _mbLabel,
                                onChanged: (v) =>
                                    setState(() => _mobileDailyMb = v),
                              ),
                              _LimitDropdown(
                                label: 'Monatslimit',
                                value: _mobileMonthlyMb,
                                options: _mobileMonthlyOptions,
                                fmt: _mbLabel,
                                onChanged: (v) =>
                                    setState(() => _mobileMonthlyMb = v),
                              ),
                              const _CardDivider(),
                              _UsageProgressRow(
                                label: 'Heute',
                                used: _bytesLabel(_mobileDailyUsed),
                                limit: _mobileDailyMb == 0
                                    ? null
                                    : _mbLabel(_mobileDailyMb),
                                pct: _mobileDailyMb == 0
                                    ? 0
                                    : (_mobileDailyUsed /
                                            (_mobileDailyMb * 1024 * 1024))
                                        .clamp(0.0, 1.0),
                              ),
                              _UsageProgressRow(
                                label: 'Dieser Monat',
                                used: _bytesLabel(_mobileMonthlyUsed),
                                limit: _mobileMonthlyMb == 0
                                    ? null
                                    : _mbLabel(_mobileMonthlyMb),
                                pct: _mobileMonthlyMb == 0
                                    ? 0
                                    : (_mobileMonthlyUsed /
                                            (_mobileMonthlyMb * 1024 * 1024))
                                        .clamp(0.0, 1.0),
                              ),
                            ],
                          ],
                        ),

                        // ── Wissensspeicher ──────────────────────────────────
                        _card(
                          icon: Icons.menu_book_rounded,
                          title: 'Wissensspeicher',
                          children: [
                            Text(
                              'Alle Artikeltexte und Vorschaubilder sind offline '
                              'auf dem Gerät gespeichert – dafür brauchst du kein '
                              'Internet.',
                              style: _hint,
                            ),
                            const SizedBox(height: 8),
                            FutureBuilder<String?>(
                              future:
                                  LicenseCacheDb.instance.getStoredZimVersion(),
                              builder: (_, snap) => Row(
                                children: [
                                  Text('Stand: ', style: _label),
                                  Text(_friendlyZimVersion(snap.data),
                                      style: _value),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                SafeArea(
                  minimum: const EdgeInsets.only(bottom: 8),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                    child: SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF2E7D32)),
                        onPressed: _saving ? null : _save,
                        child: _saving
                            ? const SizedBox(
                                width: 16, height: 16,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white))
                            : const Text('Speichern'),
                      ),
                    ),
                  ),
                ),
              ],
            )),
    );
  }
}

// ── ZIM Update Dialog ─────────────────────────────────────────────────────────

class _ZimUpdateDialog extends StatefulWidget {
  final ZimVersionInfo info;
  final VoidCallback onDone;
  const _ZimUpdateDialog({required this.info, required this.onDone});

  @override
  State<_ZimUpdateDialog> createState() => _ZimUpdateDialogState();
}

class _ZimUpdateDialogState extends State<_ZimUpdateDialog> {
  bool _downloading = false;
  double _progress = 0;
  Duration? _eta;
  String? _error;
  bool _needsRestart = false;

  String _fmtEta(Duration d) =>
      d.inMinutes >= 1 ? '~${d.inMinutes} min' : '~${d.inSeconds}s';

  Future<void> _startDownload() async {
    setState(() { _downloading = true; _error = null; });
    final ok = await ZimUpdateService.instance.downloadAndSwap(
      widget.info,
      onProgress: (recv, total, eta) {
        if (mounted) setState(() {
          _progress = total > 0 ? recv / total : 0;
          _eta = eta;
        });
      },
    );
    if (!mounted) return;
    if (ok) {
      setState(() { _downloading = false; _needsRestart = true; });
    } else {
      setState(() { _downloading = false; _error = 'Download fehlgeschlagen.'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_downloading,
      child: AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: const Row(children: [
          Icon(Icons.system_update_rounded, color: Color(0xFF2E7D32), size: 22),
          SizedBox(width: 8),
          Text('Wissensspeicher-Update'),
        ]),
        content: _downloading
            ? Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  LinearProgressIndicator(
                    value: _progress > 0 ? _progress : null,
                    backgroundColor: const Color(0xFFE8F5E9),
                    valueColor: const AlwaysStoppedAnimation(Color(0xFF2E7D32)),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    _progress > 0
                        ? '${(_progress * 100).round()} %'
                            '${_eta != null ? "  —  ${_fmtEta(_eta!)}" : ""}'
                        : 'Verbinde…',
                    style: const TextStyle(fontSize: 13),
                  ),
                ],
              )
            : _needsRestart
            ? const Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('✅', style: TextStyle(fontSize: 36)),
                  SizedBox(height: 8),
                  Text(
                    'Update heruntergeladen! Bitte starte die App neu.',
                    style: TextStyle(fontSize: 14, height: 1.45),
                    textAlign: TextAlign.center,
                  ),
                ],
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Eine neue Version des Wissens­speichers ist verfügbar.',
                    style: const TextStyle(fontSize: 14, height: 1.45),
                  ),
                  const SizedBox(height: 12),
                  _UsageRow('Neue Version:', widget.info.version),
                  _UsageRow('Größe:', widget.info.sizeMb),
                  _UsageRow('Veröffentlicht:', widget.info.updated),
                  const SizedBox(height: 8),
                  Text(
                    'Das Update wird im WLAN ohne Datenlimit heruntergeladen.',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!,
                        style: TextStyle(
                            color: Colors.red.shade700, fontSize: 13)),
                  ],
                ],
              ),
        actions: _downloading
            ? null
            : _needsRestart
            ? [
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32)),
                  onPressed: () {
                    widget.onDone();
                    Navigator.pop(context);
                  },
                  child: const Text('OK'),
                ),
              ]
            : [
                TextButton(
                  onPressed: () async {
                    await ZimUpdateService.instance.skipFor30Days();
                    widget.onDone();
                    if (context.mounted) Navigator.pop(context);
                  },
                  child: Text('30 Tage überspringen',
                      style: TextStyle(color: Colors.grey.shade600)),
                ),
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32)),
                  onPressed: _startDownload,
                  child: const Text('Jetzt aktualisieren'),
                ),
              ],
      ),
    );
  }
}

// ── Shared small widgets ───────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final String label;
  const _SectionHeader(this.label);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Colors.grey.shade500,
          letterSpacing: 1.0,
        ),
      ),
    );
  }
}

class _LimitDropdown extends StatelessWidget {
  final String label;
  final int value;
  final List<int> options;
  final String Function(int) fmt;
  final ValueChanged<int> onChanged;

  const _LimitDropdown({
    required this.label,
    required this.value,
    required this.options,
    required this.fmt,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final safeValue = options.contains(value) ? value : options.first;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: const TextStyle(fontSize: 15)),
          ),
          DropdownButton<int>(
            value: safeValue,
            items: options
                .map((o) => DropdownMenuItem(value: o, child: Text(fmt(o))))
                .toList(),
            onChanged: (v) { if (v != null) onChanged(v); },
            underline: const SizedBox(),
            style: const TextStyle(
                fontSize: 15, color: Color(0xFF2E7D32),
                fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

/// Usage row with optional progress bar (shown when [limit] != null).
class _UsageProgressRow extends StatelessWidget {
  final String  label;
  final String  used;
  final String? limit;  // null → unlimited (no bar)
  final double  pct;    // 0.0–1.0

  const _UsageProgressRow({
    required this.label,
    required this.used,
    this.limit,
    required this.pct,
  });

  Color get _barColor {
    if (pct >= 1.0) return Colors.red.shade600;
    if (pct >= 0.8) return Colors.orange.shade600;
    return const Color(0xFF4CAF50);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style: const TextStyle(fontSize: 13, color: Color(0xFF666666))),
              Text(
                limit != null
                    ? '$used / $limit  (${(pct * 100).round()}%)'
                    : used,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: limit != null ? _barColor : const Color(0xFF2E7D32),
                ),
              ),
            ],
          ),
          if (limit != null) ...[
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: pct,
                minHeight: 5,
                backgroundColor: const Color(0xFFE8F5E9),
                valueColor: AlwaysStoppedAnimation(_barColor),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _UsageRow extends StatelessWidget {
  final String label;
  final String value;
  const _UsageRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text(label,
              style:
                  const TextStyle(fontSize: 12, color: Color(0xFF666666))),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF2E7D32)),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

/// Dünner Trenner innerhalb einer Karte.
class _CardDivider extends StatelessWidget {
  const _CardDivider();
  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 10),
        child: Divider(height: 1, color: Color(0xFFE8F5E9)),
      );
}

class _StorageRow extends StatelessWidget {
  final String label;
  final String value;
  final String? emptyHint;
  final VoidCallback? onClear;
  final bool clearing;
  const _StorageRow({
    required this.label,
    required this.value,
    this.emptyHint,
    this.onClear,
    this.clearing = false,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 14)),
              Text(
                emptyHint ?? value,
                style: TextStyle(
                    fontSize: 12,
                    color: emptyHint != null
                        ? Colors.grey.shade400
                        : const Color(0xFF2E7D32),
                    fontWeight: emptyHint != null
                        ? FontWeight.normal
                        : FontWeight.w500),
              ),
            ],
          ),
        ),
        if (onClear != null)
          SizedBox(
            height: 32,
            child: clearing
                ? const Padding(
                    padding: EdgeInsets.all(6),
                    child: SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ))
                : TextButton(
                    style: TextButton.styleFrom(
                      foregroundColor: Colors.red.shade700,
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    onPressed: onClear,
                    child: const Text('Löschen'),
                  ),
          ),
      ],
    );
  }
}

// ── Rest mode badge ────────────────────────────────────────────────────────────

class _RestModeBadge extends StatelessWidget {
  const _RestModeBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF2E7D32).withValues(alpha: 0.88),
        borderRadius: BorderRadius.circular(24),
        boxShadow: const [
          BoxShadow(color: Colors.black26, blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('💤', style: TextStyle(fontSize: 16)),
          SizedBox(width: 8),
          Text(
            'Tippe mich an',
            style: TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Plus & Premium Dialog ────────────────────────────────────────────────────

// ── Subscription Screen ────────────────────────────────────────────────────────

class _SubscriptionScreen extends StatefulWidget {
  const _SubscriptionScreen();

  @override
  State<_SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<_SubscriptionScreen> {
  final _sub = SubscriptionService.instance;
  bool _loading = false;
  String? _message;

  @override
  void initState() {
    super.initState();
  }

  Future<void> _purchasePlus() async {
    setState(() { _loading = true; _message = null; });
    try {
      final tier = await _sub.purchasePlus();
      if (!mounted) return;
      if (tier == SubscriptionTier.plus || tier == SubscriptionTier.premium) {
        unawaited(ImageLibraryService.instance.downloadLibrary(thumbTier: false));
        setState(() {
          _loading = false;
          _message = 'Plus freigeschaltet! Bilder werden im Hintergrund geladen…';
        });
      } else {
        setState(() { _loading = false; });
      }
    } on PlatformException {
      if (mounted) setState(() { _loading = false; _message = null; });
    } catch (_) {
      if (mounted) setState(() { _loading = false; _message = 'Kauf fehlgeschlagen. Bitte versuche es erneut.'; });
    }
  }

  Future<void> _subscribePremium() async {
    setState(() { _loading = true; _message = null; });
    try {
      final tier = await _sub.subscribePremium();
      if (!mounted) return;
      if (tier == SubscriptionTier.premium) {
        unawaited(ImageLibraryService.instance.downloadLibrary(thumbTier: false));
        setState(() {
          _loading = false;
          _message = 'Premium aktiviert! Bilder werden im Hintergrund geladen…';
        });
      } else {
        setState(() { _loading = false; });
      }
    } on PlatformException {
      if (mounted) setState(() { _loading = false; _message = null; });
    } catch (_) {
      if (mounted) setState(() { _loading = false; _message = 'Kauf fehlgeschlagen. Bitte versuche es erneut.'; });
    }
  }

  Future<void> _restore() async {
    setState(() { _loading = true; _message = null; });
    try {
      final tier = await _sub.restorePurchases();
      if (!mounted) return;
      setState(() {
        _loading = false;
        _message = tier == SubscriptionTier.free
            ? 'Kein aktiver Kauf gefunden.'
            : 'Kauf wiederhergestellt: ${_sub.tierName}';
      });
    } catch (_) {
      if (mounted) setState(() { _loading = false; _message = 'Wiederherstellung fehlgeschlagen.'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final tier = _sub.tier;
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('Plus & Premium'),
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF2E7D32),
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(height: 1, color: Colors.grey.shade200),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF4CAF50)))
          : SafeArea(
              top: false,
              minimum: const EdgeInsets.only(bottom: 8),
              child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Aktueller Status ─────────────────────────────────
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0F7F2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _sub.tierName,
                          style: const TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                            color: Color(0xFF1B5E20),
                          ),
                        ),
                        if (tier == SubscriptionTier.free)
                          const Text(
                            'Alle Artikel kostenlos vorlesen — unbegrenzt.',
                            style: TextStyle(fontSize: 12, color: Color(0xFF555555)),
                          ),
                        if (tier == SubscriptionTier.plus)
                          const Text(
                            'Einmaliger Kauf — danke!',
                            style: TextStyle(fontSize: 12, color: Color(0xFF555555)),
                          ),
                        if (tier == SubscriptionTier.premium)
                          const Text(
                            'Abo aktiv — danke!',
                            style: TextStyle(fontSize: 12, color: Color(0xFF555555)),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ── Upgrade-Optionen ──────────────────────────────────
                  if (tier == SubscriptionTier.free) ...[
                    _UpgradeCard(
                      title: 'Wissensfreund Plus',
                      subtitle: 'Einmaliger Kauf',
                      price: '2–4 €',
                      features: const [
                        'Bessere Bilder offline (~600px)',
                        'Hochauflösende Bilder bei WLAN',
                      ],
                      onTap: _purchasePlus,
                    ),
                    const SizedBox(height: 12),
                    _UpgradeCard(
                      title: 'Wissensfreund Premium',
                      subtitle: 'Monatliches Abo',
                      price: '1–2 €/Monat',
                      features: const [
                        'Alles aus Plus',
                        'Rückfragen an Professor (Gemini)',
                        'Statistiken im Eltern-Dashboard',
                      ],
                      onTap: _subscribePremium,
                    ),
                  ] else if (tier == SubscriptionTier.plus) ...[
                    _UpgradeCard(
                      title: 'Wissensfreund Premium',
                      subtitle: 'Monatliches Abo',
                      price: '1–2 €/Monat',
                      features: const [
                        'Alles aus Plus',
                        'Rückfragen an Professor (Gemini)',
                        'Statistiken im Eltern-Dashboard',
                      ],
                      onTap: _subscribePremium,
                    ),
                  ] else ...[
                    // Premium aktiv — Rückfragen-Counter + Abo verwalten
                    FutureBuilder<int>(
                      future: context.read<WissensfreundProvider>().questionCountThisMonth(),
                      builder: (ctx, snap) {
                        final count = snap.data ?? 0;
                        const limit = WissensfreundProvider.kMonthlyQuestionLimit;
                        return Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF0F7F2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Rückfragen diesen Monat:',
                                  style: TextStyle(fontSize: 13)),
                              Text('$count / $limit',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                    color: Color(0xFF2E7D32),
                                  )),
                            ],
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: 12),
                    // ── Statistiken ──────────────────────────────────────
                    FutureBuilder<List<Map<String, dynamic>>>(
                      future: context.read<WissensfreundProvider>().recentStats(7),
                      builder: (ctx, snap) {
                        if (!snap.hasData || snap.data!.isEmpty) {
                          return const SizedBox.shrink();
                        }
                        final rows = snap.data!;
                        final totalArticles = rows.fold(0, (s, r) =>
                            s + ((r['articles_listened'] as int?) ?? 0));
                        final totalQuestions = rows.fold(0, (s, r) =>
                            s + ((r['questions_asked'] as int?) ?? 0));
                        final totalMin = rows.fold(0, (s, r) =>
                            s + ((r['session_minutes'] as int?) ?? 0));
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Diese Woche',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                  color: Color(0xFF1B5E20),
                                )),
                            const SizedBox(height: 6),
                            _StatRow(label: 'Artikel gehört', value: '$totalArticles'),
                            _StatRow(label: 'Rückfragen gestellt', value: '$totalQuestions'),
                            _StatRow(label: 'Lernzeit', value: '${totalMin} min'),
                          ],
                        );
                      },
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.open_in_new_rounded, size: 16),
                        label: const Text('Abo im Play Store verwalten'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF2E7D32),
                          side: const BorderSide(color: Color(0xFF2E7D32)),
                        ),
                        onPressed: () => Navigator.pop(context),
                      ),
                    ),
                  ],

                  // ── Feedback-Meldung ─────────────────────────────────
                  if (_message != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: _message!.contains('fehlgeschlagen')
                            ? const Color(0xFFFFEBEE)
                            : const Color(0xFFE8F5E9),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        _message!,
                        style: TextStyle(
                          fontSize: 13,
                          color: _message!.contains('fehlgeschlagen')
                              ? const Color(0xFFC62828)
                              : const Color(0xFF1B5E20),
                        ),
                      ),
                    ),
                  ],

                  // ── Käufe wiederherstellen ───────────────────────────
                  const SizedBox(height: 12),
                  Center(
                    child: TextButton(
                      onPressed: _restore,
                      child: const Text(
                        'Käufe wiederherstellen',
                        style: TextStyle(fontSize: 12, color: Color(0xFF757575)),
                      ),
                    ),
                  ),

                  // ── Debug-Tier-Umschalter (nur Debug-Build) ──────────
                  if (kDebugMode) ...[
                    const SizedBox(height: 24),
                    const Divider(),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text('Debug: Tier direkt wechseln',
                          style: TextStyle(fontSize: 12, color: Color(0xFF888888))),
                    ),
                    Row(children: [
                      Expanded(
                        child: OutlinedButton(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: tier == SubscriptionTier.free
                                ? const Color(0xFF2E7D32) : Colors.grey,
                            side: BorderSide(
                              color: tier == SubscriptionTier.free
                                  ? const Color(0xFF2E7D32) : Colors.grey.shade300,
                            ),
                          ),
                          onPressed: () async {
                            await SubscriptionService.instance
                                .setTierForTesting(SubscriptionTier.free);
                            if (mounted) setState(() {});
                          },
                          child: const Text('Free', style: TextStyle(fontSize: 12)),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: OutlinedButton(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: tier == SubscriptionTier.plus
                                ? const Color(0xFF2E7D32) : Colors.grey,
                            side: BorderSide(
                              color: tier == SubscriptionTier.plus
                                  ? const Color(0xFF2E7D32) : Colors.grey.shade300,
                            ),
                          ),
                          onPressed: () async {
                            await SubscriptionService.instance
                                .setTierForTesting(SubscriptionTier.plus);
                            if (mounted) setState(() {});
                          },
                          child: const Text('Plus', style: TextStyle(fontSize: 12)),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: OutlinedButton(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: tier == SubscriptionTier.premium
                                ? const Color(0xFF2E7D32) : Colors.grey,
                            side: BorderSide(
                              color: tier == SubscriptionTier.premium
                                  ? const Color(0xFF2E7D32) : Colors.grey.shade300,
                            ),
                          ),
                          onPressed: () async {
                            await SubscriptionService.instance
                                .setTierForTesting(SubscriptionTier.premium);
                            if (mounted) setState(() {});
                          },
                          child: const Text('Premium', style: TextStyle(fontSize: 12)),
                        ),
                      ),
                    ]),
                  ],
                ],
              ),
            ),
            ),
    );
  }
}

class _StatRow extends StatelessWidget {
  final String label;
  final String value;
  const _StatRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF555555))),
          Text(value, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}

class _UpgradeCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final String price;
  final List<String> features;
  final VoidCallback onTap;

  const _UpgradeCard({
    required this.title,
    required this.subtitle,
    required this.price,
    required this.features,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFF2E7D32)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
            decoration: const BoxDecoration(
              color: Color(0xFF2E7D32),
              borderRadius: BorderRadius.vertical(top: Radius.circular(13)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Flexible(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 14,
                          )),
                      Text(subtitle,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 11,
                          )),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(price,
                      style: const TextStyle(
                        color: Color(0xFF2E7D32),
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      )),
                ),
              ],
            ),
          ),
          // Features
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: features
                  .map((f) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(children: [
                          const Icon(Icons.check_circle_rounded,
                              size: 14, color: Color(0xFF2E7D32)),
                          const SizedBox(width: 6),
                          Text(f, style: const TextStyle(fontSize: 12)),
                        ]),
                      ))
                  .toList(),
            ),
          ),
          // CTA Button
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 4, 14, 12),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF2E7D32),
                  foregroundColor: Colors.white,
                  textStyle: const TextStyle(fontSize: 13),
                ),
                onPressed: onTap,
                child: Text('Jetzt freischalten — $price'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticleListButton extends StatelessWidget {
  const _ArticleListButton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: OutlinedButton.icon(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(
                builder: (_) => const WfArticleListScreen()),
          );
        },
        icon: const Icon(Icons.library_books_rounded, size: 18),
        label: const Text('Neue Artikel →'),
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF2E7D32),
          side: const BorderSide(color: Color(0xFF2E7D32)),
        ),
      ),
    );
  }
}

class _CardAlbumButton extends StatelessWidget {
  const _CardAlbumButton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: OutlinedButton.icon(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CardAlbumScreen()),
          );
        },
        icon: const Text('🃏', style: TextStyle(fontSize: 16)),
        label: const Text('Sammelkarten'),
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFFB8860B),
          side: const BorderSide(color: Color(0xFFB8860B)),
        ),
      ),
    );
  }
}

class _TrophyButton extends StatelessWidget {
  const _TrophyButton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: OutlinedButton.icon(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const TrophyScreen()),
          );
        },
        icon: const Text('🏆', style: TextStyle(fontSize: 16)),
        label: const Text('Trophäen'),
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFFB8860B),
          side: const BorderSide(color: Color(0xFFB8860B)),
        ),
      ),
    );
  }
}

class _RoomButton extends StatelessWidget {
  const _RoomButton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: OutlinedButton.icon(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const RoomScreen()),
          );
        },
        icon: const Text('🏠', style: TextStyle(fontSize: 16)),
        label: const Text('Mein Zimmer'),
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF6A4BB8),
          side: const BorderSide(color: Color(0xFF6A4BB8)),
        ),
      ),
    );
  }
}

// TEMP TEST BUTTON — remove before release
class _JsonTestButton extends StatelessWidget {
  const _JsonTestButton({required this.provider});
  final WissensfreundProvider provider;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: OutlinedButton.icon(
        onPressed: () {
          provider.loadAndSpeakJsonArticle('elefant_l2');
        },
        icon: const Text('🐘', style: TextStyle(fontSize: 16)),
        label: const Text('JSON Test (Elefant L2)'),
        style: OutlinedButton.styleFrom(
          foregroundColor: Colors.deepOrange,
          side: const BorderSide(color: Colors.deepOrange),
        ),
      ),
    );
  }
}

