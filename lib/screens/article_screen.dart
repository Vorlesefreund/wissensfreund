import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/rendered_article.dart';
import '../models/wf_article.dart';
import '../providers/wissensfreund_provider.dart';
import '../utils/system_ui.dart';
import '../services/data_limit_overlay_service.dart';
import '../services/hires_image_service.dart';
import '../services/network_service.dart';
import '../services/parental_lock_service.dart';
import '../services/subscription_service.dart';
import '../services/profile_service.dart';
import '../services/wikimedia_license_checker.dart';
import '../widgets/callout_box.dart';
import '../widgets/professor_widget.dart';
import '../widgets/quiz_widget.dart';

// Professor / mic layout — ALL size-dependent values derive from these constants.
// When the professor or mic button changes size, update only here.
const double _kProfW      = 178.0;
const double _kProfH      = 218.0;
const double _kProfRight  = -12.0;
const double _kProfBottom =   6.0;
const double _kMicSize    =  52.0;
const double _kMicBottom  =  14.0;
const double _kProfPad    = _kProfW - 18.0;              // 160 — right text indent beside professor
const double _kMicClear   = _kMicSize + _kMicBottom * 2; //  80 — scroll bottom clearance
const double _kProfZone   = _kProfH + _kProfBottom - 4;  // 220 — viewport bottom covered by professor
const double _kThumbRight = _kProfW + 2.0;               // 180 — thumbnail row right padding

// ─────────────────────────────────────────────────────────────────────────────
// Parental auth — required before any external URL is opened
// ─────────────────────────────────────────────────────────────────────────────

Future<void> _launchUrlWithParentalAuth(BuildContext context, Uri uri) async {
  final ps = context.read<ParentalLockService>();
  bool authenticated = false;

  await showDialog<void>(
    context: context,
    barrierDismissible: true,
    builder: (ctx) => AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: const Row(children: [
        Icon(Icons.lock_rounded, color: Color(0xFF2E7D32), size: 22),
        SizedBox(width: 8),
        Text('Für Erwachsene'),
      ]),
      content: const Text(
        'Dieser Link ist für Erwachsene.\n\nBitte Mama oder Papa fragen!',
        style: TextStyle(fontSize: 16, height: 1.5),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: Text('Schließen',
              style: TextStyle(color: Colors.grey.shade600)),
        ),
        FilledButton.icon(
          icon: const Icon(Icons.fingerprint_rounded, size: 20),
          label: const Text('Entsperren'),
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF2E7D32),
          ),
          onPressed: () async {
            final ok = await ps.authenticate(
              'Zum Öffnen externer Links bitte authentifizieren.',
            );
            if (ok) {
              authenticated = true;
              if (ctx.mounted) Navigator.pop(ctx);
            }
          },
        ),
      ],
    ),
  );

  if (authenticated && context.mounted) {
    ps.suppressNextOverlay(); // Rückkehr vom Browser kein Overlay + Professor läuft weiter
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Root screen — manages mode switching; professor + mic are always on top
// ─────────────────────────────────────────────────────────────────────────────

class ArticleScreen extends StatefulWidget {
  const ArticleScreen({super.key});

  @override
  State<ArticleScreen> createState() => _ArticleScreenState();
}

class _ArticleScreenState extends State<ArticleScreen> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (ModalRoute.of(context)?.isCurrent == true) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    }
  }

  @override
  void dispose() {
    restoreSystemUI();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        // Watch ProfileService so a profile change triggers a rebuild here.
        final ageLevel = context.watch<ProfileService>().activeAgeLevel;
        // Clamp mode: Stufe 1 may never show Mode A.
        final effectiveMode = (ageLevel == 1 && provider.viewMode == ArticleViewMode.a)
            ? ArticleViewMode.b
            : provider.viewMode;
        // Persist the clamped mode so SharedPreferences stays consistent.
        if (effectiveMode != provider.viewMode) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) context.read<WissensfreundProvider>().setViewMode(effectiveMode);
          });
        }
        final isDark = effectiveMode != ArticleViewMode.a;

        return Scaffold(
          backgroundColor:
              isDark ? const Color(0xFF1A4731) : const Color(0xFFFFF8F0),
          body: SafeArea(
            child: Stack(
              children: [
                // ── Mode content ───────────────────────────────────────────
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  transitionBuilder: (child, anim) =>
                      FadeTransition(opacity: anim, child: child),
                  child: switch (effectiveMode) {
                    ArticleViewMode.a =>
                      const _ModeAContent(key: ValueKey('a')),
                    ArticleViewMode.b =>
                      const _ModeBContent(key: ValueKey('b')),
                    ArticleViewMode.c =>
                      const _ModeCContent(key: ValueKey('c')),
                  },
                ),
                // ── Professor — same position across all modes ─────────────
                Positioned(
                  right: _kProfRight,
                  bottom: _kProfBottom,
                  width: _kProfW,
                  height: _kProfH,
                  child: IgnorePointer(
                    child: ProfessorWidget(
                      state: provider.state,
                      compact: true,
                    ),
                  ),
                ),
                // ── Controls (back / mic / pause) ──────────────────────────
                Positioned(
                  bottom: _kMicBottom,
                  left: 0,
                  right: 0,
                  child: _ArticleControls(provider: provider),
                ),
                // ── Caption-Resume Prompt ──────────────────────────────────
                if (provider.showCaptionResumePrompt)
                  Positioned(
                    bottom: _kMicClear + 16,
                    left: 0,
                    right: 0,
                    child: const Center(child: _CaptionResumeOverlay()),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared: Mic / Play-Pause button
// ─────────────────────────────────────────────────────────────────────────────
// Bottom controls — single back button (idle) or [←][🎤][⏸] (speaking/paused)
// ─────────────────────────────────────────────────────────────────────────────
// Bottom controls — [←] back | [⏸/▶] pause/play | [🎤] mic (animated when listening)
// ─────────────────────────────────────────────────────────────────────────────

class _ArticleControls extends StatefulWidget {
  final WissensfreundProvider provider;
  const _ArticleControls({required this.provider});

  @override
  State<_ArticleControls> createState() => _ArticleControlsState();
}

class _ArticleControlsState extends State<_ArticleControls>
    with TickerProviderStateMixin {
  static const _ringCount = 3;
  static const _ringDelayMs = 550;

  final List<AnimationController> _ringCtrls = [];
  final List<Animation<double>> _ringScales = [];
  final List<Animation<double>> _ringOpacities = [];

  // Tracks previous listening state to detect transitions.
  late AppState _prevState;

  @override
  void initState() {
    super.initState();
    _prevState = widget.provider.state;
    for (int i = 0; i < _ringCount; i++) {
      final ctrl = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 1700),
      );
      _ringCtrls.add(ctrl);
      _ringScales.add(Tween<double>(begin: 1.0, end: 2.4).animate(
        CurvedAnimation(parent: ctrl, curve: Curves.easeOut),
      ));
      _ringOpacities.add(Tween<double>(begin: 0.55, end: 0.0).animate(
        CurvedAnimation(parent: ctrl, curve: Curves.easeOut),
      ));
    }
    if (_prevState == AppState.listening) _startRings();
  }

  @override
  void didUpdateWidget(_ArticleControls old) {
    super.didUpdateWidget(old);
    final isListening = widget.provider.state == AppState.listening;
    final wasListening = _prevState == AppState.listening;
    if (isListening && !wasListening) _startRings();
    if (!isListening && wasListening) _stopRings();
    _prevState = widget.provider.state;
  }

  void _startRings() {
    for (int i = 0; i < _ringCount; i++) {
      Future.delayed(Duration(milliseconds: i * _ringDelayMs), () {
        if (mounted && widget.provider.state == AppState.listening) {
          _ringCtrls[i].repeat();
        }
      });
    }
  }

  void _stopRings() {
    for (final c in _ringCtrls) {
      c.stop();
      c.reset();
    }
  }

  @override
  void dispose() {
    for (final c in _ringCtrls) c.dispose();
    super.dispose();
  }

  Widget _btn({required IconData icon, required Color bg, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: _kMicSize,
        height: _kMicSize,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: bg,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.30),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Icon(icon, color: Colors.white, size: 28),
      ),
    );
  }

  Widget _micBtn(bool isListening) {
    const kRed   = Color(0xFFE53935);
    const kGreen = Color(0xFF2D6A4F);
    return SizedBox(
      width: _kMicSize,
      height: _kMicSize,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          // Pulsing rings — same style as home screen, scaled to _kMicSize
          ...List.generate(_ringCount, (i) => AnimatedBuilder(
            animation: _ringCtrls[i],
            builder: (_, __) => Transform.scale(
              scale: _ringScales[i].value,
              child: Container(
                width: _kMicSize,
                height: _kMicSize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: kRed.withValues(alpha: _ringOpacities[i].value),
                    width: 2.0,
                  ),
                ),
              ),
            ),
          )),
          // Mic button itself
          _btn(
            icon: Icons.mic_rounded,
            bg: isListening ? kRed : kGreen,
            onTap: () => isListening
                ? widget.provider.stopListening()
                : widget.provider.interruptAndStartListening(),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider    = widget.provider;
    final isSpeaking  = provider.state == AppState.speaking;
    final isPaused    = provider.isPaused;
    final isListening = provider.state == AppState.listening;

    // Three-button row: [←] left  |  [⏸/▶] center  |  [🎤] right.
    // Fixed 24dp gaps, anchored at left: 16 → group ends at ~220dp from left,
    // safely clear of the professor whose body starts at ~227dp.
    if (isSpeaking || isPaused || isListening) {
      return Padding(
        padding: const EdgeInsets.only(left: 16),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _btn(
              icon: Icons.arrow_back_rounded,
              bg: const Color(0xFF37474F),
              onTap: () async {
                if (provider.canGoBack) {
                  provider.goBack();
                } else {
                  await provider.saveCurrentArticlePosition();
                  await provider.stopSpeaking();
                  if (context.mounted) Navigator.pop(context);
                }
              },
            ),
            const SizedBox(width: 24),
            _btn(
              icon: isSpeaking ? Icons.pause_rounded : Icons.play_arrow_rounded,
              bg: const Color(0xFF2D6A4F),
              onTap: () => isSpeaking
                  ? provider.pauseSpeaking()
                  : provider.resumeSpeaking(),
            ),
            const SizedBox(width: 24),
            _micBtn(isListening),
          ],
        ),
      );
    }

    // Idle — single centered back button.
    final isDark = provider.viewMode != ArticleViewMode.a;
    return Center(
      child: GestureDetector(
        onTap: () async {
          if (provider.canGoBack) {
            provider.goBack();
          } else {
            await provider.saveCurrentArticlePosition();
            await provider.stopSpeaking();
            if (context.mounted) Navigator.pop(context);
          }
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          width: _kMicSize,
          height: _kMicSize,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDark
                ? Colors.white.withValues(alpha: 0.2)
                : const Color(0xFF546E7A),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.30),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: const Icon(Icons.arrow_back_rounded, color: Colors.white, size: 28),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared: Header (adapts to mode)
// ─────────────────────────────────────────────────────────────────────────────

class _ArticleHeader extends StatelessWidget {
  final WissensfreundProvider provider;
  final bool dark; // true for Mode B/C

  const _ArticleHeader({required this.provider, this.dark = false});

  Color get _fgColor =>
      dark ? Colors.white : const Color(0xFF2D6A4F);

  Color get _btnBg => dark
      ? Colors.white.withValues(alpha: 0.15)
      : const Color(0xFFE8F5E9);

  Widget _buildModeToggle() {
    final ageLevel = ProfileService.instance.activeAgeLevel;
    final modes = ageLevel == 1
        ? [ArticleViewMode.b, ArticleViewMode.c]
        : [ArticleViewMode.a, ArticleViewMode.b, ArticleViewMode.c];
    final icons = {
      ArticleViewMode.a: '📄',
      ArticleViewMode.b: '🔍',
      ArticleViewMode.c: '🎧',
    };
    final current = modes.contains(provider.viewMode)
        ? provider.viewMode
        : modes.first;
    final nextMode = modes[(modes.indexOf(current) + 1) % modes.length];
    return GestureDetector(
      onTap: () => provider.setViewMode(nextMode),
      child: Container(
        width: 30,
        height: 30,
        decoration: BoxDecoration(
          color: _btnBg,
          borderRadius: BorderRadius.circular(8),
        ),
        alignment: Alignment.center,
        child: Text(icons[current]!, style: const TextStyle(fontSize: 15)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 44,
      color: dark
          ? const Color(0xFF1A4731).withValues(alpha: 0.92)
          : const Color(0xFFFFF8F0),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          // Back button — shown when there's a nav stack entry to return to
          if (provider.canGoBack) ...[
            _HeaderBtn(
              bg: _btnBg,
              child: Icon(Icons.arrow_back_rounded, size: 19, color: _fgColor),
              onTap: () => provider.goBack(),
            ),
            const SizedBox(width: 8),
          ],
          const Text('🎓', style: TextStyle(fontSize: 20)),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              provider.canGoBack
                  ? provider.articleTitle
                  : 'Wissensfreund',
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: _fgColor,
              ),
            ),
          ),
          // Favorite
          if (provider.articleTitle.isNotEmpty)
            _FavoriteBtn(
              articleTitle: provider.articleTitle,
              btnBg: _btnBg,
              fgColor: _fgColor,
            ),
          const SizedBox(width: 8),
          // Mode toggle — 2 icons for ageLevel 1, 3 icons for 2/3
          _buildModeToggle(),
          const SizedBox(width: 8),
          // Menu
          _HeaderBtn(
            bg: _btnBg,
            child: Icon(Icons.menu_rounded, size: 19, color: _fgColor),
            onTap: () => _showMenu(context),
          ),
        ],
      ),
    );
  }

  void _showMenu(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (_) => _ArticleMenu(provider: provider),
    );
  }
}

