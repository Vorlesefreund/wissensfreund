import 'dart:math';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/profile_service.dart';
import '../utils/responsive.dart';
import 'home_screen.dart';

// ── Avatar palette ────────────────────────────────────────────────────────────

const _avatars = [
  '🦁', '🐼', '🦊', '🐸', '🐙',
  '🦋', '🦄', '🐬', '🦅', '🐘',
  '🐯', '🦓', '🦒', '🦜', '🐳',
  '🐺', '🦔', '🐢', '🦕', '⭐',
];

// ── Age level options ─────────────────────────────────────────────────────────

const _ageLevels = [
  (level: 1, emoji: '🌟', label: 'Kleine Forscher',  desc: 'Für Kinder bis 6 Jahre'),
  (level: 2, emoji: '🔍', label: 'Entdecker',         desc: 'Für Kinder von 7–9 Jahren'),
  (level: 3, emoji: '🚀', label: 'Wissensprofis',     desc: 'Für Kinder ab 10 Jahren'),
];

// ── Confetti particle ──────────────────────────────────────────────────────────

class _Particle {
  double x, y, vx, vy, size;
  Color color;
  _Particle(Random rng, double w)
      : x  = rng.nextDouble() * w,
        y  = -20,
        vx = (rng.nextDouble() - 0.5) * 3,
        vy = 2 + rng.nextDouble() * 3,
        size = 6 + rng.nextDouble() * 8,
        color = [
          const Color(0xFF4CAF50),
          const Color(0xFFFFC107),
          const Color(0xFFE91E63),
          const Color(0xFF2196F3),
          const Color(0xFFFF9800),
        ][rng.nextInt(5)];
}

class _ConfettiPainter extends CustomPainter {
  final List<_Particle> particles;
  _ConfettiPainter(this.particles);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint();
    for (final p in particles) {
      paint.color = p.color;
      canvas.drawRect(
        Rect.fromCenter(center: Offset(p.x, p.y), width: p.size, height: p.size * 0.5),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_ConfettiPainter old) => true;
}

// ── Main screen ───────────────────────────────────────────────────────────────

class ProfileCreationScreen extends StatefulWidget {
  final bool isFirstProfile;
  const ProfileCreationScreen({super.key, this.isFirstProfile = false});

