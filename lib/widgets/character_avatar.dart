import 'package:flutter/material.dart';

import '../models/character_config.dart';
import '../models/shop_item.dart';

/// PLACEHOLDER character rendering: a framed emoji face plus little chips for the
/// chosen hair/eyes/figure and any worn items. This is deliberately a stand-in
/// for the real layered paperdoll art — the config it displays is the real one.
class CharacterAvatar extends StatelessWidget {
  final CharacterConfig config;
  final List<ShopItem> worn;
  final double size;

  const CharacterAvatar({
    super.key,
    required this.config,
    this.worn = const [],
    this.size = 180,
  });

  @override
  Widget build(BuildContext context) {
    final hair = kHairColors[config.hairColor.clamp(0, kHairColors.length - 1)];
    final eye = kEyeColors[config.eyeColor.clamp(0, kEyeColors.length - 1)];
    final figure = kFigures[config.figure.clamp(0, kFigures.length - 1)];
    final hairStyle = kHairStyles[config.hairStyle.clamp(0, kHairStyles.length - 1)];

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [hair.$2.withValues(alpha: 0.14), Colors.white],
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
            ),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: hair.$2.withValues(alpha: 0.5), width: 2),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Hair-color band above the face as a rough placeholder cue.
              Positioned(
                top: size * 0.16,
                child: Container(
                  width: size * 0.44,
                  height: size * 0.12,
                  decoration: BoxDecoration(
                    color: hair.$2,
                    borderRadius: BorderRadius.circular(40),
                  ),
                ),
              ),
              Text(config.faceEmoji, style: TextStyle(fontSize: size * 0.42)),
              if (config.freckles)
                Positioned(
                  bottom: size * 0.30,
                  child: Text('. .',
                      style: TextStyle(
                          fontSize: size * 0.10,
                          color: const Color(0xFFB5732A),
                          fontWeight: FontWeight.bold)),
                ),
              // Worn items float around the character.
              if (worn.isNotEmpty)
                Positioned(
                  bottom: 6,
                  child: Wrap(
                    spacing: 4,
                    children: worn
                        .map((w) => Text(w.emoji,
                            style: TextStyle(fontSize: size * 0.14)))
                        .toList(),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 6,
          runSpacing: 6,
          children: [
            _Chip(label: hairStyle, color: hair.$2),
            _Chip(label: 'Augen', color: eye.$2),
            _Chip(label: figure, color: const Color(0xFF90A4AE)),
            if (config.freckles)
              const _Chip(label: 'Sommersprossen', color: Color(0xFFB5732A)),
          ],
        ),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;
  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(label,
              style: const TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF455A64))),
        ],
      ),
    );
  }
}
