import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/wissensfreund_provider.dart';
import '../services/data_limit_overlay_service.dart';
import '../services/hires_image_service.dart';
import '../services/network_service.dart';
import '../services/parental_lock_service.dart';
import '../services/subscription_service.dart';
import '../services/profile_service.dart';
import '../services/wikimedia_license_checker.dart';
import '../widgets/professor_widget.dart';

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
  void dispose() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final isDark = provider.viewMode != ArticleViewMode.a;

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
                  child: switch (provider.viewMode) {
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
            onTap: () => widget.provider.interruptAndStartListening(),
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
                await provider.saveCurrentArticlePosition();
                await provider.stopSpeaking();
                if (context.mounted) Navigator.pop(context);
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
          await provider.saveCurrentArticlePosition();
          await provider.stopSpeaking();
          if (context.mounted) Navigator.pop(context);
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

  String get _modeIcon => switch (provider.viewMode) {
        ArticleViewMode.a => '📄',
        ArticleViewMode.b => '🔍',
        ArticleViewMode.c => '🎧',
      };

  Color get _fgColor =>
      dark ? Colors.white : const Color(0xFF2D6A4F);

  Color get _btnBg => dark
      ? Colors.white.withValues(alpha: 0.15)
      : const Color(0xFFE8F5E9);

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
          const Text('🎓', style: TextStyle(fontSize: 20)),
          const SizedBox(width: 6),
          Text(
            'Wissensfreund',
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w700,
              color: _fgColor,
            ),
          ),
          const Spacer(),
          // Favorite
          if (provider.articleTitle.isNotEmpty)
            _FavoriteBtn(
              articleTitle: provider.articleTitle,
              btnBg: _btnBg,
              fgColor: _fgColor,
            ),
          const SizedBox(width: 8),
          // Mode toggle
          _HeaderBtn(
            bg: _btnBg,
            child: Text(_modeIcon, style: const TextStyle(fontSize: 17)),
            onTap: provider.cycleViewMode,
          ),
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
  const _ArticleImage({super.key, required this.title});

  static const _themes = <String, (String, List<Color>)>{
    'Elefant': ('🐘', [Color(0xFF8D6E63), Color(0xFF4E342E)]),
    'Hund': ('🐕', [Color(0xFF78909C), Color(0xFF37474F)]),
    'Katze': ('🐈', [Color(0xFFAB47BC), Color(0xFF6A1B9A)]),
  };

  @override
  Widget build(BuildContext context) {
    final theme = _themes[title] ??
        ('📚', const [Color(0xFF43A047), Color(0xFF1B5E20)]);
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: theme.$2,
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(theme.$1, style: const TextStyle(fontSize: 60)),
          const SizedBox(height: 4),
          Text(
            'Artikelbild',
            style: TextStyle(
              fontSize: 11,
              color: Colors.white.withValues(alpha: 0.65),
              letterSpacing: 0.5,
            ),
          ),
        ],
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
  const _MainArticleImage({
    required this.fallbackTitle,
    this.onTap,
    this.enableFullscreenTap = true,
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
        final fromKlexikon = images.isEmpty ? false : images[selIdx].fromKlexikon;

        final future = _bytesFuture;
        final fn     = _loadedFilename;

        return AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          child: future == null
              ? _ArticleImage(
                  key: const ValueKey('fallback'),
                  title: widget.fallbackTitle,
                )
              : FutureBuilder<Uint8List?>(
                  key: ValueKey(fn),
                  future: future,
                  builder: (_, snap) {
                    final bytes = snap.data;
                    if (bytes == null) {
                      return _ArticleImage(title: widget.fallbackTitle);
                    }
                    return GestureDetector(
                      onTap: widget.enableFullscreenTap
                          ? () => _openFullscreen(context, selIdx)
                          : widget.onTap,
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Image.memory(bytes, fit: BoxFit.cover),
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
        );
      },
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
                if (bytes == null) return const SizedBox.expand();
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
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
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

  // Cached full-width document positions (in scroll-content coordinates).
  // Built once after the first render when all sentences are at full width.
  // Stable across scroll events → no feedback-loop oscillation.
  final _sentenceTopCache = <int, double>{};
  final _sentenceHeightCache = <int, double>{};
  bool _cacheBuilt = false;

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
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  GlobalKey _keyFor(int i) =>
      _sentenceKeys.putIfAbsent(i, () => GlobalKey());

  // Scroll DOWN to active sentence only if it has drifted below 50% of viewport.
  // Never scrolls back up so the user can read ahead freely.
  void _smartScrollTo(int idx) {
    if (_scrollPending) return;
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

      // Only pull it into view when it has slipped past 50% down
      if (localY > viewportH * 0.5) {
        Scrollable.ensureVisible(
          ctx,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOut,
          alignment: 0.15, // land near top (~2nd line)
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
    if ((isSpeaking || isPaused) && sentences.isNotEmpty) {
      int sentStart = 0;
      for (int i = 0; i < activeIdx; i++) {
        sentStart += sentences[i].length + 1;
      }
      activeCursorInSent =
          (ttsCursor - sentStart).clamp(0, sentences[activeIdx].length);
    }

    final result = <Widget>[];
    int searchFrom = 0;
    for (int i = 0; i < sentences.length; i++) {
      final sentText = sentences[i];
      final actualStart = fullText.indexOf(sentText, searchFrom);

      List<Map<String, dynamic>> sentLinks = const [];
      if (actualStart >= 0 && links.isNotEmpty) {
        final actualEnd = actualStart + sentText.length;
        sentLinks = links.where((l) {
          final s = (l['startChar'] as int?) ?? 0;
          final e = (l['endChar'] as int?) ?? 0;
          return s >= actualStart && e <= actualEnd;
        }).map((l) => <String, dynamic>{
          'text': l['text'],
          'target': l['target'],
          'startChar': (l['startChar'] as int) - actualStart,
          'endChar': (l['endChar'] as int) - actualStart,
        }).toList();
        searchFrom = actualEnd;
      } else if (actualStart >= 0) {
        searchFrom = actualStart + sentText.length;
      }

      result.add(_SentenceWidget(
        key: _keyFor(i),
        text: sentText,
        isActive: i == activeIdx,
        extraRightPad: i == activeIdx ? 0.0 : (inZone[i] ? _kProfPad : 0.0),
        cursorInSent: i == activeIdx ? activeCursorInSent : -1,
        links: sentLinks,
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
        final activeIdx =
            _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);

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
            _buildCache();
            setState(() {});
          });
        }

        // Auto-scroll: pull active sentence to near top when speaking
        if (provider.state == AppState.speaking && activeIdx != _lastActiveIdx) {
          _lastActiveIdx = activeIdx;
          _smartScrollTo(activeIdx);
        }

        return Column(
          children: [
            _ArticleHeader(provider: provider),
            SizedBox(
              height: (MediaQuery.of(context).size.height * 0.25).clamp(150.0, 260.0),
              width: double.infinity,
              child: _MainArticleImage(fallbackTitle: provider.articleTitle),
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
                        ..._buildSentenceWidgets(
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
                        // ── Thumbnails at end of article ──────────────────
                        if (sentences.isNotEmpty) ...[
                          const SizedBox(height: 24),
                          const Text(
                            'WEITERE BILDER',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF2D6A4F),
                              letterSpacing: 1.2,
                            ),
                          ),
                          const SizedBox(height: 10),
                          const _ThumbnailRow(),
                          const SizedBox(height: 16),
                          _KlexikonAttribution(url: provider.articleUrl),
                        ],
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
  bool _scrollPending = false;

  static const _sentenceStyle = TextStyle(
    fontSize: 17,
    height: 1.55,
    color: Colors.white,
    fontWeight: FontWeight.w500,
  );

  static const _longThreshold = 200;

  int _sentenceStart(List<String> sentences, int idx) {
    int pos = 0;
    for (int i = 0; i < idx; i++) {
      pos += sentences[i].length + 1;
    }
    return pos;
  }

  // Drives the ScrollController to keep the current word near the top.
  // Uses real layout metrics (maxScrollExtent + viewportDimension) so no
  // TextPainter estimation is needed and all content is guaranteed visible.
  void _scheduleScroll(
      String sentence, int ttsCursor, List<String> sentences, int activeIdx) {
    if (_scrollPending) return;
    _scrollPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollPending = false;
      if (!mounted || !_scrollCtrl.hasClients) return;
      final pos = _scrollCtrl.position;
      final maxExt = pos.maxScrollExtent;
      if (maxExt <= 0) return;
      final textH = maxExt + pos.viewportDimension;
      final sentStart = _sentenceStart(sentences, activeIdx);
      final cursorInSent =
          (ttsCursor - sentStart).clamp(0, sentence.length);
      final progress =
          sentence.isEmpty ? 0.0 : cursorInSent / sentence.length;
      // progress * textH maps cursor to text pixel position;
      // clamping to maxExt keeps the current word at the viewport top
      // for most of the sentence, only reaching the bottom at the very end.
      // Delay scroll start: keep the first ~35% of the viewport static
      // before scrolling begins (≈ 2 lines of head-start at fontSize 17).
      final headStart = pos.viewportDimension * 0.35;
      _scrollCtrl.jumpTo((progress * textH - headStart).clamp(0.0, maxExt));
    });
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final sentences = _splitSentences(provider.articleText);
        final activeIdx =
            _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);
        final progress =
            sentences.isEmpty ? 0.0 : (activeIdx + 1) / sentences.length;
        final currentSentence =
            sentences.isEmpty ? '' : sentences[activeIdx];
        final isLong = currentSentence.length > _longThreshold;

        if (isLong) {
          _scheduleScroll(
              currentSentence, provider.ttsCursor, sentences, activeIdx);
        }

        // Long sentences: SingleChildScrollView driven by _scrollCtrl.
        // Keyed by activeIdx so Flutter recreates the widget (and the scroll
        // position resets to 0) whenever the sentence changes.
        // Short sentences: AnimatedSwitcher with fade + slide.
        final textWidget = isLong
            ? Expanded(
                child: SingleChildScrollView(
                  key: ValueKey('scroll_$activeIdx'),
                  controller: _scrollCtrl,
                  physics: const NeverScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
                  child: Text(currentSentence, style: _sentenceStyle),
                ),
              )
            : Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 350),
                  transitionBuilder: (child, anim) => FadeTransition(
                    opacity: anim,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, 0.05),
                        end: Offset.zero,
                      ).animate(anim),
                      child: child,
                    ),
                  ),
                  child: Align(
                    key: ValueKey(activeIdx),
                    alignment: Alignment.topLeft,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
                      child: Text(
                        currentSentence,
                        maxLines: 5,
                        overflow: TextOverflow.fade,
                        style: _sentenceStyle,
                      ),
                    ),
                  ),
                ),
              );

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
              SizedBox(
                height: (MediaQuery.of(context).size.height * 0.29).clamp(170.0, 300.0),
                width: double.infinity,
                child: _MainArticleImage(fallbackTitle: provider.articleTitle),
              ),

              // ── Fortschrittsleiste ────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: [
                    Expanded(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: progress,
                          backgroundColor:
                              Colors.white.withValues(alpha: 0.15),
                          valueColor: const AlwaysStoppedAnimation(
                              Color(0xFF95D5B2)),
                          minHeight: 5,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Text(
                      sentences.isEmpty
                          ? ''
                          : '${activeIdx + 1} / ${sentences.length}',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.white.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),

              // ── Aktueller Satz ────────────────────────────────────────────
              textWidget,

              // ── Thumbnails ────────────────────────────────────────────────
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.only(left: 16, bottom: 8),
                    child: Text(
                      'WEITERE BILDER',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: Colors.white.withValues(alpha: 0.55),
                        letterSpacing: 1.2,
                      ),
                    ),
                  ),
                  const _ThumbnailRow(),
                  _KlexikonAttribution(url: provider.articleUrl, dark: true),
                  const SizedBox(height: _kMicClear),
                ],
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
  const _ThumbnailRow();

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        final items = provider.mediaItems;
        if (items.isEmpty) return const SizedBox(height: 100);
        return SizedBox(
          height: 100,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(right: _kThumbRight),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (ctx, i) {
              final item = items[i];
              final isSelected = i == provider.selectedMediaIndex;
              return GestureDetector(
                onTap: () => provider.onMediaTap(i),
                child: item.isAudio
                    ? _SoundThumbnailTile(
                        key: ValueKey('audio_${item.filename}'),
                        isSelected: isSelected,
                        isPlaying: provider.activeAudioIndex == i,
                      )
                    : _ZimImageTile(
                        key: ValueKey(item.filename),
                        image: ArticleImageInfo(
                          filename: item.filename,
                          caption:  item.caption,
                          fromKlexikon: true,
                        ),
                        isSelected: isSelected,
                      ),
              );
            },
          ),
        );
      },
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

