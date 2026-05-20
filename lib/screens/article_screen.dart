import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/wissensfreund_provider.dart';
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
const double _kProfPad    = _kProfW + 4.0;               // 182 — right text indent beside professor
const double _kMicClear   = _kMicSize + _kMicBottom * 2; //  80 — scroll bottom clearance
const double _kProfZone   = _kProfH + _kProfBottom + 21; // 245 — viewport bottom covered by professor
const double _kThumbRight = _kProfW + 2.0;               // 180 — thumbnail row right padding


// ─────────────────────────────────────────────────────────────────────────────
// Root screen — manages mode switching; professor + mic are always on top
// ─────────────────────────────────────────────────────────────────────────────

class ArticleScreen extends StatelessWidget {
  const ArticleScreen({super.key});

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
                // ── Mic / Play-Pause ───────────────────────────────────────
                Positioned(
                  bottom: _kMicBottom,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: _ArticleMicButton(provider: provider),
                  ),
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

class _ArticleMicButton extends StatelessWidget {
  final WissensfreundProvider provider;
  const _ArticleMicButton({required this.provider});

  @override
  Widget build(BuildContext context) {
    final isDark = provider.viewMode != ArticleViewMode.a;
    final isSpeaking = provider.state == AppState.speaking;
    final isPaused = provider.isPaused;

    final Color bg;
    final IconData icon;

    if (isSpeaking) {
      bg = isDark ? const Color(0xFF2D6A4F) : const Color(0xFFF57C00);
      icon = Icons.pause_rounded;
    } else if (isPaused) {
      bg = isDark
          ? Colors.white.withValues(alpha: 0.2)
          : const Color(0xFF2D6A4F);
      icon = Icons.play_arrow_rounded;
    } else {
      bg = isDark
          ? Colors.white.withValues(alpha: 0.2)
          : const Color(0xFF546E7A);
      icon = Icons.arrow_back_rounded;
    }

    return GestureDetector(
      onTap: () {
        if (isSpeaking) {
          provider.pauseSpeaking();
        } else if (isPaused) {
          provider.resumeSpeaking();
        } else {
          provider.stopSpeaking();
          Navigator.pop(context);
        }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: _kMicSize,
        height: _kMicSize,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: bg,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.22),
              blurRadius: 10,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Icon(icon, color: Colors.white, size: 26),
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
  const _MainArticleImage({required this.fallbackTitle, this.onTap});

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

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        _updateFuture(provider);
        if (_bytesFuture == null) {
          return _ArticleImage(title: widget.fallbackTitle);
        }
        return GestureDetector(
          onTap: widget.onTap,
          child: FutureBuilder<Uint8List?>(
            future: _bytesFuture,
            builder: (_, snap) {
              final bytes = snap.data;
              return Stack(
                fit: StackFit.expand,
                children: [
                  bytes != null
                      ? Image.memory(bytes, fit: BoxFit.cover)
                      : _ArticleImage(title: widget.fallbackTitle),
                  Positioned(
                    right: 8,
                    bottom: 8,
                    child: _LicenseInfoButton(filename: _loadedFilename!),
                  ),
                ],
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
              child: _LicenseInfoButton(filename: widget.image.filename),
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
  const _LicenseInfoButton({required this.filename});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _showLicenseInfo(context, filename),
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

void _showLicenseInfo(BuildContext context, String filename) async {
  final entry = await WikimediaLicenseChecker.instance.getCached(filename);
  if (!context.mounted) return;
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
                onTap: () => launchUrl(
                  Uri.parse(entry!.lizenzUrl!),
                  mode: LaunchMode.externalApplication,
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
            if (entry == null ||
                (entry.urheber == null && entry.lizenz == null))
              const Text(
                'Keine Lizenzinformationen verfügbar.',
                style: TextStyle(fontSize: 14, color: Colors.grey),
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
            onTap: () {
              Navigator.pop(context);
              provider.stopSpeaking();
              Navigator.pop(context);
            },
          ),
          const Divider(height: 1, indent: 24, endIndent: 24),
          ListTile(
            leading:
                const Icon(Icons.home_rounded, color: Color(0xFF2D6A4F)),
            title: const Text('Zum Hauptmenü'),
            onTap: () {
              Navigator.pop(context);
              provider.stopSpeaking();
              Navigator.pop(context);
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
          await launchUrl(uri, mode: LaunchMode.externalApplication);
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
// Shared sentence utilities
// ─────────────────────────────────────────────────────────────────────────────

List<String> _splitSentences(String text) {
  if (text.isEmpty) return [];
  final matches = RegExp(r'[^.!?]+[.!?]+\s*').allMatches(text);
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
  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
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
  }) {
    // Show window highlight while speaking OR while paused (cursor saved at
    // pause position). Full-sentence highlight only when idle before playback.
    int activeCursorInSent = -1;
    if ((isSpeaking || isPaused) && sentences.isNotEmpty) {
      int sentStart = 0;
      for (int i = 0; i < activeIdx; i++) {
        sentStart += sentences[i].length + 1;
      }
      activeCursorInSent =
          (ttsCursor - sentStart).clamp(0, sentences[activeIdx].length);
    }

    return [
      for (int i = 0; i < sentences.length; i++)
        _SentenceWidget(
          key: _keyFor(i),
          text: sentences[i],
          isActive: i == activeIdx,
          // Active sentence always at full width so top lines are never narrow.
          extraRightPad: i == activeIdx ? 0.0 : (inZone[i] ? _kProfPad : 0.0),
          cursorInSent: i == activeIdx ? activeCursorInSent : -1,
        ),
    ];
  }

  // Professor: width=178, right=0, height=218, bottom=6.
  // Professor top from SafeArea bottom = 14+218 = 232px.
  // Zone = bottom 245px of viewport (with buffer). Right pad = 178+4+8=190px.
  List<bool> _computeProfessorZone({
    required List<String> sentences,
    required int activeIdx,
    required double viewportH,
    required double contentWidth,
  }) {
    final scrollOffset = _scrollCtrl.hasClients ? _scrollCtrl.offset : 0.0;
    final professorTop = scrollOffset + viewportH - _kProfZone;

    double runH = 10.0 + 16.0 * 1.5 + 8.0; // top pad + title + gap
    final result = List<bool>.filled(sentences.length, false);

    for (int i = 0; i < sentences.length; i++) {
      final tp = TextPainter(
        text: TextSpan(
          text: sentences[i],
          style: TextStyle(
            fontSize: 14,
            height: 1.85,
            fontWeight: i == activeIdx ? FontWeight.bold : FontWeight.normal,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: contentWidth);

      final sentBottom = runH + tp.height;
      if (sentBottom > professorTop && runH < scrollOffset + viewportH) {
        result[i] = true;
      }
      runH = sentBottom + 4;
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final sentences = _splitSentences(provider.articleText);
        final activeIdx =
            _findActiveIdx(provider.articleText, provider.ttsCursor, sentences);

        // Reset keys when article changes
        if (provider.articleText != _lastArticleText) {
          _lastArticleText = provider.articleText;
          _sentenceKeys.clear();
          _lastActiveIdx = -1;
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
                  final contentWidth = constraints.maxWidth - 12 - 8;
                  final inZone = _computeProfessorZone(
                    sentences: sentences,
                    activeIdx: activeIdx,
                    viewportH: constraints.maxHeight,
                    contentWidth: contentWidth,
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

class _SentenceWidget extends StatelessWidget {
  final String text;
  final bool isActive;
  final double extraRightPad;
  // ≥ 0 while speaking → show window highlight around current word.
  // -1 → show full-sentence highlight (paused / idle) or no highlight.
  final int cursorInSent;

  const _SentenceWidget({
    super.key,
    required this.text,
    required this.isActive,
    required this.extraRightPad,
    this.cursorInSent = -1,
  });

  static const _base = TextStyle(fontSize: 14, height: 1.85);

  @override
  Widget build(BuildContext context) {
    // ── Window highlight: stable at punctuation boundaries ────────────────
    if (isActive && cursorInSent >= 0 && text.isNotEmpty) {
      final pos = cursorInSent.clamp(0, text.length);

      // Window start: back to the previous punctuation mark (., , ! ? ; :)
      int baseStart = 0;
      for (int i = pos - 1; i >= 0; i--) {
        if ('.,:!?;'.contains(text[i])) {
          baseStart = i + 1;
          // Skip leading whitespace after the punctuation
          while (baseStart < text.length && text[baseStart] == ' ') baseStart++;
          break;
        }
      }

      // Window end: forward to the next punctuation mark (inclusive)
      int baseEnd = text.length;
      for (int i = pos; i < text.length; i++) {
        if ('.,:!?;'.contains(text[i])) {
          baseEnd = i + 1;
          break;
        }
      }

      // Guarantee at least 20 chars before and after cursor
      final wStart =
          (baseStart < pos - 20 ? baseStart : pos - 20).clamp(0, pos);
      final wEnd =
          (baseEnd > pos + 20 ? baseEnd : pos + 20).clamp(pos, text.length);

      return Padding(
        padding: EdgeInsets.only(right: extraRightPad, bottom: 4),
        child: Text.rich(
          TextSpan(
            style: _base.copyWith(color: const Color(0xFF333333)),
            children: [
              if (wStart > 0) TextSpan(text: text.substring(0, wStart)),
              TextSpan(
                text: text.substring(wStart, wEnd),
                style: _base.copyWith(
                  color: const Color(0xFF1B4332),
                  fontWeight: FontWeight.bold,
                  backgroundColor: const Color(0xFFC8EDDA),
                ),
              ),
              if (wEnd < text.length) TextSpan(text: text.substring(wEnd)),
            ],
          ),
        ),
      );
    }

    // ── Full-sentence highlight (paused / idle / before first word) ────────
    if (isActive) {
      return Padding(
        padding: EdgeInsets.only(right: extraRightPad, bottom: 4),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
          decoration: BoxDecoration(
            color: const Color(0xFFC8EDDA),
            borderRadius: BorderRadius.circular(3),
            border: Border.all(color: const Color(0xFF2D6A4F), width: 2),
          ),
          child: Text(
            text,
            style: _base.copyWith(
              fontWeight: FontWeight.bold,
              color: const Color(0xFF1B4332),
            ),
          ),
        ),
      );
    }

    // ── Inactive sentence ──────────────────────────────────────────────────
    return Padding(
      padding: EdgeInsets.only(right: extraRightPad, bottom: 4),
      child: Text(
        text,
        style: _base.copyWith(color: const Color(0xFF333333)),
      ),
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
// Thumbnail row (used in Mode A and later Mode B/C)
// ─────────────────────────────────────────────────────────────────────────────

class _ThumbnailRow extends StatelessWidget {
  const _ThumbnailRow();

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        final images = provider.articleImages;
        if (images.isEmpty) return const SizedBox(height: 100);
        return SizedBox(
          height: 100,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(right: _kThumbRight),
            itemCount: images.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (ctx, i) {
              final isSelected = i == provider.selectedImageIndex;
              return GestureDetector(
                onTap: () => provider.selectImage(i),
                child: _ZimImageTile(
                  key: ValueKey(images[i].filename),
                  image: images[i],
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
// MODE C — Vollbild-Bild ohne Text
// Bild füllt den gesamten Bereich unterhalb des Headers.
// Titel + Thumbnails als Overlay mit Gradienten für Lesbarkeit.
// Professor und Mic-Button identisch zu Mode B (über Root-Stack).
// ─────────────────────────────────────────────────────────────────────────────

class _ModeCContent extends StatelessWidget {
  const _ModeCContent({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        return Column(
          children: [
            _ArticleHeader(provider: provider, dark: true),
            Expanded(
              child: Stack(
                children: [
                  // ── Vollbild-Bild ─────────────────────────────────────────
                  Positioned.fill(
                    child: _MainArticleImage(fallbackTitle: provider.articleTitle),
                  ),

                  // ── Oben: Gradient + Artikeltitel ─────────────────────────
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
                    top: 12,
                    left: 14,
                    right: 14,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          provider.articleTitle.toUpperCase(),
                          style: TextStyle(
                            fontSize: 11,
                            color: Colors.white.withValues(alpha: 0.7),
                            letterSpacing: 1.2,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          provider.articleTitle,
                          style: const TextStyle(
                            fontSize: 19,
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),

                  // ── Unten: Gradient + Thumbnails (identisch Mode B) ───────
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    height: _kMicClear + 130,
                    child: const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [Colors.transparent, Color(0xDD112D1F)],
                        ),
                      ),
                    ),
                  ),
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
          ],
        );
      },
    );
  }
}
