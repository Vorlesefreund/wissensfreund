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

/// Begrenzt Inhalt auf einem Tablet auf eine angenehme Maximalbreite und
/// richtet ihn oben-zentriert aus — so werden Formular-/Textspalten auf der
/// breiten Fläche nicht auseinandergezogen.
///
/// Auf dem Handy ([ResponsiveContext.isTablet] == false) wird das Kind
/// **unverändert** zurückgegeben; der bestehende Handy-Baum bleibt Byte für
/// Byte erhalten (kein zusätzliches Align/ConstrainedBox).
class TabletMaxWidth extends StatelessWidget {
  final double maxWidth;
  final Widget child;
  const TabletMaxWidth({
    super.key,
    this.maxWidth = 560,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    if (!context.isTablet) return child;
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}

/// Wie [TabletMaxWidth], aber für **Bottom-Sheets**: begrenzt die Breite und
/// zentriert horizontal, ohne sich vertikal auszudehnen.
///
/// [TabletMaxWidth] richtet oben-zentriert aus und sein `Align` füllt die
/// verfügbare Höhe — in einem `showModalBottomSheet` würde das Sheet dadurch
/// über den ganzen Schirm aufziehen und der Inhalt oben kleben. `heightFactor:
/// 1.0` bemisst die Höhe stattdessen exakt am Kind, sodass das Sheet seine
/// inhaltsbemessene Höhe und seine Lage unten behält.
///
/// Handy-Modus unverändert: gibt bei `!isTablet` das Kind unangetastet zurück.
class TabletMaxWidthSheet extends StatelessWidget {
  final double maxWidth;
  final Widget child;
  const TabletMaxWidthSheet({
    super.key,
    this.maxWidth = 560,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    if (!context.isTablet) return child;
    return Align(
      alignment: Alignment.bottomCenter,
      heightFactor: 1.0,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}