class _HeaderBtn extends StatelessWidget {
  final Color bg;
  final Widget child;
  final VoidCallback onTap;
  const _HeaderBtn(
      {required this.bg, required this.child, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 34,
        height: 34,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(9),
        ),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}

class _FavoriteBtn extends StatefulWidget {
  final String articleTitle;
  final Color btnBg;
  final Color fgColor;
  const _FavoriteBtn({
    required this.articleTitle,
    required this.btnBg,
    required this.fgColor,
  });

  @override
  State<_FavoriteBtn> createState() => _FavoriteBtnState();
}

class _FavoriteBtnState extends State<_FavoriteBtn> {
  bool _isFavorite = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_FavoriteBtn old) {
    super.didUpdateWidget(old);
    if (old.articleTitle != widget.articleTitle) _load();
  }

  Future<void> _load() async {
    final fav = await ProfileService.instance.isFavorite(widget.articleTitle);
    if (mounted) setState(() => _isFavorite = fav);
  }

  Future<void> _toggle() async {
    await ProfileService.instance.toggleFavorite(widget.articleTitle);
    if (mounted) setState(() => _isFavorite = !_isFavorite);
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _toggle,
      child: Container(
        width: 34,
        height: 34,
        decoration: BoxDecoration(
          color: _isFavorite
              ? const Color(0xFFFFC107).withValues(alpha: 0.25)
              : widget.btnBg,
          borderRadius: BorderRadius.circular(9),
        ),
        alignment: Alignment.center,
        child: Icon(
          _isFavorite ? Icons.star_rounded : Icons.star_outline_rounded,
          size: 20,
          color: _isFavorite ? const Color(0xFFFFC107) : widget.fgColor,
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared: Article image (placeholder with emoji + gradient)
// ─────────────────────────────────────────────────────────────────────────────

class _ArticleImage extends StatelessWidget {
  final String title;
  final String emoji;
  final String themeColor;
  const _ArticleImage({
    super.key,
    required this.title,
    this.emoji = '',
    this.themeColor = '',
  });

  static const _fallbackThemes = <String, (String, List<Color>)>{
    'elefant': ('🐘', [Color(0xFF8D6E63), Color(0xFF4E342E)]),
    'hund':    ('🐕', [Color(0xFF78909C), Color(0xFF37474F)]),
    'katze':   ('🐈', [Color(0xFFAB47BC), Color(0xFF6A1B9A)]),
    'pferd':   ('🐴', [Color(0xFF6D4C41), Color(0xFF3E2723)]),
    'fisch':   ('🐠', [Color(0xFF0288D1), Color(0xFF01579B)]),
    'vogel':   ('🐦', [Color(0xFF26A69A), Color(0xFF00695C)]),
  };

  (String, List<Color>) _resolveTheme() {
    if (emoji.isNotEmpty || themeColor.isNotEmpty) {
      final e = emoji.isNotEmpty ? emoji : '📖';
      Color base = const Color(0xFF43A047);
      if (themeColor.isNotEmpty) {
        try {
          base = Color(int.parse('FF${themeColor.replaceAll('#', '')}', radix: 16));
        } catch (_) {}
      }
      final hsl = HSLColor.fromColor(base);
      return (e, [
        hsl.withLightness((hsl.lightness + 0.15).clamp(0.0, 1.0)).toColor(),
        hsl.withLightness((hsl.lightness - 0.1).clamp(0.0, 1.0)).toColor(),
      ]);
    }
    final lcTitle = title.toLowerCase();
    for (final entry in _fallbackThemes.entries) {
      if (lcTitle.contains(entry.key)) return entry.value;
    }
    return ('📚', const [Color(0xFF43A047), Color(0xFF1B5E20)]);
  }

  @override
  Widget build(BuildContext context) {
    final (emojiStr, colors) = _resolveTheme();
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors,
        ),
      ),
      child: Center(
        child: Text(emojiStr, style: const TextStyle(fontSize: 72)),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main article image — shows real ZIM image if available, falls back to emoji.
// Reads provider.selectedImageIndex and provider.articleImages.
// onTap is wired up in Step 5 (fullscreen). Leave null for now.
// ─────────────────────────────────────────────────────────────────────────────

class _MainArticleImage extends StatefulWidget {
  final String fallbackTitle;
  final VoidCallback? onTap;
  final bool enableFullscreenTap;
  final BoxFit fit;
  const _MainArticleImage({
    required this.fallbackTitle,
    this.onTap,
    this.enableFullscreenTap = true,
    this.fit = BoxFit.cover,
  });

  @override
  State<_MainArticleImage> createState() => _MainArticleImageState();
}

class _MainArticleImageState extends State<_MainArticleImage> {
  String? _loadedFilename;
  Future<Uint8List?>? _bytesFuture;

  void _updateFuture(WissensfreundProvider p) {
    final images = p.articleImages;
    if (images.isEmpty) {
      _loadedFilename = null;
      _bytesFuture = null;
      return;
    }
    final idx = p.selectedImageIndex < 0
        ? 0
        : p.selectedImageIndex.clamp(0, images.length - 1);
    final filename = images[idx].filename;
    if (filename != _loadedFilename) {
      _loadedFilename = filename;
      _bytesFuture = p.getImageBytes(filename);
    }
  }

  void _openFullscreen(BuildContext ctx, int initialIndex) {
    Navigator.of(ctx).push(PageRouteBuilder(
      opaque: false,
      barrierColor: Colors.transparent,
      pageBuilder: (routeCtx, anim, _) =>
          _FullscreenGallery(initialIndex: initialIndex, animation: anim),
      transitionDuration: const Duration(milliseconds: 280),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        _updateFuture(provider);
        final images = provider.articleImages;
        final selIdx = (images.isEmpty || provider.selectedImageIndex < 0)
            ? 0
            : provider.selectedImageIndex.clamp(0, images.length - 1);
        final fromKlexikon  = images.isEmpty ? false : images[selIdx].fromKlexikon;
        final selectedImage = images.isEmpty ? null  : images[selIdx];

        final future = _bytesFuture;
        final fn     = _loadedFilename;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: future == null
                    ? _ArticleImage(
                        key: const ValueKey('fallback'),
                        title: widget.fallbackTitle,
                        emoji: provider.articleEmoji,
                        themeColor: provider.articleThemeColor,
                      )
                    : FutureBuilder<Uint8List?>(
                        key: ValueKey(fn),
                        future: future,
                        builder: (_, snap) {
                          if (snap.connectionState == ConnectionState.waiting) {
                            return _ArticleImage(
                              title: widget.fallbackTitle,
                              emoji: provider.articleEmoji,
                              themeColor: provider.articleThemeColor,
                            );
                          }
                          final bytes = snap.data;
                          if (bytes == null) {
                            return _ArticleImage(
                              title: widget.fallbackTitle,
                              emoji: provider.articleEmoji,
                              themeColor: provider.articleThemeColor,
                            );
                          }
                          return GestureDetector(
                            onTap: widget.enableFullscreenTap
                                ? () => _openFullscreen(context, selIdx)
                                : widget.onTap,
                            child: Stack(
                              fit: StackFit.expand,
                              children: [
                                Image.memory(bytes, fit: widget.fit),
                                Positioned(
                                  right: 8,
                                  bottom: 8,
                                  child: _LicenseInfoButton(filename: fn!, fromKlexikon: fromKlexikon),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ),
            _ImageCaptionLine(image: selectedImage),
          ],
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Attribution caption shown at the bottom of the main article image.
// Tappable → opens source URL (with parental auth); hidden when both empty.
// ─────────────────────────────────────────────────────────────────────────────

class _ImageCaptionLine extends StatelessWidget {
  final ArticleImageInfo? image;
  const _ImageCaptionLine({this.image});

  @override
  Widget build(BuildContext context) {
    final author    = image?.author    ?? '';
    final license   = image?.license   ?? '';
    final sourceUrl = image?.sourceUrl ?? '';
    if (author.isEmpty && license.isEmpty) return const SizedBox.shrink();

    final parts = <String>[];
    if (author.isNotEmpty)  parts.add('© $author');
    if (license.isNotEmpty) parts.add(license);
    final label = parts.join(' · ');
    final hasUrl = sourceUrl.isNotEmpty;

    return GestureDetector(
      onTap: hasUrl
          ? () => _launchUrlWithParentalAuth(context, Uri.parse(sourceUrl))
          : null,
      child: Container(
        color: Colors.black54,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 10,
            color: Colors.white,
            decoration: hasUrl ? TextDecoration.underline : null,
            decorationColor: Colors.white,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Simple thumbnail tile: shows colored placeholder immediately, loads real
// image in background if available.
// ─────────────────────────────────────────────────────────────────────────────

class _ThumbTile extends StatefulWidget {
  final String filename;
  final Color placeholderColor;
  final bool isSelected;
  final VoidCallback onTap;
  const _ThumbTile({
    super.key,
    required this.filename,
    required this.placeholderColor,
    required this.isSelected,
    required this.onTap,
  });

  @override
  State<_ThumbTile> createState() => _ThumbTileState();
}

class _ThumbTileState extends State<_ThumbTile> {
  Uint8List? _bytes;
  bool _loading = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_loading && _bytes == null) {
      _loading = true;
      context.read<WissensfreundProvider>().getImageBytes(widget.filename).then((b) {
        if (mounted && b != null) setState(() => _bytes = b);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          width: 100,
          height: 100,
          child: Stack(
            fit: StackFit.expand,
            children: [
              _bytes != null
                  ? Image.memory(_bytes!, fit: BoxFit.cover)
                  : Container(
                      color: widget.placeholderColor,
                      alignment: Alignment.center,
                      child: const Text('🖼️', style: TextStyle(fontSize: 28)),
                    ),
              if (widget.isSelected)
                Positioned.fill(
                  child: Container(
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white, width: 2.5),
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Single thumbnail tile with lazy image load and ⓘ icon
// ─────────────────────────────────────────────────────────────────────────────

class _ZimImageTile extends StatefulWidget {
  final ArticleImageInfo image;
  final bool isSelected;

  const _ZimImageTile({
    super.key,
    required this.image,
    required this.isSelected,
  });

  @override
  State<_ZimImageTile> createState() => _ZimImageTileState();
}

class _ZimImageTileState extends State<_ZimImageTile> {
  Future<Uint8List?>? _bytesFuture;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _bytesFuture ??=
        context.read<WissensfreundProvider>().getImageBytes(widget.image.filename);
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: 100,
        height: 100,
        child: Stack(
          fit: StackFit.expand,
          children: [
            FutureBuilder<Uint8List?>(
              future: _bytesFuture,
              builder: (_, snap) {
                final bytes = snap.data;
                if (bytes == null) {
                  const thumbColors = [
                    Color(0xFFB2DFDB), Color(0xFFBBDEFB), Color(0xFFD1C4E9),
                    Color(0xFFFFF9C4), Color(0xFFFFCCBC),
                  ];
                  final color = thumbColors[widget.image.filename.hashCode.abs() % thumbColors.length];
                  return Container(
                    color: color,
                    alignment: Alignment.center,
                    child: const Text('🖼️', style: TextStyle(fontSize: 28)),
                  );
                }
                return Image.memory(bytes, fit: BoxFit.cover);
              },
            ),
            if (widget.isSelected)
              Positioned.fill(
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white, width: 2.5),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            Positioned(
              right: 4,
              bottom: 4,
              child: _LicenseInfoButton(filename: widget.image.filename, fromKlexikon: widget.image.fromKlexikon),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// 🔍 Upgrade hint — shown to Free users in fullscreen (not during TTS)
// ─────────────────────────────────────────────────────────────────────────────

class _UpgradeHint extends StatelessWidget {
  const _UpgradeHint();

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        showDialog<void>(
          context: context,
          builder: (_) => AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: const Text('Wissensfreund Plus'),
            content: const Text(
              'Mit Wissensfreund Plus lädst du bei WLAN automatisch '
              'schärfere Bilder (bis 1200px) — für eine viel bessere Bildergalerie.\n\n'
              'Wissensfreund Plus lässt sich im Menü freischalten.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Schließen'),
              ),
            ],
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.65),
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.search_rounded, color: Colors.white70, size: 15),
            SizedBox(width: 6),
            Flexible(
              child: Text(
                'Schärfere Bilder mit Wissensfreund Plus',
                style: TextStyle(
                  color: Colors.white70,
                  fontSize: 12,
                  height: 1.3,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ⓘ button — shows license dialog on tap
// ─────────────────────────────────────────────────────────────────────────────

class _LicenseInfoButton extends StatelessWidget {
  final String filename;
  final bool fromKlexikon;
  const _LicenseInfoButton({required this.filename, this.fromKlexikon = false});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _showLicenseInfo(context, filename, fromKlexikon: fromKlexikon),
      child: Container(
        width: 20,
        height: 20,
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.45),
          shape: BoxShape.circle,
        ),
        child: const Center(
          child: Text(
            'ⓘ',
            style: TextStyle(color: Colors.white, fontSize: 11, height: 1.1),
          ),
        ),
      ),
    );
  }
}

void _showLicenseInfo(
  BuildContext context,
  String filename, {
  bool fromKlexikon = false,
}) async {
  final basename = filename.split('/').last;
  final entry = await WikimediaLicenseChecker.instance.getCached(basename);
  if (!context.mounted) return;

  final hasWikimediaData =
      entry != null && (entry.urheber != null || entry.lizenz != null);

  showDialog(
    context: context,
    barrierDismissible: true,
    builder: (_) => Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Bildnachweis',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 12),
            // ── Wikimedia-Daten (wenn vorhanden) ─────────────────────────
            if (entry?.urheber != null) ...[
              Text('Urheber: ${entry!.urheber}',
                  style: const TextStyle(fontSize: 14)),
              const SizedBox(height: 4),
            ],
            if (entry?.lizenz != null) ...[
              Text('Lizenz: ${entry!.lizenz}',
                  style: const TextStyle(fontSize: 14)),
              const SizedBox(height: 8),
            ],
            if (entry?.lizenzUrl != null)
              GestureDetector(
                onTap: () => _launchUrlWithParentalAuth(
                  context,
                  Uri.parse(entry!.lizenzUrl!),
                ),
                child: const Text(
                  'Auf Wikimedia Commons ansehen →',
                  style: TextStyle(
                    color: Color(0xFF2E7D32),
                    fontSize: 14,
                    decoration: TextDecoration.underline,
                  ),
                ),
              ),
            // ── Fallback: CC BY-SA NUR wenn Klexikon-Herkunft bestätigt ──
            if (!hasWikimediaData && fromKlexikon) ...[
              const Text('Quelle: Klexikon (ZIM)',
                  style: TextStyle(fontSize: 14)),
              const SizedBox(height: 4),
              const Text('Lizenz: CC BY-SA 3.0',
                  style: TextStyle(fontSize: 14)),
              const SizedBox(height: 8),
              GestureDetector(
                onTap: () => _launchUrlWithParentalAuth(
                  context,
                  Uri.parse('https://klexikon.zum.de'),
                ),
                child: const Text(
                  'klexikon.zum.de →',
                  style: TextStyle(
                    color: Color(0xFF2E7D32),
                    fontSize: 14,
                    decoration: TextDecoration.underline,
                  ),
                ),
              ),
            ],
            // ── Unbekannte Herkunft → klar kennzeichnen ───────────────────
            if (!hasWikimediaData && !fromKlexikon)
              const Text(
                'Lizenz unbekannt — Bild gesperrt.',
                style: TextStyle(fontSize: 14, color: Colors.red),
              ),
          ],
        ),
      ),
    ),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared: Article menu (bottom sheet)
// ─────────────────────────────────────────────────────────────────────────────

class _ArticleMenu extends StatelessWidget {
  final WissensfreundProvider provider;
  const _ArticleMenu({required this.provider});

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
          const SizedBox(height: 4),
          ListTile(
            leading:
                const Icon(Icons.stop_circle_rounded, color: Color(0xFF2D6A4F)),
            title: const Text('Vorlesen beenden'),
            onTap: () async {
              Navigator.pop(context);
              await provider.clearLastArticle();
              await provider.stopSpeaking();
              if (context.mounted) Navigator.pop(context);
            },
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          ListTile(
            leading:
                const Icon(Icons.home_rounded, color: Color(0xFF2D6A4F)),
            title: const Text('Zum Hauptmenü'),
            onTap: () async {
              Navigator.pop(context);
              await provider.clearLastArticle();
              await provider.stopSpeaking();
              if (context.mounted) Navigator.pop(context);
            },
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared: Klexikon attribution footer (CC BY-SA 3.0, legally required)
// ─────────────────────────────────────────────────────────────────────────────

class _KlexikonAttribution extends StatelessWidget {
  final String url;
  final bool dark;
  const _KlexikonAttribution({required this.url, this.dark = false});

  @override
  Widget build(BuildContext context) {
    final color = dark
        ? Colors.white.withValues(alpha: 0.40)
        : const Color(0xFF2D6A4F).withValues(alpha: 0.55);
    return GestureDetector(
      onTap: () async {
        final uri = Uri.tryParse(url);
        if (uri != null) {
          await _launchUrlWithParentalAuth(context, uri);
        }
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: Text(
          'Quelle: klexikon.zum.de  ·  Lizenz: CC BY-SA 3.0',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 11,
            color: color,
            decoration: TextDecoration.underline,
            decorationColor: color,
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Vollbild-Galerie — öffnet sich beim Antippen des Hauptbilds.
// Wischen links/rechts: nächstes/vorheriges Bild.
// Nach 2,5s Wisch-Pause mit Caption: Professor unterbricht sich.
// Schliessen: ← Zurück, Wischen nach unten.
// ─────────────────────────────────────────────────────────────────────────────

class _FullscreenGallery extends StatefulWidget {
  final int initialIndex;
  final Animation<double> animation;

  const _FullscreenGallery({
    required this.initialIndex,
    required this.animation,
  });

  @override
  State<_FullscreenGallery> createState() => _FullscreenGalleryState();
}

class _FullscreenGalleryState extends State<_FullscreenGallery> {
  late int _currentIndex;
  final _futures    = <String, Future<Uint8List?>>{};
  final _hiResBytes = <String, Uint8List?>{};   // null = loading, value = done
  Timer? _swipeSettleTimer;
  bool _speakerWasUsed = false;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    // HiRes-Download für das erste Bild starten sobald Provider verfügbar.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final images = context.read<WissensfreundProvider>().articleImages;
      if (images.isNotEmpty) _loadHiRes(images[_currentIndex].filename);
    });
  }

  @override
  void dispose() {
    _swipeSettleTimer?.cancel();
    restoreSystemUI();
    super.dispose();
  }

  Future<Uint8List?> _futureFor(String fn, WissensfreundProvider p) =>
      _futures.putIfAbsent(fn, () => p.getImageBytes(fn));

  void _loadHiRes(String filename) {
    // Free users never get on-demand hires.
    if (!SubscriptionService.instance.canUseHighResOnDemand) return;

    if (_hiResBytes.containsKey(filename)) return;
    _hiResBytes[filename] = null; // mark as in-flight

    // Pre-check data limit so we can show the overlay instead of silently failing.
    NetworkService.instance
        .canUseNetwork(estimatedBytes: 3 * 1024 * 1024)
        .then((check) async {
      if (!check.allowed && check.reason == 'limit_reached') {
        if (mounted) unawaited(_triggerDataLimitOverlay(filename));
        return;
      }
      HiResImageService.instance.getHiResImage(filename).then((bytes) {
        if (mounted && bytes != null) {
          setState(() => _hiResBytes[filename] = bytes);
        }
      });
    });
  }

  Future<void> _triggerDataLimitOverlay(String filename) async {
    final provider = context.read<WissensfreundProvider>();

    // Professor finishes current state and speaks handoff phrase.
    await provider.pauseForDataLimit();
    if (!mounted) return;

    final conn    = await NetworkService.instance.getCurrentConnectionType();
    final connStr = conn == ConnectionType.wifi ? 'wifi' : 'mobile';

    DataLimitOverlayService.instance.show(
      connectionType: connStr,
      onRetry: () {
        _hiResBytes.remove(filename); // allow retry
        if (mounted) _loadHiRes(filename);
        provider.resumeAfterDataLimit();
      },
      onCancel: () {
        _hiResBytes.remove(filename); // clear in-flight marker
        provider.speakDataLimitCancelled();
      },
    );
  }

  void _swipe(DragEndDetails d) {
    final v = d.primaryVelocity ?? 0;
    if (v.abs() < 200) return;
    final provider = context.read<WissensfreundProvider>();
    final images   = provider.articleImages;
    final next     = v < 0 ? _currentIndex + 1 : _currentIndex - 1;
    if (next < 0 || next >= images.length) return;

    // Merken ob 🔊 beim aktuellen Bild gedrückt wurde → Auto-Vorlesen für nächstes
    final autoRead = _speakerWasUsed;
    _speakerWasUsed = false;

    provider.onThumbnailTap(next);
    setState(() => _currentIndex = next);
    _loadHiRes(images[next].filename);
    _swipeSettleTimer?.cancel();
    _swipeSettleTimer = Timer(const Duration(milliseconds: 2500), () {
      if (!mounted) return;
      if (!autoRead) return; // Kein Auto-Vorlesen wenn Nutzer 🔊 nicht gedrückt hat
      final caption = images[next].caption;
      if (caption != null && caption.isNotEmpty) {
        provider.interruptForCaption(caption);
      }
    });
  }

  void _close() {
    _swipeSettleTimer?.cancel();
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        final images       = provider.articleImages;
        final cur          = _currentIndex.clamp(0, images.isEmpty ? 0 : images.length - 1);
        final image        = images.isEmpty ? null : images[cur];
        final fn           = image?.filename;
        final caption      = image?.caption;
        final hasCaption   = caption != null && caption.isNotEmpty;
        final fromKlexikon = image?.fromKlexikon ?? false;
        final future       = fn != null ? _futureFor(fn, provider) : null;

        return Stack(
          fit: StackFit.expand,
          children: [
            // Immediate black backdrop
            const ColoredBox(color: Colors.black),

            // Fade + zoom entry animation
            FadeTransition(
              opacity: widget.animation,
              child: ScaleTransition(
                scale: Tween<double>(begin: 0.88, end: 1.0).animate(
                  CurvedAnimation(parent: widget.animation, curve: Curves.easeOutCubic),
                ),
                child: Scaffold(
                  backgroundColor: Colors.black,
                  body: SafeArea(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onHorizontalDragEnd: _swipe,
                      onVerticalDragEnd: (d) {
                        if ((d.primaryVelocity ?? 0) > 300) _close();
                      },
                      child: Column(
                        children: [
                          // ── Bildbereich ─────────────────────────────────
                          Expanded(
                            child: AnimatedSwitcher(
                              duration: const Duration(milliseconds: 220),
                              child: future == null
                                  ? const Center(
                                      key: ValueKey('loading'),
                                      child: CircularProgressIndicator(
                                        color: Colors.white54,
                                      ),
                                    )
                                  : FutureBuilder<Uint8List?>(
                                      key: ValueKey(fn),
                                      future: future,
                                      builder: (_, snap) {
                                        final bytes = snap.data;
                                        final hiRes = fn != null ? _hiResBytes[fn] : null;
                                        return Stack(
                                          fit: StackFit.expand,
                                          children: [
                                            // Base image layer
                                            bytes == null
                                                ? const Center(
                                                    child: CircularProgressIndicator(
                                                        color: Colors.white54))
                                                : InteractiveViewer(
                                                    minScale: 1.0,
                                                    maxScale: 4.0,
                                                    clipBehavior: Clip.none,
                                                    child: SizedBox.expand(
                                                      child: Image.memory(
                                                        bytes,
                                                        fit: BoxFit.contain,
                                                      ),
                                                    ),
                                                  ),
                                            // HiRes overlay — crossfade 300ms when loaded
                                            if (bytes != null)
                                              AnimatedSwitcher(
                                                duration: const Duration(milliseconds: 300),
                                                child: hiRes != null
                                                    ? SizedBox.expand(
                                                        key: ValueKey('hires_$fn'),
                                                        child: InteractiveViewer(
                                                          minScale: 1.0,
                                                          maxScale: 4.0,
                                                          clipBehavior: Clip.none,
                                                          child: Image.memory(
                                                            hiRes,
                                                            fit: BoxFit.contain,
                                                          ),
                                                        ),
                                                      )
                                                    : const SizedBox.shrink(
                                                        key: ValueKey('no_hires'),
                                                      ),
                                              ),
                                            // 🔍 Upgrade-Hinweis für Free-Nutzer
                                            if (SubscriptionService.instance.isFree &&
                                                provider.state != AppState.speaking)
                                              Positioned(
                                                bottom: 16,
                                                left: 16,
                                                right: 48,
                                                child: _UpgradeHint(),
                                              ),
                                            // ⓘ Lizenz
                                            if (fn != null)
                                              Positioned(
                                                bottom: 16,
                                                right: 16,
                                                child: _LicenseInfoButton(filename: fn, fromKlexikon: fromKlexikon),
                                              ),
                                          ],
                                        );
                                      },
                                    ),
                            ),
                          ),

                          // ── 🔊 Button + Bildtext unter dem Bild ──────────────
                          if (hasCaption) ...[
                            // Lautsprecher-Button
                            Padding(
                              padding: const EdgeInsets.only(top: 10),
                              child: Center(
                                child: GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: () {
                                    setState(() => _speakerWasUsed = true);
                                    provider.interruptForCaption(caption);
                                  },
                                  child: Container(
                                    width: 52,
                                    height: 52,
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF1B4332)
                                          .withValues(alpha: 0.88),
                                      shape: BoxShape.circle,
                                      border: Border.all(
                                        color: Colors.white.withValues(alpha: 0.35),
                                        width: 1.5,
                                      ),
                                    ),
                                    child: const Icon(
                                      Icons.volume_up_rounded,
                                      color: Colors.white,
                                      size: 26,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            // Bildtext — scrollbar bei langem Text, max. ~5 Zeilen
                            ConstrainedBox(
                              constraints: const BoxConstraints(maxHeight: 110),
                              child: GestureDetector(
                                behavior: HitTestBehavior.opaque,
                                onTap: () {},
                                child: SingleChildScrollView(
                                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
                                  child: Text(
                                    caption,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      color: Colors.white70,
                                      fontSize: 13,
                                      height: 1.4,
                                      fontStyle: FontStyle.italic,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],

                          // ── ← Zurück-Button ───────────────────────────────
                          Padding(
                            padding: const EdgeInsets.fromLTRB(0, 10, 0, 20),
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: _close,
                              child: Container(
                                height: 56,
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 28),
                                decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.13),
                                  borderRadius: BorderRadius.circular(28),
                                ),
                                child: const Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(Icons.arrow_back_rounded,
                                        color: Colors.white, size: 26),
                                    SizedBox(width: 10),
                                    Text(
                                      'Zurück',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 18,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),

            // Caption-Resume-Prompt — schwimmt über allem
            if (provider.showCaptionResumePrompt)
              const Positioned(
                bottom: 100,
                left: 0,
                right: 0,
                child: Center(child: _CaptionResumeOverlay()),
              ),
          ],
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Caption-Resume Overlay — shown after caption is read, countdown to auto-resume
// ─────────────────────────────────────────────────────────────────────────────

class _CaptionResumeOverlay extends StatefulWidget {
  const _CaptionResumeOverlay();

  @override
  State<_CaptionResumeOverlay> createState() => _CaptionResumeOverlayState();
}

class _CaptionResumeOverlayState extends State<_CaptionResumeOverlay> {
  int _countdown = 5;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (_countdown <= 1) { t.cancel(); return; }
      setState(() => _countdown--);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => context.read<WissensfreundProvider>().resumeAfterCaption(),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 13),
        decoration: BoxDecoration(
          color: const Color(0xFF2D6A4F),
          borderRadius: BorderRadius.circular(32),
          boxShadow: const [
            BoxShadow(color: Colors.black26, blurRadius: 14, offset: Offset(0, 4)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.play_arrow_rounded, color: Colors.white, size: 22),
            const SizedBox(width: 8),
            Text(
              'Weiterlesen ($_countdown)',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared image-swipe logic (Stufe 1: free swipe; Stufe 2/3: TTS-synced)
// ─────────────────────────────────────────────────────────────────────────────

/// Handles a horizontal drag end for all three modes.
/// [onLeftSwipe] is called when the user swipes backward (older image) on
/// Stufe 2/3 — the caller should start a 10 s timer to resync.
void _doImageSwipe(
  DragEndDetails d,
  WissensfreundProvider provider,
  int ageLevel,
  VoidCallback onLeftSwipe,
) {
  final v = d.primaryVelocity ?? 0;
  if (v.abs() < 200) return;
  final images     = provider.articleImages;
  final mediaItems = provider.mediaItems;
  if (images.isEmpty) return;
  final cur  = provider.selectedImageIndex.clamp(0, images.length - 1);
  final next = v < 0 ? cur + 1 : cur - 1; // left-swipe = next image (forward)
  if (next < 0 || next >= images.length) return;
  int ic = 0;
  for (int i = 0; i < mediaItems.length; i++) {
    if (!mediaItems[i].isAudio) {
      if (ic == next) { provider.onMediaTap(i); break; }
      ic++;
    }
  }
  if (ageLevel < 2) return; // Stufe 1: no TTS sync
  final ttsImg = provider.currentTtsImageIndex;
  if (ttsImg < 0) return;  // ZIM article: no img_index data
  if (next > ttsImg) {
    provider.pauseImageSync(); // ahead of TTS → pause; auto-resumes when TTS catches up
  } else if (next < ttsImg) {
    onLeftSwipe();             // behind TTS → caller starts 10 s resync timer
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Callout-Box / Quiz helpers (JSON articles, Mode A + B only)
// ─────────────────────────────────────────────────────────────────────────────

/// Inserts [CalloutBox] widgets after the last flat sentence of each section.
/// Uses text-content matching: searches the flat sentence list for the text
/// of each section's last [RenderedSentence], then inserts boxes after that index.
/// Returns a new list — original [sentenceWidgets] unchanged.
///
/// [boxKeys]: if provided, GlobalKeys are assigned per box (key = "$sIdx-$bIdx")
///   so Mode B can scroll directly to the active box.
/// [activeSectionIdx]/[activeBoxIdx]: which box is currently being read aloud.
List<Widget> _insertSectionBoxes(
  List<Widget> sentenceWidgets,
  List<String> sentences,
  List<RenderedSection> sections, {
  Map<String, GlobalKey>? boxKeys,
  int activeSectionIdx = -1,
  int activeBoxIdx = -1,
}) {
  if (sections.isEmpty || sentences.isEmpty) return sentenceWidgets;
  if (sections.every((s) => s.boxes.isEmpty)) return sentenceWidgets;

  // For each section with boxes, find the flat-sentence index that contains
  // the last sentence of that section, then record (sectionIdx, boxes) after it.
  final Map<int, (int sIdx, List<RenderedBox> boxes)> boxesAfter = {};
  int searchFrom = 0;
  for (int sIdx = 0; sIdx < sections.length; sIdx++) {
    final sec = sections[sIdx];
    if (sec.sentences.isEmpty) continue;
    final lastText = sec.sentences.last.text;
    for (int i = searchFrom; i < sentences.length; i++) {
      if (sentences[i] == lastText || sentences[i].contains(lastText)) {
        if (sec.boxes.isNotEmpty) boxesAfter[i] = (sIdx, sec.boxes);
        searchFrom = i + 1;
        break;
      }
    }
  }

  if (boxesAfter.isEmpty) return sentenceWidgets;

  final result = <Widget>[];
  for (int i = 0; i < sentenceWidgets.length; i++) {
    result.add(sentenceWidgets[i]);
    final entry = boxesAfter[i];
    if (entry != null) {
      final (sIdx, boxes) = entry;
      for (int bIdx = 0; bIdx < boxes.length; bIdx++) {
        final gKey = boxKeys?.putIfAbsent('$sIdx-$bIdx', () => GlobalKey());
        result.add(Padding(
          key: gKey,
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: CalloutBox(
            box: boxes[bIdx],
            isActive: sIdx == activeSectionIdx && bIdx == activeBoxIdx,
          ),
        ));
      }
    }
  }
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared sentence utilities
// ─────────────────────────────────────────────────────────────────────────────

List<String> _splitSentences(String text) {
  if (text.isEmpty) return [];
  // \d+(?:[.,]\d+)+ matches German numbers (1.000, 1.000.000, 1,5) as one unit
  // so the period/comma inside them is not treated as a sentence boundary.
  final matches = RegExp(r'(?:\d+(?:[.,]\d+)+|[^.!?])+[.!?]+\s*').allMatches(text);
  final result = matches.map((m) => m.group(0)!.trim()).toList();
  return result.isEmpty ? [text] : result;
}

int _findActiveIdx(String text, int cursor, List<String> sentences) {
  if (sentences.isEmpty) return 0;
  int pos = 0;
  for (int i = 0; i < sentences.length; i++) {
    pos += sentences[i].length + 1;
    if (pos > cursor) return i;
  }
  return sentences.length - 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// MODE A — Volltext mit Highlighting
// ─────────────────────────────────────────────────────────────────────────────

class _ModeAContent extends StatefulWidget {
  const _ModeAContent({super.key});

  @override
  State<_ModeAContent> createState() => _ModeAContentState();
}

class _ModeAContentState extends State<_ModeAContent> {
  final _scrollCtrl = ScrollController();
  final _sentenceKeys = <int, GlobalKey>{};
  int _lastActiveIdx = -1;
  String _lastArticleText = '';
  bool _scrollPending = false;
  bool _userScrolling = false;     // true while user is manually scrolling
  bool _programmaticScroll = false; // suppresses _onScroll during TTS auto-scroll
  Timer? _programmaticScrollTimer;

  // Cached full-width document positions (in scroll-content coordinates).
  // Built once after the first render when all sentences are at full width.
  // Stable across scroll events → no feedback-loop oscillation.
  final _sentenceTopCache = <int, double>{};
  final _sentenceHeightCache = <int, double>{};
  bool _cacheBuilt = false;

  // Stufe 2/3: debounce timer for scroll-jump navigation.
  Timer? _scrollDebounce;
  // Keeps _userScrolling=true until pending seek takes effect (prevents snap-back).
  Timer? _seekResumeTimer;
  // Stufe 2/3: resync timer after backward image swipe (10 s).
  Timer? _syncResetTimer;

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
    // After the first frame: render objects exist → recompute professor zone,
    // then jump instantly to the active sentence (handles B→A and C→A switch).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _buildCache(); // snapshot full-width positions BEFORE zone padding applied
      setState(() {}); // now zone uses stable cached positions
      final provider = context.read<WissensfreundProvider>();
      final sentences = _splitSentences(provider.articleText);
      final idx = _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);
      if (idx <= 0) return;
      _lastActiveIdx = idx;
      final ctx = _sentenceKeys[idx]?.currentContext;
      if (ctx == null) return;
      Scrollable.ensureVisible(ctx, duration: Duration.zero, alignment: 0.15);
    });
  }

  void _onScroll() {
    if (!mounted) return;
    setState(() {});
    if (_programmaticScroll) return; // ignore scroll events from TTS auto-scroll
    _userScrolling = true;
    final ageLevel = ProfileService.instance.activeAgeLevel;
    if (ageLevel < 2) {
      _scrollDebounce?.cancel();
      _scrollDebounce = Timer(const Duration(milliseconds: 300), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    _scrollDebounce?.cancel();
    _scrollDebounce = Timer(const Duration(milliseconds: 300), _jumpToTopSentence);
  }

  void _jumpToTopSentence() {
    if (!mounted || !_scrollCtrl.hasClients || !_cacheBuilt) { _userScrolling = false; return; }
    final provider = context.read<WissensfreundProvider>();
    // Never seek while a box chunk is active — boxes have no sentence position.
    if (provider.currentChunkIsBox) { _userScrolling = false; return; }
    final sentences = _splitSentences(provider.articleText);
    if (sentences.isEmpty) { _userScrolling = false; return; }
    final activeIdx = _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);
    final scrollOffset = _scrollCtrl.offset;
    final vpH = _scrollCtrl.position.viewportDimension;

    // No jump if the current TTS sentence is already visible.
    final activeDocY = _sentenceTopCache[activeIdx];
    if (activeDocY != null) {
      final activeViewY = activeDocY - scrollOffset;
      if (activeViewY >= 0 && activeViewY < vpH) { _userScrolling = false; return; }
    }

    // Find the topmost fully visible sentence.
    int topIdx = -1;
    double minY = double.infinity;
    for (int i = 0; i < sentences.length; i++) {
      final docY = _sentenceTopCache[i];
      if (docY == null) continue;
      final h = _sentenceHeightCache[i] ?? 24.0;
      final viewY = docY - scrollOffset;
      if (viewY >= 0 && viewY + h <= vpH && viewY < minY) {
        minY = viewY;
        topIdx = i;
      }
    }
    if (topIdx < 0) {
      // User scrolled past all sentence content — cancel pending seek and lock scroll.
      provider.cancelPendingSeek();
      _seekResumeTimer?.cancel();
      _seekResumeTimer = Timer(const Duration(milliseconds: 2000), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    if (topIdx == activeIdx) {
      provider.cancelPendingSeek(); // restart TTS if it was stopped for a delayed seek
      _userScrolling = false;
      return;
    }
    if (topIdx == activeIdx + 1) {
      // Only 1 sentence ahead — likely viewing box content between sentences.
      // Cancel any stale pending seek and let TTS advance naturally through box chunks.
      provider.cancelPendingSeek();
      _seekResumeTimer?.cancel();
      _seekResumeTimer = Timer(const Duration(milliseconds: 3000), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    if (provider.isPaused) { _userScrolling = false; return; }

    // Compute char offset by summing sentence lengths up to topIdx.
    // If sentences[topIdx] is a heading-merged sentence (contains \n), advance past the heading
    // so the seek lands on the real sentence start rather than the heading gap.
    int charOffset = 0;
    for (int i = 0; i < topIdx; i++) {
      charOffset += sentences[i].length + 1; // +1 for the stripped delimiter
    }
    final nl = sentences[topIdx].indexOf('\n');
    if (nl >= 0) charOffset += nl + 1;

    // seekWithDelay: TTS stops immediately, restarts after 1.2s at new position.
    // To revert: replace seekWithDelay with seekAfterCurrentChunk and timer with 3000ms.
    provider.seekWithDelay(charOffset);
    _seekResumeTimer?.cancel();
    _seekResumeTimer = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) _userScrolling = false;
    });
  }

  void _startSyncResetTimer(WissensfreundProvider provider) {
    _syncResetTimer?.cancel();
    _syncResetTimer = Timer(const Duration(seconds: 10), () {
      if (!mounted) return;
      final ttsImg = provider.currentTtsImageIndex;
      if (ttsImg < 0) return;
      final media = provider.mediaItems;
      int ic = 0;
      for (int i = 0; i < media.length; i++) {
        if (!media[i].isAudio) {
          if (ic == ttsImg) { provider.onMediaTap(i); break; }
          ic++;
        }
      }
    });
  }

  void _swipeImage(DragEndDetails d, WissensfreundProvider provider) {
    final ageLevel = ProfileService.instance.activeAgeLevel;
    _doImageSwipe(d, provider, ageLevel, () => _startSyncResetTimer(provider));
  }

  @override
  void dispose() {
    _scrollDebounce?.cancel();
    _seekResumeTimer?.cancel();
    _syncResetTimer?.cancel();
    _programmaticScrollTimer?.cancel();
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  GlobalKey _keyFor(int i) =>
      _sentenceKeys.putIfAbsent(i, () => GlobalKey());

  // Scroll DOWN to active sentence only if it has drifted below 50% of viewport.
  // Blocked while user is manually scrolling (_userScrolling = true).
  void _smartScrollTo(int idx) {
    if (_scrollPending || _userScrolling) return;
    _lastActiveIdx = idx;
    _scrollPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollPending = false;
      if (!mounted || !_scrollCtrl.hasClients) return;
      final ctx = _sentenceKeys[idx]?.currentContext;
      if (ctx == null) return;

      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null) return;

      // Sentence y-position relative to the scroll viewport
      final scrollable = Scrollable.of(ctx);
      final vpBox = scrollable.context.findRenderObject() as RenderBox?;
      if (vpBox == null) return;
      final localY = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      final viewportH = _scrollCtrl.position.viewportDimension;

      // Scroll if sentence is above viewport or below the lower third
      if (localY < 0 || localY > viewportH * 0.6) {
        _programmaticScroll = true;
        _programmaticScrollTimer?.cancel();
        _programmaticScrollTimer = Timer(const Duration(milliseconds: 600), () {
          _programmaticScroll = false;
        });
        Scrollable.ensureVisible(
          ctx,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOut,
          alignment: 0.5,
        );
      }
    });
  }

  List<Widget> _buildSentenceWidgets({
    required List<String> sentences,
    required int activeIdx,
    required List<bool> inZone,
    required int ttsCursor,
    required bool isSpeaking,
    required bool isPaused,
    required String fullText,
    required List<Map<String, dynamic>> links,
    required void Function(String) onLinkTap,
  }) {
    int activeCursorInSent = -1;
    if ((isSpeaking || isPaused) && sentences.isNotEmpty && activeIdx >= 0) {
      int sentStart = 0;
      for (int i = 0; i < activeIdx; i++) {
        sentStart += sentences[i].length + 1;
      }
      activeCursorInSent =
          (ttsCursor - sentStart).clamp(0, sentences[activeIdx].length);
    }

    // Pass 1: locate each sentence in fullText (in order).
    final sentStarts = <int>[];
    int scanPos = 0;
    for (final sent in sentences) {
      final idx = fullText.indexOf(sent, scanPos);
      if (idx >= 0) {
        sentStarts.add(idx);
        scanPos = idx + sent.length;
      } else {
        sentStarts.add(scanPos);
      }
    }

    // Pass 2: assign every link to the sentence whose start immediately precedes
    // the link's startChar (half-open interval sentStarts[i] <= s < sentStarts[i+1]).
    // This covers links in inter-sentence whitespace gaps that strict end-boundary
    // checks would miss.
    final sentLinks = List<List<Map<String, dynamic>>>.generate(sentences.length, (_) => []);
    if (links.isNotEmpty && sentStarts.isNotEmpty) {
      for (final link in links) {
        final s = (link['startChar'] as int?) ?? 0;
        final e = (link['endChar']   as int?) ?? 0;
        // Find rightmost sentence whose start is <= link start.
        int assigned = -1;
        for (int i = sentStarts.length - 1; i >= 0; i--) {
          if (s >= sentStarts[i]) { assigned = i; break; }
        }
        if (assigned < 0) continue;
        final base     = sentStarts[assigned];
        final maxLen   = sentences[assigned].length;
        final localS   = s - base;
        final localE   = (e - base).clamp(0, maxLen);
        if (localS < 0 || localS >= maxLen || localS >= localE) continue;
        sentLinks[assigned].add(<String, dynamic>{
          'text':      link['text'],
          'target':    link['target'],
          'startChar': localS,
          'endChar':   localE,
        });
      }
    }

    final result = <Widget>[];
    for (int i = 0; i < sentences.length; i++) {
      result.add(_SentenceWidget(
        key: _keyFor(i),
        text: sentences[i],
        isActive: i == activeIdx,
        extraRightPad: i == activeIdx ? 0.0 : (inZone[i] ? _kProfPad : 0.0),
        cursorInSent: i == activeIdx ? activeCursorInSent : -1,
        links: sentLinks[i],
        onLinkTap: onLinkTap,
      ));
    }
    return result;
  }

  // Snapshot each sentence's top position (in scroll-content coordinates) while
  // all sentences are still at full width (before zone padding is applied).
  // Called once per article from the first-frame post-frame callback.
  void _buildCache() {
    if (_cacheBuilt || !_scrollCtrl.hasClients) return;
    _sentenceTopCache.clear();
    _sentenceHeightCache.clear();
    final scrollOffset = _scrollCtrl.offset;
    RenderBox? vpBox;
    for (int i = 0; i < _sentenceKeys.length; i++) {
      final ctx = _sentenceKeys[i]?.currentContext;
      if (ctx == null) continue;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.attached) continue;
      vpBox ??= Scrollable.maybeOf(ctx)?.context.findRenderObject() as RenderBox?;
      if (vpBox == null || !vpBox.attached) break;
      final topInVp = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      _sentenceTopCache[i] = topInVp + scrollOffset;
      _sentenceHeightCache[i] = box.size.height;
    }
    if (_sentenceTopCache.isNotEmpty) _cacheBuilt = true;
  }

  // Uses stable cached document positions so zone membership never oscillates:
  // applying zone padding shifts sentences down, but cached docY values don't
  // change → no feedback loop between zone assignment and position measurement.
  List<bool> _computeProfessorZone({
    required int count,
    required double viewportH,
  }) {
    if (count == 0) return const [];
    if (!_cacheBuilt || !_scrollCtrl.hasClients) return List.filled(count, false);
    final scrollOffset = _scrollCtrl.offset;
    final profTopDoc = scrollOffset + viewportH - _kProfZone;
    final profBottomDoc = scrollOffset + viewportH;
    return List.generate(count, (i) {
      final docY = _sentenceTopCache[i];
      if (docY == null) return false;
      final h = _sentenceHeightCache[i] ?? 24.0;
      return (docY + h) > profTopDoc && docY < profBottomDoc;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final sentences = _splitSentences(provider.articleText);
        final activeIdx = provider.currentChunkIsBox
            ? -1
            : _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);

        // Reset keys + cache when article changes; rebuild after full-width render.
        if (provider.articleText != _lastArticleText) {
          _lastArticleText = provider.articleText;
          _sentenceKeys.clear();
          _sentenceTopCache.clear();
          _sentenceHeightCache.clear();
          _cacheBuilt = false;
          _lastActiveIdx = -1;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            if (_scrollCtrl.hasClients) _scrollCtrl.jumpTo(0);
            _buildCache();
            setState(() {});
          });
        }

        // Auto-scroll: pull active sentence to near top when speaking.
        // _lastActiveIdx is updated inside _smartScrollTo only when scroll actually fires —
        // so blocked calls (during _userScrolling) keep retrying on every rebuild.
        if (provider.state == AppState.speaking && activeIdx != _lastActiveIdx) {
          _smartScrollTo(activeIdx);
        }

        return Column(
          children: [
            _ArticleHeader(provider: provider),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onHorizontalDragEnd: (d) => _swipeImage(d, provider),
              child: SizedBox(
                height: (MediaQuery.of(context).size.height * 0.25).clamp(150.0, 260.0),
                width: double.infinity,
                child: _MainArticleImage(fallbackTitle: provider.articleTitle),
              ),
            ),
            Expanded(
              child: LayoutBuilder(
                builder: (ctx, constraints) {
                  final inZone = _computeProfessorZone(
                    count: sentences.length,
                    viewportH: constraints.maxHeight,
                  );
                  return SingleChildScrollView(
                    controller: _scrollCtrl,
                    padding: const EdgeInsets.fromLTRB(12, 10, 8, _kMicClear),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          provider.articleTitle,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF2D6A4F),
                          ),
                        ),
                        const SizedBox(height: 8),
                        ..._insertSectionBoxes(
                          _buildSentenceWidgets(
                            sentences: sentences,
                            activeIdx: activeIdx,
                            inZone: inZone,
                            ttsCursor: provider.ttsCursor,
                            isSpeaking: provider.state == AppState.speaking,
                            isPaused: provider.isPaused,
                            fullText: provider.articleText,
                            links: provider.articleLinks,
                            onLinkTap: provider.onLinkTapped,
                          ),
                          sentences,
                          provider.articleSections,
                          activeSectionIdx: provider.currentBoxSectionIdx,
                          activeBoxIdx: provider.currentBoxInSectionIdx,
                        ),
                        _ThumbnailRow(
                          images: provider.articleImages,
                          selectedIndex: provider.selectedImageIndex,
                          onTap: provider.onImageSelected,
                        ),
                        if (sentences.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          _KlexikonAttribution(url: provider.articleUrl),
                        ],
                        if (provider.articleQuiz != null &&
                            provider.articleQuiz!.questions.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 24, bottom: _kProfZone),
                            child: QuizWidget(quiz: provider.articleQuiz!),
                          ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }
}

class _SentenceWidget extends StatefulWidget {
  final String text;
  final bool isActive;
  final double extraRightPad;
  final int cursorInSent;
  final List<Map<String, dynamic>> links;
  final void Function(String) onLinkTap;

  const _SentenceWidget({
    super.key,
    required this.text,
    required this.isActive,
    required this.extraRightPad,
    this.cursorInSent = -1,
    this.links = const [],
    required this.onLinkTap,
  });

  @override
  State<_SentenceWidget> createState() => _SentenceWidgetState();
}

class _SentenceWidgetState extends State<_SentenceWidget> {
  final _recognizers = <TapGestureRecognizer>[];
  List<InlineSpan>? _cachedSpans;
  String? _cachedText;
  int _cachedLinksLen = -1;

  static const _base = TextStyle(fontSize: 14, height: 1.85);
  static const _linkStyle = TextStyle(
    fontSize: 14,
    height: 1.85,
    color: Color(0xFF1565C0),
    decoration: TextDecoration.underline,
    decorationColor: Color(0xFF1565C0),
  );

  @override
  void dispose() {
    _clearRecognizers();
    super.dispose();
  }

  void _clearRecognizers() {
    for (final r in _recognizers) r.dispose();
    _recognizers.clear();
  }

  List<InlineSpan> _inactiveSpans() {
    if (widget.text == _cachedText && widget.links.length == _cachedLinksLen) {
      return _cachedSpans!;
    }
    _clearRecognizers();
    _cachedText = widget.text;
    _cachedLinksLen = widget.links.length;

    final baseStyle = _base.copyWith(color: const Color(0xFF333333));
    if (widget.links.isEmpty) {
      _cachedSpans = [TextSpan(text: widget.text, style: baseStyle)];
      return _cachedSpans!;
    }

    final spans = <InlineSpan>[];
    int cursor = 0;
    for (final link in widget.links) {
      final start  = (link['startChar'] as int?) ?? 0;
      final end    = (link['endChar']   as int?) ?? 0;
      final target = link['target']  as String? ?? '';
      final lText  = link['text']    as String? ?? '';
      if (start < cursor || start >= widget.text.length ||
          end > widget.text.length || lText.isEmpty) continue;
      if (start > cursor) {
        spans.add(TextSpan(text: widget.text.substring(cursor, start), style: baseStyle));
      }
      final rec = TapGestureRecognizer()..onTap = () => widget.onLinkTap(target);
      _recognizers.add(rec);
      spans.add(TextSpan(text: lText, style: _linkStyle, recognizer: rec));
      cursor = end;
    }
    if (cursor < widget.text.length) {
      spans.add(TextSpan(text: widget.text.substring(cursor), style: baseStyle));
    }
    _cachedSpans = spans;
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    // ── Window highlight: stable at punctuation boundaries ────────────────
    if (widget.isActive && widget.cursorInSent >= 0 && widget.text.isNotEmpty) {
      final pos = widget.cursorInSent.clamp(0, widget.text.length);
      int baseStart = 0;
      for (int i = pos - 1; i >= 0; i--) {
        if ('.,:!?;'.contains(widget.text[i])) {
          baseStart = i + 1;
          while (baseStart < widget.text.length && widget.text[baseStart] == ' ') baseStart++;
          break;
        }
      }
      int baseEnd = widget.text.length;
      for (int i = pos; i < widget.text.length; i++) {
        if ('.,:!?;'.contains(widget.text[i])) { baseEnd = i + 1; break; }
      }
      final wStart = (baseStart < pos - 20 ? baseStart : pos - 20).clamp(0, pos);
      final wEnd   = (baseEnd > pos + 20 ? baseEnd : pos + 20).clamp(pos, widget.text.length);
      return Padding(
        padding: EdgeInsets.only(right: widget.extraRightPad, bottom: 4),
        child: Text.rich(
          TextSpan(
            style: _base.copyWith(color: const Color(0xFF333333)),
            children: [
              if (wStart > 0) TextSpan(text: widget.text.substring(0, wStart)),
              TextSpan(
                text: widget.text.substring(wStart, wEnd),
                style: _base.copyWith(
                  color: const Color(0xFF1B4332),
                  fontWeight: FontWeight.bold,
                  backgroundColor: const Color(0xFFC8EDDA),
                ),
              ),
              if (wEnd < widget.text.length) TextSpan(text: widget.text.substring(wEnd)),
            ],
          ),
        ),
      );
    }

    // ── Full-sentence highlight (active, paused / idle) ────────────────────
    if (widget.isActive) {
      return Padding(
        padding: EdgeInsets.only(right: widget.extraRightPad, bottom: 4),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
          decoration: BoxDecoration(
            color: const Color(0xFFC8EDDA),
            borderRadius: BorderRadius.circular(3),
            border: Border.all(color: const Color(0xFF2D6A4F), width: 2),
          ),
          child: Text(
            widget.text,
            style: _base.copyWith(
              fontWeight: FontWeight.bold,
              color: const Color(0xFF1B4332),
            ),
          ),
        ),
      );
    }

    // ── Inactive sentence — with tappable links ────────────────────────────
    return Padding(
      padding: EdgeInsets.only(right: widget.extraRightPad, bottom: 4),
      child: Text.rich(TextSpan(children: _inactiveSpans())),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODE B — Fokus: aktueller Satz groß, Bild oben, Progress, Thumbnails
// ─────────────────────────────────────────────────────────────────────────────

class _ModeBContent extends StatefulWidget {
  const _ModeBContent({super.key});

  @override
  State<_ModeBContent> createState() => _ModeBContentState();
}

class _ModeBContentState extends State<_ModeBContent> {
  final _scrollCtrl = ScrollController();
  final _sentenceKeys = <int, GlobalKey>{};
  int _lastActiveIdx = -1;
  String? _lastBoxKey;           // last '$sIdx-$bIdx' key scrolled to
  final _boxKeys = <String, GlobalKey>{}; // GlobalKey per box widget
  String _lastArticleText = '';
  bool _scrollPending = false;
  bool _userScrolling = false;
  bool _programmaticScroll = false;
  Timer? _programmaticScrollTimer;
  Timer? _scrollDebounce;
  Timer? _syncResetTimer;
  Timer? _seekResumeTimer;

  final _sentenceTopCache = <int, double>{};
  bool _cacheBuilt = false;

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _buildCache();
      final provider = context.read<WissensfreundProvider>();
      final sentences = _splitSentences(provider.articleText);
      final idx = _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);
      if (idx <= 0) return;
      _lastActiveIdx = idx;
      final ctx = _sentenceKeys[idx]?.currentContext;
      if (ctx == null) return;
      Scrollable.ensureVisible(ctx, duration: Duration.zero, alignment: 0.1);
    });
  }

  void _onScroll() {
    if (!mounted) return;
    if (_programmaticScroll) return;
    _userScrolling = true;
    _seekResumeTimer?.cancel();
    final ageLevel = ProfileService.instance.activeAgeLevel;
    if (ageLevel < 2) {
      _scrollDebounce?.cancel();
      _scrollDebounce = Timer(const Duration(milliseconds: 300), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    _scrollDebounce?.cancel();
    _scrollDebounce = Timer(const Duration(milliseconds: 300), _jumpToTopSentence);
  }

  void _jumpToTopSentence() {
    // _userScrolling stays TRUE here — only reset after seek settles or no seek needed
    if (!mounted || !_scrollCtrl.hasClients) { _userScrolling = false; return; }
    final provider = context.read<WissensfreundProvider>();
    // Never seek while a box chunk is active — boxes have no sentence position.
    if (provider.currentChunkIsBox) { _userScrolling = false; return; }
    final sentences = _splitSentences(provider.articleText);
    if (sentences.isEmpty) { _userScrolling = false; return; }
    final activeIdx = _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);

    // Live render query — avoids stale positions caused by font-size changes (active: 19px, inactive: 15px)
    RenderBox? vpBox;
    int topIdx = -1;
    double minY = double.infinity;
    for (int i = 0; i < sentences.length; i++) {
      final ctx = _sentenceKeys[i]?.currentContext;
      if (ctx == null) continue;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.attached) continue;
      vpBox ??= Scrollable.maybeOf(ctx)?.context.findRenderObject() as RenderBox?;
      if (vpBox == null || !vpBox.attached) break;
      final localY = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      if (localY >= 0 && localY < minY) {
        minY = localY;
        topIdx = i;
      }
    }

    if (topIdx < 0) {
      // User scrolled past all sentence content — cancel pending seek and lock scroll.
      provider.cancelPendingSeek();
      _seekResumeTimer?.cancel();
      _seekResumeTimer = Timer(const Duration(milliseconds: 2000), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    if (topIdx == activeIdx) {
      provider.cancelPendingSeek(); // restart TTS if it was stopped for a delayed seek
      _userScrolling = false;
      return;
    }
    if (topIdx == activeIdx + 1) {
      // Only 1 sentence ahead — likely viewing box content between sentences.
      // Cancel any stale pending seek and let TTS advance naturally through box chunks.
      provider.cancelPendingSeek();
      _seekResumeTimer?.cancel();
      _seekResumeTimer = Timer(const Duration(milliseconds: 3000), () {
        if (mounted) _userScrolling = false;
      });
      return;
    }
    if (provider.isPaused) { _userScrolling = false; return; }

    // Compute char offset by summing sentence lengths up to topIdx.
    // If sentences[topIdx] is a heading-merged sentence (contains \n), advance past the heading
    // so the seek lands on the real sentence start rather than the heading gap.
    int charOffset = 0;
    for (int i = 0; i < topIdx; i++) {
      charOffset += sentences[i].length + 1;
    }
    final nl = sentences[topIdx].indexOf('\n');
    if (nl >= 0) charOffset += nl + 1;

    // seekWithDelay: TTS stops immediately, restarts after 1.2s at new position.
    // To revert: replace seekWithDelay with seekAfterCurrentChunk and timer with 3000ms.
    provider.seekWithDelay(charOffset);
    _seekResumeTimer?.cancel();
    _seekResumeTimer = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) _userScrolling = false;
    });
  }

  void _buildCache() {
    if (_cacheBuilt || !_scrollCtrl.hasClients) return;
    _sentenceTopCache.clear();
    final scrollOffset = _scrollCtrl.offset;
    RenderBox? vpBox;
    for (int i = 0; i < _sentenceKeys.length; i++) {
      final ctx = _sentenceKeys[i]?.currentContext;
      if (ctx == null) continue;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.attached) continue;
      vpBox ??= Scrollable.maybeOf(ctx)?.context.findRenderObject() as RenderBox?;
      if (vpBox == null || !vpBox.attached) break;
      final topInVp = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      _sentenceTopCache[i] = topInVp + scrollOffset;
    }
    if (_sentenceTopCache.isNotEmpty) _cacheBuilt = true;
  }

  void _smartScrollTo(int idx) {
    if (_scrollPending || _userScrolling) return;
    _lastActiveIdx = idx;
    _scrollPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollPending = false;
      if (!mounted || !_scrollCtrl.hasClients) return;
      final ctx = _sentenceKeys[idx]?.currentContext;
      if (ctx == null) return;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.attached) return;
      final scrollable = Scrollable.of(ctx);
      final vpBox = scrollable.context.findRenderObject() as RenderBox?;
      if (vpBox == null || !vpBox.attached) return;
      final sentenceTopInVp = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      final sentenceTopInContent = sentenceTopInVp + _scrollCtrl.offset;
      final viewportH = _scrollCtrl.position.viewportDimension;
      // Center the active sentence vertically in the viewport
      final target = (sentenceTopInContent - viewportH / 2 + box.size.height / 2)
          .clamp(_scrollCtrl.position.minScrollExtent, _scrollCtrl.position.maxScrollExtent);
      _programmaticScroll = true;
      _programmaticScrollTimer?.cancel();
      _programmaticScrollTimer = Timer(const Duration(milliseconds: 600), () {
        _programmaticScroll = false;
      });
      _scrollCtrl.animateTo(target,
          duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
    });
  }

  GlobalKey _keyFor(int i) => _sentenceKeys.putIfAbsent(i, () => GlobalKey());

  /// Scrolls to a box widget identified by GlobalKey. Same logic as [_smartScrollTo]
  /// but uses live RenderBox coordinates instead of the sentence position cache.
  void _smartScrollToBox(GlobalKey key, String? boxKey, int rawIdx) {
    if (_scrollPending || _userScrolling) return;
    _lastBoxKey = boxKey;
    _lastActiveIdx = rawIdx;
    _scrollPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollPending = false;
      if (!mounted || !_scrollCtrl.hasClients) return;
      final ctx = key.currentContext;
      if (ctx == null) return;
      final box = ctx.findRenderObject() as RenderBox?;
      if (box == null || !box.attached) return;
      final scrollable = Scrollable.maybeOf(ctx);
      if (scrollable == null) return;
      final vpBox = scrollable.context.findRenderObject() as RenderBox?;
      if (vpBox == null || !vpBox.attached) return;
      final boxTopInVp = vpBox.globalToLocal(box.localToGlobal(Offset.zero)).dy;
      final boxTopInContent = boxTopInVp + _scrollCtrl.offset;
      final viewportH = _scrollCtrl.position.viewportDimension;
      final target = (boxTopInContent - viewportH / 2 + box.size.height / 2)
          .clamp(_scrollCtrl.position.minScrollExtent, _scrollCtrl.position.maxScrollExtent);
      _programmaticScroll = true;
      _programmaticScrollTimer?.cancel();
      _programmaticScrollTimer = Timer(const Duration(milliseconds: 600), () {
        _programmaticScroll = false;
      });
      _scrollCtrl.animateTo(target,
          duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
    });
  }

  void _startSyncResetTimer(WissensfreundProvider provider) {
    _syncResetTimer?.cancel();
    _syncResetTimer = Timer(const Duration(seconds: 10), () {
      if (!mounted) return;
      final ttsImg = provider.currentTtsImageIndex;
      if (ttsImg < 0) return;
      final media = provider.mediaItems;
      int ic = 0;
      for (int i = 0; i < media.length; i++) {
        if (!media[i].isAudio) {
          if (ic == ttsImg) { provider.onMediaTap(i); break; }
          ic++;
        }
      }
    });
  }

  void _swipeImage(DragEndDetails d, WissensfreundProvider provider) {
    final ageLevel = ProfileService.instance.activeAgeLevel;
    _doImageSwipe(d, provider, ageLevel, () => _startSyncResetTimer(provider));
  }

  @override
  void dispose() {
    _scrollDebounce?.cancel();
    _syncResetTimer?.cancel();
    _seekResumeTimer?.cancel();
    _programmaticScrollTimer?.cancel();
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final sentences = _splitSentences(provider.articleText);
        final rawIdx = _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);
        // -1 while box chunk plays → no sentence highlighted; scroll still uses rawIdx
        // so the view follows the last sentence and the box below it stays visible.
        final activeIdx = provider.currentChunkIsBox ? -1 : rawIdx;
        final scrollIdx = provider.currentChunkIsBox ? rawIdx : activeIdx;
        final progress = sentences.isEmpty
            ? 0.0
            : (activeIdx < 0 ? 1.0 : (activeIdx + 1) / sentences.length);

        if (provider.articleText != _lastArticleText) {
          _lastArticleText = provider.articleText;
          _sentenceKeys.clear();
          _boxKeys.clear();
          _sentenceTopCache.clear();
          _cacheBuilt = false;
          _lastActiveIdx = -1;
          _lastBoxKey = null;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            if (_scrollCtrl.hasClients) _scrollCtrl.jumpTo(0);
            _buildCache();
          });
        }

        // Determine box key for the currently active box chunk.
        final sIdx = provider.currentBoxSectionIdx;
        final bIdx = provider.currentBoxInSectionIdx;
        final currentBoxKey = (provider.currentChunkIsBox && sIdx >= 0) ? '$sIdx-$bIdx' : null;

        if (provider.state == AppState.speaking) {
          if (!provider.currentChunkIsBox && scrollIdx != _lastActiveIdx) {
            // Sentence chunk: scroll to the active sentence.
            // _lastActiveIdx is updated inside _smartScrollTo only when not blocked.
            _lastBoxKey = null;
            _smartScrollTo(scrollIdx);
          } else if (provider.currentChunkIsBox && currentBoxKey != _lastBoxKey) {
            // Box chunk: scroll to the active box widget.
            // _lastBoxKey/_lastActiveIdx updated inside _smartScrollToBox only when not blocked.
            final key = currentBoxKey != null ? _boxKeys[currentBoxKey] : null;
            if (key != null) _smartScrollToBox(key, currentBoxKey, scrollIdx);
          }
        }

        return Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFF112D1F), Color(0xFF1A4731), Color(0xFF2D6A4F)],
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ArticleHeader(provider: provider, dark: true),

              // ── Hauptbild ─────────────────────────────────────────────────
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onHorizontalDragEnd: (d) => _swipeImage(d, provider),
                child: SizedBox(
                  height: (MediaQuery.of(context).size.height * 0.32).clamp(180.0, 300.0),
                  width: double.infinity,
                  child: _MainArticleImage(fallbackTitle: provider.articleTitle),
                ),
              ),

              // ── Fortschrittsleiste ────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                child: Row(
                  children: [
                    Expanded(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: progress,
                          backgroundColor: Colors.white.withValues(alpha: 0.15),
                          valueColor: const AlwaysStoppedAnimation(Color(0xFF95D5B2)),
                          minHeight: 4,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Text(
                      sentences.isEmpty ? '' : '${activeIdx + 1} / ${sentences.length}',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.white.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),

              // ShaderMask federt oben/unten nahtlos mit dem Hintergrundgradienten —
              // kein Farbmismatch, weil nur der Alpha-Kanal des Inhalts moduliert wird.
              Expanded(
                child: Column(
                  children: [
                    Expanded(
                      child: ShaderMask(
                        shaderCallback: (rect) => const LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          stops: [0.0, 0.18, 0.72, 1.0],
                          colors: [
                            Colors.transparent,
                            Colors.white,
                            Colors.white,
                            Colors.transparent,
                          ],
                        ).createShader(rect),
                        blendMode: BlendMode.dstIn,
                        child: SingleChildScrollView(
                          controller: _scrollCtrl,
                          padding: const EdgeInsets.fromLTRB(16, 10, 16, 40),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              ..._insertSectionBoxes(
                                [
                                  for (int i = 0; i < sentences.length; i++)
                                    Padding(
                                      key: _keyFor(i),
                                      padding: const EdgeInsets.only(bottom: 12),
                                      child: Text(
                                        sentences[i],
                                        style: TextStyle(
                                          fontSize: i == activeIdx ? 19 : 15,
                                          height: 1.5,
                                          color: i == activeIdx
                                              ? Colors.white
                                              : Colors.white.withValues(alpha: 0.4),
                                          fontWeight: i == activeIdx
                                              ? FontWeight.w600
                                              : FontWeight.w400,
                                        ),
                                      ),
                                    ),
                                ],
                                sentences,
                                provider.articleSections,
                                boxKeys: _boxKeys,
                                activeSectionIdx: provider.currentBoxSectionIdx,
                                activeBoxIdx: provider.currentBoxInSectionIdx,
                              ),
                              // Quellenhinweis am Ende des Textes (im Scrollbereich)
                              _KlexikonAttribution(url: provider.articleUrl, dark: true),
                              if (provider.articleQuiz != null &&
                                  provider.articleQuiz!.questions.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 16, bottom: 8),
                                  child: _QuizStartButton(quiz: provider.articleQuiz!),
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    // Abstand zwischen Textfeld und Thumbnails
                    const SizedBox(height: 20),
                    _ThumbnailRow(
                      images: provider.articleImages,
                      selectedIndex: provider.selectedImageIndex,
                      onTap: provider.onImageSelected,
                    ),
                    const SizedBox(height: _kMicClear),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Thumbnail row — images and audio mixed in document order
// ─────────────────────────────────────────────────────────────────────────────

class _ThumbnailRow extends StatelessWidget {
  final List<ArticleImageInfo> images;
  final int selectedIndex;
  final ValueChanged<int> onTap;

  const _ThumbnailRow({
    required this.images,
    required this.selectedIndex,
    required this.onTap,
  });

  static const _placeholderColors = [
    Color(0xFFB2DFDB), Color(0xFFBBDEFB), Color(0xFFD1C4E9),
    Color(0xFFFFF9C4), Color(0xFFFFCCBC), Color(0xFFC8E6C9),
    Color(0xFFFFCDD2), Color(0xFFE1BEE7),
  ];

  @override
  Widget build(BuildContext context) {
    if (images.isEmpty) return const SizedBox.shrink();

    final selIdx = selectedIndex < 0 ? 0 : selectedIndex;

    return SizedBox(
      height: 108,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.only(right: _kThumbRight),
        itemCount: images.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final name = images[i].filename;
          final color = _placeholderColors[i % _placeholderColors.length];
          return _ThumbTile(
            key: ValueKey(name),
            filename: name,
            placeholderColor: color,
            isSelected: i == selIdx,
            onTap: () => onTap(i),
          );
        },
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sound thumbnail tile — 🎵 icon with pulse animation when playing
// ─────────────────────────────────────────────────────────────────────────────

class _SoundThumbnailTile extends StatefulWidget {
  final bool isSelected;
  final bool isPlaying;

  const _SoundThumbnailTile({
    super.key,
    required this.isSelected,
    required this.isPlaying,
  });

  @override
  State<_SoundThumbnailTile> createState() => _SoundThumbnailTileState();
}

class _SoundThumbnailTileState extends State<_SoundThumbnailTile>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    )..addStatusListener((s) {
        if (s == AnimationStatus.completed) _pulse.reverse();
        if (s == AnimationStatus.dismissed && widget.isPlaying) _pulse.forward();
      });
    _scale = Tween<double>(begin: 1.0, end: 1.18).animate(
      CurvedAnimation(parent: _pulse, curve: Curves.easeInOut),
    );
    if (widget.isPlaying) _pulse.forward();
  }

  @override
  void didUpdateWidget(_SoundThumbnailTile old) {
    super.didUpdateWidget(old);
    if (widget.isPlaying && !_pulse.isAnimating) {
      _pulse.forward();
    } else if (!widget.isPlaying && _pulse.isAnimating) {
      _pulse.stop();
      _pulse.value = 0;
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: 100,
        height: 100,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Background — subtle waveform-like gradient
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: widget.isPlaying
                      ? [const Color(0xFF1B5E20), const Color(0xFF2E7D32)]
                      : [const Color(0xFFE8F5E9), const Color(0xFFC8E6C9)],
                ),
              ),
            ),
            // Waveform decoration lines
            Positioned.fill(
              child: CustomPaint(painter: _WaveformPainter(playing: widget.isPlaying)),
            ),
            // Animated music note icon
            Center(
              child: ScaleTransition(
                scale: _scale,
                child: Text(
                  '🎵',
                  style: TextStyle(fontSize: widget.isPlaying ? 36 : 32),
                ),
              ),
            ),
            // Selection border
            if (widget.isSelected)
              Positioned.fill(
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white, width: 2.5),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  final bool playing;
  const _WaveformPainter({required this.playing});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = (playing ? Colors.white : const Color(0xFF2E7D32)).withValues(alpha: 0.15)
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    const barCount = 7;
    final barW = size.width / (barCount * 2.0);
    final heights = [0.3, 0.55, 0.75, 0.9, 0.75, 0.55, 0.3];
    for (int i = 0; i < barCount; i++) {
      final x = barW + i * barW * 2;
      final h = size.height * heights[i];
      final top = (size.height - h) / 2;
      canvas.drawLine(Offset(x, top), Offset(x, top + h), paint);
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter old) => old.playing != playing;
}


// ─────────────────────────────────────────────────────────────────────────────
// MODE C — Vollbild-Bild ohne Text
// Bild füllt den gesamten Bereich unterhalb des Headers.
// Titel + Thumbnails als Overlay mit Gradienten für Lesbarkeit.
// Professor und Mic-Button identisch zu Mode B (über Root-Stack).
// ─────────────────────────────────────────────────────────────────────────────

class _ModeCContent extends StatefulWidget {
  const _ModeCContent({super.key});
  @override
  State<_ModeCContent> createState() => _ModeCContentState();
}

class _ModeCContentState extends State<_ModeCContent> {
  Timer? _syncResetTimer;
  double? _sliderDragValue; // non-null while user drags section slider

  double _chunkFraction(WissensfreundProvider provider) {
    final total = provider.totalChunks;
    if (total <= 1) return 0.0;
    return provider.currentChunkIndex / (total - 1);
  }

  void _startSyncResetTimer(WissensfreundProvider provider) {
    _syncResetTimer?.cancel();
    _syncResetTimer = Timer(const Duration(seconds: 10), () {
      if (!mounted) return;
      final ttsImg = provider.currentTtsImageIndex;
      if (ttsImg < 0) return;
      final media = provider.mediaItems;
      int ic = 0;
      for (int i = 0; i < media.length; i++) {
        if (!media[i].isAudio) {
          if (ic == ttsImg) { provider.onMediaTap(i); break; }
          ic++;
        }
      }
    });
  }

  void _swipeImage(DragEndDetails d, WissensfreundProvider provider) {
    final ageLevel = ProfileService.instance.activeAgeLevel;
    _doImageSwipe(d, provider, ageLevel, () => _startSyncResetTimer(provider));
  }

  void _prevChunk(WissensfreundProvider provider) {
    final cur = provider.currentChunkIndex;
    if (cur <= 0) return;
    final offset = provider.chunkCharOffset(cur - 1);
    if (offset != null) provider.jumpToSection(offset);
  }

  void _nextChunk(WissensfreundProvider provider) {
    final cur = provider.currentChunkIndex;
    final total = provider.totalChunks;
    if (cur >= total - 1) return;
    final offset = provider.chunkCharOffset(cur + 1);
    if (offset != null) provider.jumpToSection(offset);
  }

  @override
  void dispose() {
    _syncResetTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        // Image ends 36dp higher than professor top → more room for slider above thumbnails.
        const double imageClearance = _kProfH + _kProfBottom + 36;

        // Caption of the currently selected image (for the 🔊 button).
        final images  = provider.articleImages;
        final imgIdx  = images.isEmpty ? 0
            : provider.selectedImageIndex.clamp(0, images.length - 1);
        final caption = images.isNotEmpty ? images[imgIdx].caption : null;
        final hasCaption = caption != null && caption.isNotEmpty;

        return Column(
          children: [
            _ArticleHeader(provider: provider, dark: true),
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onHorizontalDragEnd: (d) => _swipeImage(d, provider),
                child: Stack(
                  children: [
                    // ── Hintergrund unter dem Bild (sichtbar ab Bildunterkante) ──
                    const Positioned.fill(
                      child: ColoredBox(color: Color(0xFF112D1F)),
                    ),

                    // ── Vollbild-Bild — endet oberhalb von Thumbnails+Professor ──
                    Positioned(
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: imageClearance,
                      child: _MainArticleImage(
                        fallbackTitle: provider.articleTitle,
                        enableFullscreenTap: false,
                        fit: BoxFit.contain,
                      ),
                    ),

                    // ── Oben: Gradient + Artikeltitel ───────────────────────
                    Positioned(
                      top: 0,
                      left: 0,
                      right: 0,
                      height: 90,
                      child: const DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Color(0xCC112D1F), Colors.transparent],
                          ),
                        ),
                      ),
                    ),
                    Positioned(
                      top: 14,
                      left: 14,
                      right: 14,
                      child: Text(
                        provider.articleTitle,
                        style: const TextStyle(
                          fontSize: 19,
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          shadows: [
                            Shadow(color: Colors.black54, blurRadius: 6),
                          ],
                        ),
                      ),
                    ),

                    // ── Unten: Gradient an der Bildunterkante ───────────────
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: imageClearance,
                      height: 80,
                      child: const DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.transparent, Color(0xFF112D1F)],
                          ),
                        ),
                      ),
                    ),

                    // ── 🔊 Bildtext vorlesen — nur wenn Caption vorhanden ───
                    Positioned(
                      top: 90,
                      right: 14,
                      child: hasCaption
                          ? GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () => provider.interruptForCaption(caption),
                              child: Container(
                                width: 48,
                                height: 48,
                                decoration: BoxDecoration(
                                  color: const Color(0xFF1B4332)
                                      .withValues(alpha: 0.88),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: Colors.white.withValues(alpha: 0.35),
                                    width: 1.5,
                                  ),
                                ),
                                child: const Icon(
                                  Icons.volume_up_rounded,
                                  color: Colors.white,
                                  size: 24,
                                ),
                              ),
                            )
                          : const SizedBox.shrink(),
                    ),

                    // ── Thumbnails + Attribution — etwas tiefer als vorher ───
                    Positioned(
                      bottom: _kMicClear + 32,
                      left: 0,
                      right: 0,
                      child: _ThumbnailRow(
                        images: images,
                        selectedIndex: provider.selectedImageIndex,
                        onTap: provider.onImageSelected,
                      ),
                    ),
                    Positioned(
                      bottom: _kMicClear,
                      left: 0,
                      right: 0,
                      child: _KlexikonAttribution(
                        url: provider.articleUrl,
                        dark: true,
                      ),
                    ),
                    // ── Section-Slider — Stufe 2/3, unter Bildkante ─────────
                    if (ProfileService.instance.activeAgeLevel >= 2 &&
                        provider.totalChunks > 1)
                      Positioned(
                        bottom: imageClearance - 36,
                        left: 4,
                        right: 4,
                        height: 48,
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            GestureDetector(
                              onTap: () => _prevChunk(provider),
                              child: const Padding(
                                padding: EdgeInsets.symmetric(horizontal: 4),
                                child: Icon(
                                  Icons.skip_previous_rounded,
                                  color: Colors.white,
                                  size: 30,
                                ),
                              ),
                            ),
                            Expanded(
                              child: SliderTheme(
                                data: SliderThemeData(
                                  trackHeight: 3.0,
                                  thumbShape: const RoundSliderThumbShape(
                                    enabledThumbRadius: 8,
                                  ),
                                  overlayShape: const RoundSliderOverlayShape(
                                    overlayRadius: 18,
                                  ),
                                  activeTrackColor: Colors.white,
                                  inactiveTrackColor:
                                      Colors.white.withValues(alpha: 0.3),
                                  thumbColor: Colors.white,
                                  overlayColor:
                                      Colors.white.withValues(alpha: 0.2),
                                ),
                                child: Slider(
                                  value: _sliderDragValue ??
                                      _chunkFraction(provider),
                                  divisions: provider.totalChunks - 1,
                                  onChanged: (v) =>
                                      setState(() => _sliderDragValue = v),
                                  onChangeEnd: (v) {
                                    final total = provider.totalChunks;
                                    final idx = (v * (total - 1))
                                        .round()
                                        .clamp(0, total - 1);
                                    final offset =
                                        provider.chunkCharOffset(idx);
                                    if (offset != null) {
                                      provider.jumpToSection(offset);
                                    }
                                    setState(() => _sliderDragValue = null);
                                  },
                                ),
                              ),
                            ),
                            GestureDetector(
                              onTap: () => _nextChunk(provider),
                              child: const Padding(
                                padding: EdgeInsets.symmetric(horizontal: 4),
                                child: Icon(
                                  Icons.skip_next_rounded,
                                  color: Colors.white,
                                  size: 30,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _QuizStartButton extends StatelessWidget {
  final WfQuiz quiz;
  const _QuizStartButton({required this.quiz});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF2D6A4F),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        icon: const Text('🎯', style: TextStyle(fontSize: 18)),
        label: const Text(
          'Quiz starten',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        onPressed: () => showModalBottomSheet(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (_) => DraggableScrollableSheet(
            initialChildSize: 0.7,
            minChildSize: 0.4,
            maxChildSize: 0.92,
            expand: false,
            builder: (ctx, scrollCtrl) => Container(
              decoration: const BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
              ),
              child: Column(
                children: [
                  // Drag handle
                  Padding(
                    padding: const EdgeInsets.only(top: 10, bottom: 4),
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  Expanded(
                    child: SingleChildScrollView(
                      controller: scrollCtrl,
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
                      child: QuizWidget(quiz: quiz),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SectionArrowBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _SectionArrowBtn({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.22),
          shape: BoxShape.circle,
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.35),
            width: 1.0,
          ),
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: Colors.white, size: 26),
      ),
    );
  }
}