  @override
  State<ProfileCreationScreen> createState() => _ProfileCreationScreenState();
}

class _ProfileCreationScreenState extends State<ProfileCreationScreen>
    with TickerProviderStateMixin {
  final _pageController = PageController();
  int _step = 0; // 0–3

  // Form state
  final _nameController = TextEditingController();
  String _avatarId = _avatars[0];
  static const _languageLevel = 'medium';
  int _ageLevel = 2;

  // Confetti
  late AnimationController _confettiCtrl;
  final List<_Particle> _particles = [];
  final _rng = Random();

  @override
  void initState() {
    super.initState();
    _confettiCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..addListener(_tickConfetti);
  }

  @override
  void dispose() {
    _pageController.dispose();
    _nameController.dispose();
    _confettiCtrl.dispose();
    super.dispose();
  }

  void _tickConfetti() {
    if (!mounted) return;
    final size = MediaQuery.of(context).size;
    setState(() {
      if (_particles.length < 80 && _confettiCtrl.value < 0.5) {
        _particles.add(_Particle(_rng, size.width));
      }
      for (final p in _particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.1;
      }
      _particles.removeWhere((p) => p.y > size.height + 20);
    });
  }

  void _next() {
    if (_step < 3) {
      FocusScope.of(context).unfocus();
      setState(() => _step++);
      _pageController.animateToPage(
        _step,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
      if (_step == 3) _startConfetti();
    }
  }

  bool get _canProceed {
    switch (_step) {
      case 0: return _nameController.text.trim().isNotEmpty;
      default: return true;
    }
  }

  void _startConfetti() {
    _particles.clear();
    _confettiCtrl.forward(from: 0);
  }

  Future<void> _finish() async {
    final ps = context.read<ProfileService>();
    final profile = await ps.createProfile(
      name:          _nameController.text.trim(),
      avatarId:      _avatarId,
      languageLevel: _languageLevel,
      ageLevel:      _ageLevel,
    );
    await ps.setActiveProfile(profile);
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const HomeScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !widget.isFirstProfile,
      child: Scaffold(
        backgroundColor: const Color(0xFFFFF8EE),
        body: Stack(
          children: [
            TabletMaxWidth(
                child: SafeArea(
              child: Column(
                children: [
                  _buildHeader(),
                  _buildStepIndicator(),
                  Expanded(
                    child: PageView(
                      controller: _pageController,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        _NameStep(
                          controller: _nameController,
                          onChange: () => setState(() {}),
                        ),
                        _AgeLevelStep(
                          selected: _ageLevel,
                          onChange: (v) => setState(() => _ageLevel = v),
                        ),
                        _AvatarStep(
                          selected: _avatarId,
                          onChange: (v) => setState(() => _avatarId = v),
                        ),
                        _DoneStep(
                          name: _nameController.text.trim(),
                          avatar: _avatarId,
                        ),
                      ],
                    ),
                  ),
                  _buildButtons(),
                  const SizedBox(height: 24),
                ],
              ),
            )),
            if (_step == 3)
              IgnorePointer(
                child: AnimatedBuilder(
                  animation: _confettiCtrl,
                  builder: (_, __) => CustomPaint(
                    size: MediaQuery.of(context).size,
                    painter: _ConfettiPainter(List.of(_particles)),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: Row(
        children: [
          if (_step > 0 && _step < 3)
            IconButton(
              icon: const Icon(Icons.arrow_back_rounded, color: Color(0xFF2E7D32)),
              onPressed: () {
                setState(() => _step--);
                _pageController.animateToPage(
                  _step,
                  duration: const Duration(milliseconds: 300),
                  curve: Curves.easeInOut,
                );
              },
            )
          else
            const SizedBox(width: 48),
          const Expanded(
            child: Text(
              'Neues Profil',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: Color(0xFF2E7D32),
              ),
            ),
          ),
          if (!widget.isFirstProfile && _step < 3)
            IconButton(
              icon: const Icon(Icons.close_rounded, color: Color(0xFF888888)),
              onPressed: () => Navigator.of(context).pop(),
            )
          else
            const SizedBox(width: 48),
        ],
      ),
    );
  }

  Widget _buildStepIndicator() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(4, (i) {
          final active = i == _step;
          final done   = i < _step;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            margin: const EdgeInsets.symmetric(horizontal: 4),
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

  Widget _buildButtons() {
    if (_step == 3) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: FilledButton.icon(
          icon: const Icon(Icons.rocket_launch_rounded),
          label: const Text(
            'Los geht\'s!',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF2E7D32),
            minimumSize: const Size(double.infinity, 56),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(50)),
          ),
          onPressed: _finish,
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: _canProceed ? const Color(0xFF2E7D32) : const Color(0xFFCCCCCC),
          minimumSize: const Size(double.infinity, 56),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(50)),
        ),
        onPressed: _canProceed ? _next : null,
        child: Text(
          _step == 2 ? 'Fertig' : 'Weiter',
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}

// ── Step 1: Name ──────────────────────────────────────────────────────────────

class _NameStep extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onChange;
  const _NameStep({required this.controller, required this.onChange});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('Wie heißt du?', style: _titleStyle),
          const SizedBox(height: 8),
          const Text(
            'Gib deinen Namen oder Spitznamen ein.',
            style: _subtitleStyle,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          TextField(
            controller: controller,
            onChanged: (_) => onChange(),
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            decoration: InputDecoration(
              hintText: 'z.B. Lena',
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: const BorderSide(color: Color(0xFF4CAF50), width: 2),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: const BorderSide(color: Color(0xFFCCCCCC)),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(16),
                borderSide: const BorderSide(color: Color(0xFF4CAF50), width: 2),
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Step 2: Age level ─────────────────────────────────────────────────────────

class _AgeLevelStep extends StatelessWidget {
  final int selected;
  final ValueChanged<int> onChange;
  const _AgeLevelStep({required this.selected, required this.onChange});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('Welche Stufe?', style: _titleStyle),
          const SizedBox(height: 8),
          const Text(
            'Eltern wählen die passende Lernstufe.\nDie Stufe kann jederzeit geändert werden.',
            style: _subtitleStyle,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          ..._ageLevels.map((lvl) {
            final isSelected = lvl.level == selected;
            return GestureDetector(
              onTap: () => onChange(lvl.level),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                decoration: BoxDecoration(
                  color: isSelected ? const Color(0xFFE8F5E9) : Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: isSelected ? const Color(0xFF4CAF50) : const Color(0xFFDDDDDD),
                    width: isSelected ? 2.5 : 1,
                  ),
                ),
                child: Row(
                  children: [
                    Text(lvl.emoji, style: const TextStyle(fontSize: 28)),
                    const SizedBox(width: 16),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Stufe ${lvl.level} — ${lvl.label}',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: isSelected
                                ? const Color(0xFF2E7D32)
                                : const Color(0xFF333333),
                          ),
                        ),
                        Text(
                          lvl.desc,
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(0xFF888888),
                          ),
                        ),
                      ],
                    ),
                    const Spacer(),
                    if (isSelected)
                      const Icon(Icons.check_circle_rounded,
                          color: Color(0xFF4CAF50), size: 24),
                  ],
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ── Step 3: Avatar ────────────────────────────────────────────────────────────

class _AvatarStep extends StatelessWidget {
  final String selected;
  final ValueChanged<String> onChange;
  const _AvatarStep({required this.selected, required this.onChange});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          const SizedBox(height: 8),
          const Text('Wähle dein Tier!', style: _titleStyle),
          const SizedBox(height: 4),
          const Text(
            'Das ist dein Begleiter in Wissensfreund.',
            style: _subtitleStyle,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 5,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
              ),
              itemCount: _avatars.length,
              itemBuilder: (_, i) {
                final avatar = _avatars[i];
                final isSelected = avatar == selected;
                return GestureDetector(
                  onTap: () => onChange(avatar),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    decoration: BoxDecoration(
                      color: isSelected ? const Color(0xFFE8F5E9) : Colors.white,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: isSelected ? const Color(0xFF4CAF50) : Colors.transparent,
                        width: 2.5,
                      ),
                      boxShadow: isSelected
                          ? [BoxShadow(
                              color: const Color(0xFF4CAF50).withValues(alpha: 0.3),
                              blurRadius: 8,
                            )]
                          : [],
                    ),
                    child: Center(
                      child: Text(avatar, style: const TextStyle(fontSize: 32)),
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

// ── Step 4: Done ──────────────────────────────────────────────────────────────

class _DoneStep extends StatelessWidget {
  final String name;
  final String avatar;
  const _DoneStep({required this.name, required this.avatar});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(avatar, style: const TextStyle(fontSize: 80)),
          const SizedBox(height: 20),
          Text(
            'Hallo, $name!',
            style: const TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w900,
              color: Color(0xFF1B5E20),
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          const Text(
            'Dein Profil ist fertig.\nBereit zum Entdecken?',
            style: TextStyle(
              fontSize: 18,
              color: Color(0xFF555555),
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ── Shared text styles ────────────────────────────────────────────────────────

const _titleStyle = TextStyle(
  fontSize: 24,
  fontWeight: FontWeight.w800,
  color: Color(0xFF1B5E20),
);

const _subtitleStyle = TextStyle(
  fontSize: 15,
  color: Color(0xFF666666),
  height: 1.4,
);
