import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Setzt Status- und Navigationsleiste in den sichtbaren Standardzustand.
/// Wird beim App-Start, jedem Route-Wechsel und nach dem Artikel-Screen aufgerufen.
void restoreSystemUI() {
  SystemChrome.setEnabledSystemUIMode(
    SystemUiMode.manual,
    overlays: SystemUiOverlay.values,
  );
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    systemNavigationBarColor: Color(0xFFFFFFFF),
    systemNavigationBarIconBrightness: Brightness.dark,
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
  ));
}
