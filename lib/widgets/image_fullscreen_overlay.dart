import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:photo_view_plus/photo_view_plus.dart';
import 'package:photo_view_plus/photo_view_plus_gallery.dart';
import 'package:provider/provider.dart';

import '../providers/wissensfreund_provider.dart';
import '../utils/system_ui.dart';

// Doppeltipp-Cycle: zoom-in → covering (füllt Bildschirm), zoom-out → initial.
// WICHTIG: nie zoomedOut zurückgeben — PV's _blindScaleStateListener prüft
// isZooming (= zoomedIn|zoomedOut) und überspringt Animation bei zoomedOut-Ziel.
// 'initial' hat dieselbe Scale wie zoomedOut (= initialScale = contained),
// ist aber nicht in isZooming → Animation läuft korrekt.
PhotoViewScaleState _scaleStateCycle(PhotoViewScaleState state) {
  if (state == PhotoViewScaleState.initial ||
      state == PhotoViewScaleState.zoomedOut) {
    return PhotoViewScaleState.covering;
  }
  return PhotoViewScaleState.initial;
}

const _kBlurredBackdrop = true;

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

  bool _isZoomed = false;
  Timer? _rotateHintTimer;
  bool _showRotateHint = false;

  final _imageRatios             = <String, double?>{};
  final _imageSizes              = <String, Size>{};
  final _pvControllers           = <int, PhotoViewController>{};
  final _pvScaleStateControllers = <int, PhotoViewScaleStateController>{};
  final _loadedBytes             = <String, Uint8List>{};
  final _startedLoading          = <String>{};

  // Double-tap detection (via onTapDown timing, works even when DTGR wins arena).
  DateTime? _lastTapDownTime;
  int?      _lastTapIndex;

  // Custom zoom animation (3-step cycle, drives ctrl.updateMultiple directly).
  late final AnimationController _zoomAnimCtrl;
  int    _zoomAnimIndex    = -1;
  double _zoomAnimFromScale = 1.0;
  double _zoomAnimToScale   = 1.0;
  Offset _zoomAnimFromPos   = Offset.zero;
  Offset _zoomAnimToPos     = Offset.zero;
  bool   _zoomAnimToBase    = false;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex.clamp(
        0, (widget.images.length - 1).clamp(0, widget.images.length));
    _pageCtrl = PageController(initialPage: _currentIndex);
    _zoomAnimCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 220))
      ..addListener(_onZoomAnimTick)
      ..addStatusListener(_onZoomAnimStatus);

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
    _zoomAnimCtrl.dispose();
    for (final c in _pvControllers.values) { c.dispose(); }
    for (final c in _pvScaleStateControllers.values) { c.dispose(); }
    _rotateHintTimer?.cancel();
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    restoreSystemUI();
    super.dispose();
  }

  PhotoViewController _ctrlFor(int i) =>
      _pvControllers.putIfAbsent(i, () => PhotoViewController());

  PhotoViewScaleStateController _scaleStateCtrlFor(int i) =>
      _pvScaleStateControllers.putIfAbsent(
          i, () => PhotoViewScaleStateController());

  // Startet Ladevorgang für ein Bild (einmalig; speichert Bytes + triggert Rebuild).
  void _startLoading(String fn, WissensfreundProvider provider) {
    if (_startedLoading.contains(fn)) return;
    _startedLoading.add(fn);
    provider.getImageBytes(fn).then((bytes) {
      if (!mounted || bytes == null) return;
      _onBytesLoaded(fn, bytes.toList());
      setState(() => _loadedBytes[fn] = bytes);
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

  // Numerisch konsistent mit PhotoViewComputedScale.contained * 1.18.
  double _initialScaleFor(int index) {
    if (index >= widget.images.length) return 1.0;
    final imgSize = _imageSizes[widget.images[index].filename];
    if (imgSize == null) return 1.0;
    final outer = MediaQuery.sizeOf(context);
    final sc = math.min(
        outer.width / imgSize.width, outer.height / imgSize.height);
    return sc;
  }

  void _resetController(int index) {
    final ctrl = _pvControllers[index];
    if (ctrl == null) return;
    ctrl.updateMultiple(scale: _initialScaleFor(index), position: Offset.zero);
    // Reset scaleState to initial so PV recognises true rest state:
    // shouldMove → false, double-tap cycle re-arms, _blindScaleListener silent.
    _pvScaleStateControllers[index]?.reset();
  }

  void _onPageChanged(int index) {
    _zoomAnimCtrl.stop();
    _resetController(_currentIndex);
    _resetController(index);
    setState(() {
      _currentIndex = index;
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

  // Manual double-tap via onTapDown timing. TGR fires onTapDown for EVERY
  // pointer-down (even for the 2nd tap of a double-tap where DTGR wins arena).
  // Min 80ms guards against pinch (2 fingers within <40ms).
  void _onImageTapDown(int index, TapDownDetails details) {
    final now = DateTime.now();
    if (_lastTapIndex == index &&
        _lastTapDownTime != null &&
        now.difference(_lastTapDownTime!) > const Duration(milliseconds: 80) &&
        now.difference(_lastTapDownTime!) < const Duration(milliseconds: 300)) {
      _lastTapDownTime = null;
      _lastTapIndex    = null;
      _handleDoubleTap(index, details.localPosition);
    } else {
      _lastTapDownTime = now;
      _lastTapIndex    = index;
    }
  }

  // 3-step cycle: Basis → Stufe 1 (2.5×) → Max (covered*4) → Basis → …
  // Reads ctrl.scale directly → zustandslos, funktioniert nach jedem Pinch.
  void _handleDoubleTap(int index, Offset tapLocalPos) {
    final ctrl     = _ctrlFor(index);
    final minScale = _initialScaleFor(index);
    final maxScale = _computeMaxScale(index);
    final s0       = ctrl.scale ?? minScale;

    if (s0 <= minScale * 1.05) {
      final s1 = minScale * 2.5;
      _animateTo(index, s1, _focalPos(index, tapLocalPos, s0, s1));
      if (mounted) setState(() => _isZoomed = true);
    } else if (s0 <= minScale * 2.5 * 1.05) {
      final s1 = maxScale;
      _animateTo(index, s1, _focalPos(index, tapLocalPos, s0, s1));
      if (mounted) setState(() => _isZoomed = true);
    } else {
      // Über Stufe 1 (auch nach Pinch) → zurück zur Basis.
      _animateTo(index, minScale, Offset.zero, toBase: true);
      if (mounted) setState(() => _isZoomed = false);
    }
  }

  double _computeMaxScale(int index) {
    if (index >= widget.images.length) return 4.0;
    final imgSize = _imageSizes[widget.images[index].filename];
    if (imgSize == null) return 4.0;
    final outer = MediaQuery.sizeOf(context);
    return math.max(outer.width / imgSize.width, outer.height / imgSize.height) * 4.0;
  }

  // Berechnet Zielposition so dass tapLocalPos unter dem Finger bleibt.
  Offset _focalPos(int index, Offset tapLocalPos, double s0, double s1) {
    if (index >= widget.images.length) return Offset.zero;
    final imgSize = _imageSizes[widget.images[index].filename];
    if (imgSize == null) return Offset.zero;
    final outer  = MediaQuery.sizeOf(context);
    final center = Offset(outer.width / 2, outer.height / 2);
    final p0     = _ctrlFor(index).position;
    final p1     = tapLocalPos - center - (tapLocalPos - center - p0) * (s1 / s0);
    // Clampen auf PVs gültige Pan-Range (gleiche Formel wie photo_view_layout.dart cornersX/Y).
    final halfX  = math.max(0.0, (imgSize.width  * s1 - outer.width)  / 2);
    final halfY  = math.max(0.0, (imgSize.height * s1 - outer.height) / 2);
    return Offset(p1.dx.clamp(-halfX, halfX), p1.dy.clamp(-halfY, halfY));
  }

  void _animateTo(int index, double toScale, Offset toPos, {bool toBase = false}) {
    final ctrl        = _ctrlFor(index);
    _zoomAnimIndex    = index;
    _zoomAnimFromScale = ctrl.scale ?? _initialScaleFor(index);
    _zoomAnimToScale  = toScale;
    _zoomAnimFromPos  = ctrl.position;
    _zoomAnimToPos    = toPos;
    _zoomAnimToBase   = toBase;
    _zoomAnimCtrl
      ..stop()
      ..value = 0.0
      ..forward();
  }

  void _onZoomAnimTick() {
    final ctrl = _pvControllers[_zoomAnimIndex];
    if (ctrl == null) return;
    final t = Curves.easeOut.transform(_zoomAnimCtrl.value);
    ctrl.updateMultiple(
      scale:    _zoomAnimFromScale + (_zoomAnimToScale - _zoomAnimFromScale) * t,
      position: _zoomAnimFromPos   + (_zoomAnimToPos   - _zoomAnimFromPos)   * t,
    );
  }

  void _onZoomAnimStatus(AnimationStatus status) {
    if (status != AnimationStatus.completed) return;
    if (_zoomAnimToBase) {
      // Exakter Reset: scaleState auf initial → PV erkennt Ruhezustand.
      _pvScaleStateControllers[_zoomAnimIndex]?.reset();
      if (mounted) setState(() => _isZoomed = false);
    }
  }

  // After pinch-out reaching base: reset scaleState so PV recognises rest state.
  void _onScaleEnd(int index, ScaleEndDetails details, PhotoViewControllerValue value) {
    _zoomAnimCtrl.stop();
    final minScale = _initialScaleFor(index);
    final s = value.scale;
    if (s != null && s <= minScale * 1.01) {
      _pvScaleStateControllers[index]?.reset();
      if (mounted) setState(() => _isZoomed = false);
    }
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

        final cur         = images[_currentIndex];
        final hasCaption  = cur.caption != null && cur.caption!.isNotEmpty;
        final imgCount    = images.length;
        final bottomInset = MediaQuery.of(context).padding.bottom;

        // Seitenoptionen aufbauen; Ladevorgang pro Bild starten.
        // PhotoViewGallery (non-builder) cached NICHT → pageOptions werden
        // bei jedem Rebuild neu ausgewertet → Spinner → Bild-Transition korrekt.
        final pageOptions = List.generate(images.length, (index) {
          final img = images[index];
          _startLoading(img.filename, provider);
          final bytes = _loadedBytes[img.filename];

          if (bytes == null) {
            return PhotoViewGalleryPageOptions.customChild(
              pageKey: ValueKey('loading_$index'),
              child: const Center(
                  child: CircularProgressIndicator(color: Colors.white54)),
            );
          }

          return PhotoViewGalleryPageOptions(
            pageKey:              ValueKey(img.filename),
            imageProvider:        MemoryImage(bytes),
            controller:           _ctrlFor(index),
            scaleStateController: _scaleStateCtrlFor(index),
            initialScale:         PhotoViewComputedScale.contained,
            minScale:             PhotoViewComputedScale.contained,
            maxScale:             PhotoViewComputedScale.covered * 4.0,
            strictScale:          true,
            filterQuality:        FilterQuality.high,
            scaleStateCycle:      _scaleStateCycle,
            disableDoubleTap:     true,
            onTapDown:   (ctx, details, value) => _onImageTapDown(index, details),
            onScaleStart:(ctx, details, value) => _zoomAnimCtrl.stop(),
            onScaleEnd:  (ctx, details, value) => _onScaleEnd(index, details, value),
          );
        });

        return Scaffold(
          backgroundColor: Colors.black,
          body: OrientationBuilder(
            builder: (_, orientation) {
              return Stack(
                fit: StackFit.expand,
                children: [
                  // ── Weichgezeichneter Hintergrund-Füller ─────────────────
                  // Nur aktiv wenn _kBlurredBackdrop=true. Liegt unter Gallery,
                  // keine Gesten. Starke Unschärfe kaschiert niedrige Auflösung.
                  if (_kBlurredBackdrop) ...[
                    if (_loadedBytes[cur.filename] != null)
                      Positioned.fill(
                        child: ImageFiltered(
                          imageFilter: ui.ImageFilter.blur(
                              sigmaX: 24,
                              sigmaY: 24,
                              tileMode: TileMode.mirror),
                          child: Image.memory(
                            _loadedBytes[cur.filename]!,
                            fit: BoxFit.cover,
                            cacheWidth: 96,
                          ),
                        ),
                      ),
                    const Positioned.fill(
                        child: ColoredBox(color: Color(0x44000000))),
                  ],

                  // ── PhotoViewGallery ─────────────────────────────────────
                  // Verwaltet PageView + PhotoViewGestureDetectorScope intern.
                  // disableDoubleTap nicht gesetzt → PV nutzt scaleStateCycle.
                  PhotoViewGallery(
                    pageOptions:       pageOptions,
                    pageController:    _pageCtrl,
                    onPageChanged:     _onPageChanged,
                    backgroundDecoration: _kBlurredBackdrop
                        ? const BoxDecoration(color: Colors.transparent)
                        : const BoxDecoration(color: Colors.black),
                    scaleStateChangedCallback: (state) {
                      final zoomed = state != PhotoViewScaleState.initial &&
                          state != PhotoViewScaleState.zoomedOut;
                      if (zoomed != _isZoomed && mounted) {
                        setState(() => _isZoomed = zoomed);
                      }
                    },
                  ),

                  // ── Caption-Gradient + Text ──────────────────────────────
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
                              cur.caption!,
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
                              '${_currentIndex + 1} / $imgCount',
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

                  // ── Zähler ohne Caption ──────────────────────────────────
                  if (!hasCaption && imgCount > 1)
                    Positioned(
                      right: 46, bottom: 12 + bottomInset,
                      child: Text(
                        '${_currentIndex + 1} / $imgCount',
                        style: const TextStyle(
                          color:      Colors.white70,
                          fontSize:   12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),

                  // ── ⓘ Lizenz (nur ungezoomt) ─────────────────────────────
                  if (!_isZoomed && widget.onLicenseInfo != null)
                    Positioned(
                      right:  12,
                      bottom: (hasCaption ? 88 : 12) + bottomInset,
                      child: GestureDetector(
                        onTap: () =>
                            widget.onLicenseInfo!(context, _currentIndex),
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
                            dimmed: provider.isCaptionPlaying,
                            onTap:  provider.isCaptionPlaying
                                ? null
                                : () => provider.interruptForCaption(
                                    cur.caption!),
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
