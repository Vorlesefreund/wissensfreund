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

  Widget _buildReveal() {
    final correct = widget.box.answer ?? false;
    return GestureDetector(
      onTap: _revealed ? null : () => setState(() => _revealed = true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
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
              width: double.infinity,
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
          else ...[
            Text(
              correct ? '✅ Stimmt!' : '❌ Stimmt nicht!',
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
            ),
            if ((widget.box.explanation ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                widget.box.explanation!,
                style: const TextStyle(fontSize: 13, height: 1.4),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
