import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'providers/wissensfreund_provider.dart';
import 'services/data_limit_overlay_service.dart';
import 'services/parental_lock_service.dart';
import 'services/profile_service.dart';
import 'screens/first_run_screen.dart';
import 'screens/home_screen.dart';
import 'screens/profile_selection_screen.dart';
import 'widgets/data_limit_overlay.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ParentalLockService.instance.init();
  await ProfileService.instance.initialize();
  final prefs = await SharedPreferences.getInstance();
  final onboardingComplete = prefs.getBool('onboarding_complete') ?? false;
  // Kiosk-Modus nach erstem Frame automatisch reaktivieren (falls zuvor aktiviert)
  WidgetsBinding.instance.addPostFrameCallback((_) {
    ParentalLockService.instance.tryAutoStartKiosk();
  });
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => WissensfreundProvider()),
        ChangeNotifierProvider.value(value: ParentalLockService.instance),
        ChangeNotifierProvider.value(value: ProfileService.instance),
        ChangeNotifierProvider.value(value: DataLimitOverlayService.instance),
      ],
      child: WissensfreundApp(onboardingComplete: onboardingComplete),
    ),
  );
}

class WissensfreundApp extends StatefulWidget {
  final bool onboardingComplete;
  const WissensfreundApp({super.key, required this.onboardingComplete});
  @override
  State<WissensfreundApp> createState() => _WissensfreundAppState();
}

class _WissensfreundAppState extends State<WissensfreundApp>
    with WidgetsBindingObserver {
  bool _wentToBackground = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    final ps = context.read<ParentalLockService>();

    if (state == AppLifecycleState.paused) {
      _wentToBackground = true;
      final provider = context.read<WissensfreundProvider>();
      unawaited(provider.saveCurrentArticlePosition());
      // enterBackground: Timer stoppen + TTS beenden (auch Idle-Ansagen)
      unawaited(provider.enterBackground());
    } else if (state == AppLifecycleState.resumed && _wentToBackground) {
      _wentToBackground = false;
      ps.refreshAdminStatus();
      final provider = context.read<WissensfreundProvider>();
      provider.exitBackground();
      unawaited(provider.resumeSpeaking());
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wissensfreund',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4CAF50),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: !widget.onboardingComplete
          ? const FirstRunScreen()
          : ProfileService.instance.hasProfiles
              ? const HomeScreen()
              : const ProfileSelectionScreen(),
      builder: (context, child) => _AppShell(child: child!),
    );
  }
}

// ── App-Shell: hält den Eltern-Overlay über allem anderen ──────────────────

class _AppShell extends StatelessWidget {
  final Widget child;
  const _AppShell({required this.child});

  @override
  Widget build(BuildContext context) {
    return Consumer<ParentalLockService>(
      builder: (ctx, ps, _) => Stack(
        children: [
          child,
          const DataLimitOverlay(),
          if (ps.showOverlay) _ParentalOverlay(ps: ps),
        ],
      ),
    );
  }
}

// ── Eltern-Bildschirm ──────────────────────────────────────────────────────

class _ParentalOverlay extends StatefulWidget {
  final ParentalLockService ps;
  const _ParentalOverlay({required this.ps});

  @override
  State<_ParentalOverlay> createState() => _ParentalOverlayState();
}

class _ParentalOverlayState extends State<_ParentalOverlay> {
  bool _authenticated = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('🎓', style: TextStyle(fontSize: 56)),
                const SizedBox(height: 6),
                const Text(
                  'Wissensfreund',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFF2E7D32),
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 52),
                Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE8F5E9),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.green.withValues(alpha: 0.18),
                        blurRadius: 28,
                        spreadRadius: 6,
                      ),
                    ],
                  ),
                  child: Icon(
                    _authenticated ? Icons.lock_open_rounded : Icons.lock_rounded,
                    size: 52,
                    color: const Color(0xFF2E7D32),
                  ),
                ),
                const SizedBox(height: 32),
                Text(
                  _authenticated ? 'Was möchtest du tun?' : 'Für Erwachsene',
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF2E7D32),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                Text(
                  _authenticated
                      ? 'Du hast Wissensfreund entsperrt.'
                      : 'Bitte Fingerabdruck oder PIN eingeben',
                  style: const TextStyle(
                    fontSize: 16,
                    color: Color(0xFF555555),
                    height: 1.5,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 44),
                if (!_authenticated)
                  FilledButton.icon(
                    icon: const Icon(Icons.fingerprint_rounded, size: 26),
                    label: const Text(
                      'Entsperren',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 44, vertical: 18),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(50),
                      ),
                    ),
                    onPressed: () async {
                      final ok = await widget.ps.authenticate(
                        'Bitte authentifizieren um Wissensfreund zu entsperren.',
                      );
                      if (ok && mounted) {
                        setState(() => _authenticated = true);
                      }
                    },
                  )
                else ...[
                  // Zurück zu Wissensfreund
                  FilledButton.icon(
                    icon: const Icon(Icons.school_rounded, size: 22),
                    label: const Text(
                      'Zurück zu Wissensfreund',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 28, vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(50),
                      ),
                    ),
                    onPressed: () {
                      if (!mounted) return;
                      widget.ps.hideParentalOverlay();
                      widget.ps.tryAutoStartKiosk();
                      context.read<WissensfreundProvider>().resumeSpeaking();
                    },
                  ),
                  const SizedBox(height: 14),
                  // Gerät freigeben
                  OutlinedButton.icon(
                    icon: const Icon(Icons.phone_android_rounded, size: 22,
                        color: Color(0xFF555555)),
                    label: const Text(
                      'Gerät freigeben',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF555555)),
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Color(0xFFCCCCCC)),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 28, vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(50),
                      ),
                    ),
                    onPressed: () async {
                      if (!mounted) return;
                      await widget.ps.releaseKioskTemporarily();
                      if (!mounted) return;
                      widget.ps.hideParentalOverlay();
                      context.read<WissensfreundProvider>().pauseSpeaking();
                    },
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
