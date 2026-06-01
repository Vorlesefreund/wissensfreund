import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/profile_service.dart';
import 'profile_creation_screen.dart';

class ProfileManagementScreen extends StatelessWidget {
  const ProfileManagementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8EE),
        elevation: 0,
        title: const Text(
          'Profile verwalten',
          style: TextStyle(
            color: Color(0xFF2E7D32),
            fontWeight: FontWeight.w800,
            fontSize: 20,
          ),
        ),
        iconTheme: const IconThemeData(color: Color(0xFF2E7D32)),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_circle_outline_rounded),
            tooltip: 'Neues Profil',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => const ProfileCreationScreen(),
                fullscreenDialog: true,
              ),
            ),
          ),
        ],
      ),
      body: Consumer<ProfileService>(
        builder: (context, ps, _) {
          if (!ps.hasProfiles) {
            return const Center(
              child: Text(
                'Keine Profile vorhanden.',
                style: TextStyle(color: Color(0xFF888888), fontSize: 16),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: ps.profiles.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (_, i) {
              final profile = ps.profiles[i];
              final isActive = ps.activeProfile?.id == profile.id;
              return Container(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: isActive
                      ? Border.all(color: const Color(0xFF4CAF50), width: 2)
                      : null,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.06),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: ListTile(
                  onTap: isActive
                      ? null
                      : () => ps.setActiveProfile(profile),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 8,
                  ),
                  leading: Container(
                    width: 52,
                    height: 52,
                    decoration: const BoxDecoration(
                      color: Color(0xFFE8F5E9),
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text(
                        profile.avatarId,
                        style: const TextStyle(fontSize: 28),
                      ),
                    ),
                  ),
                  title: Row(
                    children: [
                      Text(
                        profile.name,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF1B5E20),
                        ),
                      ),
                      if (isActive) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE8F5E9),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            'Aktiv',
                            style: TextStyle(
                              fontSize: 11,
                              color: Color(0xFF2E7D32),
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  subtitle: Text(
                    '${profile.age} Jahre · ${_levelLabel(profile.languageLevel)}',
                    style: const TextStyle(
                      fontSize: 13,
                      color: Color(0xFF888888),
                    ),
                  ),
                  trailing: PopupMenuButton<_Action>(
                    icon: const Icon(Icons.more_vert_rounded,
                        color: Color(0xFF888888)),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    onSelected: (action) => _handleAction(context, ps, profile, action),
                    itemBuilder: (_) => [
                      const PopupMenuItem(
                        value: _Action.edit,
                        child: Row(children: [
                          Icon(Icons.edit_rounded, size: 18, color: Color(0xFF2E7D32)),
                          SizedBox(width: 10),
                          Text('Bearbeiten'),
                        ]),
                      ),
                      PopupMenuItem(
                        value: _Action.delete,
                        enabled: ps.profiles.length > 1,
                        child: Row(children: [
                          Icon(Icons.delete_outline_rounded,
                              size: 18,
                              color: ps.profiles.length > 1
                                  ? Colors.red.shade700
                                  : Colors.grey),
                          const SizedBox(width: 10),
                          Text(
                            'Löschen',
                            style: TextStyle(
                              color: ps.profiles.length > 1
                                  ? Colors.red.shade700
                                  : Colors.grey,
                            ),
                          ),
                        ]),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  void _handleAction(
    BuildContext context,
    ProfileService ps,
    UserProfile profile,
    _Action action,
  ) {
    switch (action) {
      case _Action.edit:
        showDialog<void>(
          context: context,
          builder: (_) => _EditProfileDialog(profile: profile),
        );
      case _Action.delete:
        _confirmDelete(context, ps, profile);
    }
  }

  void _confirmDelete(
    BuildContext context,
    ProfileService ps,
    UserProfile profile,
  ) {
    showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Profil löschen?'),
        content: Text(
          'Das Profil von "${profile.name}" wird dauerhaft gelöscht. '
          'Verlauf und Favoriten gehen verloren.',
          style: const TextStyle(fontSize: 15),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () async {
              Navigator.pop(ctx);
              await ps.deleteProfile(profile.id);
            },
            child: const Text('Löschen'),
          ),
        ],
      ),
    );
  }

  static String _levelLabel(String level) => switch (level) {
    'easy'     => 'Einfach',
    'advanced' => 'Fortgeschritten',
    _          => 'Mittel',
  };
}

// ── Edit Profile Dialog ────────────────────────────────────────────────────────

enum _Action { edit, delete }

class _EditProfileDialog extends StatefulWidget {
  final UserProfile profile;
  const _EditProfileDialog({required this.profile});

  @override
  State<_EditProfileDialog> createState() => _EditProfileDialogState();
}

class _EditProfileDialogState extends State<_EditProfileDialog> {
  late final TextEditingController _nameCtrl;
  late int _birthYear;
  late String _avatarId;
  late String _languageLevel;

  @override
  void initState() {
    super.initState();
    _nameCtrl       = TextEditingController(text: widget.profile.name);
    _birthYear      = widget.profile.birthYear;
    _avatarId       = widget.profile.avatarId;
    _languageLevel  = widget.profile.languageLevel;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now().year;
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: const Text('Profil bearbeiten'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Avatar row
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  '🦁','🐼','🦊','🐸','🐙',
                  '🦋','🦄','🐬','🦅','🐘',
                  '🐯','🦓','🦒','🦜','🐳',
                  '🐺','🦔','🐢','🦕','⭐',
                ].map((a) {
                  final sel = a == _avatarId;
                  return GestureDetector(
                    onTap: () => setState(() => _avatarId = a),
                    child: Container(
                      margin: const EdgeInsets.only(right: 6),
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: sel ? const Color(0xFFE8F5E9) : Colors.transparent,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: sel ? const Color(0xFF4CAF50) : Colors.transparent,
                          width: 2,
                        ),
                      ),
                      child: Center(
                        child: Text(a, style: const TextStyle(fontSize: 22)),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),
            // Name
            TextField(
              controller: _nameCtrl,
              decoration: const InputDecoration(
                labelText: 'Name',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            // Birth year slider
            Text('Alter: ${now - _birthYear} Jahre',
                style: const TextStyle(fontSize: 14)),
            Slider(
              value: _birthYear.toDouble(),
              min: (now - 18).toDouble(),
              max: (now - 3).toDouble(),
              divisions: 15,
              activeColor: const Color(0xFF4CAF50),
              onChanged: (v) => setState(() => _birthYear = v.round()),
            ),
            const SizedBox(height: 4),
            // Language level
            DropdownButtonFormField<String>(
              initialValue: _languageLevel,
              decoration: const InputDecoration(
                labelText: 'Sprachniveau',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(value: 'easy',     child: Text('Einfach')),
                DropdownMenuItem(value: 'medium',   child: Text('Mittel')),
                DropdownMenuItem(value: 'advanced', child: Text('Fortgeschritten')),
              ],
              onChanged: (v) => setState(() => _languageLevel = v!),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Abbrechen'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
          onPressed: () async {
            final updated = widget.profile.copyWith(
              name:          _nameCtrl.text.trim(),
              birthYear:     _birthYear,
              avatarId:      _avatarId,
              languageLevel: _languageLevel,
            );
            await context.read<ProfileService>().updateProfile(updated);
            if (context.mounted) Navigator.pop(context);
          },
          child: const Text('Speichern'),
        ),
      ],
    );
  }
}
