import 'package:flutter/material.dart';
import '../providers/wissensfreund_provider.dart';

class ProfessorWidget extends StatefulWidget {
  final AppState state;
  final bool compact;
  const ProfessorWidget({super.key, required this.state, this.compact = false});

  @override
  State<ProfessorWidget> createState() => _ProfessorWidgetState();
}

class _ProfessorWidgetState extends State<ProfessorWidget>
    with TickerProviderStateMixin {
  late final AnimationController _pulseCtrl;
  late final AnimationController _blinkCtrl;
  late final Animation<double> _scale;
  late final Animation<double> _blinkOpacity;

  @override
  void initState() {
    super.initState();

    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _scale = Tween<double>(begin: 1.0, end: 1.06).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );

    _blinkCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    _blinkOpacity = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 1.0, end: 0.5), weight: 35),
      TweenSequenceItem(tween: Tween(begin: 0.5, end: 1.0), weight: 65),
    ]).animate(CurvedAnimation(parent: _blinkCtrl, curve: Curves.easeInOut));
  }

  @override
  void didUpdateWidget(ProfessorWidget old) {
    super.didUpdateWidget(old);
    if (widget.state == old.state) return;

    if (widget.state == AppState.thinking) {
      _blinkCtrl.forward(from: 0);
    }

    final shouldPulse = widget.state == AppState.listening ||
        widget.state == AppState.speaking;
    if (shouldPulse) {
      _pulseCtrl.repeat(reverse: true);
    } else {
      _pulseCtrl.animateTo(0, duration: const Duration(milliseconds: 400));
    }
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _blinkCtrl.dispose();
    super.dispose();
  }

  Color get _glowColor => switch (widget.state) {
        AppState.listening => Colors.green,
        AppState.thinking => Colors.amber,
        AppState.speaking => Colors.orange,
        _ => Colors.transparent,
      };

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_pulseCtrl, _blinkCtrl]),
      builder: (_, child) {
        final isActive = widget.state != AppState.idle;
        return Stack(
          alignment: widget.compact ? Alignment.centerRight : Alignment.center,
          children: [
            if (isActive && !widget.compact)
              Container(
                width: 220,
                height: 220,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _glowColor.withOpacity(
                      0.07 + _pulseCtrl.value * 0.07),
                  boxShadow: [
                    BoxShadow(
                      color: _glowColor.withOpacity(
                          0.25 + _pulseCtrl.value * 0.25),
                      blurRadius: 70,
                      spreadRadius: 20,
                    ),
                  ],
                ),
              ),
            if (isActive && widget.compact)
              Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: _glowColor.withOpacity(
                          0.4 + _pulseCtrl.value * 0.2),
                      blurRadius: 20,
                      spreadRadius: 6,
                    ),
                  ],
                ),
              ),
            Opacity(
              opacity: _blinkOpacity.value,
              child: Transform.scale(
                scale: widget.compact ? 1.0 : _scale.value,
                child: child!,
              ),
            ),
          ],
        );
      },
      child: SizedBox(
        height: widget.compact ? null : 260,
        child: Image.asset(
          'assets/images/professor.png',
          fit: BoxFit.contain,
          alignment: Alignment.centerRight,
        ),
      ),
    );
  }
}
