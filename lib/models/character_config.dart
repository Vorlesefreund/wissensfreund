import 'package:flutter/material.dart';

// Character customization (Baustein 3). All options are PLACEHOLDER
// representations (emoji base + colored chips) until real paperdoll art exists;
// the stored config is final and will drive the real art later.

class CharBase {
  final String id;
  final String label;
  final String emoji; // placeholder base
  const CharBase(this.id, this.label, this.emoji);
}

const List<CharBase> kCharBases = [
  CharBase('boy1', 'Junge 1', '👦'),
  CharBase('boy2', 'Junge 2', '🧒'),
  CharBase('girl1', 'Mädchen 1', '👧'),
  CharBase('girl2', 'Mädchen 2', '👩'),
];

/// Fitzpatrick emoji skin-tone modifiers.
const List<String> kSkinModifiers = ['🏻', '🏼', '🏽', '🏾', '🏿'];

const List<(String, Color)> kHairColors = [
  ('Blond', Color(0xFFE6C86E)),
  ('Braun', Color(0xFF8B5A2B)),
  ('Schwarz', Color(0xFF2B2B2B)),
  ('Rot', Color(0xFFB5532A)),
  ('Grau', Color(0xFFBDBDBD)),
];

const List<String> kHairStyles = ['Kurz', 'Lang', 'Locken', 'Zopf', 'Stachelig'];

const List<(String, Color)> kEyeColors = [
  ('Blau', Color(0xFF4A80C0)),
  ('Grün', Color(0xFF4C9A5A)),
  ('Braun', Color(0xFF7A4A2B)),
  ('Grau', Color(0xFF8A8F96)),
];

const List<String> kFigures = ['Dünn', 'Mittel', 'Dick'];

class CharacterConfig {
  final String base;
  final int skinTone; // index into kSkinModifiers
  final int hairStyle;
  final int hairColor;
  final int eyeColor;
  final bool freckles;
  final int figure;

  const CharacterConfig({
    this.base = 'boy1',
    this.skinTone = 1,
    this.hairStyle = 0,
    this.hairColor = 1,
    this.eyeColor = 0,
    this.freckles = false,
    this.figure = 1,
  });

  CharBase get baseChar =>
      kCharBases.firstWhere((c) => c.id == base, orElse: () => kCharBases.first);

  /// Placeholder composed emoji, e.g. "👦🏽".
  String get faceEmoji {
    final mod = (skinTone >= 0 && skinTone < kSkinModifiers.length)
        ? kSkinModifiers[skinTone]
        : '';
    return '${baseChar.emoji}$mod';
  }

  CharacterConfig copyWith({
    String? base,
    int? skinTone,
    int? hairStyle,
    int? hairColor,
    int? eyeColor,
    bool? freckles,
    int? figure,
  }) =>
      CharacterConfig(
        base: base ?? this.base,
        skinTone: skinTone ?? this.skinTone,
        hairStyle: hairStyle ?? this.hairStyle,
        hairColor: hairColor ?? this.hairColor,
        eyeColor: eyeColor ?? this.eyeColor,
        freckles: freckles ?? this.freckles,
        figure: figure ?? this.figure,
      );

  Map<String, dynamic> toMap(int profileId, String nowIso) => {
        'profile_id': profileId,
        'base': base,
        'skin_tone': skinTone,
        'hair_style': hairStyle,
        'hair_color': hairColor,
        'eye_color': eyeColor,
        'freckles': freckles ? 1 : 0,
        'figure': figure,
        'updated_at': nowIso,
      };

  static CharacterConfig fromMap(Map<String, dynamic> m) => CharacterConfig(
        base: m['base'] as String? ?? 'boy1',
        skinTone: m['skin_tone'] as int? ?? 1,
        hairStyle: m['hair_style'] as int? ?? 0,
        hairColor: m['hair_color'] as int? ?? 1,
        eyeColor: m['eye_color'] as int? ?? 0,
        freckles: (m['freckles'] as int? ?? 0) == 1,
        figure: m['figure'] as int? ?? 1,
      );
}
