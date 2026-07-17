import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/parental_lock_service.dart';
import '../utils/security_questions.dart';

/// Eltern-PIN-Dialog — greift nur auf Geräten OHNE Sperrbildschirm
/// (eine Gerätesperre gewinnt immer, siehe [ParentalLockService.authenticate]).
///
/// Drei Modi:
///  * [_Mode.create]   → PIN vergeben + Sicherheitsfrage hinterlegen
///  * [_Mode.verify]   → PIN prüfen (mit „PIN vergessen?"-Ausgang)
///  * [_Mode.recover]  → Sicherheitsfrage beantworten → danach neue PIN
///
/// Gibt `true` zurück, wenn authentifiziert bzw. eingerichtet wurde.
/// Abbrechen ⇒ `false` (Fail-closed).
Future<bool> showParentalPinDialog(
  BuildContext context, {
  required bool create,
  required String reason,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _ParentalPinDialog(
      initialMode: create ? _Mode.create : _Mode.verify,
      reason: reason,
    ),
  );
  return ok ?? false;
}

const _kPinLength = 4;
const _kCustomQuestion = '__custom__';

enum _Mode { create, verify, recover }

class _ParentalPinDialog extends StatefulWidget {
  final _Mode initialMode;
  final String reason;
  const _ParentalPinDialog({required this.initialMode, required this.reason});

  @override
  State<_ParentalPinDialog> createState() => _ParentalPinDialogState();
}

class _ParentalPinDialogState extends State<_ParentalPinDialog> {
  late _Mode _mode = widget.initialMode;

  final _pin = TextEditingController();
  final _confirm = TextEditingController();
  final _answer = TextEditingController();
  final _customQuestion = TextEditingController();

  int _questionOffset = 0;
  String? _selectedQuestion;
  String? _error;
  bool _busy = false;
  int _failures = 0;

  @override
  void initState() {
    super.initState();
    _selectedQuestion = securityQuestionPage(0).first;
  }

  @override
  void dispose() {
    _pin.dispose();
    _confirm.dispose();
    _answer.dispose();
    _customQuestion.dispose();
    super.dispose();
  }

  String? get _effectiveQuestion {
    if (_selectedQuestion == _kCustomQuestion) {
      final q = _customQuestion.text.trim();
      return q.isEmpty ? null : q;
    }
    return _selectedQuestion;
  }

  // ── Aktionen ───────────────────────────────────────────────────────────────

  Future<void> _submitCreate() async {
    final pin = _pin.text.trim();
    if (pin.length != _kPinLength) {
      setState(() => _error = 'Bitte $_kPinLength Ziffern eingeben.');
      return;
    }
    if (_confirm.text.trim() != pin) {
      setState(() => _error = 'Die PINs stimmen nicht überein.');
      return;
    }
    final question = _effectiveQuestion;
    if (question == null) {
      setState(() => _error = 'Bitte eine eigene Sicherheitsfrage eingeben.');
      return;
    }
    if (_answer.text.trim().isEmpty) {
      setState(() => _error = 'Bitte die Sicherheitsfrage beantworten.');
      return;
    }
    setState(() { _busy = true; _error = null; });
    await ParentalLockService.instance
        .setAppPin(pin, question: question, answer: _answer.text);
    if (mounted) Navigator.of(context).pop(true);
  }

