import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ParentalLockService extends ChangeNotifier {
  static const _channel = MethodChannel('wissensfreund/parental');
  static final instance = ParentalLockService._();
  ParentalLockService._();

  final _localAuth = LocalAuthentication();

  bool _isAdminActive         = false;
  bool _showOverlay           = false;
  bool _onboardingDone        = false;
  bool _suppressOverlay       = false;
  bool _isKioskMode           = false;
  bool _kioskAutoStart        = false;
  bool _hasOverlayPermission = false;

  bool get isAdminActive        => _isAdminActive;
  bool get showOverlay          => _showOverlay;
  bool get onboardingDone       => _onboardingDone;
  bool get isKioskMode          => _isKioskMode;
  bool get hasOverlayPermission => _hasOverlayPermission;

  /// Verhindert Eltern-Overlay UND Self-Restore beim nächsten Hintergrundwechsel.
  /// Einmalig — wird beim Prüfen automatisch zurückgesetzt.
  void suppressNextOverlay() {
    _suppressOverlay = true;
    // Kotlin-Seite informieren, damit onUserLeaveHint() nicht re-launcht
    _channel.invokeMethod('suppressRestoreOnce').catchError((_) {});
  }

  /// Gibt zurück ob das nächste Overlay unterdrückt werden soll und setzt das Flag zurück.
  bool consumeSuppressFlag() {
    final v = _suppressOverlay;
    _suppressOverlay = false;
    return v;
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _onboardingDone = prefs.getBool('parental_onboarding_done') ?? false;
    _kioskAutoStart = prefs.getBool('kiosk_auto_start') ?? false;
    await _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    try {
      _isAdminActive = await _channel.invokeMethod<bool>('isDeviceAdminActive') ?? false;
    } catch (_) {
      _isAdminActive = false;
    }
    try {
      _isKioskMode = await _channel.invokeMethod<bool>('isInKioskMode') ?? false;
    } catch (_) {
      _isKioskMode = false;
    }
    try {
      _hasOverlayPermission = await _channel.invokeMethod<bool>('hasOverlayPermission') ?? false;
    } catch (_) {
      _hasOverlayPermission = false;
    }
    notifyListeners();
  }

  Future<void> refreshAdminStatus() => _refreshStatus();

  Future<void> requestDeviceAdmin() async {
    suppressNextOverlay();
    try {
      await _channel.invokeMethod('requestDeviceAdmin');
    } catch (_) {}
  }

  /// Öffnet die Android-Einstellung "Über anderen Apps anzeigen" direkt für Wissensfreund.
  Future<void> requestOverlayPermission() async {
    suppressNextOverlay();
    try {
      await _channel.invokeMethod('requestOverlayPermission');
    } catch (_) {}
  }

  /// Gibt das Gerät vorübergehend für Eltern frei — Kiosk pausiert bis Wissensfreund wieder geöffnet wird.
  Future<void> releaseKioskTemporarily() async {
    try {
      await _channel.invokeMethod('releaseKioskTemporarily');
    } catch (_) {}
  }

  Future<bool> lockDevice() async {
    try {
      return await _channel.invokeMethod<bool>('lockDevice') ?? false;
    } catch (_) {
      return false;
    }
  }

  /// Startet den Kiosk-Modus (Lock Task Mode).
  /// Gibt true zurück wenn erfolgreich, false wenn manuelle Bildschirmfixierung nötig ist.
  Future<bool> startKioskMode() async {
    try {
      final ok = await _channel.invokeMethod<bool>('startKioskMode') ?? false;
      if (ok) {
        _isKioskMode = true;
        _kioskAutoStart = true;
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool('kiosk_auto_start', true);
        notifyListeners();
      }
      return ok;
    } catch (_) {
      return false;
    }
  }

  /// Beendet den Kiosk-Modus.
  Future<void> stopKioskMode() async {
    try {
      await _channel.invokeMethod<bool>('stopKioskMode');
    } catch (_) {}
    _isKioskMode = false;
    _kioskAutoStart = false;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('kiosk_auto_start', false);
    notifyListeners();
  }

  /// Kiosk-Modus beim App-Start automatisch aktivieren (wenn zuvor aktiviert).
  Future<void> tryAutoStartKiosk() async {
    if (!_kioskAutoStart || _isKioskMode) return;
    await startKioskMode();
  }

  Future<bool> authenticate(String reason) async {
    try {
      final supported = await _localAuth.isDeviceSupported();
      if (!supported) return true; // kein Sperrbildschirm eingerichtet → erlauben
      return await _localAuth.authenticate(
        localizedReason: reason,
        persistAcrossBackgrounding: true,
      );
    } catch (_) {
      return false;
    }
  }

  void showParentalOverlay() {
    if (_showOverlay) return;
    _showOverlay = true;
    notifyListeners();
  }

  void hideParentalOverlay() {
    _showOverlay = false;
    notifyListeners();
  }

  Future<void> markOnboardingDone() async {
    _onboardingDone = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('parental_onboarding_done', true);
    notifyListeners();
  }
}
