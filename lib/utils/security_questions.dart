/// Fragen-Pool für die Eltern-PIN-Wiederherstellung.
///
/// Auswahlkriterium: Das eigene Kind ist hier der wahrscheinlichste Angreifer —
/// es lebt im selben Haushalt und kennt Haustiere, Lieblingsfarben und
/// Urlaubsorte. Deshalb ausschliesslich Fragen aus der Zeit VOR dem Kind
/// (Jugend, erste Wohnung, erster Job) oder aus der Elternbiografie.
/// Bewusst NICHT im Pool: „Wie hiess dein erstes Haustier?", „Lieblingsfilm",
/// „Geburtsort" — das weiss ein Kind oft.
const kSecurityQuestions = <String>[
  'Wie hiess deine Klassenlehrerin in der 1. Klasse?',
  'In welcher Strasse hast du als Kind gewohnt?',
  'Wie hiess dein erster Arbeitgeber?',
  'Wie lautete dein Spitzname in der Schulzeit?',
  'Wie hiess deine beste Freundin / dein bester Freund in der Grundschule?',
  'Welches Modell war dein erstes Auto?',
  'In welcher Stadt war dein erster Urlaub ohne Eltern?',
  'Wie hiess die Strasse deiner ersten eigenen Wohnung?',
  'Welchen Beruf wolltest du als Kind ergreifen?',
  'Wie hiess dein Lieblingslehrer in der Oberstufe?',
  'In welchem Lokal hattest du dein erstes Vorstellungsgespraech?',
  'Wie hiess der erste Verein, in dem du Mitglied warst?',
];

/// Liefert [count] Fragen ab [offset] — zyklisch, damit „Andere Fragen anzeigen"
/// endlos durchblaettern kann, ohne je leer auszugehen.
List<String> securityQuestionPage(int offset, {int count = 3}) => List.generate(
      count,
      (i) => kSecurityQuestions[(offset + i) % kSecurityQuestions.length],
    );