  Future<void> _submitVerify() async {
    final pin = _pin.text.trim();
    if (pin.length != _kPinLength) {
      setState(() => _error = 'Bitte $_kPinLength Ziffern eingeben.');
      return;
    }
    setState(() { _busy = true; _error = null; });
    final ok = await ParentalLockService.instance.verifyAppPin(pin);
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
      return;
    }
    _failures++;
    // Wachsende Wartezeit bremst systematisches Durchprobieren.
    await Future<void>.delayed(Duration(milliseconds: 400 * _failures));
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = 'Falsche PIN.';
      _pin.clear();
    });
  }

  Future<void> _submitRecover() async {
    if (_answer.text.trim().isEmpty) {
      setState(() => _error = 'Bitte die Frage beantworten.');
      return;
    }
    setState(() { _busy = true; _error = null; });
    final ok =
        await ParentalLockService.instance.verifySecurityAnswer(_answer.text);
    if (!mounted) return;
    if (ok) {
      // Antwort stimmt → neue PIN vergeben. Frage bleibt bestehen.
      setState(() {
        _busy = false;
        _mode = _Mode.create;
        _error = null;
        _pin.clear();
        _confirm.clear();
        _answer.clear();
        _selectedQuestion = ParentalLockService.instance.securityQuestion;
      });
      return;
    }
    _failures++;
    await Future<void>.delayed(Duration(milliseconds: 400 * _failures));
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = 'Antwort stimmt nicht.';
    });
  }

  // ── Aufbau ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final isCreate  = _mode == _Mode.create;
    final isRecover = _mode == _Mode.recover;
    // Beim Zurücksetzen ist die Frage bereits hinterlegt → nicht neu wählen.
    final questionAlreadySet =
        isCreate && ParentalLockService.instance.securityQuestion != null;

    return AlertDialog(
      backgroundColor: const Color(0xFFFFF8EE),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(
        children: [
          const Icon(Icons.lock_rounded, color: Color(0xFF2E7D32), size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              isRecover
                  ? 'PIN zurücksetzen'
                  : isCreate
                      ? 'Eltern-PIN festlegen'
                      : 'Eltern-PIN',
              style: const TextStyle(
                color: Color(0xFF2E7D32),
                fontWeight: FontWeight.w800,
                fontSize: 18,
              ),
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: 340,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isRecover
                    ? 'Beantworte deine Sicherheitsfrage, um eine neue PIN zu vergeben.'
                    : isCreate
                        ? 'Dieses Gerät hat keinen Sperrbildschirm. Vergib eine PIN, '
                            'damit nur du in den Eltern-Bereich kommst.'
                        : widget.reason,
                style: const TextStyle(
                    fontSize: 13, height: 1.45, color: Color(0xFF555555)),
              ),
              const SizedBox(height: 16),

              if (isRecover) ...[
                _QuestionBox(ParentalLockService.instance.securityQuestion ?? ''),
                const SizedBox(height: 10),
                _TextRow(controller: _answer, label: 'Deine Antwort'),
              ] else ...[
                _PinField(
                  controller: _pin,
                  label: isCreate ? 'Neue PIN' : 'PIN',
                  autofocus: true,
                  onSubmitted: isCreate ? null : (_) => _submitVerify(),
                ),
                if (isCreate) ...[
                  const SizedBox(height: 10),
                  _PinField(controller: _confirm, label: 'PIN wiederholen'),
                  const SizedBox(height: 14),
                  const _NoteHint(),
                  const SizedBox(height: 14),
                  if (questionAlreadySet)
                    _QuestionBox(
                        ParentalLockService.instance.securityQuestion ?? '')
                  else
                    _QuestionPicker(
                      offset: _questionOffset,
                      selected: _selectedQuestion,
                      customController: _customQuestion,
                      onSelect: (q) => setState(() => _selectedQuestion = q),
                      onMore: () => setState(() => _questionOffset += 3),
                    ),
                  const SizedBox(height: 10),
                  _TextRow(controller: _answer, label: 'Deine Antwort'),
                ],
              ],

              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!,
                    style: TextStyle(fontSize: 12, color: Colors.red.shade700)),
              ],

              // „PIN vergessen?" nur anbieten, wenn es auch eine Frage gibt.
              if (_mode == _Mode.verify &&
                  ParentalLockService.instance.securityQuestion != null) ...[
                const SizedBox(height: 4),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _mode = _Mode.recover;
                              _error = null;
                              _answer.clear();
                            }),
                    style: TextButton.styleFrom(
                        padding: EdgeInsets.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                    child: const Text('PIN vergessen?',
                        style: TextStyle(
                            fontSize: 12, color: Color(0xFF2E7D32))),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(false),
          child: const Text('Abbrechen',
              style: TextStyle(color: Color(0xFF888888))),
        ),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
          onPressed: _busy
              ? null
              : isRecover
                  ? _submitRecover
                  : isCreate
                      ? _submitCreate
                      : _submitVerify,
          child: Text(isRecover
              ? 'Weiter'
              : isCreate
                  ? 'Speichern'
                  : 'Entsperren'),
        ),
      ],
    );
  }
}