class _ModeCContent extends StatelessWidget {
  const _ModeCContent({super.key});

  // Swipe to next/previous image — syncs both selectedImageIndex and selectedMediaIndex.
  void _swipeImage(DragEndDetails d, WissensfreundProvider provider) {
    final v = d.primaryVelocity ?? 0;
    if (v.abs() < 200) return;
    final images     = provider.articleImages;
    final mediaItems = provider.mediaItems;
    if (images.isEmpty) return;
    final curImgIdx  = provider.selectedImageIndex.clamp(0, images.length - 1);
    final nextImgIdx = v < 0 ? curImgIdx + 1 : curImgIdx - 1;
    if (nextImgIdx < 0 || nextImgIdx >= images.length) return;

    // Find the mediaItems index for the target image (skip audio items).
    int imgCount = 0;
    for (int i = 0; i < mediaItems.length; i++) {
      if (!mediaItems[i].isAudio) {
        if (imgCount == nextImgIdx) {
          provider.onMediaTap(i); // syncs both _selectedMediaIndex + _selectedImageIndex
          return;
        }
        imgCount++;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        // Bottom of image = professor's top edge (_kProfH + _kProfBottom = 224px).
        // This clears both the professor (224px) and the thumbnail row (180px).
        const double imageClearance = _kProfH + _kProfBottom;

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
                      bottom: imageClearance + 10,
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

                    // ── Thumbnails + Attribution ─────────────────────────────
                    Positioned(
                      bottom: _kMicClear,
                      left: 0,
                      right: 0,
                      child: const _ThumbnailRow(),
                    ),
                    Positioned(
                      bottom: _kMicClear + 104,
                      left: 0,
                      right: 0,
                      child: _KlexikonAttribution(
                        url: provider.articleUrl,
                        dark: true,
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
