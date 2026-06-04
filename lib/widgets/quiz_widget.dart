import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/wf_article.dart';
import '../providers/wissensfreund_provider.dart';
import '../utils/professor_phrases.dart';

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

  // Each question gets a stable "Weiter" phrase so it doesn't change on rebuild.
  late final List<String> _nextPhrases = List.generate(
    widget.quiz.questions.length,
    (_) => ProfessorPhrases.pick(ProfessorPhrases.quizNextQuestion),
  );
  late final String _result100Phrase =
      ProfessorPhrases.pick(ProfessorPhrases.quizResult100);
  late final String _resultGoodPhrase =
      ProfessorPhrases.pick(ProfessorPhrases.quizResultGood);
  late final String _resultTryPhrase =
      ProfessorPhrases.pick(ProfessorPhrases.quizResultTryAgain);

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
      _speakResult();
    } else {
      setState(() {
        _questionIdx++;
        _selectedKey = null;
        _answered = false;
      });
    }
  }

  void _speakQuestion() {
    final q = _question;
    final optionTexts = q.options
        .map((o) => '${o.key.toUpperCase()}: ${o.text}')
        .join('. ');
    final text = '${q.question} $optionTexts';
    context.read<WissensfreundProvider>().speakInterrupt(text);
  }

  void _speakResult() {
    final total = widget.quiz.questions.length;
    final String phrase;
    if (_correctCount == total) {
      phrase = _result100Phrase;
    } else if (_correctCount >= (total / 2).ceil()) {
      phrase = '$_resultGoodPhrase $_correctCount von $total richtig!';
    } else {
      phrase = '$_resultTryPhrase $_correctCount von $total richtig!';
    }
    context.read<WissensfreundProvider>().speakInterrupt(phrase);
  }

  String _resultText() {
    final total = widget.quiz.questions.length;
    if (_correctCount == total) return _result100Phrase;
    if (_correctCount >= (total / 2).ceil()) {
      return '$_resultGoodPhrase $_correctCount von $total richtig!';
    }
    return '$_resultTryPhrase $_correctCount von $total richtig!';
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
    final emoji = _correctCount == total
        ? '🎉'
        : _correctCount >= (total / 2).ceil()
            ? '👍'
            : '🤔';
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 48)),
        const SizedBox(height: 12),
        Text(
          _resultText(),
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }

  Widget _buildQuestion() {
    final total = widget.quiz.questions.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Header row: 🔊 links, Fortschritt rechts
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            GestureDetector(
              onTap: _speakQuestion,
              child: Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: const Color(0xFFE3F2FD),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text('🔊', style: TextStyle(fontSize: 18)),
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
          style: const TextStyle(
              fontSize: 17, fontWeight: FontWeight.w600, height: 1.4),
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
            style: const TextStyle(
                fontSize: 13, color: Color(0xFF455A64), height: 1.4),
          ),
          const SizedBox(height: 12),
        ] else if (_answered) ...[
          const SizedBox(height: 8),
        ],

        // Weiter button
        if (_answered)
          SizedBox(
            height: 52,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF2D6A4F),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
              onPressed: _next,
              child: Text(
                _questionIdx >= total - 1
                    ? 'Ergebnis anzeigen'
                    : _nextPhrases[_questionIdx],
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w600),
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
        fillColor = Colors.green.shade400;
        borderColor = const Color(0xFF388E3C);
        textColor = Colors.white;
      } else if (selected) {
        fillColor = Colors.red.shade400;
        borderColor = const Color(0xFFC62828);
        textColor = Colors.white;
      }
    }

    return SizedBox(
      width: double.infinity,
      height: 52,
      child: GestureDetector(
        onTap: answered ? null : onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: fillColor ?? Colors.white,
            borderRadius: BorderRadius.circular(10),
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
                    color: fillColor != null
                        ? textColor
                        : const Color(0xFF607D8B),
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
