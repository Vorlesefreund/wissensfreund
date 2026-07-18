import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/parental_lock_service.dart';

/// Setzt Status- und Navigationsleiste in den sichtbaren Standardzustand.
/// Wird beim App-Start, jedem Route-Wechsel und nach dem Artikel-Screen aufgerufen.
///
/// Ausnahme Kinderschutz: Ist der Kindermodus aktiv, werden beide Leisten
/// ausgeblendet (immersiveSticky). Das Kind sieht Home/Recents dann gar nicht
/// erst, und die Schnelleinstellungen brauchen zwei bewusste Wische statt einem
/// — vorher genügte ein Wisch, um über die Leiste in die Android-Einstellungen
/// zu gelangen (PO-Fund am Tablet).
///
/// Bewusst KEIN Ersatz für Screen-Pinning: Es blockiert nicht, es versteckt.
/// Gegen ein kleines Kind wirksam, gegen ein älteres nicht. Dafür ohne
/// Systemdialog und ohne Berechtigung — deshalb der Standard.
void restoreSystemUI() {
  if (ParentalLockService.instance.isKioskMode) {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    return;
  }
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
