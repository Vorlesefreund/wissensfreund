import 'package:flutter/widgets.dart';

/// Zentrale Tablet-/Responsive-Helfer für den Wissensfreund.
///
/// WICHTIG — Handy-Modus bleibt unangetastet:
/// Diese Helfer ändern NICHTS am Handy-Verhalten. Auf dem Handy ist
/// [ResponsiveContext.isTablet] immer `false`, d. h. alle bestehenden
/// Codepfade laufen unverändert. Tablet-Anpassungen werden ausschließlich
/// additiv über `if (context.isTablet)` eingehängt, sodass der Handy-Zweig
/// Byte für Byte erhalten bleibt.

/// Breakpoint: ab 600 dp kürzester Bildschirmkante gilt ein Gerät als Tablet
/// (Material-Konvention — 7"+-Tablets liegen darüber, Handys darunter).
const double kTabletBreakpoint = 600.0;

extension ResponsiveContext on BuildContext {
  /// `true` auf Tablets (kürzeste Bildschirmkante ≥ [kTabletBreakpoint] dp).
  /// Auf Handys immer `false` → bestehender Handy-Codepfad.
  bool get isTablet =>
      MediaQuery.of(this).size.shortestSide >= kTabletBreakpoint;

  /// `true`, wenn das Gerät gerade im Querformat gehalten wird.
  bool get isLandscape =>
      MediaQuery.of(this).orientation == Orientation.landscape;

  /// Der „großer Zweispalter"-Fall: Tablet UND quer.
  bool get isTabletLandscape => isTablet && isLandscape;
}

/// Begrenzt Inhalt auf eine angenehme Maximalbreite und zentriert ihn.
///
/// Auf dem Handy (Viewport schmaler als [maxWidth]) ist das ein No-Op —
/// die Ansicht bleibt exakt wie bisher. Erst auf breiten Tablet-Screens
/// verhindert es, dass Text-/Formularspalten unangenehm auseinandergezogen
/// werden.
class MaxWidthCenter extends StatelessWidget {
  final double maxWidth;
  final Widget child;
  const MaxWidthCenter({
    super.key,
    this.maxWidth = 640,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}
