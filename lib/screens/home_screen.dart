import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../services/parental_lock_service.dart';
import '../widgets/professor_widget.dart';
import 'article_screen.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkOnboarding());
  }

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
      // Kind bleibt → Professor weiterlesen lassen
      provider.resumeSpeaking();
      return;
    }

    if (!mounted) return;
    final authenticated = await ps.authenticate(
      'Zum Beenden der App bitte authentifizieren.',
    );

    if (!authenticated) {
      provider.resumeSpeaking();
      return;
    }

    // Auth erfolgreich → Kiosk-Modus beenden, dann Gerät sperren, dann App beenden
    if (ps.isKioskMode) await ps.stopKioskMode();
    if (ps.isAdminActive) await ps.lockDevice();
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
          if (mounted) _navigatingToArticle = false;
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

  @override
  void dispose() {
    _breathCtrl.dispose();
    _zimFadeTimer?.cancel();
    _provider?.removeListener(_onProviderChanged);
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
                              if (provider.recognizedText.isNotEmpty &&
                                  provider.articleText.isEmpty)
                                _RecognizedText(text: provider.recognizedText),
                              if (provider.articleText.isNotEmpty)
                                _ArticleCard(
                                  title: provider.articleTitle,
                                  text: provider.articleText,
                                ),
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
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
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
    // context (HomeScreen-Ebene) wird als outerContext weitergegeben,
    // damit Dialoge aus _AppMenu nach dem Schließen des BottomSheets
    // noch einen gültigen BuildContext haben.
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _AppMenu(provider: provider, outerContext: context),
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

class _AppMenu extends StatelessWidget {
  final WissensfreundProvider provider;
  final BuildContext outerContext; // HomeScreen-Ebene — bleibt nach BottomSheet-Pop gültig
  const _AppMenu({required this.provider, required this.outerContext});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8EE),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 12),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey.shade300,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 8),
          _MenuItem(
            icon: Icons.home_rounded,
            label: 'Hauptmenü',
            onTap: () => Navigator.pop(context),
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          _MenuItem(
            icon: Icons.keyboard_rounded,
            label: 'Texteingabe',
            onTap: () {
              Navigator.pop(context);
              _showTextInput(outerContext);
            },
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          _MenuItem(
            icon: Icons.history_rounded,
            label: 'Verlauf',
            onTap: () => Navigator.pop(context),
            comingSoon: true,
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          _MenuItem(
            icon: Icons.settings_rounded,
            label: 'Einstellungen',
            onTap: () => Navigator.pop(context),
            comingSoon: true,
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          _MenuItem(
            icon: Icons.shield_rounded,
            label: 'Kinderschutz',
            onTap: () {
              Navigator.pop(context);
              _authenticateAndShowDashboard(outerContext);
            },
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  void _authenticateAndShowDashboard(BuildContext ctx) async {
    final ps = ctx.read<ParentalLockService>();
    final ok = await ps.authenticate(
      'Bitte authentifizieren um die Kinderschutz-Einstellungen zu öffnen.',
    );
    if (!ok || !ctx.mounted) return;
    _showParentalDashboard(ctx);
  }

  void _showParentalDashboard(BuildContext stableCtx) {
    showDialog(
      context: stableCtx,
      builder: (ctx) => Consumer<ParentalLockService>(
        builder: (ctx, ps, _) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Row(children: [
            Icon(Icons.shield_rounded, color: Color(0xFF2E7D32), size: 22),
            SizedBox(width: 8),
            Text('Kinderschutz'),
          ]),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Overlay-Berechtigung ──────────────────────────────
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
                const SizedBox(height: 16),

                // ── Kindersicherung (Kiosk) ──────────────────────────
                _DashboardRow(
                  icon: ps.isKioskMode
                      ? Icons.lock_outline_rounded
                      : Icons.lock_open_rounded,
                  color: ps.isKioskMode
                      ? const Color(0xFF2E7D32)
                      : Colors.orange.shade700,
                  label: ps.isKioskMode
                      ? 'Kindermodus aktiv'
                      : 'Kindermodus inaktiv',
                ),
                const SizedBox(height: 6),
                Text(
                  ps.isKioskMode
                      ? 'Home- und Recents-Taste führen direkt zum Eltern-Bildschirm. Das Kind kann nicht frei surfen.'
                      : 'Wenn aktiviert, kehrt das Gerät bei Home- oder Recents-Taste sofort zum Eltern-Bildschirm zurück.',
                  style: const TextStyle(fontSize: 13, height: 1.45),
                ),
                const SizedBox(height: 16),

                // ── Eltern-Entsperrung ──────────────────────────────────
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
                      ? 'Beim Verlassen der App über die Zurück-Taste sperrt sich das Gerät.'
                      : 'Beim Zurückkehren zur App erscheint der Eltern-Bildschirm mit Fingerabdruck/PIN.',
                  style: const TextStyle(fontSize: 13, height: 1.45),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Schließen'),
            ),
            if (!ps.hasOverlayPermission)
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: Colors.red.shade700),
                onPressed: () async {
                  Navigator.pop(ctx);
                  await ps.requestOverlayPermission();
                  await ps.refreshAdminStatus();
                },
                child: const Text('Overlay-Berechtigung einrichten'),
              ),
            if (!ps.isAdminActive)
              OutlinedButton(
                onPressed: () async {
                  Navigator.pop(ctx);
                  await ps.requestDeviceAdmin();
                  await ps.refreshAdminStatus();
                },
                child: const Text('Gerätesperre aktivieren'),
              ),
            if (!ps.isKioskMode)
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF2E7D32)),
                onPressed: () async {
                  await ps.startKioskMode();
                  if (ctx.mounted) Navigator.pop(ctx);
                },
                child: const Text('Kindermodus aktivieren'),
              )
            else
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: Colors.grey.shade600),
                onPressed: () async {
                  final authenticated = await ps.authenticate(
                    'Kindersicherung deaktivieren — bitte authentifizieren.',
                  );
                  if (authenticated) {
                    await ps.stopKioskMode();
                    if (ctx.mounted) Navigator.pop(ctx);
                  }
                },
                child: const Text('Kindersicherung deaktivieren'),
              ),
          ],
        ),
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
