import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/image_library_service.dart';
import '../services/network_settings_service.dart';
import '../services/parental_lock_service.dart';
import '../services/storage_manager.dart';
import '../services/subscription_service.dart';
import '../widgets/parental_pin_dialog.dart';
import 'profile_creation_screen.dart';

class FirstRunScreen extends StatefulWidget {
  const FirstRunScreen({super.key});

  @override
  State<FirstRunScreen> createState() => _FirstRunScreenState();
}

class _FirstRunScreenState extends State<FirstRunScreen>
    with WidgetsBindingObserver {
  final _pageCtrl = PageController();
  int _page = 0;
  static const _kPages = 4;

  // ─── Network settings ──────────────────────────────────────────────────────
  bool _wifiUnlimited   = true;
  int  _wifiDailyMb     = 0;
  int  _wifiMonthlyMb   = 0;
  bool _mobileAllowed   = false;
  int  _mobileDailyMb   = 100;
  int  _mobileMonthlyMb = 500;
  bool _netLoading = true;
  bool _netSaving  = false;

  static const _wifiDailyOpts    = [0, 250, 500, 1024, 2048];
  static const _wifiMonthlyOpts  = [0, 1024, 5120, 10240, 51200];
  static const _mobileDailyOpts  = [25, 50, 100, 250, 500];
  static const _mobileMonthlyOpts = [100, 250, 500, 1024, 5120];

  // ─── Image quality ─────────────────────────────────────────────────────────
  bool      _imgDownloading = false;
  bool      _imgDone        = false;
  double    _imgProgress    = 0;
  int       _imgReceived    = 0;
  Duration? _imgEta;
  String?   _imgError;
  int       _freeBytes      = -1;

  // Need ~400 MB free for thumb (141 MB ZIP + extraction peak).
  // Need ~600 MB free for standard (218 MB ZIP + extraction peak).
  static const int _kRequiredBytesThumb    = 400 * 1024 * 1024;
  static const int _kRequiredBytesStandard = 600 * 1024 * 1024;

  // ─── Kiosk / child safety ──────────────────────────────────────────────────
  int  _kioskPhase  = 0; // 0 = intro, 1 = waiting for permission, 2 = done
  bool _kioskDenied = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadNetworkSettings();
    StorageManager.instance.getFreeStorageBytes().then((b) {
      if (mounted) setState(() => _freeBytes = b);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pageCtrl.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _page == 3 && _kioskPhase == 1) {
      _checkKioskPermission();
    }
  }

  Future<void> _loadNetworkSettings() async {
    final s = NetworkSettingsService.instance;
    _wifiUnlimited   = await s.wifiUnlimited;
    _wifiDailyMb     = await s.wifiDailyLimitMb;
    _wifiMonthlyMb   = await s.wifiMonthlyLimitMb;
    _mobileAllowed   = await s.mobileAllowed;
    _mobileDailyMb   = await s.mobileDailyLimitMb;
    _mobileMonthlyMb = await s.mobileMonthlyLimitMb;
    if (mounted) setState(() => _netLoading = false);
  }

  void _goTo(int page) {
    setState(() => _page = page);
    _pageCtrl.animateToPage(
      page,
      duration: const Duration(milliseconds: 350),
      curve: Curves.easeInOut,
    );
  }

  Future<void> _saveNetworkAndNext() async {
    setState(() => _netSaving = true);
    final s = NetworkSettingsService.instance;
    await s.setWifiUnlimited(_wifiUnlimited);
    await s.setWifiDailyLimitMb(_wifiDailyMb);
    await s.setWifiMonthlyLimitMb(_wifiMonthlyMb);
    await s.setMobileAllowed(_mobileAllowed);
    await s.setMobileDailyLimitMb(_mobileDailyMb);
    await s.setMobileMonthlyLimitMb(_mobileMonthlyMb);
    await s.setNetworkSettingsOffered(true);
    if (mounted) {
      setState(() => _netSaving = false);
      _goToAfterNetwork();
    }
  }

  Future<void> _skipNetworkAndNext() async {
    await NetworkSettingsService.instance.setNetworkSettingsOffered(true);
    _goToAfterNetwork();
  }

  void _goToAfterNetwork() {
    _goTo(2); // Bildseite für alle User
  }

  Future<void> _downloadImage() async {
    setState(() {
      _imgDownloading = true;
      _imgDone        = false;
      _imgError       = null;
      _imgReceived    = 0;
      _imgProgress    = 0;
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('image_quality_offered', true);
    _goTo(3); // sofort weiter — Download läuft im Hintergrund

    final error = await ImageLibraryService.instance.downloadLibrary(
      thumbTier: true,
      onProgress: (received, total, eta) {
        if (mounted) setState(() {
          _imgReceived = received;
          _imgProgress = total > 0 ? received / total : 0;
          _imgEta      = eta;
        });
      },
    );
    if (!mounted) return;
    if (error == null) {
      setState(() { _imgDownloading = false; _imgDone = true; });
      Future.delayed(const Duration(seconds: 4), () {
        if (mounted) setState(() => _imgDone = false);
      });
    } else {
      setState(() { _imgDownloading = false; _imgError = _mapImgError(error); });
    }
  }

  Future<void> _skipImageAndNext() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('image_quality_offered', true);
    _goTo(3);
  }

  Future<void> _requestKioskPermission() async {
    setState(() { _kioskPhase = 1; _kioskDenied = false; });
    await context.read<ParentalLockService>().requestOverlayPermission();
  }

  Future<void> _checkKioskPermission() async {
    final ps = context.read<ParentalLockService>();
    await ps.refreshStatus();
    if (!mounted) return;
    if (ps.hasOverlayPermission) {
      await ps.startKioskMode();
      if (mounted) setState(() { _kioskPhase = 2; _kioskDenied = false; });
    } else {
      setState(() => _kioskDenied = true);
    }
  }

  Future<void> _complete() async {
    // Kinderschutz aktiv, aber das Gerät hat keinen Sperrbildschirm? Dann jetzt
    // eine Eltern-PIN vergeben — sonst gäbe es nichts, womit sich der
    // Sperr-Bildschirm entsperren ließe.
    if (_kioskPhase == 2) await _ensureParentPin();
    if (!mounted) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_complete', true);
    await prefs.setBool('image_quality_offered', true);
    await NetworkSettingsService.instance.setNetworkSettingsOffered(true);
    if (!mounted) return;
    await context.read<ParentalLockService>().markOnboardingDone();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const ProfileCreationScreen(isFirstProfile: true)),
    );
  }

  /// Vergibt eine Eltern-PIN, falls das Gerät keine Sperre hat und noch keine
  /// PIN existiert. Bricht der Elternteil ab, greift später der Bootstrap beim
  /// ersten Zugriff auf den Eltern-Bereich — der Zugang ist nie ungeschützt.
  Future<void> _ensureParentPin() async {
    final ps = ParentalLockService.instance;
    if (await ps.deviceLockAvailable() || ps.hasAppPin) return;
    if (!mounted) return;
    await showParentalPinDialog(
      context,
      create: true,
      reason: 'Eltern-PIN festlegen',
    );
  }

  String _mapImgError(String code) {
    if (code.startsWith('http_404')) {
      return 'Bildpaket noch nicht verfügbar — bitte später erneut versuchen.';
    }
    if (code == 'no_network' || code == 'wifi_lost') return 'Keine WLAN-Verbindung.';
    if (code == 'mobile_not_allowed') return 'Mobile Daten nicht erlaubt.';
    if (code == 'limit_reached') return 'Datenlimit erreicht.';
    return 'Download fehlgeschlagen ($code).';
  }

  String _mbLabel(int mb) {
    if (mb == 0) return 'Unbegrenzt';
    if (mb >= 1024) return '${(mb / 1024).round()} GB';
    return '$mb MB';
  }

  String _fmtEta(Duration d) => d.inMinutes >= 1
      ? 'noch ca. ${d.inMinutes} min'
      : 'noch ca. ${d.inSeconds} Sek.';

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: const Color(0xFFFFF8EE),
        body: SafeArea(
          child: Column(
            children: [
              _buildTopBar(),
              _buildDownloadBanner(),
              Expanded(
                child: PageView(
                  controller: _pageCtrl,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    _buildWelcomePage(),
                    _buildNetworkPage(),
                    _buildImagePage(),
                    _buildKioskPage(),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(_kPages, (i) {
          final active = i == _page;
          final done   = i < _page;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            margin: const EdgeInsets.symmetric(horizontal: 3),
            width: active ? 24 : 8,
            height: 8,
            decoration: BoxDecoration(
              color: done || active
                  ? const Color(0xFF4CAF50)
                  : const Color(0xFFCCCCCC),
              borderRadius: BorderRadius.circular(4),
            ),
          );
        }),
      ),
    );
  }

  // ─── Page 0: Welcome ───────────────────────────────────────────────────────

  Widget _buildWelcomePage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(28, 16, 28, 16),
      child: Column(
        children: [
          const Text('🎓', style: TextStyle(fontSize: 52)),
          const SizedBox(height: 10),
          const Text(
            'Willkommen beim\nWissensfreund!',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w900,
              color: Color(0xFF1B5E20),
              height: 1.2,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 10),
          const Text(
            'Kurze Einrichtung — dann kann es losgehen.',
            style: TextStyle(fontSize: 14, color: Color(0xFF555555), height: 1.5),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
            decoration: BoxDecoration(
              color: const Color(0xFFE8F5E9),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.timer_outlined, size: 14, color: Color(0xFF2E7D32)),
                SizedBox(width: 5),
                Text(
                  'Dauert nur ca. 3 Minuten',
                  style: TextStyle(fontSize: 13, color: Color(0xFF2E7D32), fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          _InfoRow(icon: Icons.wifi_rounded,        text: 'Internet & Datennutzung festlegen'),
          _InfoRow(icon: Icons.image_outlined,      text: 'Bildqualität wählen'),
          _InfoRow(icon: Icons.security_rounded,    text: 'Kinderschutz einrichten'),
          _InfoRow(icon: Icons.person_add_rounded,  text: 'Profil erstellen'),
          const SizedBox(height: 20),
          _BigButton(
            label: 'Los geht\'s!',
            icon: Icons.arrow_forward_rounded,
            onPressed: () => _goTo(1),
          ),
        ],
      ),
    );
  }

  // ─── Page 1: Network ───────────────────────────────────────────────────────

  Widget _buildNetworkPage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.wifi_rounded, color: Color(0xFF2E7D32), size: 28),
            SizedBox(width: 12),
            Text(
              'Internet & Daten',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Color(0xFF1B5E20)),
            ),
          ]),
          const SizedBox(height: 8),
          const Text(
            'Lege fest, wann und wie viele Daten Wissensfreund herunterladen darf.',
            style: TextStyle(fontSize: 14, color: Color(0xFF666666), height: 1.45),
          ),
          const SizedBox(height: 24),
          if (_netLoading)
            const Center(child: Padding(
              padding: EdgeInsets.all(32),
              child: CircularProgressIndicator(),
            ))
          else ...[
            _SectionLabel('WLAN'),
            SwitchListTile(
              value: _wifiUnlimited,
              onChanged: (v) => setState(() => _wifiUnlimited = v),
              title: const Text('Unbegrenzt', style: TextStyle(fontSize: 14)),
              subtitle: const Text('Kein Datenlimit im WLAN', style: TextStyle(fontSize: 12)),
              dense: true,
              activeThumbColor: const Color(0xFF2E7D32),
              contentPadding: EdgeInsets.zero,
            ),
            if (!_wifiUnlimited) ...[
              _LimitDropdown(
                label: 'Tageslimit',
                value: _wifiDailyMb,
                options: _wifiDailyOpts,
                fmt: _mbLabel,
                onChanged: (v) => setState(() => _wifiDailyMb = v),
              ),
              _LimitDropdown(
                label: 'Monatslimit',
                value: _wifiMonthlyMb,
                options: _wifiMonthlyOpts,
                fmt: _mbLabel,
                onChanged: (v) => setState(() => _wifiMonthlyMb = v),
              ),
            ],
            const SizedBox(height: 16),
            _SectionLabel('Mobilfunk'),
            SwitchListTile(
              value: _mobileAllowed,
              onChanged: (v) => setState(() => _mobileAllowed = v),
              title: const Text('Downloads erlaubt', style: TextStyle(fontSize: 14)),
              subtitle: const Text('Standardmäßig deaktiviert', style: TextStyle(fontSize: 12)),
              dense: true,
              activeThumbColor: const Color(0xFF2E7D32),
              contentPadding: EdgeInsets.zero,
            ),
            if (_mobileAllowed) ...[
              _LimitDropdown(
                label: 'Tageslimit',
                value: _mobileDailyMb,
                options: _mobileDailyOpts,
                fmt: _mbLabel,
                onChanged: (v) => setState(() => _mobileDailyMb = v),
              ),
              _LimitDropdown(
                label: 'Monatslimit',
                value: _mobileMonthlyMb,
                options: _mobileMonthlyOpts,
                fmt: _mbLabel,
                onChanged: (v) => setState(() => _mobileMonthlyMb = v),
              ),
            ],
            const SizedBox(height: 32),
            _BigButton(
              label: 'Speichern & Weiter',
              icon: Icons.arrow_forward_rounded,
              loading: _netSaving,
              onPressed: _netSaving ? null : _saveNetworkAndNext,
            ),
            const SizedBox(height: 12),
            Center(
              child: TextButton(
                onPressed: _skipNetworkAndNext,
                child: Text('Überspringen', style: TextStyle(color: Colors.grey.shade600)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ─── Page 2: Image Quality (Plus/Premium only) ────────────────────────────

  Widget _buildDownloadBanner() {
    if (!_imgDownloading && !_imgDone && _imgError == null) return const SizedBox.shrink();

    final Color bg     = _imgError != null ? const Color(0xFFFFF3E0) : const Color(0xFFE8F5E9);
    final Color barClr = _imgError != null ? Colors.orange        : const Color(0xFF2E7D32);
    final IconData icon = _imgDone
        ? Icons.check_circle_rounded
        : _imgError != null
            ? Icons.warning_amber_rounded
            : Icons.download_rounded;
    final Color iconClr = _imgDone
        ? const Color(0xFF2E7D32)
        : _imgError != null
            ? Colors.orange.shade700
            : const Color(0xFF388E3C);

    String label;
    if (_imgDone) {
      label = 'Bilder erfolgreich gespeichert';
    } else if (_imgError != null) {
      label = _imgError!;
    } else if (_imgProgress > 0) {
      final pct = '${(_imgProgress * 100).round()} %';
      label = _imgEta != null ? 'Bilder: $pct  ·  ${_fmtEta(_imgEta!)}' : 'Bilder: $pct';
    } else {
      label = _imgReceived > 0
          ? 'Bilder: ${(_imgReceived / (1024 * 1024)).toStringAsFixed(1)} MB geladen…'
          : 'Bilder werden geladen…';
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      color: bg,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_imgDownloading)
            LinearProgressIndicator(
              value: _imgProgress > 0 ? _imgProgress : null,
              minHeight: 3,
              backgroundColor: const Color(0xFFC8E6C9),
              valueColor: AlwaysStoppedAnimation(barClr),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
            child: Row(
              children: [
                Icon(icon, size: 16, color: iconClr),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(label,
                      style: TextStyle(fontSize: 12, color: iconClr, fontWeight: FontWeight.w500)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildImagePage() {
    final hasEnoughSpace = _freeBytes < 0 || _freeBytes >= _kRequiredBytesThumb;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.image_outlined, color: Color(0xFF2E7D32), size: 28),
            SizedBox(width: 12),
            Text(
              'Bilder einrichten',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Color(0xFF1B5E20)),
            ),
          ]),
          const SizedBox(height: 8),
          const Text(
            'Wie soll Wissensfreund Bilder laden?',
            style: TextStyle(fontSize: 14, color: Color(0xFF666666), height: 1.45),
          ),
          const SizedBox(height: 24),
          _QualityCard(
            icon: Icons.download_rounded,
            title: 'Bilder aufs Gerät (empfohlen)',
            subtitle: '300px-Paket herunterladen — Bilder sind dann offline und schnell da',
            highlight: hasEnoughSpace,
          ),
          const SizedBox(height: 12),
          _QualityCard(
            icon: Icons.wifi_rounded,
            title: 'Nur per WLAN',
            subtitle: 'Kein Download — Bilder werden bei Bedarf über WLAN geladen',
            highlight: !hasEnoughSpace,
          ),
          if (_freeBytes >= 0 && !hasEnoughSpace) ...[
            const SizedBox(height: 10),
            Row(children: [
              Icon(Icons.warning_amber_rounded, size: 15, color: Colors.orange.shade700),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Wenig Speicherplatz (${(_freeBytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB frei). '
                  'WLAN-Modus empfohlen.',
                  style: TextStyle(fontSize: 12, color: Colors.orange.shade800),
                ),
              ),
            ]),
          ],
          const SizedBox(height: 32),
          _BigButton(
            label: hasEnoughSpace ? 'Herunterladen & weiter' : 'Weiter (nur per WLAN)',
            icon: hasEnoughSpace ? Icons.download_rounded : Icons.wifi_rounded,
            onPressed: hasEnoughSpace ? _downloadImage : _skipImageAndNext,
          ),
          // Der kleine Offline-Download ist Pflicht (die App ist ohne Bilder
          // langweilig). Nur wenn der Speicher NICHT reicht, gibt es den
          // WLAN-Ausweg — dann ist „Weiter" oben ohnehin der WLAN-Weg.
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFF1F8E9),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFC8E6C9)),
            ),
            child: const Text(
              'Mit Wissensfreund Plus gibt es Bilder in besserer Qualität (800px). '
              'Du kannst das jederzeit in den Einstellungen freischalten.',
              style: TextStyle(fontSize: 12, color: Color(0xFF558B2F), height: 1.4),
            ),
          ),
        ],
      ),
    );
  }

  // ─── Page 3: Kiosk / Child Safety ─────────────────────────────────────────

  Widget _buildKioskPage() {
    final String emoji;
    final String title;
    final String body;
    final Color titleColor;

    if (_kioskPhase == 2) {
      emoji = '✅';
      title = 'Kinderschutz ist aktiv!';
      titleColor = const Color(0xFF1B5E20);
      // Ohne Gerätesperre gäbe es keinen Fingerabdruck — dann ist die Eltern-PIN
      // der Schlüssel, und die Gerätesperre wird dringend empfohlen.
      body = ParentalLockService.instance.hasDeviceLock
          ? 'Ab jetzt erscheint ein Sperr-Bildschirm, wenn dein Kind '
              'Wissensfreund verlässt. Du kannst ihn jederzeit mit '
              'Fingerabdruck oder PIN entsperren.'
          : 'Ab jetzt erscheint ein Sperr-Bildschirm, wenn dein Kind '
              'Wissensfreund verlässt.\n\n'
              'Dieses Gerät hat keine Bildschirmsperre. Wir richten gleich eine '
              'Eltern-PIN ein — richte zusätzlich dringend eine Bildschirmsperre '
              'in den Android-Einstellungen ein, sie schützt deutlich besser.';
    } else if (_kioskDenied) {
      emoji = '⚠️';
      title = 'Berechtigung nicht erteilt';
      titleColor = Colors.red.shade700;
      body = 'Ohne diese Berechtigung kann kein Sperr-Bildschirm '
          'erscheinen. Bitte erteile sie, um dein Kind zu schützen.';
    } else if (_kioskPhase == 1) {
      emoji = '🔐';
      title = 'Fast geschafft!';
      titleColor = const Color(0xFF1B5E20);
      body = 'Bitte aktiviere in den Einstellungen den Schalter für '
          'Wissensfreund und kehre dann hierher zurück.';
    } else {
      emoji = '🔐';
      title = 'Kinderschutz einrichten';
      titleColor = const Color(0xFF1B5E20);
      body = 'Wissensfreund benötigt einmalig die Berechtigung, über '
          'anderen Apps angezeigt zu werden.\n\n'
          'So erscheint ein Sperr-Bildschirm, wenn dein Kind die App verlässt.';
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(32, 48, 32, 32),
      child: Column(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 64)),
          const SizedBox(height: 16),
          Text(
            title,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: titleColor,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            body,
            style: const TextStyle(fontSize: 15, color: Color(0xFF555555), height: 1.6),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 40),
          ..._buildKioskActions(),
        ],
      ),
    );
  }

  List<Widget> _buildKioskActions() {
    if (_kioskPhase == 2) {
      return [
        _BigButton(
          label: 'Profil erstellen',
          icon: Icons.person_add_rounded,
          onPressed: _complete,
        ),
      ];
    }
    if (_kioskPhase == 1 && !_kioskDenied) {
      return [
        Center(
          child: TextButton(
            onPressed: _complete,
            child: Text('Überspringen', style: TextStyle(color: Colors.grey.shade600)),
          ),
        ),
      ];
    }
    return [
      _BigButton(
        label: _kioskDenied
            ? 'Berechtigung erteilen'
            : 'Jetzt einrichten — empfohlen',
        icon: Icons.security_rounded,
        onPressed: _requestKioskPermission,
      ),
      const SizedBox(height: 12),
      Center(
        child: TextButton(
          onPressed: _complete,
          child: Text(
            'Ohne Kinderschutz fortfahren',
            style: TextStyle(color: Colors.grey.shade600),
          ),
        ),
      ),
    ];
  }
}

