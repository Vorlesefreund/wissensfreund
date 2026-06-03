import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../utils/system_ui.dart';

class ImageFullscreenOverlay extends StatefulWidget {
  final List<ArticleImageInfo> images;
  final int initialIndex;

  const ImageFullscreenOverlay({
    required this.images,
    required this.initialIndex,
    super.key,
  });

  @override
  State<ImageFullscreenOverlay> createState() => _ImageFullscreenOverlayState();
}

class _ImageFullscreenOverlayState extends State<ImageFullscreenOverlay>
    with TickerProviderStateMixin {
  late final PageController _pageCtrl;
  late int _currentIndex;

  bool _isZoomed = false;
  bool _speakerUsed = false;
  Timer? _rotateHintTimer;
  bool _showRotateHint = false;

  final _futures = <String, Future<Uint8List?>>{};
  final _imageRatios = <String, double?>{};

  final _transformControllers = <int, TransformationController>{};
  final _animControllers = <int, AnimationController>{};

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex.clamp(
        0, (widget.images.length - 1).clamp(0, widget.images.length));
    _pageCtrl = PageController(initialPage: _currentIndex);

    SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<WissensfreundProvider>().pauseSpeaking();
    });
  }

  @override
  void dispose() {
    _pageCtrl.dispose();
    for (final tc in _transformControllers.values) { tc.dispose(); }
    for (final ac in _animControllers.values) { ac.dispose(); }
    _rotateHintTimer?.cancel();
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    restoreSystemUI();
    super.dispose();
  }

  TransformationController _tcFor(int i) =>
      _transformControllers.putIfAbsent(i, () {
        final tc = TransformationController();
        tc.addListener(() {
          final zoomed = tc.value.getMaxScaleOnAxis() > 1.05;
          if (zoomed != _isZoomed && mounted) setState(() => _isZoomed = zoomed);
        });
        return tc;
      });

  AnimationController _acFor(int i) => _animControllers.putIfAbsent(
        i,
        () => AnimationController(
            vsync: this, duration: const Duration(milliseconds: 230)),
      );

  void _doubleTap(int index, TapDownDetails details) {
    final tc = _tcFor(index);
    final ac = _acFor(index);
    if (tc.value.getMaxScaleOnAxis() > 1.05) {
      _animateTo(tc, ac, Matrix4.identity());
    } else {
      final dx = details.localPosition.dx;
      final dy = details.localPosition.dy;
      const s = 2.5;
      final target = Matrix4.translationValues(-dx * (s - 1), -dy * (s - 1), 0)
        ..multiply(Matrix4.diagonal3Values(s, s, 1.0));
      _animateTo(tc, ac, target);
    }
  }

  void _animateTo(
      TransformationController tc, AnimationController ac, Matrix4 target) {
    final begin = tc.value.clone();
    final tween = Matrix4Tween(begin: begin, end: target);
    ac.reset();
    final animation =
        tween.animate(CurvedAnimation(parent: ac, curve: Curves.easeOut));
    animation.addListener(() => tc.value = animation.value);
    ac.forward();
  }

  void _onPageChanged(int index) {
    setState(() {
      _currentIndex = index;
      _speakerUsed = false;
      _isZoomed = false;
    });
    _transformControllers[index]?.value = Matrix4.identity();
    _checkRotateHint(index);
  }

  void _checkRotateHint(int index) {
    if (index >= widget.images.length) return;
    final filename = widget.images[index].filename;
    final ratio = _imageRatios[filename];
    if (ratio == null) return;
    final orient = MediaQuery.of(context).orientation;
    if (ratio > 1.3 && orient == Orientation.portrait) _showHint();
  }

  void _showHint() {
    _rotateHintTimer?.cancel();
    if (mounted) setState(() => _showRotateHint = true);
    _rotateHintTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => _showRotateHint = false);
    });
  }

  void _onBytesLoaded(String filename, Uint8List bytes) {
    if (_imageRatios.containsKey(filename)) return;
    _imageRatios[filename] = null;
    ui.decodeImageFromList(bytes, (image) {
      if (!mounted) return;
      _imageRatios[filename] = image.width / image.height;
      if (_currentIndex < widget.images.length &&
          widget.images[_currentIndex].filename == filename) {
        _checkRotateHint(_currentIndex);
      }
    });
  }

  Future<Uint8List?> _futureFor(String fn, WissensfreundProvider p) =>
      _futures.putIfAbsent(fn, () => p.getImageBytes(fn));

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        final images = widget.images;
        if (images.isEmpty) {
          return const Scaffold(
            backgroundColor: Colors.black,
            body: SizedBox.shrink(),
          );
        }
        final cur = images[_currentIndex];
        final hasCaption = cur.caption != null && cur.caption!.isNotEmpty;

        return Scaffold(
          backgroundColor: Colors.black,
          body: OrientationBuilder(
            builder: (_, orientation) {
              return Stack(
                fit: StackFit.expand,
                children: [
                  // ── PageView ──────────────────────────────────────────────
                  PageView.builder(
                    controller: _pageCtrl,
                    physics: _isZoomed
                        ? const NeverScrollableScrollPhysics()
                        : const AlwaysScrollableScrollPhysics(),
                    onPageChanged: _onPageChanged,
                    itemCount: images.length,
                    itemBuilder: (_, i) =>
                        _buildPage(i, images[i], provider),
                  ),

                  // ── ← Zurück (oben links) ─────────────────────────────────
                  SafeArea(
                    child: Align(
                      alignment: Alignment.topLeft,
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: _OverlayBtn(
                          icon: Icons.arrow_back_rounded,
                          onTap: () => Navigator.of(context).pop(),
                        ),
                      ),
                    ),
                  ),

                  // ── 🔊 Speaker (oben rechts) ──────────────────────────────
                  if (hasCaption)
                    SafeArea(
                      child: Align(
                        alignment: Alignment.topRight,
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: _OverlayBtn(
                            icon: Icons.volume_up_rounded,
                            dimmed: _speakerUsed,
                            onTap: _speakerUsed
                                ? null
                                : () {
                                    setState(() => _speakerUsed = true);
                                    provider.interruptForCaption(cur.caption!);
                                  },
                          ),
                        ),
                      ),
                    ),

                  // ── Zähler (oben mitte) ───────────────────────────────────
                  if (images.length > 1)
                    SafeArea(
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: Padding(
                          padding: const EdgeInsets.only(top: 14),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 5),
                            decoration: BoxDecoration(
                              color: Colors.black54,
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Text(
                              '${_currentIndex + 1} / ${images.length}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),

                  // ── Dreh-Hinweis (unten mitte) ────────────────────────────
                  if (_showRotateHint && orientation == Orientation.portrait)
                    Positioned(
                      bottom: 100,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 8),
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.screen_rotation_rounded,
                                  color: Colors.white70, size: 18),
                              SizedBox(width: 6),
                              Text(
                                'Handy drehen',
                                style: TextStyle(
                                    color: Colors.white70, fontSize: 13),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildPage(
      int index, ArticleImageInfo img, WissensfreundProvider provider) {
    final future = _futureFor(img.filename, provider);
    final hasCaption = img.caption != null && img.caption!.isNotEmpty;
    final tc = _tcFor(index);

    return FutureBuilder<Uint8List?>(
      key: ValueKey(img.filename),
      future: future,
      builder: (ctx, snap) {
        final bytes = snap.data;
        if (bytes == null) {
          return const Center(
              child: CircularProgressIndicator(color: Colors.white54));
        }

        _onBytesLoaded(img.filename, bytes);

        return Stack(
          fit: StackFit.expand,
          children: [
            GestureDetector(
              onDoubleTapDown: (d) => _doubleTap(index, d),
              onDoubleTap: () {},
              child: InteractiveViewer(
                transformationController: tc,
                minScale: 1.0,
                maxScale: 4.0,
                panEnabled: true,
                boundaryMargin: EdgeInsets.zero,
                child: SizedBox.expand(
                  child: Image.memory(bytes, fit: BoxFit.contain),
                ),
              ),
            ),

            // Bildunterschrift mit Gradient
            if (hasCaption) ...[
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                height: 80,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        Colors.black.withValues(alpha: 0.6),
                      ],
                    ),
                  ),
                ),
              ),
              Positioned(
                left: 60,
                right: 60,
                bottom: 12,
                child: Text(
                  img.caption!,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    height: 1.4,
                    fontStyle: FontStyle.italic,
                    shadows: [Shadow(color: Colors.black87, blurRadius: 4)],
                  ),
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _OverlayBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final bool dimmed;

  const _OverlayBtn({
    required this.icon,
    this.onTap,
    this.dimmed = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: Colors.black54,
          borderRadius: BorderRadius.circular(22),
        ),
        child: Icon(
          icon,
          color: dimmed ? Colors.white38 : Colors.white,
          size: 24,
        ),
      ),
    );
  }
}
