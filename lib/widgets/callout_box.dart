import 'package:flutter/material.dart';
import '../models/rendered_article.dart';

class CalloutBox extends StatefulWidget {
  final RenderedBox box;
  final bool isActive;
  const CalloutBox({required this.box, this.isActive = false, super.key});

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
        border: widget.isActive
            ? Border.all(color: const Color(0xFF2D6A4F), width: 2.5)
            : null,
        boxShadow: widget.isActive
            ? [const BoxShadow(color: Color(0x33000000), blurRadius: 8, spreadRadius: 1)]
            : null,
      ),
      child: widget.box.type == 'stimmt_das'
          ? _buildStimmt()
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

  Widget _buildStimmt() {
    final revealMode = widget.box.revealMode;
    final explanation = widget.box.explanation ?? '';
    final correct = widget.box.answer ?? false;
    final explanationStyle = TextStyle(
      fontSize: 14,
      height: 1.45,
      fontWeight: FontWeight.w500,
      color: correct ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
    );

    if (!revealMode) {
      // reveal_mode: false → Erklärung sofort sichtbar
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(_emoji(), style: const TextStyle(fontSize: 24)),
              const SizedBox(width: 8),
              const Text(
                'Stimmt das wirklich?',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(widget.box.text, style: const TextStyle(fontSize: 14, height: 1.45)),
          if (explanation.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(explanation, style: explanationStyle),
          ],
        ],
      );
    }

    // reveal_mode: true → Kind tippt um Erklärung zu sehen
    return GestureDetector(
      onTap: _revealed ? null : () => setState(() => _revealed = true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(_emoji(), style: const TextStyle(fontSize: 24)),
              const SizedBox(width: 8),
              const Text(
                'Stimmt das wirklich?',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(widget.box.text, style: const TextStyle(fontSize: 14, height: 1.45)),
          const SizedBox(height: 8),
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 300),
            crossFadeState: _revealed
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            firstChild: Text(
              'Tippe auf die Box um die Antwort zu sehen',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
            secondChild: explanation.isNotEmpty
                ? Text(explanation, style: explanationStyle)
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}
