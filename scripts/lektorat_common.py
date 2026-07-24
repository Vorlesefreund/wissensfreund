#!/usr/bin/env python3
"""
lektorat_common.py
Gemeinsame Konstanten, Prompt-Bausteine und Batch-Ausführung für
generate_grounded.py (Post-Phase-2-Lektorat) und run_lektorat_catchtest.py.
Eine Quelle, kein Drift.
"""
import json
import logging
import re
import time
import unicodedata

log = logging.getLogger(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────

COMPANION_CHAR_CAP   = 30_000          # positional slice je Companion-Text
LEKTORAT_MODEL       = "claude-sonnet-5"
TIER_VALUES_V2       = {"SILENT", "KORRIGIERT", "PRÜFEN"}
# Aliase für Backward-Compat (generate_grounded.py, ältere Skripte)
PROBLEMATIC_VERDICTS = {"NICHT_BELEGT", "ÜBERZOGEN", "WIDERSPRUCH"}
TIER_VALUES          = {"AUTO", "VORSCHLAG", "ESKALATION"}

LEKTORAT_SYSTEM = (
    "Du bist Korrektor für Kinderlexikon-Artikel (Wissensfreund). "
    "Prüfe alle faktischen Aussagen AUSSCHLIESSLICH gegen die beigefügten "
    "Wikipedia-Volltexte — niemals aus eigenem Vorwissen.\n\n"

    "══════════════════════════════════════════════════\n"
    "GRUNDPRINZIP: KINDSTIL HAT VORRANG\n"
    "══════════════════════════════════════════════════\n"
    "Korrekturen müssen den Kindstil bewahren — NIE verschlechtern.\n"
    "Wenn das Original kindgerechter, lebendiger oder anschaulicher ist als die\n"
    "Wikipedia-Formulierung, bleibt das Original.\n"
    "Du korrigierst gegen die Quelle; du verbesserst nicht den Stil. Füge bei einer\n"
    "Korrektur kein Sprachkolorit, kein Sinnesdetail und keinen neuen Vergleich hinzu —\n"
    "das ist Autoren-Arbeit, nicht Korrektor-Arbeit.\n\n"
    "KONKRET VERBOTEN als Korrekturbegründung:\n"
    "  · Parenthetische Alternativangaben («nach anderen Quellen…», «oder bis zu X»)\n"
    "  · Wissenschaftliche Einheiten/Maße wenn das Original eine Näherung ist die\n"
    "    sachlich stimmt — «fast einen Meter» ist keine Falschaussage wenn WP «95 cm»\n"
    "    nennt. Keine Korrektur.\n"
    "  · Synonym-Austausch wenn das Original genauso gut oder besser ist\n"
    "    («ohne Zähne» ist nicht schlechter als «zahnlos», «überall auf der Erde»\n"
    "    ist kindgerechter als «auf allen Kontinenten»)\n"
    "  · Wikipedia-Wortlaut der akademischer klingt als das Original\n"
    "  · Kindwelt-Metaphern und altersgerechte Vereinfachungen für S1/S2 (4–9 J.):\n"
    "    «Elefanten-Oma» für Leitkuh, «runde Eier» als Vereinfachung — KEIN Eingriff\n"
    "    solange die Aussage inhaltlich nicht falsch ist.\n\n"

    "══════════════════════════════════════════════════\n"
    "GROUNDING-REGEL\n"
    "══════════════════════════════════════════════════\n"
    "  EINGRIFFSGRENZE (Kernregel): Greife NUR ein, wenn eine Aussage entweder\n"
    "  (a) der Quelle faktisch WIDERSPRICHT oder (b) etwas Ungedecktes HINZUFÜGT.\n"
    "  Sonst kein Eingriff — auch nicht, wenn die Aussage vage, vereinfacht oder\n"
    "  unvollständig ist.\n\n"
    "  · Der Sachverhalt darf der Quelle nicht widersprechen und nichts Ungedecktes\n"
    "    hinzufügen — sinngemäße Deckung genügt; wörtliche Übereinstimmung ist nicht\n"
    "    erforderlich.\n"
    "  · SINNGEMÄSSE BELEGE zählen: «fliehen» wird durch «verlassen gefährdetes Gebiet»\n"
    "    gedeckt — sinngemäße Übereinstimmung zählt als BELEGT. Nicht flaggen wenn die\n"
    "    Quelle dasselbe mit anderen Worten sagt.\n"
    "  · Domänen-/Fächerlisten: Steht X in einer Quellliste als Unterrichtsfach,\n"
    "    Tätigkeit oder Kompetenzfeld, ist eine kindgerechte, nicht übertreibende\n"
    "    Aussage über X-Praxis sinngemäß belegt. Beispiel: «Sprachen» als Lehrfach\n"
    "    in der Quelle → «sprachen mehrere Sprachen» im Artikel ist sinngemäß gedeckt\n"
    "    — kein Flag.\n"
    "  · Verbund-Satz (A UND B): beide Teilaussagen müssen direkt belegt sein.\n"
    "  · DETAILATTRIBUTE IN VERBUND-SÄTZEN: Ortsangaben, Lagebezeichnungen und konkrete\n"
    "    Modalattribute (z.B. «an den geschützten Buchten», «im nördlichen Teil»,\n"
    "    «mit Überschallgeschwindigkeit») sind faktische Sachaussagen — KEINE illustrativen\n"
    "    Vergleiche. Jedes solche Detail muss im Volltext nachweisbar sein. Findet sich\n"
    "    kein Beleg: ungedeckter Zusatz → KORRIGIERT (streiche das unbelegte Attribut).\n"
    "  · NICHT flaggen: Illustrative Vergleiche belegter Größen («so groß wie ein Haus»);\n"
    "    mildes Sprachkolorit («stolz», «wunderschön»); register-gerechte Vereinfachungen.\n"
    "  · NUR flaggen: (a) neue unbelegte Sachaussage, (b) Zahl/Superlativ den die\n"
    "    Quelle nicht stützt oder widerspricht. Dazu zählt eine falsche GRENZE:\n"
    "    «bis zu 20 km», wenn die Quelle 30 km als Maximum nennt, behauptet eine\n"
    "    falsche Obergrenze — das ist ein Widerspruch zur Quelle und WIRD korrigiert.\n"
    "    (Abgrenzung: etwas WEGLASSEN ist erlaubt; eine falsche Grenze BEHAUPTEN ist\n"
    "    ein Widerspruch.)\n"
    "  · STARKE QUANTOREN (völlig, vollständig, gänzlich, ausnahmslos, immer, nie,\n"
    "    niemals, kein einziger, überhaupt nicht): Suche bei jedem dieser Wörter AKTIV\n"
    "    nach Gegenbelegen im Volltext ALLER beigefügten Quellen — nicht nur nach\n"
    "    bestätigenden Stellen. Findet sich eine Stelle mit Vorzeichen, Ausnahmen oder\n"
    "    Einschränkungen: KORRIGIERT. Beispiel: «völlig unvorbereitet» wenn eine der\n"
    "    Quellen Vorzeichen vor dem Ereignis beschreibt → Quantor widerspricht der\n"
    "    Quelle → KORRIGIERT.\n"
    "  · ABGELEITETE VERGLEICHE: «60 Tonnen – so viel wie zehn große Elefanten» ist\n"
    "    ein illustrativer Vergleich für eine belegte Maßangabe (60 Tonnen). Selbst\n"
    "    wenn «zehn Elefanten» nicht wortgleich in der Quelle steht: KEIN Eingriff.\n"
    "    Solche Vergleiche sind Veranschaulichungen, keine eigenständigen Faktenaussagen.\n"
    "  · UNVOLLSTÄNDIGKEIT IST KEIN FEHLER. Ein Kinderartikel darf und soll weglassen.\n"
    "    Eine quellengetreue, vereinfachte Formulierung, die einen Aspekt der Quelle nicht\n"
    "    erwähnt, ist KEIN Korrekturgrund — solange sie dem Erwähnten nicht widerspricht.\n"
    "    NICHT flaggen (Beispiele):\n"
    "      - «Bletchley Park war ein schönes Landhaus» — verschweigt die Code-Knacker-\n"
    "        Funktion, ist aber nicht falsch.\n"
    "      - «unterseeische Erdspalte» — die Quelle stützt «Spalte»; dass es auch ein\n"
    "        Vulkan war, fehlt, aber nichts ist falsch.\n"
    "      - «drei Rotoren» als vereinfachte Beschreibung der Enigma — verkürzt, nicht falsch.\n\n"

    "══════════════════════════════════════════════════\n"
    "DREI KORREKTURSTUFEN\n"
    "══════════════════════════════════════════════════\n\n"

    "  SILENT — Standard für kleine, klar belegbare Korrekturen:\n"
    "    Wann: Beleg eindeutig, Kindstil bleibt erhalten, Eingriff minimal.\n"
    "    Diese Fälle sind IMMER SILENT — kein Zögern, keine Rückfrage:\n"
    "      - Superlativ ohne Beleg: «ältestes Haustier» → «eines der ältesten Haustiere»\n"
    "      - Falsche Tierverhalten-Details wenn Quelle andere Angabe belegt → richtigstellen\n"
    "      - Präzisionsfehler bei belegten Zahlen → auf Quellzahl korrigieren\n"
    "      - Kausalbrücke die Kindern fehlt: «Diese Kälteperiode» nach einem Satz über\n"
    "        aufgewirbelten Staub → SILENT: «Die dadurch entstandene Kälteperiode»\n"
    "      - Jedes «diese», «dabei», «dadurch» das für ein Kind (4–12 J.) einen eigenen\n"
    "        Gedankenschritt erfordert → Kausalbrücke explizit machen, SILENT\n"
    "    Aktion: Satz in korrektur_neu korrigieren.\n\n"

    "  KORRIGIERT — für größere, aber klare Korrekturen:\n"
    "    Wann: Substanziellerer Eingriff ODER klar unbelegte Aussage mit eindeutiger\n"
    "    kindgerechter Korrektur. Quelllage eindeutig, kein echter Zweifel.\n"
    "    PROAKTIV KORRIGIEREN (nicht nur flaggen) wenn:\n"
    "      - Unbelegte Funktion streichbar: «kleine Ohren gegen Kälte» → «kleine Ohren»\n"
    "      - Übertreibung abschwächbar: «völlig unabhängig» → «weitgehend unabhängig»\n"
    "      - Tierverhalten-Zahl falsch: «meistens durch Heulen» wenn Quelle anderes\n"
    "        Lautbild belegt → auf Quellbasis korrigieren\n"
    "    Aktion: Satz in korrektur_neu korrigieren + kurzes WP-Zitat als Beleg.\n\n"

    "  PRÜFEN — der seltene Zweifelsfall, der NICHT eindeutig auflösbar ist:\n"
    "    1. Zwei Quellen widersprechen sich direkt und BEIDE sind plausibel\n"
    "    2. Eine Korrektur würde den pädagogischen Kern des Absatzes zerstören\n"
    "    3. Echter Verdacht auf Trainingswissen das in keiner Quelle nachweisbar ist\n"
    "    SCHWELLE ist ein Qualitätskriterium, kein Zähllimit: PRÜFEN nur bei echtem,\n"
    "    nicht eindeutig auflösbarem Zweifel — eindeutige Fälle gehören nach KORRIGIERT.\n"
    "    Ziel sind möglichst wenige PRÜFEN-Fälle, in der Regel 0–1 pro Artikel. ABER:\n"
    "    Hat ein Artikel mehrere ECHTE Zweifelsfälle, melde ALLE — kein Verschweigen und\n"
    "    kein Umdeklarieren zu KORRIGIERT, nur um eine Quote zu halten.\n"
    "    Stilistische Anmerkungen, Klausurstitel, Leseransprache → gehören NICHT hierher.\n"
    "    Aktion: Artikel NICHT automatisch ändern, ABER IMMER mindestens einen konkreten,\n"
    "    ankreuzbaren Korrekturvorschlag mitliefern (korrektur_vorschlag) — plus Problem\n"
    "    und Begründung. Je nach Fall:\n"
    "      · Fall 1 (Quellenwiderspruch): ENTWEDER zwei Varianten — korrektur_vorschlag\n"
    "        und korrektur_alt, je eine pro Quelle — ODER eine einzige widerspruchsfreie\n"
    "        Formulierung im Schnittbereich beider Quellen. Kriterium: Sind beide\n"
    "        Quellangaben für das Kind relevant UND unterscheidbar → zwei Varianten;\n"
    "        fällt der Unterschied für die kindgerechte Aussage nicht ins Gewicht → eine\n"
    "        Formulierung im Schnittbereich. NIE eine dritte, in keiner Quelle belegte Aussage.\n"
    "      · Fall 2 (pädagogischer Kern): ein konkreter Vorschlag, der den Kern bewahrt und\n"
    "        die ungedeckte Stelle korrigiert.\n"
    "      · Fall 3 (Trainingswissen-Verdacht): weglassen ODER auf das von der Quelle\n"
    "        gedeckte Maß zurücknehmen. GRENZE: «zurücknehmen» heißt auf das Belegte kürzen,\n"
    "        NICHT ein aufweichendes ungedecktes Wort hinzufügen («vermutlich»,\n"
    "        «möglicherweise» sind selbst ungedeckt und damit unzulässig).\n"
    "    MAXIME: Im Zweifel zurückschneiden, nie hinzudichten. Jeder Vorschlag bleibt\n"
    "    innerhalb dessen, was die deklarierten Quelltexte hergeben.\n\n"

    "══════════════════════════════════════════════════\n"
    "ENTSCHEIDUNGSPRINZIP (Kernregel)\n"
    "══════════════════════════════════════════════════\n"
    "Im Zweifel KORRIGIERT statt PRÜFEN.\n"
    "Eine leicht zu aggressive Auto-Korrektur die Andreas in 2 Sekunden rückgängig\n"
    "machen kann ist besser als ein PRÜFEN-Flag der Andreas zwingt, den ganzen\n"
    "Kontext zu verstehen. Das Lektorat entscheidet selbst — es delegiert nicht.\n\n"
    "SELBSTKONSISTENZ-PFLICHT: Wenn deine eigene Begründung zu dem Schluss kommt,\n"
    "dass kein Handlungsbedarf besteht → Verdict MUSS «kein Flag» sein, NICHT PRÜFEN.\n"
    "Beispiel: Begründung «fast einen Meter ist keine Falschaussage wenn die Quelle\n"
    "95 cm nennt» → kein Flag. Widerspruch zwischen Begründung und Verdict ist ein\n"
    "Fehler — die Begründung gewinnt immer.\n"
    "Weiteres Beispiel: Begründung enthält «sachgerecht», «kein Handlungsbedarf»\n"
    "oder «nicht falsch» → Verdict muss «kein Flag» sein, niemals PRÜFEN.\n"
    "Eine Begründung die zum Schluss kommt dass die Aussage in Ordnung ist,\n"
    "erzwingt Silence — auch wenn die Formulierung von der Quelle abweicht.\n\n"

    "══════════════════════════════════════════════════\n"
    "ZUSÄTZLICHE PRÜFPFLICHTEN\n"
    "══════════════════════════════════════════════════\n\n"

    "  FRAMING, TON UND EPOCHENPASSUNG (P1+P3):\n"
    "    1. SENTIMENT-FRAMING belegter Fakten:\n"
    "    · Box-Titel die eine Meinung nahelegen («Teilen macht Freude», «Ein gerechter Anführer»)\n"
    "      → KORRIGIERT: auf neutrale, beschreibende Überschrift («Wie Spartacus die Beute teilte»)\n"
    "    · Intensifier über die Quelle hinaus («ganz gerecht» wenn Quelle «gleichmäßig» sagt,\n"
    "      «absolut fair») → KORRIGIERT: auf Quellenformulierung zurückführen\n"
    "    · Märchenhafte Aufladung neutraler Quellbegriffe («Schätze» statt «Beute»)\n"
    "      → KORRIGIERT: neutralen Quellbegriff wiederherstellen\n"
    "    2. TON/EPOCHE-PASSUNG (Leitfrage: «Würde ein Fachkundiger sagen, dieser Begriff/Ton\n"
    "    trifft den historischen Kontext und die Schwere?»):\n"
    "    · Verharmlosende Modernbegriffe für ernste Sachverhalte: «Kampfsport» für Gladiatorenkämpfe\n"
    "      auf Leben und Tod → KORRIGIERT: «Kämpfe auf Leben und Tod» / «gefährliches Kampftraining»\n"
    "    · Anachronismen wenn ein sachlich korrekter Begriff existiert: «Hallen» für Gladiatoren-\n"
    "      kampfstätten → KORRIGIERT: «Arenen» (offen, keine Überdachung)\n"
    "    · Wertende Personenattribute: «grausamer Herrscher» → KORRIGIERT: sachlicher Titel («Diktator»)\n"
    "    · Person/Ereignis ohne notwendigen Kontext (Anne Frank ohne Verfolgungsgrund)\n"
    "      → KORRIGIERT: Kontext ergänzen\n"
    "    NICHT FLAGGEN: altersgerechte Vereinfachungen, Vergleiche, Metaphern, Kindstil.\n\n"
    "  SUBSTANZ-PRÜFUNG (P1):\n"
    "    Leitfrage für Sätze und Boxen: «Wenn dieser Inhalt fehlte — verlöre das Kind etwas\n"
    "    Wissenswertes?» Wenn nein → KORRIGIERT: streichen oder durch echten Inhalt ersetzen.\n"
    "    Deckt ab (z.B., nicht abschließend):\n"
    "    · Tautologien / Leerformeln: «Flugzeuge flogen durch die Luft», «bewegt sich in alle\n"
    "      Richtungen» (null Information) → KORRIGIERT: streichen\n"
    "    · Warnboxen mit Selbstverständlichem statt themenspezifischer Gefahr → KORRIGIERT:\n"
    "      echten Mehrwert einsetzen (z.B. bei Hund: Schokolade/Zwiebeln/Xylit) oder streichen\n"
    "    · Unvollständige Boxen mit unklarem Bezug («Spartacus aber verteilte sie…» ohne Subjekt)\n"
    "      → KORRIGIERT: vollständigen Satz mit klarem Bezug\n"
    "    NICHT FLAGGEN: kontextgebende Einleitungen, Übergangssätze, zulässige Stilmittel.\n"
    "    Engagierende Hinführungen, pädagogische «Warum»-Fragen und lebendige Denkanstöße sind\n"
    "    KEINE Leerformeln, auch wenn sie keinen eigenständigen Fakt tragen — sie dienen der\n"
    "    Bindung, und die ist im Kinderlexikon legitimer Inhalt. Streiche nur ECHTE Tautologien\n"
    "    (eine Aussage, die nichts sagt), nicht Stil oder Rhetorik.\n\n"
    "  VERGLEICHE — EINDEUTIGKEIT UND RICHTIGKEIT (P2):\n"
    "    Prüfe jeden Vergleich auf zwei Kriterien:\n"
    "    1. Eindeutiges Bezugsobjekt: «ein Haus», «ein Flugzeug», «ein Gebäude», «ein Baum»\n"
    "       haben zu große Spannweite → KORRIGIERT: präzisieren oder eindeutigen Ersatz wählen.\n"
    "       NICHT FLAGGEN: «ein Meter», «ein Mensch», «ein Auto», «ein Bus», «ein Fußballtor»,\n"
    "       «X Elefanten» — klar und dem Kind vertraut.\n"
    "    2. Rechnerische Richtigkeit (Fußballtor: 2,44 m · Mensch: ~1,8 m · Auto: ~1,5 t\n"
    "       · Bus: ~12 m · Elefant: ~5 t): wenn Bezugsobjekt feste Größe hat, nachrechnen.\n"
    "       «höher als ein Fußballtor» für ein 4-m-Tier → KORRIGIERT mit stimmigem Vergleich.\n"
    "    NICHT FLAGGEN: abgeleitete illustrative Vergleiche für belegte Maßangaben\n"
    "    («60 Tonnen — so viel wie zehn Elefanten»).\n\n"

    "  STIMMT_DAS-KOHÄRENZ:\n"
    "    Wenn eine stimmt_das-Box korrigiert wird: IMMER Frage UND reveal_text zusammen\n"
    "    auf Kohärenz prüfen. Passen Frage und Auflösung nach der Korrektur noch zusammen?\n"
    "    Falls nicht: Box KOMPLETT unverändert lassen und als PRÜFEN flaggen\n"
    "    (zählt als einer der 0–1 Ausnahmefälle).\n\n"

    "  UNVOLLSTÄNDIGE BOXEN:\n"
    "    Titel/Text vorhanden, aber Inhalt leer oder bei stimmt_das: reveal_text fehlt\n"
    "    → als PRÜFEN flaggen (zählt als einer der 0–1 Ausnahmefälle).\n\n"

    "  SINN, PLAUSIBILITÄT & KONTINUITÄT (Kernprüfung — entlastet den Generator):\n"
    "    Prüfe JEDEN Satz auf zwei Fragen: (1) Ergibt er für sich genommen Sinn?\n"
    "    (2) Passt er widerspruchsfrei zum Rest des Artikels UND zur Quelle?\n"
    "    A) QUELLEN-WIDERSPRUCH (dein stärkstes Werkzeug): Sagt die Quelle das\n"
    "       Gegenteil oder etwas anderes, korrigiere auf die Quelle. Beispiel:\n"
    "       Quelle nennt einen KALTWASSER-Geysir → jede Formulierung, die ihn heiß,\n"
    "       glühend oder feuerspeiend macht, WIDERSPRICHT der Quelle → KORRIGIERT\n"
    "       (auf das von der Quelle Gedeckte zurückführen).\n"
    "    B) INNERER WIDERSPRUCH / KONTINUITÄT: Etwas, das erst als X eingeführt und\n"
    "       später als Y bezeichnet wird (ein Hühnerknochen, der zum Schnitzelknochen\n"
    "       wird); eine Zahl/Angabe, die sich ohne Grund ändert; eine Figur, die\n"
    "       etwas tut, das dem zuvor Erzählten widerspricht → KORRIGIERT auf die\n"
    "       konsistente Fassung (die von der Quelle gedeckte gewinnt).\n"
    "    C) UNPLAUSIBLE / SINNLOSE AUSSAGE: Ein Satz, der offensichtlich keinen Sinn\n"
    "       ergibt, sachlich unmöglich wirkt oder eine unplausible Handlung/Requisite\n"
    "       behauptet (eine Figur, die ständig ein dickes Buch mit sich trägt; ein\n"
    "       Vorgang, der physikalisch nicht sein kann). Löst die Quelle es auf →\n"
    "       KORRIGIERT. Löst die Quelle es NICHT auf → PRÜFEN mit konkreter\n"
    "       Problembeschreibung. NIE aus eigenem Weltwissen einen Ersatzfakt einsetzen —\n"
    "       im Zweifel zurückschneiden oder flaggen, nie hinzudichten.\n"
    "    D) REGISTER-/JARGON-BRUCH IM DIALOG (Hörspiel): Legt der Text einem Kind\n"
    "       (Theo) oder einer Alltagsfigur einen Fachbegriff oder eine erwachsene\n"
    "       Formulierung in den Mund, die dort unpassend ist → KORRIGIERT auf eine\n"
    "       kindgerechte/figurengerechte Formulierung, ohne den belegten Inhalt zu\n"
    "       verlieren. (Das nimmt dem Generator eine Last ab, die er im Ein-Pass oft\n"
    "       übersieht.)\n"
    "    Grenze: Diese Prüfung ändert NIE etwas, das bloß knapp, vereinfacht oder\n"
    "    stilistisch schlicht ist — nur echte Sinn-, Widerspruchs- und Plausibilitäts-\n"
    "    fehler. Bei jeder Auto-Korrektur bleibt die kleinste Änderung maßgeblich.\n\n"

    "  DEZIMALZAHLEN KINDGERECHT (Ausnahme zur Zahl-Treue, entlastet den Generator):\n"
    "    Eine Nachkommazahl im Fließtext (z.B. «4,4 Zentimeter», «1,8 Tonnen») ist für\n"
    "    Kinder ungeeignet → KORRIGIERT: auf eine gerundete, kindgerechte Näherung mit\n"
    "    «knapp / etwas mehr als / ungefähr» umformen («knapp viereinhalb Zentimeter»,\n"
    "    «fast zwei Tonnen»). Runde immer in Richtung der Quellzahl, ohne die Aussage\n"
    "    zu verfälschen. Erfinde dabei KEINEN neuen Größenvergleich (das bleibt Autoren-\n"
    "    Arbeit) — nur die Zahl selbst wird kindgerecht gerundet. Ausgenommen: exakte\n"
    "    Jahres-/Datumsangaben und Zahlen, bei denen die Nachkommastelle den Sinn trägt.\n\n"

    "══════════════════════════════════════════════════\n"
    "KORREKTIONS-PRINZIP\n"
    "══════════════════════════════════════════════════\n"
    "  · Gleichwertiger Ersatz: Zahl→Quell-Zahl, Superlativ→Quell-Form.\n"
    "  · KEINE Abschwächung ins Vage wenn Quelle eine Zahl liefert.\n"
    "  · Minimaler Eingriff: Nimm die kleinste Änderung, die das konkrete Problem behebt.\n"
    "    Erhalte jedes quellbelegte Detail, das du nicht ausdrücklich korrigierst — lass\n"
    "    z. B. einen belegten Zusatz («stumpfe» Lanze) nicht fallen, während du etwas\n"
    "    anderes im selben Satz richtigstellst. Schreib keinen ganzen Satz/Teilsatz um,\n"
    "    wenn ein Wort genügt.\n"
    "  · Register wahren (S1 kindgerecht, S3 sachlich). Belegte Aussagen: nicht auflisten.\n\n"

    "Antworte NUR mit diesem JSON-Objekt:\n"
    "{\n"
    '  "corrections": [\n'
    "    {\n"
    '      "claim_original": "Exakter Satz aus dem Artikel",\n'
    '      "korrektur_neu":  "Korrigierter Satz (quellenbasiert, gleiches Register)",\n'
    '      "stufe":          "SILENT|KORRIGIERT",\n'
    '      "beleg":          "Wörtliches WP-Zitat (≤25 Wörter) oder Positionsangabe"\n'
    "    }\n"
    "  ],\n"
    '  "pruefen": [\n'
    "    {\n"
    '      "claim_original":      "Exakter Satz aus dem Artikel",\n'
    '      "korrektur_vorschlag": "Konkreter Korrektursatz (quellenbasiert, gleiches Register)",\n'
    '      "korrektur_alt":       "Optionaler zweiter Vorschlag NUR bei Fall-1-Quellenwiderspruch mit zwei relevanten Varianten; sonst weglassen",\n'
    '      "problem":             "Kurze Problembeschreibung (1 Satz)",\n'
    '      "begruendung":         "Warum PRÜFEN statt KORRIGIERT (1 Satz)"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Wenn alles belegt: {\"corrections\": [], \"pruefen\": []}\n"
    "JSON-Sicherheit: Innerhalb von Feldwerten keine geraden Anführungszeichen. "
    "Zitierte Textstellen in «» einschließen."
)

# Reihenfolge der Felder im JSON (für robust extractor)
_ALL_FIELD_ORDER = [
    "claim", "verdikt", "tier", "beleg_oder_begruendung",
    "korrektur_neu", "beleg_fuer_korrektur",
]


# ── Quellblock (symmetrisch zur Generierung) ──────────────────────────────────

def build_grounded_sources_block(
    primary_title: str,
    primary_text: str,
    companion_titles: list[str],
    companion_texts: dict[str, str],
) -> str:
    """Primär ungekürzt · Companions[:COMPANION_CHAR_CAP]."""
    parts = [f"### Quelle: {primary_title}\n{primary_text}"]
    for title in companion_titles:
        text = companion_texts.get(title, "")
        if text:
            parts.append(f"### Quelle: {title}\n{text[:COMPANION_CHAR_CAP]}")
    return "DEKLARIERTE QUELLEN:\n" + "\n\n".join(parts)


# ── Artikel → lesbarer Fließtext ─────────────────────────────────────────────

def article_to_lektorat_text(article: dict) -> str:
    """Wandelt Artikel-JSON in lesbaren Text für den Lektorat-Prompt.

    Boxen: Typ + Text + bei stimmt_das auch reveal_text (für Kohärenz-Check).
    """
    lines = []
    for sec in article.get("sections", []):
        # null-Werte wie leer/fehlend behandeln ((x or "") fängt None ab, .get-Default
        # greift nur bei fehlendem Schlüssel, nicht bei JSON-null).
        heading = (sec.get("heading") or sec.get("title") or "").strip()
        if heading:
            lines.append(f"\n[{heading}]")
        for s in sec.get("sentences", []):
            t = (s.get("text") or "").strip()
            if t:
                lines.append(t)
        for box in sec.get("boxes", []):
            btype = box.get("type", "box")
            t = (box.get("text") or "").strip()
            if t:
                lines.append(f"  BOX[{btype}]: {t}")
            reveal = (box.get("reveal_text") or "").strip()
            if reveal:
                lines.append(f"  BOX[{btype}/reveal]: {reveal}")
            for s in box.get("sentences", []):
                t = (s.get("text") or "").strip()
                if t:
                    lines.append(f"  BOX[{btype}]: {t}")
    return "\n".join(lines)


# ── Prompt-Builder ────────────────────────────────────────────────────────────

def build_lektorat_parts(article: dict, sources_block: str) -> tuple[str, str]:
    """Teilt Lektorat-Prompt in (sources_prefix, article_task).

    sources_prefix: stabiler Quellblock, identisch für alle Stufen eines Themas
                    → Anthropic cache_control: ephemeral greift über die 3 Batch-Calls.
    article_task:   variabler Teil (Artikeltext je Stufe + Aufgabe).
    """
    article_text = article_to_lektorat_text(article)
    level = article.get("meta", {}).get("age_level", "?")
    title = article.get("meta", {}).get("title", "?")
    article_task = (
        f"PRÜF-ARTIKEL (Stufe {level}, Titel: {title}):\n{article_text}\n\n"
        "Prüfe alle faktischen Aussagen gegen die deklarierten Quellen. "
        "Liefere corrections (SILENT/KORRIGIERT) und pruefen-Flags im vorgegebenen JSON-Format."
    )
    return sources_block, article_task


def build_lektorat_prompt(article: dict, sources_block: str) -> str:
    """Backward-compat: ungecachte Volltext-Version (für Catch-Test / direkte Aufrufe)."""
    sources, task = build_lektorat_parts(article, sources_block)
    return f"{sources}\n\n{task}"


# ── JSON-Parser ───────────────────────────────────────────────────────────────

def _fix_inner_quotes(text: str) -> str:
    """Fix German inner quotes (U+201E + U+0022) that break JSON string parsing.

    Two cases:
    - inner" immediately before structural " → drop the inner "
    - inner" followed by more text → replace inner " with '
    """
    text = text.replace("„", "«")  # „ → «
    text = re.sub(r'(?<=[^\s{[\n,"])"(?=")', "", text)          # Case 1
    text = re.sub(r'(?<=[^\s{[\n,"])"(?!\s*[:{}\],""])', "'", text)  # Case 2
    return text


def parse_lektorat_json(raw: str) -> list[dict]:
    if not raw:
        raise ValueError("Leere Antwort")
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    has_array = "[" in cleaned

    # Try standard JSON parse — as-is, then with inner-quote fix
    for attempt in (cleaned, _fix_inner_quotes(cleaned)):
        start = attempt.find("[")
        if start != -1:
            try:
                inner = _extract_balanced(attempt[start:], "[", "]")
                result = json.loads(inner)
                if isinstance(result, list):
                    return result
            except (ValueError, json.JSONDecodeError):
                pass

    # Single-object fallback only when response has no array wrapper
    if not has_array:
        for attempt in (cleaned, _fix_inner_quotes(cleaned)):
            start = attempt.find("{")
            if start != -1:
                try:
                    inner = _extract_balanced(attempt[start:], "{", "}")
                    return [json.loads(inner)]
                except (ValueError, json.JSONDecodeError):
                    pass

    # Robust structural extraction — works even with unescaped " inside values
    result = _extract_lektorat_objects_robust(cleaned)
    if result:
        return result
    raise ValueError("Kein JSON-Array oder Objekt gefunden")


def _extract_lektorat_objects_robust(text: str) -> list[dict]:
    """Structural extraction: split on { } depth, extract fields by key position.

    Works even when string values contain unescaped " characters.
    """
    blocks = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                blocks.append(text[start : i + 1])

    results = []
    for block in blocks:
        vm = re.search(r'"verdikt"\s*:\s*"([^"]{1,30})"', block)
        tm = re.search(r'"tier"\s*:\s*"([^"]{0,20})"', block)
        obj: dict = {
            "verdikt": vm.group(1) if vm else "UNBEKANNT",
            "tier":    tm.group(1) if tm else "",
        }
        for i, field in enumerate(_ALL_FIELD_ORDER):
            if field in ("verdikt", "tier"):
                continue
            next_fields = _ALL_FIELD_ORDER[i + 1:]
            if next_fields:
                obj[field] = _field_value_between_keys(block, field, next_fields)
            else:
                obj[field] = _field_value_before_close(block, field)
        results.append(obj)
    return results


def _field_value_between_keys(block: str, field: str, next_keys: list[str]) -> str:
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', block)
    if not m:
        return ""
    rest = block[m.end():]
    next_pat = "|".join(re.escape(k) for k in next_keys)
    end = re.search(r'",\s*\n\s*"(?:' + next_pat + r'")', rest)
    if end:
        return rest[: end.start()]
    return rest.split('",')[0]


def _field_value_before_close(block: str, field: str) -> str:
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', block)
    if not m:
        return ""
    rest = block[m.end():]
    end = re.search(r'"\s*\n?\s*}', rest)
    if end:
        return rest[: end.start()]
    idx = rest.rfind('"')
    return rest[:idx] if idx >= 0 else rest


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str:
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[:i + 1]
    raise ValueError(f"Unvollständiges JSON (kein balanciertes '{close_ch}')")


# ── Hilfsfunktionen für Beleg-Check + Textersatz ─────────────────────────────

def _normalize_for_check(text: str) -> str:
    """NFKC-normalisiert + lowercase + whitespace-kollabiert für Substring-Check."""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.lower().split())


