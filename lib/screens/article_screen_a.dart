import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../widgets/professor_widget.dart';

class ArticleScreenA extends StatefulWidget {
  const ArticleScreenA({super.key});

  @override
  State<ArticleScreenA> createState() => _ArticleScreenAState();
}

class _ArticleScreenAState extends State<ArticleScreenA>
    with SingleTickerProviderStateMixin {
  late final AnimationController _enterCtrl;
  late final Animation<Offset> _imageSlide;
  late final Animation<Offset> _panelSlide;
  late final Animation<double> _fadeIn;

  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    _enterCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
    _imageSlide = Tween<Offset>(
      begin: const Offset(0, -0.18),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _enterCtrl, curve: Curves.easeOut));

    _panelSlide = Tween<Offset>(
      begin: const Offset(0, 0.18),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _enterCtrl, curve: Curves.easeOut));

    _fadeIn = CurvedAnimation(parent: _enterCtrl, curve: Curves.easeOut);
    _enterCtrl.forward();
  }

  @override
  void dispose() {
    _enterCtrl.dispose();
    super.dispose();
  }

  List<String> _splitSentences(String text) {
    final matches = RegExp(r'[^.!?]+[.!?]+\s*').allMatches(text);
    final result = matches.map((m) => m.group(0)!.trim()).toList();
    return result.isEmpty ? [text] : result;
  }

  String _currentSentence(String text, int cursor) {
    if (text.isEmpty) return '';
    final sentences = _splitSentences(text);
    int pos = 0;
    for (final s in sentences) {
      pos += s.length + 1;
      if (pos > cursor) return s;
    }
    return sentences.last;
  }

  @override
  Widget build(BuildContext context) {
    final sh = MediaQuery.of(context).size.height;
    final topPad = MediaQuery.of(context).viewPadding.top;
    final imageH = sh * 0.52;

    return Consumer<WissensfreundProvider>(
      builder: (context, provider, _) {
        final isSpeaking = provider.state == AppState.speaking;
        final sentence = _currentSentence(
            provider.articleText, provider.ttsCursor);

        return Scaffold(
          backgroundColor: Colors.black,
          body: Stack(
            clipBehavior: Clip.none,
            children: [
              // ── Column: image top, panel fills the rest ─────────────────
              Column(
                children: [
                  SlideTransition(
                    position: _imageSlide,
                    child: SizedBox(
                      height: imageH,
                      width: double.infinity,
                      child: _ArticleHero(title: provider.articleTitle),
                    ),
                  ),
                  Expanded(
                    child: SlideTransition(
                      position: _panelSlide,
                      child: LayoutBuilder(
                        builder: (ctx, constraints) => _ArticlePanel(
                          title: provider.articleTitle,
                          currentSentence: sentence,
                          fullText: provider.articleText,
                          isSpeaking: isSpeaking,
                          expanded: _expanded,
                          panelH: constraints.maxHeight,
                          onExpandToggle: () =>
                              setState(() => _expanded = !_expanded),
                        ),
                      ),
                    ),
                  ),
                ],
              ),

              // ── Professor — flush right, swipe-through for gallery ────────
              Positioned(
                right: 0,
                bottom: 80,
                height: 200,
                child: IgnorePointer(
                  child: FadeTransition(
                    opacity: _fadeIn,
                    child: ProfessorWidget(
                      state: provider.state,
                      compact: true,
                    ),
                  ),
                ),
              ),

              // ── Mic FAB — bottom left (pause/play while TTS active) ─────
              Positioned(
                left: 20,
                bottom: 28,
                child: FadeTransition(
                  opacity: _fadeIn,
                  child: _MicFab(
                    state: provider.state,
                    isPaused: provider.isPaused,
                    onTap: () {
                      if (provider.state == AppState.speaking) {
                        provider.pauseSpeaking();
                      } else if (provider.isPaused) {
                        provider.resumeSpeaking();
                      } else if (provider.state == AppState.listening) {
                        provider.stopListening();
                      } else {
                        provider.stopSpeaking();
                        Navigator.pop(context);
                      }
                    },
                  ),
                ),
              ),

              // ── Close — top right ───────────────────────────────────────
              Positioned(
                right: 14,
                top: topPad + 10,
                child: FadeTransition(
                  opacity: _fadeIn,
                  child: _IconPill(
                    icon: Icons.close_rounded,
                    onTap: () {
                      provider.stopSpeaking();
                      Navigator.pop(context);
                    },
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── Article hero ───────────────────────────────────────────────────────────────

class _ArticleHero extends StatelessWidget {
  final String title;
  const _ArticleHero({required this.title});

  static const _themes = <String, (String, List<Color>)>{
    'Elefant': ('🐘', [Color(0xFF6D4C41), Color(0xFF3E2723)]),
    'Hund': ('🐕', [Color(0xFF546E7A), Color(0xFF263238)]),
    'Katze': ('🐈', [Color(0xFF7B1FA2), Color(0xFF4A148C)]),
  };

  @override
  Widget build(BuildContext context) {
    final theme = _themes[title] ??
        ('📚', const [Color(0xFF2E7D32), Color(0xFF1B5E20)]);
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: theme.$2,
        ),
      ),
      child: Center(
        child: Text(theme.$1, style: const TextStyle(fontSize: 110)),
      ),
    );
  }
}

// ── Article panel ──────────────────────────────────────────────────────────────

class _ArticlePanel extends StatelessWidget {
  final String title;
  final String currentSentence;
  final String fullText;
  final bool isSpeaking;
  final bool expanded;
  final double panelH;
  final VoidCallback onExpandToggle;

  const _ArticlePanel({
    required this.title,
    required this.currentSentence,
    required this.fullText,
    required this.isSpeaking,
    required this.expanded,
    required this.panelH,
    required this.onExpandToggle,
  });

  @override
  Widget build(BuildContext context) {
    final maxH = MediaQuery.of(context).size.height * 0.74;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
      height: expanded ? maxH : panelH,
      width: double.infinity,
      decoration: const BoxDecoration(
        color: Color(0xFFFFF8EE),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        boxShadow: [
          BoxShadow(
            color: Color(0x28000000),
            blurRadius: 20,
            offset: Offset(0, -4),
          ),
        ],
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 14, 64, 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              title,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: Color(0xFF2E7D32),
              ),
            ),
            const SizedBox(height: 10),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 280),
              child: Text(
                currentSentence.isNotEmpty ? currentSentence : fullText,
                key: ValueKey(currentSentence),
                style: const TextStyle(
                  fontSize: 18,
                  height: 1.6,
                  color: Color(0xFF222222),
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            if (!isSpeaking) ...[
              const SizedBox(height: 20),
              GestureDetector(
                onTap: onExpandToggle,
                child: Text(
                  expanded ? 'Weniger anzeigen ↑' : 'Mehr entdecken ↓',
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF2E7D32),
                  ),
                ),
              ),
              if (expanded) ...[
                const SizedBox(height: 16),
                Text(
                  fullText,
                  style: const TextStyle(
                    fontSize: 16,
                    height: 1.65,
                    color: Color(0xFF333333),
                  ),
                ),
                const SizedBox(height: 28),
                const Text(
                  'Weitere Bilder',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF333333),
                  ),
                ),
                const SizedBox(height: 12),
                _ImageGallery(title: title),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

// ── Placeholder image gallery ──────────────────────────────────────────────────

class _ImageGallery extends StatelessWidget {
  final String title;
  const _ImageGallery({required this.title});

  static const _palettes = [
    [Color(0xFFEF9A9A), Color(0xFFE57373)],
    [Color(0xFF90CAF9), Color(0xFF64B5F6)],
    [Color(0xFFA5D6A7), Color(0xFF81C784)],
    [Color(0xFFFFCC80), Color(0xFFFFB74D)],
    [Color(0xFFCE93D8), Color(0xFFBA68C8)],
  ];

  @override
  Widget build(BuildContext context) {
    // Trailing padding so the last image can be scrolled to screen center
    final trailingPad =
        (MediaQuery.of(context).size.width / 2 - 70).clamp(0.0, 300.0);
    return SizedBox(
      height: 140,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.only(right: trailingPad),
        itemCount: _palettes.length,
        separatorBuilder: (_, __) => const SizedBox(width: 12),
        itemBuilder: (ctx, i) => GestureDetector(
          onTap: () => _showFullscreen(ctx, i),
          child: Container(
            width: 140,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: _palettes[i],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            alignment: Alignment.center,
            child: Text(
              'Bild ${i + 1}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _showFullscreen(BuildContext context, int index) {
    showDialog(
      context: context,
      builder: (_) => Dialog.fullscreen(
        backgroundColor: Colors.black,
        child: Stack(
          children: [
            Center(
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: _palettes[index],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                alignment: Alignment.center,
                child: Text(
                  'Bild ${index + 1}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            Positioned(
              top: 48,
              right: 16,
              child: IconButton(
                icon: const Icon(Icons.close_rounded,
                    color: Colors.white, size: 28),
                onPressed: () => Navigator.pop(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Mic FAB ────────────────────────────────────────────────────────────────────

class _MicFab extends StatelessWidget {
  final AppState state;
  final bool isPaused;
  final VoidCallback onTap;
  const _MicFab({required this.state, required this.isPaused, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final (color, icon) = switch (state) {
      AppState.listening => (const Color(0xFFE53935), Icons.stop_rounded),
      AppState.speaking  => (const Color(0xFFF57C00), Icons.pause_rounded),
      AppState.thinking  => (Colors.grey.shade400, Icons.hourglass_top_rounded),
      _ => isPaused
          ? (const Color(0xFF1B5E20), Icons.play_arrow_rounded)
          : (const Color(0xFF546E7A), Icons.arrow_back_rounded),
    };

    return GestureDetector(
      onTap: state == AppState.thinking ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: 65,
        height: 65,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color,
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.4),
              blurRadius: 14,
              spreadRadius: 2,
            ),
          ],
        ),
        child: state == AppState.thinking
            ? const Padding(
                padding: EdgeInsets.all(18),
                child: CircularProgressIndicator(
                    color: Colors.white, strokeWidth: 3),
              )
            : Icon(icon, size: 32, color: Colors.white),
      ),
    );
  }
}

// ── Semi-transparent icon pill ─────────────────────────────────────────────────

class _IconPill extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _IconPill({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.black.withValues(alpha: 0.38),
        ),
        child: Icon(icon, color: Colors.white, size: 22),
      ),
    );
  }
}
