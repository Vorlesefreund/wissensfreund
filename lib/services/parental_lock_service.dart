import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:local_auth/local_auth.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Globaler Navigator-Key. Erlaubt [ParentalLockService.authenticate], den
/// PIN-Dialog selbst zu zeigen — dadurch ist JEDE Aufrufstelle automatisch
/// geschützt und keine künftige kann die Prüfung versehentlich auslassen.
final GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();

/// Zeigt den Eltern-PIN-Dialog. Wird von [main.dart] gesetzt, damit der Service
/// keine Widget-Abhängigkeit hat (sonst Import-Zyklus Service ↔ Widget).
/// Rückgabe: `true` = korrekt authentifiziert / PIN gesetzt.
typedef ParentalPinPrompt = Future<bool> Function(
  BuildContext context, {
  required bool create,
  required String reason,
});

class ParentalLockService extends ChangeNotifier {
  static const _channel = MethodChannel('wissensfreund/parental');
  static final instance = ParentalLockService._();
  ParentalLockService._();

  final _localAuth = LocalAuthentication();

  /// Wird beim App-Start registriert (siehe main.dart).
  ParentalPinPrompt? pinPrompt;

  bool _showOverlay           = false;
  bool _onboardingDone        = false;
  bool _suppressOverlay       = false;
  bool _isKioskMode           = false;
  bool _kioskAutoStart        = false;
  bool _hasOverlayPermission = false;

  bool _hasDeviceLock = false;

  bool get showOverlay          => _showOverlay;
  bool get onboardingDone       => _onboardingDone;
  bool get isKioskMode          => _isKioskMode;
  bool get hasOverlayPermission => _hasOverlayPermission;

  /// Zuletzt ermittelter Stand von [deviceLockAvailable] — synchron für die UI
  /// (wird in [init] und [_refreshStatus] aktualisiert). Ist er `false`, läuft
  /// der Eltern-Schutz nur über die App-PIN und die Gerätesperre wird dringend
  /// empfohlen.
  bool get hasDeviceLock => _hasDeviceLock;

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
    _pinningEnabled = prefs.getBool('kiosk_pinning_enabled') ?? false;
    await _loadPinState();
    await _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    _hasDeviceLock = await deviceLockAvailable();
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

  /// Aktualisiert den Kinderschutz-Status (Kiosk, Overlay-Berechtigung,
  /// Gerätesperre). Nach Rückkehr aus Systemeinstellungen oder App-Resume.
  Future<void> refreshStatus() => _refreshStatus();

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

  // ── Screen-Pinning (optional) ──────────────────────────────────────────────

  bool _pinningEnabled = false;

  /// Heftet die App zusätzlich per Android-Screen-Pinning an. Standard: aus.
  ///
  /// Warum optional: Ohne Device-Owner-Provisioning zeigt Android bei JEDEM
  /// Anheften einen eigenen Systemdialog („kann auf personenbezogene Daten
  /// zugreifen", „kann andere Apps öffnen"). Der Text ist nicht änderbar und
  /// wirkt bei einer Kinder-App unseriös (PO-Urteil). Deshalb entscheiden
  /// Eltern bewusst darüber; der Standardschutz ist Overlay + immersiveSticky.
  bool get pinningEnabled => _pinningEnabled;

  Future<void> setPinningEnabled(bool value) async {
    _pinningEnabled = value;
    final prefs = await SharedPreferences.getInstance();
    // Die Kotlin-Seite liest diesen Wert direkt (onResume) — Schluessel dort:
    // "flutter.kiosk_pinning_enabled".
    await prefs.setBool('kiosk_pinning_enabled', value);
    try {
      await _channel.invokeMethod(value ? 'startPinning' : 'stopPinning');
    } catch (_) {}
    notifyListeners();
  }

  /// Kiosk-Modus beim App-Start automatisch aktivieren (wenn zuvor aktiviert).
  Future<void> tryAutoStartKiosk() async {
    if (!_kioskAutoStart || _isKioskMode) return;
    await startKioskMode();
  }

  /// Prüft die Eltern-Berechtigung.
  ///
  /// Reihenfolge: **Gerätesperre gewinnt immer** (Fingerabdruck/PIN/Muster —
  /// bequem und vom System abgesichert), sonst **App-eigene Eltern-PIN**.
  ///
  /// PO-Entscheidung (bewusst): Richtet jemand nachträglich eine Gerätesperre
  /// ein, greift ab dann sie — auch wenn eine App-PIN existiert. Das ist zugleich
  /// ein Ausweg bei vergessener PIN und theoretisch ein Umweg für ein älteres
  /// Kind. Gegenmaßnahme ist die dringende Empfehlung, von Anfang an eine
  /// Gerätesperre einzurichten (Onboarding + Kinderschutz-Screen).
  ///
  /// WICHTIG — vormalige Sicherheitslücke: Hier stand
  /// `if (!supported) return true;` — auf einem Gerät OHNE Sperrbildschirm war
  /// damit die gesamte Kindersicherung wirkungslos (Kiosk verlassen, Kindermodus
  /// abschalten, Datenlimit ändern). Genau der Normalfall auf einem Kinder-Tablet.
  /// Es wird nie wieder ohne Prüfung `true` zurückgegeben.
  Future<bool> authenticate(String reason) async {
    if (await deviceLockAvailable()) {
      try {
        return await _localAuth.authenticate(
          localizedReason: reason,
          persistAcrossBackgrounding: true,
        );
      } catch (_) {
        return false;
      }
    }
    return _authenticateWithAppPin(reason);
  }

