import 'dart:math';

class ProfessorPhrases {
  static final _rng = Random();

  static String pick(List<String> list) => list[_rng.nextInt(list.length)];

  static final quizInvitation = [
    'Lust auf ein kleines Quiz? 🎯',
    'Ich habe noch ein paar Fragen für dich!',
    // TODO: 8 weitere Einträge
  ];

  static final wowPrefix = [
    'Und weißt du was?',
    'Das ist wirklich unglaublich:',
    // TODO: 8 weitere Einträge
  ];

  static final faktPrefix = [
    'Übrigens:',
    'Wusstest du schon?',
    // TODO: 8 weitere Einträge
  ];

  static final quizNextQuestion = [
    'Weiter zur nächsten Frage!',
    'Gut gemacht — weiter geht\'s!',
    // TODO: 8 weitere Einträge
  ];

  static final quizResult100 = [
    'Super! Alles richtig! 🎉',
    'Perfekt — du hast alles gewusst! 🌟',
    // TODO: 8 weitere Einträge
  ];

  static final quizResultGood = [
    'Gut gemacht!',
    'Das war schon richtig gut!',
    // TODO: 8 weitere Einträge
  ];

  static final quizResultTryAgain = [
    'Fast — beim nächsten Mal schaffst du mehr!',
    'Das war knifflig — nicht aufgeben!',
    // TODO: 8 weitere Einträge
  ];
}
