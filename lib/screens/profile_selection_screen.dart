import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/profile_service.dart';
import 'home_screen.dart';
import 'profile_creation_screen.dart';

class ProfileSelectionScreen extends StatelessWidget {
  const ProfileSelectionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      body: SafeArea(
        child: Consumer<ProfileService>(
          builder: (context, ps, _) {
            if (!ps.hasProfiles) {
              // First launch: go straight to profile creation
              WidgetsBinding.instance.addPostFrameCallback((_) {
                _openCreation(context, isFirst: true);
              });
              return const _LoadingPlaceholder();
            }
            return _ProfileGrid(profiles: ps.profiles);
          },
        ),
      ),
    );
  }

  static void _openCreation(BuildContext context, {bool isFirst = false}) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ProfileCreationScreen(isFirstProfile: isFirst),
        fullscreenDialog: true,
      ),
    );
  }
}

// ── Loading placeholder (shown for one frame on first launch) ─────────────────

class _LoadingPlaceholder extends StatelessWidget {
  const _LoadingPlaceholder();

  @override
  Widget build(BuildContext context) => const Center(
    child: CircularProgressIndicator(color: Color(0xFF4CAF50)),
  );
}

// ── Profile grid ──────────────────────────────────────────────────────────────

class _ProfileGrid extends StatelessWidget {
  final List<UserProfile> profiles;
  const _ProfileGrid({required this.profiles});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          const Text(
            '🎓',
            style: TextStyle(fontSize: 48),
          ),
          const SizedBox(height: 8),
          const Text(
            'Wissensfreund',
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w900,
              color: Color(0xFF2E7D32),
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 32),
          const Text(
            'Wer bist du heute?',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1B5E20),
            ),
          ),
          const SizedBox(height: 24),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 180,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: 0.85,
              ),
              itemCount: profiles.length + 1, // +1 for "add" card
              itemBuilder: (ctx, i) {
                if (i < profiles.length) {
                  return _ProfileCard(profile: profiles[i]);
                }
                return _AddProfileCard(
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const ProfileCreationScreen(),
                      fullscreenDialog: true,
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

// ── Profile card ──────────────────────────────────────────────────────────────

class _ProfileCard extends StatelessWidget {
  final UserProfile profile;
  const _ProfileCard({required this.profile});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        await context.read<ProfileService>().setActiveProfile(profile);
        if (!context.mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      },
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF2E7D32).withValues(alpha: 0.10),
              blurRadius: 16,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFFE8F5E9),
                shape: BoxShape.circle,
              ),
              child: Center(
                child: Text(
                  profile.avatarId,
                  style: const TextStyle(fontSize: 38),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Text(
                profile.name,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF1B5E20),
                ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '${profile.age} Jahre',
              style: const TextStyle(
                fontSize: 13,
                color: Color(0xFF888888),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Add profile card ──────────────────────────────────────────────────────────

class _AddProfileCard extends StatelessWidget {
  final VoidCallback onTap;
  const _AddProfileCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: const Color(0xFF4CAF50).withValues(alpha: 0.4),
            width: 2,
          ),
        ),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.add_circle_outline_rounded,
              size: 48,
              color: Color(0xFF4CAF50),
            ),
            SizedBox(height: 10),
            Text(
              'Neues Profil',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Color(0xFF4CAF50),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