  /// Ist eine Gerätesperre (Biometrie oder Geräte-PIN/Muster) nutzbar?
  Future<bool> deviceLockAvailable() async {
    try {
      return await _localAuth.isDeviceSupported();
    } catch (_) {
      return false;
    }
  }

  Future<bool> _authenticateWithAppPin(String reason) async {
    // PIN-Zustand VOR dem Context-Zugriff laden — so entsteht keine async-Lücke,
    // über die der Context veralten könnte.
    await _loadPinState();
    final ctx = appNavigatorKey.currentContext;
    final prompt = pinPrompt;
    // Ohne (lebenden) UI-Kanal gibt es keine Freigabe — Fail-closed statt Fail-open.
    if (ctx == null || prompt == null || !ctx.mounted) return false;
    // Bestandsinstallation oder Onboarding übersprungen: PIN jetzt einrichten.
    return prompt(ctx, create: !_hasAppPin, reason: reason);
  }

  // ── Eltern-PIN (Fallback ohne Gerätesperre) ────────────────────────────────

  static const _pinHashKey  = 'parental_pin_hash';
  static const _pinSaltKey  = 'parental_pin_salt';
  static const _secQKey     = 'parental_sec_question';
  static const _secHashKey  = 'parental_sec_answer_hash';
  static const _secSaltKey  = 'parental_sec_answer_salt';

  bool _hasAppPin = false;
  bool get hasAppPin => _hasAppPin;

  String? _secQuestion;
  /// Die gesetzte Sicherheitsfrage (für den „PIN vergessen?"-Weg), oder null.
  String? get securityQuestion => _secQuestion;

  Future<void> _loadPinState() async {
    final prefs = await SharedPreferences.getInstance();
    // Frisch von der Platte lesen: Die PIN kann per Sicherheitsfrage auch am
    // Kiosk-Overlay zurückgesetzt worden sein — das passiert nativ
    // (ParentalUnlockActivity), an Darts In-Memory-Cache vorbei. Ohne reload()
    // prüfte die App danach weiter gegen den alten Hash.
    await prefs.reload();
    _hasAppPin = (prefs.getString(_pinHashKey) ?? '').isNotEmpty;
    _secQuestion = prefs.getString(_secQKey);
  }

  // Gesalzener SHA-256 — weder PIN noch Antwort werden je im Klartext gespeichert.
  String _hash(String value, String salt) =>
      sha256.convert(utf8.encode('$salt:$value')).toString();

  String _newSalt() {
    final rnd = Random.secure();
    return base64Url.encode(List<int>.generate(16, (_) => rnd.nextInt(256)));
  }

  /// Setzt die PIN. [question]/[answer] optional — beim Ersteinrichten Pflicht,
  /// beim Zurücksetzen per Sicherheitsfrage bleibt die alte Frage bestehen.
  Future<void> setAppPin(String pin, {String? question, String? answer}) async {
    final prefs = await SharedPreferences.getInstance();
    final salt = _newSalt();
    await prefs.setString(_pinSaltKey, salt);
    await prefs.setString(_pinHashKey, _hash(pin, salt));
    if (question != null && answer != null && answer.trim().isNotEmpty) {
      final aSalt = _newSalt();
      await prefs.setString(_secQKey, question);
      await prefs.setString(_secSaltKey, aSalt);
      await prefs.setString(_secHashKey, _hash(_normalizeAnswer(answer), aSalt));
      _secQuestion = question;
    }
    _hasAppPin = true;
    notifyListeners();
  }

  Future<bool> verifyAppPin(String pin) async {
    final prefs = await SharedPreferences.getInstance();
    final hash = prefs.getString(_pinHashKey);
    final salt = prefs.getString(_pinSaltKey);
    if (hash == null || salt == null) return false;
    return _hash(pin, salt) == hash;
  }

  /// Gross-/Kleinschreibung und Randleerzeichen dürfen die Antwort nicht
  /// scheitern lassen — „Müller " und „müller" sind dieselbe Antwort.
  String _normalizeAnswer(String a) => a.trim().toLowerCase();

  Future<bool> verifySecurityAnswer(String answer) async {
    final prefs = await SharedPreferences.getInstance();
    final hash = prefs.getString(_secHashKey);
    final salt = prefs.getString(_secSaltKey);
    if (hash == null || salt == null) return false;
    return _hash(_normalizeAnswer(answer), salt) == hash;
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