// ─── Shared helper widgets ────────────────────────────────────────────────────

class _BigButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool loading;
  const _BigButton({
    required this.label,
    required this.icon,
    this.onPressed,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: FilledButton.icon(
        icon: loading
            ? const SizedBox(
                width: 20, height: 20,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
            : Icon(icon),
        label: Text(
          label,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
        style: FilledButton.styleFrom(
          backgroundColor: onPressed != null
              ? const Color(0xFF2E7D32)
              : const Color(0xFFCCCCCC),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(50)),
        ),
        onPressed: loading ? null : onPressed,
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String text;
  const _InfoRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(icon, color: const Color(0xFF4CAF50), size: 20),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 15, color: Color(0xFF444444)))),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: Color(0xFF888888),
          letterSpacing: 1.2,
        ),
      ),
    );
  }
}

class _QualityCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool highlight;
  const _QualityCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: highlight ? const Color(0xFFE8F5E9) : const Color(0xFFF5F5F5),
        borderRadius: BorderRadius.circular(16),
        border: highlight
            ? Border.all(color: const Color(0xFF2E7D32), width: 1.5)
            : null,
      ),
      child: Row(
        children: [
          Icon(icon,
              color: highlight
                  ? const Color(0xFF2E7D32)
                  : Colors.grey.shade600,
              size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: highlight
                        ? const Color(0xFF1B5E20)
                        : const Color(0xFF333333),
                  ),
                ),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey.shade600,
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LimitDropdown extends StatelessWidget {
  final String label;
  final int value;
  final List<int> options;
  final String Function(int) fmt;
  final ValueChanged<int> onChanged;
  const _LimitDropdown({
    required this.label,
    required this.value,
    required this.options,
    required this.fmt,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: const TextStyle(fontSize: 14)),
          ),
          DropdownButton<int>(
            value: value,
            items: options
                .map((o) => DropdownMenuItem(value: o, child: Text(fmt(o))))
                .toList(),
            onChanged: (v) { if (v != null) onChanged(v); },
            isDense: true,
            underline: const SizedBox(),
          ),
        ],
      ),
    );
  }
}