// ── Bausteine ────────────────────────────────────────────────────────────────

/// Hinweis, die PIN zusätzlich zu sichern — die Sicherheitsfrage ist der
/// Notausgang, nicht der Normalweg.
class _NoteHint extends StatelessWidget {
  const _NoteHint();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: const Color(0xFFF1F8E9),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFFC8E6C9)),
        ),
        child: const Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.photo_camera_rounded, size: 16, color: Color(0xFF558B2F)),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Notiere die PIN oder fotografiere sie — bewahre sie ausserhalb '
                'der Reichweite deines Kindes auf.',
                style: TextStyle(
                    fontSize: 11.5, height: 1.4, color: Color(0xFF558B2F)),
              ),
            ),
          ],
        ),
      );
}

class _QuestionBox extends StatelessWidget {
  final String question;
  const _QuestionBox(this.question);

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFFC8E6C9)),
        ),
        child: Text(
          question,
          style: const TextStyle(
              fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF1B5E20)),
        ),
      );
}

class _QuestionPicker extends StatelessWidget {
  final int offset;
  final String? selected;
  final TextEditingController customController;
  final ValueChanged<String> onSelect;
  final VoidCallback onMore;

  const _QuestionPicker({
    required this.offset,
    required this.selected,
    required this.customController,
    required this.onSelect,
    required this.onMore,
  });

  @override
  Widget build(BuildContext context) {
    final page = securityQuestionPage(offset);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Sicherheitsfrage — falls du die PIN vergisst:',
          style: TextStyle(
              fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF555555)),
        ),
        const SizedBox(height: 6),
        ...page.map((q) => _Choice(
              label: q,
              value: q,
              selected: selected,
              onSelect: onSelect,
            )),
        _Choice(
          label: 'Eigene Frage schreiben',
          value: _kCustomQuestion,
          selected: selected,
          onSelect: onSelect,
        ),
        if (selected == _kCustomQuestion)
          Padding(
            padding: const EdgeInsets.only(left: 28, top: 4, bottom: 4),
            child: _TextRow(
                controller: customController, label: 'Deine Frage'),
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: onMore,
            icon: const Icon(Icons.refresh_rounded, size: 15),
            style: TextButton.styleFrom(
              padding: EdgeInsets.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              foregroundColor: const Color(0xFF2E7D32),
            ),
            label: const Text('Andere Fragen anzeigen',
                style: TextStyle(fontSize: 12)),
          ),
        ),
      ],
    );
  }
}

class _Choice extends StatelessWidget {
  final String label;
  final String value;
  final String? selected;
  final ValueChanged<String> onSelect;
  const _Choice({
    required this.label,
    required this.value,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: () => onSelect(value),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                selected == value
                    ? Icons.radio_button_checked_rounded
                    : Icons.radio_button_unchecked_rounded,
                size: 18,
                color: selected == value
                    ? const Color(0xFF2E7D32)
                    : const Color(0xFFBBBBBB),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(label,
                    style: const TextStyle(fontSize: 12.5, height: 1.35)),
              ),
            ],
          ),
        ),
      );
}

class _TextRow extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  const _TextRow({required this.controller, required this.label});

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        style: const TextStyle(fontSize: 14),
        decoration: InputDecoration(
          labelText: label,
          isDense: true,
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFFC8E6C9)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFF4CAF50), width: 2),
          ),
        ),
      );
}

class _PinField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final bool autofocus;
  final ValueChanged<String>? onSubmitted;
  const _PinField({
    required this.controller,
    required this.label,
    this.autofocus = false,
    this.onSubmitted,
  });

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        autofocus: autofocus,
        obscureText: true,
        keyboardType: TextInputType.number,
        maxLength: _kPinLength,
        onSubmitted: onSubmitted,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        style: const TextStyle(fontSize: 20, letterSpacing: 8),
        decoration: InputDecoration(
          labelText: label,
          counterText: '',
          isDense: true,
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFFC8E6C9)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF4CAF50), width: 2),
          ),
        ),
      );
}
