import 'package:flutter/material.dart';
import '../models/rendered_article.dart';

class CalloutBox extends StatefulWidget {
  final RenderedBox box;
  const CalloutBox({required this.box, super.key});

  @override
  State<CalloutBox> createState() => _CalloutBoxState();
}

class _CalloutBoxState extends State<CalloutBox> {
  bool _revealed = false;

  Color _bgColor() => switch (widget.box.type) {
        'wow'        => Colors.amber.shade100,
        'fakt'       => Colors.blue.shade100,
        'stimmt_das' => Colors.purple.shade100,
        'warnung'    => Colors.orange.shade100,
        _            => Colors.grey.shade100,
      };

  String _emoji() => switch (widget.box.type) {
        'wow'        => '🤩',
        'fakt'       => '🔍',
        'stimmt_das' => '🤔',
        'warnung'    => '⚠️',
        _            => 'ℹ️',
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      decoration: BoxDecoration(
        color: _bgColor(),
        borderRadius: BorderRadius.circular(12),
      ),
      child: widget.box.type == 'stimmt_das' && widget.box.revealMode
          ? _buildReveal()
          : _buildStatic(),
    );
  }

  Widget _buildStatic() => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_emoji(), style: const TextStyle(fontSize: 24)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              widget.box.text,
              style: const TextStyle(fontSize: 14, height: 1.45),
            ),
          ),
        ],
      );

  static const _correctPhrases = [
    'Richtig!',
    'Genau so ist es!',
    'Super, du hast es gewusst!',
    'Ja, das stimmt!',
  ];

  Widget _buildReveal() {
    final correct = widget.box.answer ?? false;
    final explanation = widget.box.explanation ?? '';
    final phrase = correct
        ? _correctPhrases[widget.box.text.hashCode.abs() % _correctPhrases.length]
        : 'Das ist leider nicht ganz richtig.';
    final revealText = explanation.isNotEmpty ? '$phrase $explanation' : phrase;

    return GestureDetector(
      onTap: _revealed ? null : () => setState(() => _revealed = true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_emoji(), style: const TextStyle(fontSize: 24)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.box.text,
                  style: const TextStyle(fontSize: 14, height: 1.45),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (!_revealed)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 9),
              decoration: BoxDecoration(
                color: Colors.purple.shade300,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                'Tippe um die Antwort zu sehen',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.w600),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                revealText,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                  color: correct ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
