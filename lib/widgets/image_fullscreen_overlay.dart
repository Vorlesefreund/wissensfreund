import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:photo_view_plus/photo_view_plus.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../utils/system_ui.dart';


class ImageFullscreenOverlay extends StatefulWidget {
  final List<ArticleImageInfo> images;
  final int initialIndex;
  final void Function(BuildContext ctx, int imageIndex)? onLicenseInfo;

  const ImageFullscreenOverlay({
    required this.images,
    required this.initialIndex,
    this.onLicenseInfo,
    super.key,
  });

  @override
  State<ImageFullscreenOverlay> createState() => _ImageFullscreenOverlayState();
}

class _ImageFullscreenOverlayState extends State<ImageFullscreenOverlay>
    with TickerProviderStateMixin {
  late final PageController _pageCtrl;
  late int _currentIndex;

  bool _isZoomed    = false;
  bool _speakerUsed = false;
  Timer? _rotateHintTimer;
  bool _showRotateHint = false;

  final _futures     = <String, Future<List<int>?>>{};
  final _imageRatios = <String, double?>{};  // für Dreh-Hinweis
  final _imageSizes  = <String, Size>{};     // für Double-tap initScale-Berechnung

  final _pvControllers     = <int, PhotoViewController>{};
  final _pvAnimControllers = <int, AnimationController>{};
  final _outerSizes        = <int, Size>{};

  // Double-tap via Listener (raw pointer down) — kein GestureArena-Teilnehmer
  DateTime? _lastTapTime;
  Offset?   _lastTapPos;
  int?      _lastTapIndex;

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
    for (final c in _pvControllers.values) { c.dispose(); }
    for (final c in _pvAnimControllers.values) { c.dispose(); }
    _rotateHintTimer?.cancel();
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    restoreSystemUI();
    super.dispose();
  }

  PhotoViewController _ctrlFor(int i) =>
      _pvControllers.putIfAbsent(i, () => PhotoViewController());

  void _onPageChanged(int index) {
    _resetController(_currentIndex); // verlassene Seite zurücksetzen
    _resetController(index);         // neue Seite sicherheitshalber auch
    setState(() {
      _currentIndex = index;
      _speakerUsed  = false;
      _isZoomed     = false;
    });
    _checkRotateHint(index);
  }

  void _checkRotateHint(int index) {
    if (index >= widget.images.length) return;
    final ratio = _imageRatios[widget.images[index].filename];
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

  void _onBytesLoaded(String filename, List<int> bytes) {
    if (_imageRatios.containsKey(filename)) return;
    _imageRatios[filename] = null;
    ui.decodeImageFromList(Uint8List.fromList(bytes), (image) {
      if (!mounted) return;
      setState(() {
        _imageRatios[filename] = image.width / image.height;
        _imageSizes[filename]  = Size(
            image.width.toDouble(), image.height.toDouble());
      });
      if (_currentIndex < widget.images.length &&
          widget.images[_currentIndex].filename == filename) {
        _checkRotateHint(_currentIndex);
      }
    });
  }

  Future<List<int>?> _futureFor(String fn, WissensfreundProvider p) =>
      _futures.putIfAbsent(fn, () async {
        final bytes = await p.getImageBytes(fn);
        return bytes?.toList();
      });

  // Klemmt position nach Double-tap-Zoom-in: verhindert Bild außerhalb Viewport.
  // Koordinatensystem PV (basePosition=center): position=0 → Bildmitte = Viewportmitte.
  // Erlaubter Bereich: ±(scaledDim - outerDim)/2 wenn Bild größer als Viewport, sonst 0.
  Offset _clampPosition(Offset pos, double scale, int index) {
    final outerSize = _outerSizes[index];
    final imgSize   = index < widget.images.length
        ? _imageSizes[widget.images[index].filename] : null;
    if (outerSize == null || imgSize == null) return pos;

    double clampAxis(double p, double scaled, double outer) {
      if (scaled <= outer) return 0.0;
      final half = (scaled - outer) / 2;
      return p.clamp(-half, half);
    }
    return Offset(
      clampAxis(pos.dx, imgSize.width  * scale, outerSize.width),
      clampAxis(pos.dy, imgSize.height * scale, outerSize.height),
    );
  }

  // Limited-Cover: min(covered, contained*1.18) — entspricht dem PV-initialScale.
  // Stimmt numerisch mit PhotoViewComputedScale.contained*1.18 überein (Zoom-out-Ziel).
  double _initialScaleFor(int index) {
    if (index >= widget.images.length) return 1.0;
    final imgSize   = _imageSizes[widget.images[index].filename];
    final outerSize = _outerSizes[index];
    if (imgSize == null || outerSize == null) return 1.0;
    final sc = math.min(outerSize.width / imgSize.width, outerSize.height / imgSize.height);
    final sk = math.max(outerSize.width / imgSize.width, outerSize.height / imgSize.height);
    return math.min(sk, sc * 1.18);
  }

  // Setzt den Controller einer Seite auf Basis-Scale zurück (nach Wischen).
  void _resetController(int index) {
    final ctrl = _pvControllers[index];
    if (ctrl == null) return;
    _pvAnimControllers.remove(index)?.dispose();
    final initScale = _initialScaleFor(index);
    ctrl.updateMultiple(scale: initScale, position: Offset.zero);
  }

  // Doppeltipp via Listener.onPointerDown (kein GestureArena-Konflikt):
  // erster Pointer DOWN → speichert Zeit/Position;
  // zweiter Pointer DOWN (≤300ms, ≤40px) → löst _handleDoubleTap aus.
  void _trackPointerDown(PointerDownEvent event, int index) {
    final now = DateTime.now();
    if (_lastTapIndex == index &&
        _lastTapTime != null &&
        now.difference(_lastTapTime!) < const Duration(milliseconds: 300) &&
        _lastTapPos != null &&
        (event.localPosition - _lastTapPos!).distance < 40) {
      _lastTapTime = null;
      final ctrl = _ctrlFor(index);
      _handleDoubleTap(event.localPosition, ctrl.value, ctrl, index);
    } else {
      _lastTapTime  = now;
      _lastTapPos   = event.localPosition;
      _lastTapIndex = index;
    }
  }

  void _handleDoubleTap(Offset tapPos, PhotoViewControllerValue value,
      PhotoViewController ctrl, int index) {
    final currentScale = value.scale ?? 1.0;
    final currentPos   = value.position;
    final outerSize    = _outerSizes[index] ?? Size.zero;
    final outerCenter  = Offset(outerSize.width / 2, outerSize.height / 2);
    final initScale    = _initialScaleFor(index);

    _pvAnimControllers.remove(index)?.dispose();
    final ac = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 230));
    _pvAnimControllers[index] = ac;
    final curve = CurvedAnimation(parent: ac, curve: Curves.easeOut);

    final double targetScale;
    final Offset targetPos;

    if (currentScale > initScale * 1.05) {
      // Zoom-out: zurück zur Ausgangsgröße, zentriert (PV position=0 = Bildmitte)
      targetScale = initScale;
      targetPos   = Offset.zero;
      if (mounted) setState(() => _isZoomed = false);
    } else {
      // Zoom-in: 2.5× auf Tippposition. Fokuspunkt unter dem Finger bleibt fest.
      // Formel: newPos = (tapPos - outerCenter) * (1 - r) + currentPos * r
      // mit r = targetScale / currentScale. Äquivalent zur alten newCx/newCy-Formel.
      // _clampPosition stellt sicher, dass das Bild nach der Animation im Viewport bleibt.
      targetScale = initScale * 2.5;
      final r = targetScale / currentScale;
      final rawPos = (tapPos - outerCenter) * (1 - r) + currentPos * r;
      targetPos = _clampPosition(rawPos, targetScale, index);
      if (mounted) setState(() => _isZoomed = true);
    }

    final scaleTween = Tween<double>(begin: currentScale, end: targetScale);
    final posTween   = Tween<Offset>(begin: currentPos, end: targetPos);
    ac.addListener(() => ctrl.updateMultiple(
          scale:    scaleTween.evaluate(curve),
          position: posTween.evaluate(curve),
        ));
    ac.forward();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<WissensfreundProvider>(
      builder: (ctx, provider, _) {
        final images = widget.images;
        if (images.isEmpty) {
          return const Scaffold(
              backgroundColor: Colors.black, body: SizedBox.shrink());
        }

        final cur        = images[_currentIndex];
        final hasCaption = cur.caption != null && cur.caption!.isNotEmpty;

        return Scaffold(
          backgroundColor: Colors.black,
          body: OrientationBuilder(
            builder: (_, orientation) {
              return Stack(
                fit: StackFit.expand,
                children: [
                  // ── PageView + PhotoViewGestureDetectorScope ──────────────
                  // Der Scope gibt PhotoViewGestureRecognizer den Kontext:
                  //   2-Pointer (Pinch) → immer PhotoView
                  //   1-Pointer am Bildrand → PageView (Seitenwechsel)
                  //   1-Pointer auf Bild (nicht am Rand) → PhotoView (Panning)
                  PhotoViewGestureDetectorScope(
                    axis: Axis.horizontal,
                    child: PageView.builder(
                      controller:    _pageCtrl,
                      onPageChanged: _onPageChanged,
                      itemCount:     images.length,
                      itemBuilder:   (_, i) =>
                          _buildPage(i, images[i], provider),
                    ),
                  ),

                  // ── ← Zurück ─────────────────────────────────────────────
                  SafeArea(
                    child: Align(
                      alignment: Alignment.topLeft,
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: _OverlayBtn(
                          icon:  Icons.arrow_back_rounded,
                          onTap: () => Navigator.of(context).pop(),
                        ),
                      ),
                    ),
                  ),

                  // ── 🔊 Speaker (Bildunterschrift vorlesen) ────────────────
                  if (hasCaption)
                    SafeArea(
                      child: Align(
                        alignment: Alignment.topRight,
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: _OverlayBtn(
                            icon:   Icons.volume_up_rounded,
                            dimmed: _speakerUsed,
                            onTap:  _speakerUsed
                                ? null
                                : () {
                                    setState(() => _speakerUsed = true);
                                    provider.interruptForCaption(cur.caption!);
                                  },
                          ),
                        ),
                      ),
                    ),

                  // ── Dreh-Hinweis ─────────────────────────────────────────
                  if (_showRotateHint && orientation == Orientation.portrait)
                    Positioned(
                      bottom: MediaQuery.of(context).padding.bottom + 60,
                      left: 0, right: 0,
                      child: Center(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 8),
                          decoration: BoxDecoration(
                            color:        Colors.black54,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.screen_rotation_rounded,
                                  color: Colors.white70, size: 18),
                              SizedBox(width: 6),
                              Text('Handy drehen',
                                  style: TextStyle(
                                      color: Colors.white70, fontSize: 13)),
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
    final future     = _futureFor(img.filename, provider);
    final hasCaption = img.caption != null && img.caption!.isNotEmpty;
    final imgCount   = widget.images.length;

    return FutureBuilder<List<int>?>(
      key:    ValueKey(img.filename),
      future: future,
      builder: (ctx, snap) {
        if (snap.data == null) {
          return const Center(
              child: CircularProgressIndicator(color: Colors.white54));
        }
        final bytes = Uint8List.fromList(snap.data!);
        _onBytesLoaded(img.filename, snap.data!);

        return LayoutBuilder(builder: (_, constraints) {
          _outerSizes[index] =
              Size(constraints.maxWidth, constraints.maxHeight);
          // Systembar-Inset (iOS home indicator / Android Nav-Bar in nicht-immersiver Phase)
          final bottomInset = MediaQuery.of(ctx).padding.bottom;

          return Stack(
            fit: StackFit.expand,
            children: [
              // ── PhotoView (in Listener für Double-tap via raw pointer) ────
              // Listener nimmt NICHT am GestureArena teil → kein Pinch-Konflikt.
              // disableDoubleTap:true verhindert PV-eigene nextScaleState-Logik.
              // onTapUp entfernt → kein TapGestureRecognizer in der Arena.
              Listener(
                behavior: HitTestBehavior.translucent,
                onPointerDown: (event) => _trackPointerDown(event, index),
                child: PhotoView(
                  key:               ValueKey('pv_${img.filename}'),
                  imageProvider:     MemoryImage(bytes),
                  controller:        _ctrlFor(index),
                  initialScale:      PhotoViewComputedScale.contained * 1.18,
                  minScale:          PhotoViewComputedScale.contained * 1.18,
                  maxScale:          PhotoViewComputedScale.covered * 4.0,
                  strictScale:       true,
                  backgroundDecoration:
                      const BoxDecoration(color: Colors.black),
                  filterQuality:     FilterQuality.high,
                  disableDoubleTap:  true,
                  onScaleStart: (ctx, details, value) {
                    _pvAnimControllers.remove(index)?.dispose();
                  },
                  scaleStateChangedCallback: (state) {
                    if (index != _currentIndex) return;
                    final zoomed = state != PhotoViewScaleState.initial &&
                        state != PhotoViewScaleState.zoomedOut;
                    if (zoomed != _isZoomed && mounted) {
                      setState(() => _isZoomed = zoomed);
                    }
                  },
                  loadingBuilder: (ctx, event) => const Center(
                      child: CircularProgressIndicator(color: Colors.white54)),
                ),
              ),

              // ── Caption-Gradient + Text ──────────────────────────────────
              if (hasCaption) ...[
                Positioned(
                  left: 0, right: 0, bottom: 0,
                  height: 80 + bottomInset,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin:  Alignment.topCenter,
                        end:    Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.6),
                        ],
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: 60, right: 12, bottom: 12 + bottomInset,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: Text(
                          img.caption!,
                          textAlign: TextAlign.center,
                          maxLines:  2,
                          overflow:  TextOverflow.ellipsis,
                          style: const TextStyle(
                            color:     Colors.white,
                            fontSize:  13,
                            height:    1.4,
                            fontStyle: FontStyle.italic,
                            shadows:   [
                              Shadow(color: Colors.black87, blurRadius: 4)
                            ],
                          ),
                        ),
                      ),
                      if (imgCount > 1) ...[
                        const SizedBox(width: 8),
                        Text(
                          '${index + 1} / $imgCount',
                          style: const TextStyle(
                            color:      Colors.white60,
                            fontSize:   12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],

              // ── Zähler ohne Caption ──────────────────────────────────────
              if (!hasCaption && imgCount > 1)
                Positioned(
                  right: 46, bottom: 12 + bottomInset,
                  child: Text(
                    '${index + 1} / $imgCount',
                    style: const TextStyle(
                      color:      Colors.white70,
                      fontSize:   12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),

              // ── ⓘ Lizenz (nur ungezoomt) ─────────────────────────────────
              if (!_isZoomed && widget.onLicenseInfo != null)
                Positioned(
                  right:  12,
                  bottom: (hasCaption ? 88 : 12) + bottomInset,
                  child: GestureDetector(
                    onTap: () => widget.onLicenseInfo!(context, index),
                    child: Container(
                      width: 28, height: 28,
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.50),
                        shape: BoxShape.circle,
                      ),
                      child: const Center(
                        child: Text('ⓘ',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                height: 1.1)),
                      ),
                    ),
                  ),
                ),
            ],
          );
        });
      },
    );
  }
}

class _OverlayBtn extends StatelessWidget {
  final IconData      icon;
  final VoidCallback? onTap;
  final bool          dimmed;

  const _OverlayBtn({required this.icon, this.onTap, this.dimmed = false});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44, height: 44,
        decoration: BoxDecoration(
          color:        Colors.black54,
          borderRadius: BorderRadius.circular(22),
        ),
        child: Icon(icon,
            color: dimmed ? Colors.white38 : Colors.white, size: 24),
      ),
    );
  }
}
