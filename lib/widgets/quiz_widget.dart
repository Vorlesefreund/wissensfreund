import 'package:flutter/material.dart';
import '../models/wf_article.dart';

class QuizWidget extends StatefulWidget {
  final WfQuiz quiz;
  const QuizWidget({required this.quiz, super.key});

  @override
  State<QuizWidget> createState() => _QuizWidgetState();
}

class _QuizWidgetState extends State<QuizWidget> {
  int _questionIdx = 0;
  String? _selectedKey;
  bool _answered = false;
  int _correctCount = 0;
  bool _finished = false;

  WfQuizQuestion get _question => widget.quiz.questions[_questionIdx];

  void _selectAnswer(String key) {
    if (_answered) return;
    final correct = key == _question.correctKey;
    setState(() {
      _selectedKey = key;
      _answered = true;
      if (correct) _correctCount++;
    });
  }

  void _next() {
    final total = widget.quiz.questions.length;
    if (_questionIdx >= total - 1) {
      setState(() => _finished = true);
    } else {
      setState(() {
        _questionIdx++;
        _selectedKey = null;
        _answered = false;
      });
    }
  }

  String _resultEmoji() {
    final total = widget.quiz.questions.length;
    if (_correctCount == total) return '🎉';
    if (_correctCount >= (total / 2).ceil()) return '👍';
    return '🤔';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF0F4F8),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFCCDAE8), width: 1),
      ),
      padding: const EdgeInsets.all(16),
      child: _finished ? _buildResult() : _buildQuestion(),
    );
  }

  Widget _buildResult() {
    final total = widget.quiz.questions.length;
    return Column(
      children: [
        Text(
          _resultEmoji(),
          style: const TextStyle(fontSize: 48),
        ),
        const SizedBox(height: 12),
        Text(
          'Du hast $_correctCount von $total richtig!',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        if (_correctCount == total)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Perfekt! Du weißt alles über Elefanten!',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Color(0xFF2D6A4F)),
            ),
          ),
      ],
    );
  }

  Widget _buildQuestion() {
    final total = widget.quiz.questions.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Header row with progress
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              widget.quiz.heading,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: Color(0xFF2D6A4F),
              ),
            ),
            Text(
              'Frage ${_questionIdx + 1} von $total',
              style: const TextStyle(fontSize: 12, color: Color(0xFF607D8B)),
            ),
          ],
        ),
        const SizedBox(height: 12),

        // Question text
        Text(
          _question.question,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, height: 1.4),
        ),
        const SizedBox(height: 14),

        // Answer buttons
        for (final opt in _question.options) ...[
          _AnswerButton(
            optionKey: opt.key,
            text: opt.text,
            answered: _answered,
            selected: _selectedKey == opt.key,
            correct: opt.key == _question.correctKey,
            onTap: () => _selectAnswer(opt.key),
          ),
          const SizedBox(height: 8),
        ],

        // Explanation after answer
        if (_answered && _question.explanation.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(
            _question.explanation,
            style: const TextStyle(fontSize: 13, color: Color(0xFF455A64), height: 1.4),
          ),
          const SizedBox(height: 12),
        ] else if (_answered) ...[
          const SizedBox(height: 8),
        ],

        // Weiter button
        if (_answered)
          SizedBox(
            height: 48,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF2D6A4F),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              onPressed: _next,
              child: Text(
                _questionIdx >= total - 1 ? 'Ergebnis anzeigen' : 'Weiter →',
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
            ),
          ),
      ],
    );
  }
}

class _AnswerButton extends StatelessWidget {
  final String optionKey;
  final String text;
  final bool answered;
  final bool selected;
  final bool correct;
  final VoidCallback onTap;

  const _AnswerButton({
    required this.optionKey,
    required this.text,
    required this.answered,
    required this.selected,
    required this.correct,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    Color? fillColor;
    Color borderColor = const Color(0xFF90A4AE);
    Color textColor = const Color(0xFF37474F);

    if (answered) {
      if (correct) {
        fillColor = const Color(0xFF4CAF50);
        borderColor = const Color(0xFF388E3C);
        textColor = Colors.white;
      } else if (selected) {
        fillColor = const Color(0xFFE53935);
        borderColor = const Color(0xFFC62828);
        textColor = Colors.white;
      }
    }

    return SizedBox(
      width: double.infinity,
      height: 48,
      child: GestureDetector(
        onTap: answered ? null : onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: fillColor ?? Colors.white,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: borderColor, width: 1.5),
          ),
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            children: [
              Container(
                width: 24,
                height: 24,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: fillColor != null
                      ? Colors.white.withValues(alpha: 0.25)
                      : const Color(0xFFECEFF1),
                ),
                child: Text(
                  optionKey.toUpperCase(),
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: fillColor != null ? textColor : const Color(0xFF607D8B),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  text,
                  style: TextStyle(
                    fontSize: 14,
                    color: textColor,
                    fontWeight: selected || (answered && correct)
                        ? FontWeight.w600
                        : FontWeight.normal,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