def _jaccard(a: str, b: str) -> float:
    """Jaccard-Ähnlichkeit auf Wort-Ebene für Satz-Matching."""
    wa = set(re.sub(r"[^\w\s]", "", a.lower()).split())
    wb = set(re.sub(r"[^\w\s]", "", b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _split_sentences(text: str) -> list[str]:
    """Leichtgewichtiges Satz-Splitting für Box-Prosa (Mehr-Satz-Strings).

    Trennt nach .!? + Whitespace, ohne NLP-Abhängigkeit. Gibt die ECHTEN
    Teil-Strings zurück (sind exakte Substrings des Originals → für punktgenauen
    .replace-Einbau). Kein Satzende-Zeichen → [text] (= heutiges Ganzfeld-Verhalten).

    Bewusst konservativ: Bei Fehlschnitt (z. B. Abkürzung „z. B.") matcht der
    Ein-Satz-claim höchstens nicht (≥0.40-Gate) → „Einbau fehlgeschlagen", aber
    NIE ein zerstörender Ersatz (es wird nur der exakt getroffene Teil-String ersetzt).
    """
    if not text or not text.strip():
        return []
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


_RENDER_MARKER_RE = re.compile(r"\s*BOX\[[^\]]*\]:\s*")


def _strip_render_markers(text: str) -> str:
    """Entfernt interne Render-Marker (BOX[...]: / BOX[.../reveal]:) aus LLM-Rückgaben.

    Das Lektorat-Prompt rendert Boxen mit dem Präfix «BOX[typ]: …» (article_to_lektorat_text).
    Das Modell kopiert dieses Präfix mitunter in claim_original/korrektur_neu zurück. Ungestrippt
    würde es das Matching verfälschen UND (bei Ganzbox-Ersatz) wörtlich in box["text"] landen.
    """
    if not text:
        return text
    return _RENDER_MARKER_RE.sub(" ", text).strip()


def _is_single_sentence(text: str) -> bool:
    return len(_split_sentences(text)) <= 1


def _covers_whole_box(claim: str, box_text: str) -> bool:
    """True, wenn der (Marker-bereinigte) claim die GANZE Box abdeckt.

    Kriterium (strukturell, Option A): jeder Box-Satz hat ein ≥0.5-Jaccard-Gegenstück
    unter den claim-Sätzen → der claim ist ein Rewrite der gesamten Box. Ein-Satz-Boxen
    sind trivial abgedeckt. Bei nur teilweiser Abdeckung (mehrdeutiger Mehr-Satz-Match)
    liefert dies False → der Aufrufer flaggt statt zu spleißen.
    """
    box_sents = _split_sentences(box_text)
    if len(box_sents) <= 1:
        return True
    claim_sents = _split_sentences(claim) or [claim]
    return all(
        max((_jaccard(bs, cs) for cs in claim_sents), default=0.0) >= 0.5
        for bs in box_sents
    )


def _claim_covers_run(
    claim_parts: list[str], sents: list[dict], sj: int, thr: float = 0.4
) -> bool:
    """True, wenn die Claim-Teilsätze ab Position sj einen ZUSAMMEN-
    HÄNGENDEN Lauf von Original-Sätzen der Reihe nach abdecken:
    jeder Teilsatz Ck matcht sentences[sj+k] mit _jaccard >= thr,
    innerhalb der Array-Grenzen. Sonst False (→ kein Eingriff)."""
    n = len(claim_parts)
    if n == 0 or sj + n > len(sents):
        return False
    return all(
        _jaccard(claim_parts[k], sents[sj + k].get("text", "")) >= thr
        for k in range(n)
    )


def _apply_auto_correction(article: dict, claim_text: str, korrektur_neu: str) -> bool:
    """Ersetzt den Satz in article, der claim_text am besten trifft, mit korrektur_neu.

    Gibt True zurück wenn Jaccard >= 0.4 und Ersatz vorgenommen wurde.

    Mehr-Satz-Box-Strings (box.text / box.reveal_text) werden satz-granular
    behandelt: das Feld wird in Sätze geteilt, der claim gegen jeden Box-Satz
    gematcht und nur der beste Treffer ersetzt — die übrigen Box-Sätze bleiben
    erhalten. Ein-Satz-Felder verhalten sich wie bisher (Split liefert ein Element).
    """
    if not claim_text or not korrektur_neu or claim_text == korrektur_neu:
        return False

    # Ursache A: interne Render-Marker aus den LLM-Strings entfernen, bevor gematcht
    # oder geschrieben wird (sonst leakt «BOX[...]:» ins box["text"]).
    claim_text    = _strip_render_markers(claim_text)
    korrektur_neu = _strip_render_markers(korrektur_neu)
    if not claim_text or not korrektur_neu or claim_text == korrektur_neu:
        return False

    # Mehr-Turn-Claim: das Lektorat zitiert im Dialog oft eine Frage + Antwort
    # über ZWEI sentences[]-Einträge, mit Zeilenumbruch dazwischen verbunden
    # (»Frage Theo\nAntwort Ronja«) — geändert wird meist nur EIN Turn, der
    # andere ist in claim und korrektur identisch. Auf \n splitten und jeden
    # geänderten Turn einzeln über die Einzel-Turn-Logik einbauen; identische
    # Teile überspringen. Verhindert das stille Flaggen solcher Dialog-Korrekturen.
    if "\n" in claim_text and "\n" in korrektur_neu:
        cparts = [p.strip() for p in claim_text.split("\n") if p.strip()]
        nparts = [p.strip() for p in korrektur_neu.split("\n") if p.strip()]
        if len(cparts) == len(nparts) and len(cparts) > 1:
            changed = [(c, n) for c, n in zip(cparts, nparts) if c != n]
            if changed:
                return all(_apply_auto_correction(article, c, n) for c, n in changed)

    # Exakter-Teilstring-Override (höchste Konfidenz, VOR der Jaccard-Schwelle):
    # Liegt der Claim WÖRTLICH in genau EINEM sentences[]-Turn, ersetze ihn dort
    # direkt. Ein kurzer Claim in einem langen Hörspiel-Mehrsatz-Turn hat gegen den
    # ganzen Turn ein Jaccard < 0.4 und würde sonst an der Schwelle unten abgewiesen —
    # obwohl die wörtliche Enthaltung der sicherste denkbare Treffer ist. Nur bei
    # EINDEUTIGKEIT (genau ein Turn enthält ihn), sonst regulär per Jaccard weiter.
    treffer = [sent for sec in article.get("sections", [])
               for sent in sec.get("sentences", [])
               if claim_text in (sent.get("text") or "") and claim_text != (sent.get("text") or "")]
    if len(treffer) == 1:
        treffer[0]["text"] = treffer[0]["text"].replace(claim_text, korrektur_neu, 1)
        return True

    best_score = 0.0
    # ("sec", si, sj) | ("box", si, bi, sj)
    # | ("box_text"|"box_reveal", si, bi, satz_str)  ← satz_str = exakt zu ersetzender Teil
    best_loc: tuple | None = None

    for si, sec in enumerate(article.get("sections", [])):
        for sj, sent in enumerate(sec.get("sentences", [])):
            score = _jaccard(claim_text, sent.get("text", ""))
            if score > best_score:
                best_score = score
                best_loc = ("sec", si, sj)
        for bi, box in enumerate(sec.get("boxes", [])):
            for satz in _split_sentences(box.get("text", "") or ""):
                score = _jaccard(claim_text, satz)
                if score > best_score:
                    best_score = score
                    best_loc = ("box_text", si, bi, satz)
            for satz in _split_sentences(box.get("reveal_text", "") or ""):
                score = _jaccard(claim_text, satz)
                if score > best_score:
                    best_score = score
                    best_loc = ("box_reveal", si, bi, satz)
            for sj, sent in enumerate(box.get("sentences", [])):
                score = _jaccard(claim_text, sent.get("text", ""))
                if score > best_score:
                    best_score = score
                    best_loc = ("box", si, bi, sj)

    if best_score < 0.4 or best_loc is None:
        return False

    if best_loc[0] == "sec":
        _, si, sj = best_loc
        sents = article["sections"][si]["sentences"]
        entry_text = sents[sj].get("text", "")
        claim_parts = _split_sentences(claim_text) or [claim_text]
        if claim_text in entry_text and claim_text != entry_text:
            # Claim ist exakter Teilstring des Turns (Hörspiel: ein sentences[]-
            # Eintrag ist ein Mehrsatz-Turn). Nur den Claim ersetzen, die übrigen
            # Sätze des Turns (führender Satz UND Redebegleitsatz) bleiben stehen.
            # Deckt Ein-Satz-Claims IN einem Mehrsatz-Turn UND Schwanz-/Mittel-
            # Claims ab, die der Jaccard-/Lauf-Pfad sonst als „prüfen" flaggt.
            sents[sj]["text"] = entry_text.replace(claim_text, korrektur_neu, 1)
        elif len(claim_parts) <= 1:
            # Ein-Satz-Claim: unverändertes Verhalten (nur Text ersetzen)
            sents[sj]["text"] = korrektur_neu
        elif _jaccard(claim_text, sents[sj].get("text", "")) >= 0.9:
            # Mehr-Satz-Claim, der GANZ in EINEM Turn-Eintrag steckt (Hörspiel:
            # eine sentences[]-Zeile ist ein Mehrsatz-Turn, kein Einzelsatz). Der
            # Claim deckt den ganzen Eintrag → direkt ersetzen (nicht über mehrere
            # Einträge laufen lassen). Partielle Zitate (Jaccard<0.9) fallen weiter
            # in den _claim_covers_run-Pfad und werden sonst geflaggt.
            sents[sj]["text"] = korrektur_neu
        elif _claim_covers_run(claim_parts, sents, sj):
            # Mehr-Satz-Claim, sauberer zusammenhängender Lauf ab sj:
            # ganzen Korrektur-Block in den ersten Satz, weitere abgedeckte
            # Original-Sätze entfernen (verhindert Waisen-Dublette).
            sents[sj]["text"] = korrektur_neu
            del sents[sj + 1 : sj + len(claim_parts)]
        else:
            # Best-Match nicht der erste Teilsatz / Folgesätze passen nicht /
            # Lauf überschritte das Array-Ende → kein Eingriff (→ flaggen).
            return False
    elif best_loc[0] == "box_text":
        # Ursache B: Granularitäts-Guard. Ganzbox-Korrektur nie in einen Einzelsatz spleißen.
        _, si, bi, satz = best_loc
        box = article["sections"][si]["boxes"][bi]
        if _covers_whole_box(claim_text, box.get("text", "") or ""):
            box["text"] = korrektur_neu                       # deckt ganze Box ab → ganz ersetzen
        elif _is_single_sentence(claim_text):
            box["text"] = box["text"].replace(satz, korrektur_neu, 1)   # genau ein Satz → ersetzen
        else:
            return False                                      # mehrdeutiger Mehr-Satz-Match → flaggen
    elif best_loc[0] == "box_reveal":
        _, si, bi, satz = best_loc
        box = article["sections"][si]["boxes"][bi]
        if _covers_whole_box(claim_text, box.get("reveal_text", "") or ""):
            box["reveal_text"] = korrektur_neu
        elif _is_single_sentence(claim_text):
            box["reveal_text"] = box["reveal_text"].replace(satz, korrektur_neu, 1)
        else:
            return False
    else:
        _, si, bi, sj = best_loc
        article["sections"][si]["boxes"][bi]["sentences"][sj]["text"] = korrektur_neu
    return True


# ── Prüfbericht erstellen + Artikel annotieren ───────────────────────────────

def build_pruefbericht(verdicts: list[dict], primary_text: str = "") -> dict:
    """Strukturiert Verdikt-Liste in pruefbericht mit Korrektur-Status (Stufe 2).

    Status je Finding:
      belegt         — Aussage korrekt, keine Aktion
      auto_angewandt — AUTO-Tier + beleg_fuer_korrektur wörtlich in primary_text
      vorschlag_offen— VORSCHLAG, oder AUTO dessen Beleg nicht wörtlich gefunden
      eskaliert      — ESKALATION (kein gegroundeter Ersatz)
    """
    n_primary = _normalize_for_check(primary_text)

    findings = []
    for v in verdicts:
        verdikt   = v.get("verdikt", "UNBEKANNT")
        tier      = v.get("tier", "")
        kor_neu   = v.get("korrektur_neu", "")
        beleg_k   = v.get("beleg_fuer_korrektur", "")

        if verdikt == "BELEGT":
            status = "belegt"
        elif tier == "ESKALATION":
            status = "eskaliert"
        elif tier == "AUTO":
            # Mechanischer Beleg-Check: wörtliches Zitat im Primärtext?
            if beleg_k and n_primary and _normalize_for_check(beleg_k) in n_primary:
                status = "auto_angewandt"
            else:
                tier   = "VORSCHLAG"   # Downgrade
                status = "vorschlag_offen"
        else:
            status = "vorschlag_offen"

        findings.append({
            "claim_original":         v.get("claim", ""),
            "verdikt":                verdikt,
            "tier":                   tier,
            "beleg_oder_begruendung": v.get("beleg_oder_begruendung", ""),
            "korrektur_neu":          kor_neu if status in ("auto_angewandt", "vorschlag_offen") else "",
            "beleg_fuer_korrektur":   beleg_k if status in ("auto_angewandt", "vorschlag_offen") else "",
            "status":                 status,
        })

    summary = {
        "auto_angewandt":  sum(1 for f in findings if f["status"] == "auto_angewandt"),
        "vorschlag_offen": sum(1 for f in findings if f["status"] == "vorschlag_offen"),
        "eskaliert":       sum(1 for f in findings if f["status"] == "eskaliert"),
    }
    return {"findings": findings, "summary": summary}


def annotate_article_lektorat(
    article: dict,
    verdicts: list[dict],
    primary_text: str = "",
) -> None:
    """Schreibt pruefbericht-Feld ins Artikel-JSON und wendet AUTO-Korrekturen an.

    review_flag = True nur bei vorschlag_offen oder eskaliert.
    AUTO-Korrekturen werden direkt in article["sections"] eingebaut.
    """
    pb = build_pruefbericht(verdicts, primary_text)

    # AUTO-Korrekturen einbauen
    for finding in pb["findings"]:
        if finding["status"] == "auto_angewandt" and finding["korrektur_neu"]:
            applied = _apply_auto_correction(
                article, finding["claim_original"], finding["korrektur_neu"]
            )
            if not applied:
                # Satz nicht im Artikel gefunden — auf VORSCHLAG herabstufen
                finding["status"] = "vorschlag_offen"
                finding["tier"]   = "VORSCHLAG"
                pb["summary"]["auto_angewandt"]  -= 1
                pb["summary"]["vorschlag_offen"] += 1

    article["pruefbericht"] = pb

    n_v = pb["summary"]["vorschlag_offen"]
    n_e = pb["summary"]["eskaliert"]
    if n_v > 0 or n_e > 0:
        article.setdefault("meta", {})["review_flag"] = True
        existing = article["meta"].get("review_reason", "")
        reason   = f"lektorat: {n_v} vorschlag, {n_e} eskaliert"
        article["meta"]["review_reason"] = (existing + "; " + reason).lstrip("; ")


# ── V2: Parser + Annotator (SILENT / KORRIGIERT / PRÜFEN) ────────────────────

def parse_lektorat_v2(raw: str) -> dict:
    """Parst das neue Lektorat-JSON-Format: {"corrections": [...], "pruefen": [...]}."""
    if not raw:
        raise ValueError("Leere Antwort")
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    for attempt in (cleaned, _fix_inner_quotes(cleaned)):
        start = attempt.find("{")
        if start == -1:
            continue
        try:
            inner = _extract_balanced(attempt[start:], "{", "}")
            obj = json.loads(inner)
            if isinstance(obj, dict):
                return {
                    "corrections": obj.get("corrections", []),
                    "pruefen":     obj.get("pruefen", []),
                }
        except (ValueError, json.JSONDecodeError):
            pass

    raise ValueError("Kein gültiges JSON-Objekt gefunden")


def _diff_excerpt(orig: str, new: str, ctx: int = 35) -> tuple[str, str]:
    """Zeigt den geänderten Teil mit Kontext; niemals nach fixer Zeichenzahl abschneiden.

    Gibt (orig_excerpt, new_excerpt) zurück. Beide Strings haben Auslassungszeichen
    am Rand wo Text vor/nach dem Kontextfenster weggelassen wurde, aber der
    geänderte Teil selbst ist immer vollständig enthalten.
    """
    # Gemeinsamen Präfix finden
    i = 0
    min_len = min(len(orig), len(new))
    while i < min_len and orig[i] == new[i]:
        i += 1

    # Gemeinsamen Suffix finden (von hinten)
    j_o, j_n = len(orig), len(new)
    while j_o > i and j_n > i and orig[j_o - 1] == new[j_n - 1]:
        j_o -= 1
        j_n -= 1

    # Kontextfenster: ctx Zeichen vor/nach dem Diff
    start   = max(0, i - ctx)
    end_o   = min(len(orig), j_o + ctx)
    end_n   = min(len(new),  j_n + ctx)

    pre_o   = ("…" if start > 0 else "") + orig[start:end_o] + ("…" if end_o < len(orig) else "")
    pre_n   = ("…" if start > 0 else "") + new[start:end_n]  + ("…" if end_n < len(new)  else "")

    # Fallback: wenn beide Strings identisch oder sehr kurz → vollständig zurückgeben
    if pre_o == pre_n or not pre_o or not pre_n:
        return orig, new
    return pre_o, pre_n


def annotate_article_lektorat_v2(
    article: dict,
    lektorat_result: dict,
    thema:  str = "",
    stufe:  str = "",
) -> None:
    """Wendet SILENT+KORRIGIERT-Korrekturen an; schreibt pruefbericht ins Artikel-JSON.

    review_flag = True nur bei PRÜFEN-Flags oder nicht einbaubaren Korrekturen.
    """
    corrections = lektorat_result.get("corrections", [])
    pruefen_in  = lektorat_result.get("pruefen", [])

    silent_lines:     list[str] = []
    korrigiert_lines: list[str] = []
    pruefen_lines:    list[str] = []
    findings:         list[dict] = []

    for c in corrections:
        claim  = c.get("claim_original", "").strip()
        neu    = c.get("korrektur_neu", "").strip()
        tier   = c.get("stufe", "KORRIGIERT")
        beleg  = c.get("beleg", "").strip()

        if not claim or not neu or claim == neu:
            continue

        applied = _apply_auto_correction(article, claim, neu)

        # Display-only: interne Render-Marker strippen, damit nie ein «BOX[...]:»-
        # Fragment in den Prüfbericht leakt (Apply-Logik bleibt unberührt).
        claim_disp = _strip_render_markers(claim)
        neu_disp   = _strip_render_markers(neu)

        if not applied:
            pruefen_lines.append(
                f"«{claim_disp[:80]}» — Einbau fehlgeschlagen (Satz nicht gefunden)"
            )
            findings.append({
                "verdikt":        "EINBAU_FEHLGESCHLAGEN",
                "claim_original": claim_disp,
                "korrektur_neu":  neu_disp,
                "korrektur_alt":  None,
                "beleg":          beleg or None,
                "problem":        None,
                "begruendung":    None,
            })
            continue

        claim_s, neu_s = _diff_excerpt(claim_disp, neu_disp)
        if tier == "SILENT":
            beleg_s = f" (WP: {beleg})" if beleg else ""
            silent_lines.append(f"«{claim_s}» → «{neu_s}»{beleg_s}")
            findings.append({
                "verdikt":        "SILENT",
                "claim_original": claim_disp,
                "korrektur_neu":  neu_disp,
                "korrektur_alt":  None,
                "beleg":          beleg or None,
                "problem":        None,
                "begruendung":    None,
            })
        else:
            beleg_s = f" — WP: «{beleg}»" if beleg else ""
            korrigiert_lines.append(f"«{claim_s}» → «{neu_s}»{beleg_s}")
            findings.append({
                "verdikt":        "KORRIGIERT",
                "claim_original": claim_disp,
                "korrektur_neu":  neu_disp,
                "korrektur_alt":  None,
                "beleg":          beleg or None,
                "problem":        None,
                "begruendung":    None,
            })

    for p in pruefen_in:
        claim  = p.get("claim_original", "").strip()
        prob   = p.get("problem", "").strip()
        beg    = p.get("begruendung", "").strip()
        vor    = (p.get("korrektur_vorschlag") or "").strip()
        alt    = (p.get("korrektur_alt") or "").strip()
        entry  = f"«{claim}» — {prob}"
        if vor:
            entry += f" → Vorschlag: «{vor}»"
            if alt:
                entry += f" / «{alt}»"
        if beg:
            entry += f" ({beg})"
        pruefen_lines.append(entry)
        findings.append({
            "verdikt":        "PRÜFEN",
            "claim_original": claim,
            "korrektur_neu":  vor or None,
            "korrektur_alt":  alt or None,
            "beleg":          None,
            "problem":        prob or None,
            "begruendung":    beg or None,
        })

    # Pruefbericht aufbauen
    header = f"## {thema} {stufe} — Lektorat" if thema else "## Lektorat"
    parts  = [header]
    if silent_lines:
        parts.append(f"### SILENT ({len(silent_lines)} Korrekturen)")
        parts.extend(f"- {l}" for l in silent_lines)
    if korrigiert_lines:
        parts.append(f"### KORRIGIERT ({len(korrigiert_lines)} Korrekturen)")
        parts.extend(f"- {l}" for l in korrigiert_lines)
    if pruefen_lines:
        parts.append(f"### PRÜFEN ({len(pruefen_lines)} Flags)")
        parts.extend(f"- {l}" for l in pruefen_lines)
    n_pr = len(pruefen_lines)
    parts.append(
        f"Zusammenfassung: {len(silent_lines)} silent, "
        f"{len(korrigiert_lines)} korrigiert, {n_pr} zu prüfen."
    )

    article["pruefbericht"] = {
        "text":         "\n".join(parts),
        "n_silent":     len(silent_lines),
        "n_korrigiert": len(korrigiert_lines),
        "n_pruefen":    n_pr,
        "findings":     findings,
    }

    if n_pr > 0:
        article.setdefault("meta", {})["review_flag"] = True
        existing = article["meta"].get("review_reason", "")
        reason   = f"lektorat: {n_pr} zu prüfen"
        article["meta"]["review_reason"] = (existing + "; " + reason).lstrip("; ")


# ── Anthropic Sync-API (Default für Test-/Kleinläufe) ────────────────────────

def run_lektorat_sync(
    parts_by_id: dict[str, tuple[str, str]],
    api_key: str,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Führt Lektorat-Calls SEQUENZIELL aus (schnell für ≤5 Artikel).

    Gibt (results, usage_by_id) zurück.
    usage_by_id keys: input_tok, output_tok, cache_create_tok, cache_read_tok.

    Gleiche Prompt-Struktur wie run_lektorat_batch (cache_control: ephemeral).
    Sequenziell statt parallel: Call 1 schreibt den Anthropic-KV-Cache
    (cache_creation_input_tokens), Calls 2-3 lesen ihn (cache_read_input_tokens).
    """
    import anthropic

    client    = anthropic.Anthropic(api_key=api_key)
    results:    dict[str, dict] = {}   # aid -> {"corrections": [...], "pruefen": [...]}
    usage_by_id: dict[str, dict]     = {}

    for aid, (sources_prefix, article_task) in parts_by_id.items():
        log.info("  Lektorat-Sync [%s] …", aid)
        try:
            # Streaming PFLICHT: Die Lektorat-Calls tragen den ganzen Quellblock
            # (~40–60k Tokens) + adaptives Thinking + JSON-Antwort. Non-Streaming lehnt
            # die Anthropic-API ab ("Streaming is required for operations that may take
            # longer than 10 minutes", Befund 2026-07-24).
            # Claude-5-Familie: Thinking wird über output_config.effort gesteuert (NICHT
            # thinking.enabled — das lehnt sonnet-5 mit 400 ab). max_tokens großzügig,
            # sonst frisst adaptives Reasoning den Cap und der JSON-Block bleibt leer
            # (Befund: out=16000 → "Leere Antwort").
            with client.messages.stream(
                model=LEKTORAT_MODEL,
                max_tokens=24000,
                output_config={"effort": "medium"},
                # temperature entfernt: claude-sonnet-4-6 lehnt den Parameter mit 400 ab
                # ("temperature is deprecated for this model"). Default (=1) ist ok — das
                # Lektorat ist ohnehin durch forced-JSON/Beleg-Prüfung eng geführt.
                system=[
                    {"type": "text", "text": LEKTORAT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}},
                ],
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": sources_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": article_task},
                ]}],
            ) as stream:
                msg = stream.get_final_message()
            # Robust gegen Thinking-Blocks: claude-sonnet-4-6 liefert bei aktivem
            # Reasoning zuerst einen ThinkingBlock (ohne .text) — den echten
            # Text-Block herausfischen statt blind content[0] zu nehmen.
            raw = next(
                (b.text for b in msg.content
                 if getattr(b, "type", None) == "text" and hasattr(b, "text")),
                "",
            )
            u   = msg.usage
            log.info(
                "  [%s] tokens in=%d create=%d read=%d out=%d",
                aid, u.input_tokens,
                getattr(u, "cache_creation_input_tokens", 0),
                getattr(u, "cache_read_input_tokens", 0),
                u.output_tokens,
            )
            usage_by_id[aid] = {
                "input_tok":       u.input_tokens,
                "output_tok":      u.output_tokens,
                "cache_create_tok": getattr(u, "cache_creation_input_tokens", 0),
                "cache_read_tok":   getattr(u, "cache_read_input_tokens", 0),
            }
            try:
                results[aid] = parse_lektorat_v2(raw)
            except Exception as exc:
                log.warning("  Lektorat JSON-Parse [%s]: %s", aid, exc)
                results[aid] = {"corrections": [], "pruefen": []}
        except Exception as exc:
            log.warning("  Lektorat-Sync [%s] fehlgeschlagen: %s", aid, exc)
            results[aid] = {"corrections": [], "pruefen": []}
            usage_by_id[aid] = {}

    return results, usage_by_id


# ── Sprach-Pass (leichter Wortwahl-/Grammatik-Durchgang) ─────────────────────
#
# Das Beleg-Lektorat oben prüft NUR Fakten gegen die Quelle und lässt Sprache
# bewusst unangetastet. Dieser zweite, leichte Pass fängt genau das Übrige:
# offensichtliche Wort-Verschreiber (die faktisch stimmen und daher durchrutschen,
# z.B. "die Vorlagen der Wale" statt "Vorfahren") + un-kindgerechte Fachkürzel.
# Bewusst KONSERVATIV: nur echte Fehler, keine Stilverschönerung (sonst kippt der
# Kindstil, dieselbe Falle wie beim Beleg-Lektorat). Läuft über call_claude_json
# (fischt den tool_use-Block → robust gegen Thinking-Blocks, keine temperature).

SPRACH_SYSTEM = (
    "Du bist Korrektor für Kinder-Hörspiele (4–9 Jahre) im Wissensfreund. "
    "Du prüfst Wortwahl, Grammatik UND offensichtliche Unmöglichkeiten der erzählten "
    "Szene — NIEMALS Fakten über die echte Welt (die sind bereits gegen die Quelle "
    "geprüft) und NIEMALS Stil, Ton oder erfundene Gefühle/Fantasie.\n\n"
    "KORRIGIERE nur echte Fehler:\n"
    "  (a) Offensichtliche Wort-/Verschreiber: ein falsches Wort, das im Kontext "
    "keinen Sinn ergibt (z. B. «die Vorlagen der Wale» → «die Vorfahren der Wale»).\n"
    "  (b) Grammatik-/Flexionsfehler (falscher Fall, Numerus, Verbform, Bezug).\n"
    "  (c) Un-kindgerechte Fachbegriffe/Fremdwörter, die ein 6-Jähriger nicht "
    "versteht und die NICHT im Text selbst kindgerecht erklärt werden. Zwei Fälle:\n"
    "      – Es gibt ein einfaches deutsches Wort → ERSETZE («CO2» → «Kohlendioxid»; "
    "«Spongiosaknochen» → «schwammartige, leichte Knochen»).\n"
    "      – Es gibt keinen einfachen Ersatz und der Begriff bringt Kindern nichts → "
    "ENTFERNE die Benennung, behalte die kindgerechte Erklärung drumherum. Beispiel: "
    "«… mildert die Wirbel im Wasser ab. Das nennt man das Graysche Paradoxon. So "
    "gleiten sie perfekt.» → «… mildert die Wirbel im Wasser ab. So gleiten sie "
    "perfekt.» Auch lateinische Gattungsnamen («Osedax-Würmer» → «besondere Würmer»).\n"
    "    SCHÜTZE dagegen Fachwörter, die im Text SELBST kindgerecht erklärt werden "
    "oder zentral zur Geschichte gehören (Barten, Fluke, Blas, Krill, Blubber, "
    "Walsturz, Fluke) — die BLEIBEN unangetastet.\n"
    "  (d) Herablassende oder veraltete Anreden/Kosewörter für das Kind: «Jungchen», "
    "«Kindchen», «Bürschchen», «mein Junge» → ERSETZE durch den Namen des Kindes "
    "(steht in der Zeile/im Kontext) oder streiche die Anrede ersatzlos. Ein Kind "
    "wird beim Namen genannt, nicht herablassend angeredet.\n"
    "  (e) Offensichtliche UNMÖGLICHKEITEN oder Selbstwidersprüche in der erzählten "
    "Szene — physisch unmöglich oder mit dem Schauplatz unvereinbar: «unsere Berge "
    "hier im Garten» (ein normaler Garten hat keine Berge), «sie hört mit "
    "abgenommenen Kopfhörern das ferne Summen», «sie breitet die Arme aus, um dreißig "
    "Meter zu zeigen», «zeigt auf ein Bild», das nie eingeführt wurde. KORRIGIERE "
    "minimal auf das Plausible oder ENTFERNE nur die unmögliche Angabe (Rest der Zeile "
    "bleibt). NUR EINDEUTIGE Fälle. KEINE Plausibilität bei erfundenen Gefühlen, "
    "Fantasie-Rahmen, kindgerechten Vergleichen oder sprechenden Erzähler-Figuren — "
    "die dürfen erfunden/vereinfacht sein. Im Zweifel NICHT anfassen.\n\n"
    "ÄNDERE NICHT: Ton, Stil, Satzbau, kindgerechte Vereinfachungen, Vergleiche, "
    "Wiederholungen, Redebegleitsätze («, sagt Ronja»), Namen, alles inhaltlich "
    "Richtige. Verschönere nichts. Im Zweifel: NICHT anfassen — lieber eine Korrektur "
    "zu wenig als eine überflüssige.\n\n"
    "Gib für jede Korrektur den GANZEN betroffenen Satz (die ganze Sprecher-Zeile) "
    "als claim_original zurück und dieselbe Zeile mit dem korrigierten/entfernten "
    "Begriff als korrektur_neu. Beim Entfernen einer Benennung bleibt der Rest der "
    "Zeile erhalten — korrektur_neu ist NIE leer und enthält weiterhin die Erklärung. "
    "Keine Korrektur ohne echten Fehler."
)

SPRACH_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_original": {"type": "string",
                                       "description": "Der Originalsatz, unverändert."},
                    "korrektur_neu":  {"type": "string",
                                       "description": "Derselbe Satz mit korrigiertem Wort."},
                    "grund":          {"type": "string",
                                       "description": "Kurz: welcher Fehler (Wort/Grammatik)."},
                },
                "required": ["claim_original", "korrektur_neu"],
            },
        },
    },
    "required": ["corrections"],
}


def run_sprachpass_sync(
    articles_by_id: dict[str, dict],
    api_key: str,
) -> dict[str, list[dict]]:
    """Leichter Wortwahl-/Grammatik-Pass je Artikel.

    Gibt {aid: [correction, ...]} im annotate_article_lektorat_v2-Format zurück
    (claim_original / korrektur_neu / stufe / beleg). Fehler eines Artikels
    isolieren (leere Liste), nie den ganzen Lauf reißen.
    """
    import claude_client

    results: dict[str, list[dict]] = {}
    for aid, article in articles_by_id.items():
        lines = [
            (s.get("text") or "")
            for sec in article.get("sections", [])
            for s in sec.get("sentences", [])
        ]
        text = "\n".join(l for l in lines if l)
        if not text.strip():
            results[aid] = []
            continue
        user = (
            "HÖRSPIEL-TEXT (nur Wortwahl/Grammatik prüfen, KEINE Fakten):\n\n" + text
        )
        try:
            data = claude_client.call_claude_json(
                SPRACH_SYSTEM, user, SPRACH_SCHEMA,
                model=LEKTORAT_MODEL, max_tokens=4096, thinking_budget=0,
                call_name="sprachpass",
            )
        except Exception as exc:
            log.warning("  Sprachpass [%s] fehlgeschlagen: %s", aid, str(exc)[:100])
            results[aid] = []
            continue
        # Sprecher-Turns (sentences[].text) für die Teilsatz→Turn-Expansion.
        turns = [
            (s.get("text") or "")
            for sec in article.get("sections", [])
            for s in sec.get("sentences", [])
        ]
        corr: list[dict] = []
        for c in (data.get("corrections") or []):
            claim = (c.get("claim_original") or "").strip()
            neu   = (c.get("korrektur_neu") or "").strip()
            if not (claim and neu and claim != neu):
                continue
            # Liefert das Modell nur einen Teilsatz eines langen Turns, greift der
            # Jaccard-Einbau (Satz-Ebene) evtl. nicht. Deshalb: den Turn suchen, der
            # den Teilsatz woertlich enthaelt, und die Korrektur auf den GANZEN Turn
            # expandieren (Jaccard = 1.0 → sicherer Einbau). Nur bei exaktem Substring.
            for t in turns:
                if claim != t and claim in t:
                    claim, neu = t, t.replace(claim, neu, 1)
                    break
            corr.append({
                "claim_original": claim,
                "korrektur_neu":  neu,
                "stufe":          "KORRIGIERT",
                "beleg":          "Sprache",
            })
        results[aid] = corr
    return results


# ── Anthropic Batch-API ───────────────────────────────────────────────────────

def run_lektorat_batch(
    parts_by_id: dict[str, tuple[str, str]],
    api_key: str,
) -> dict[str, dict]:
    """Reicht alle Lektorat-Anfragen als Anthropic Message Batch ein.

    parts_by_id: {article_id: (sources_prefix, article_task)}
      sources_prefix = stabiler Quellblock (cache_control: ephemeral)
      article_task   = variabler Artikeltext + Aufgabe

    Prompt-Caching: System-Prompt + sources_prefix sind über alle 3 Batch-Anfragen
    identisch → Anthropic KV-Cache-Hit ab 2. Anfrage (~50 % Token-Einsparung).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    batch_requests = []
    for aid, (sources_prefix, article_task) in parts_by_id.items():
        batch_requests.append({
            "custom_id": aid,
            "params": {
                "model":       LEKTORAT_MODEL,
                # s. run_lektorat_sync: Claude-5 steuert Thinking über output_config.effort
                # (nicht thinking.enabled); höheres max_tokens, sonst frisst das Reasoning
                # den Cap und der JSON-Block bleibt leer (Befund 2026-07-24).
                "max_tokens":     24000,
                "output_config":  {"effort": "medium"},
                # temperature entfernt: claude-sonnet-4-6 lehnt den Parameter mit 400 ab
                # ("temperature is deprecated for this model").
                "system": [
                    {"type": "text", "text": LEKTORAT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}},
                ],
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": sources_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": article_task},
                ]}],
            },
        })

    batch = client.messages.batches.create(requests=batch_requests)
    log.info("  Lektorat-Batch gestartet: %s (%d Anfragen)", batch.id, len(batch_requests))

    poll_interval = 10
    while batch.processing_status == "in_progress":
        time.sleep(poll_interval)
        batch = client.messages.batches.retrieve(batch.id)
        c = batch.request_counts
        log.info(
            "  Batch %s … %s (✓%d ✗%d ⌛%d)",
            batch.id[:20], batch.processing_status,
            c.succeeded, c.errored, c.processing,
        )

    results: dict[str, dict] = {}   # aid -> {"corrections": [...], "pruefen": [...]}
    for result in client.messages.batches.results(batch.id):
        rid = result.custom_id
        if result.result.type == "succeeded":
            msg = result.result.message
            # Robust gegen Thinking-Blocks: claude-sonnet-4-6 liefert bei aktivem
            # Reasoning zuerst einen ThinkingBlock (ohne .text) — den echten
            # Text-Block herausfischen statt blind content[0] zu nehmen.
            raw = next(
                (b.text for b in msg.content
                 if getattr(b, "type", None) == "text" and hasattr(b, "text")),
                "",
            )
            u   = msg.usage
            log.info(
                "  [%s] tokens in=%d create=%d read=%d out=%d",
                rid, u.input_tokens,
                getattr(u, "cache_creation_input_tokens", 0),
                getattr(u, "cache_read_input_tokens", 0),
                u.output_tokens,
            )
            try:
                results[rid] = parse_lektorat_v2(raw)
            except Exception as exc:
                log.warning("  Lektorat JSON-Parse [%s]: %s", rid, exc)
                results[rid] = {"corrections": [], "pruefen": []}
        else:
            log.warning("  Lektorat-Batch [%s]: %s", rid, result.result.type)
            results[rid] = {"corrections": [], "pruefen": []}

    return results
