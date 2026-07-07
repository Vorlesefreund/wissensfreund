import 'package:flutter/material.dart';

import '../models/character_config.dart';
import '../services/license_cache_db.dart';
import '../services/profile_service.dart';
import '../widgets/character_avatar.dart';

/// Character customization (Baustein 3). Placeholder rendering; the saved config
/// is the real thing and will later drive the paperdoll art.
class CharacterCustomizeScreen extends StatefulWidget {
  const CharacterCustomizeScreen({super.key});

  @override
  State<CharacterCustomizeScreen> createState() =>
      _CharacterCustomizeScreenState();
}

class _CharacterCustomizeScreenState extends State<CharacterCustomizeScreen> {
  CharacterConfig _cfg = const CharacterConfig();
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final pid = ProfileService.instance.activeProfile?.id;
    final cfg = pid == null ? null : await LicenseCacheDb.instance.getCharacter(pid);
    if (mounted) {
      setState(() {
        _cfg = cfg ?? const CharacterConfig();
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    final pid = ProfileService.instance.activeProfile?.id;
    if (pid != null) await LicenseCacheDb.instance.saveCharacter(pid, _cfg);
    if (mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8EE),
      appBar: AppBar(
        title: const Text('Charakter anpassen'),
        centerTitle: false,
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text('Fertig',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              children: [
                Center(child: CharacterAvatar(config: _cfg, size: 190)),
                const SizedBox(height: 20),
                _Section(
                  label: 'Figur',
                  child: _Choices(
                    count: kCharBases.length,
                    selected: kCharBases.indexWhere((c) => c.id == _cfg.base),
                    builder: (i) => kCharBases[i].emoji,
                    labelBuilder: (i) => kCharBases[i].label,
                    onSelect: (i) =>
                        setState(() => _cfg = _cfg.copyWith(base: kCharBases[i].id)),
                  ),
                ),
                _Section(
                  label: 'Hautton',
                  child: _Swatches(
                    colors: const [
                      Color(0xFFFAD9BE),
                      Color(0xFFE8B98E),
                      Color(0xFFC68A5E),
                      Color(0xFF9A6438),
                      Color(0xFF6B4326),
                    ],
                    selected: _cfg.skinTone,
                    onSelect: (i) => setState(() => _cfg = _cfg.copyWith(skinTone: i)),
                  ),
                ),
                _Section(
                  label: 'Frisur',
                  child: _Choices(
                    count: kHairStyles.length,
                    selected: _cfg.hairStyle,
                    builder: (i) => null,
                    labelBuilder: (i) => kHairStyles[i],
                    onSelect: (i) => setState(() => _cfg = _cfg.copyWith(hairStyle: i)),
                  ),
                ),
                _Section(
                  label: 'Haarfarbe',
                  child: _Swatches(
                    colors: kHairColors.map((e) => e.$2).toList(),
                    selected: _cfg.hairColor,
                    onSelect: (i) => setState(() => _cfg = _cfg.copyWith(hairColor: i)),
                  ),
                ),
                _Section(
                  label: 'Augenfarbe',
                  child: _Swatches(
                    colors: kEyeColors.map((e) => e.$2).toList(),
                    selected: _cfg.eyeColor,
                    onSelect: (i) => setState(() => _cfg = _cfg.copyWith(eyeColor: i)),
                  ),
                ),
                _Section(
                  label: 'Statur',
                  child: _Choices(
                    count: kFigures.length,
                    selected: _cfg.figure,
                    builder: (i) => null,
                    labelBuilder: (i) => kFigures[i],
                    onSelect: (i) => setState(() => _cfg = _cfg.copyWith(figure: i)),
                  ),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Sommersprossen',
                      style: TextStyle(fontWeight: FontWeight.w600)),
                  value: _cfg.freckles,
                  activeThumbColor: const Color(0xFF2E7D32),
                  onChanged: (v) => setState(() => _cfg = _cfg.copyWith(freckles: v)),
                ),
              ],
            ),
    );
  }
}

class _Section extends StatelessWidget {
  final String label;
  final Widget child;
  const _Section({required this.label, required this.child});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w700, color: Color(0xFF37474F))),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

class _Choices extends StatelessWidget {
  final int count;
  final int selected;
  final String? Function(int) builder; // emoji or null
  final String Function(int) labelBuilder;
  final ValueChanged<int> onSelect;
  const _Choices({
    required this.count,
    required this.selected,
    required this.builder,
    required this.labelBuilder,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: List.generate(count, (i) {
        final sel = i == selected;
        final emoji = builder(i);
        return GestureDetector(
          onTap: () => onSelect(i),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: sel ? const Color(0xFFE8F5E9) : Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: sel ? const Color(0xFF2E7D32) : const Color(0xFFD8CFC2),
                width: sel ? 2 : 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (emoji != null) ...[
                  Text(emoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 6),
                ],
                Text(labelBuilder(i),
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: sel ? FontWeight.bold : FontWeight.normal)),
              ],
            ),
          ),
        );
      }),
    );
  }
}

class _Swatches extends StatelessWidget {
  final List<Color> colors;
  final int selected;
  final ValueChanged<int> onSelect;
  const _Swatches({
    required this.colors,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: List.generate(colors.length, (i) {
        final sel = i == selected;
        return GestureDetector(
          onTap: () => onSelect(i),
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: colors[i],
              shape: BoxShape.circle,
              border: Border.all(
                color: sel ? const Color(0xFF2E7D32) : Colors.white,
                width: sel ? 3 : 2,
              ),
              boxShadow: [
                BoxShadow(
                    color: Colors.black.withValues(alpha: 0.12),
                    blurRadius: 4,
                    offset: const Offset(0, 2)),
              ],
            ),
            child: sel
                ? const Icon(Icons.check, color: Colors.white, size: 20)
                : null,
          ),
        );
      }),
    );
  }
}
