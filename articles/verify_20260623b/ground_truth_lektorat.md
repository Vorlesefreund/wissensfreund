# Ground Truth — Wissensfreund Lektorat (GT_v1)

Erstellt: 2026-06-24 | Claude Chat | Basis: verify_20260623b-Artefakte
Methodik: Claim-für-Claim-Abgleich Artikel-Text vs. source_passages + (wo nötig) Volltext-Quellen
Architektur-Hinweis: Das Lektorat liest die vollen Wikipedia-Texte (primary_text + companion_texts
aus stage1_checkpoint.json), NICHT source_passages. source_passages sind Generator-Output, kein
Lektorat-Input. Die GT-Verdichte (TP/FN/FP) sind beobachtetes Verhalten — die Ursachendiagnose
unten trägt dem Rechnung.

Zielkorridor: Recall ≥ 0,70 · FPR ≤ 0,15

---

## SEKTION A — SOLL_FLAGGEN (echte Fehler, Lektorat MUSS eingreifen)

### A1 · vulkan_l2 · s017
Claim: „Im Jahr 79 nach Christus brach er völlig überraschend aus."
Fehler: „völlig überraschend" widerspricht der Quelle.
Beleg: Pompeji-Artikel (Volltext im Snapshot): mehrere Tage Vorzeichen vor dem Ausbruch;
ein Teil der Einwohner verließ Pompeji rechtzeitig.
Erwartetes Lektorat-Verhalten: KORRIGIERT → „…brach er aus."
Lektorat-Ist (pre-0a39bf8): KORRIGIERT ✓
Verdikt: TRUE POSITIVE

### A2 · vulkan_l2 · s023
Claim: „So entstanden Gipsfiguren, die uns heute den genauen Moment der Flucht zeigen."
Fehler: „Flucht" ist sachlich falsch.
Beleg: Pompeji-Volltext: Die Hohlräume entstammen Todesopfern, nicht Fliehenden.
„Ausdruck reicht vom offensichtlichen Todeskampf bis hin zu einem friedlichen Eindruck des
Einschlafens."
Erwartetes Lektorat-Verhalten: KORRIGIERT → „…den Moment zeigen, in dem die Menschen starben."
Lektorat-Ist: KORRIGIERT ✓
Verdikt: TRUE POSITIVE

### A3 · vulkan_l3 · s025
Claim: „Pyroklastische Ströme – extrem heiße Lawinen aus Gas und Asche – rasten mit
Überschallgeschwindigkeit den Berghang hinab."
Fehler (doppelt):
(1) Quelle Vesuv-Volltext: Überschallgeschwindigkeit gilt nur für Magma im Schlot, nicht für
pyroklastische Ströme.
(2) Interne Inkonsistenz: Die Warnung-Box desselben Artikels sagt „mehrere hundert Kilometer pro
Stunde" (Unterschall; Schallgeschwindigkeit ≈ 1235 km/h).
Erwartetes Lektorat-Verhalten: KORRIGIERT → „…rasten mit mehreren hundert Kilometern pro Stunde
den Berghang hinab."
Lektorat-Ist: KORRIGIERT ✓
Verdikt: TRUE POSITIVE

### A4 · vulkan_l3 · s035
Claim: „Robben sonnten sich an den geschützten Buchten"
Fehler: „geschützten Buchten" ist ein ungedeckter Zusatz.
Beleg: Surtsey-Volltext (im Snapshot): „Sie begannen früh, sich auf der Insel zu sonnen, speziell
im nördlichen Teil." Kein Hinweis auf Buchten jedweder Art.
Das Lektorat hatte Zugriff auf den vollen Surtsey-Text — der Zusatz war trotzdem findbar, wurde
aber nicht gemeldet.
Erwartetes Lektorat-Verhalten: KORRIGIERT → „Robben sonnten sich auf der Insel"
Lektorat-Ist: SILENT ✗
Verdikt: FALSE NEGATIVE — Ursache Typ 2 (s. Diagnose unten)

### A5 · vulkan_l3 · s020
Claim: „Der Vesuv, ein mächtiger Schichtvulkan, explodierte völlig unvorbereitet für die Menschen."
Fehler: Strukturell identisch mit A1. Dasselbe Argument (Vorzeichen, Teilevakuierung) gilt.
Das Lektorat hatte Zugriff auf Pompeji-Volltext (Companion im Snapshot). A1 wurde in vulkan_l2
korrekt geflaggt; in vulkan_l3 nicht — inkonsistentes Verhalten über Stufen.
Erwartetes Lektorat-Verhalten: KORRIGIERT (analog A1)
Lektorat-Ist: KEIN FINDING ✗
Verdikt: FALSE NEGATIVE — Ursache Typ 3 (s. Diagnose unten)

### A6 · vulkan_l3 · wow-Box (Surtsey-Perlen)
Claim: „Forscher machten ein Experiment und warfen 10 Millionen winzige Plastikperlen ins Wasser
bei der Nachbarinsel Heimaey. Tatsächlich schwamm etwa ein Prozent davon bis an Surtseys Strände."
Status: Kein source_passage-Eintrag vorhanden; ob der Inhalt im vollen Surtsey-Snapshot steht,
ist nicht verifiziert (Claude Chat hatte keinen Zugriff auf den vollen Primärtext).
[OFFEN: Claude Code soll im Re-Lauf prüfen, ob das Perlen-Experiment im Surtsey-Volltext des
Snapshots vorkommt. Liegt es dort → B-Kandidat (gedeckt, GT-Korrektur nötig). Liegt es nicht
dort → echter FN-Kandidat.]
Erwartetes Lektorat-Verhalten: PRÜFEN (spezifische Zahlen + Eigenname ohne verifizierten Beleg)
Lektorat-Ist: KEIN FINDING
Vorläufiges Verdikt: FALSE NEGATIVE (vorbehaltlich Volltext-Prüfung durch Claude Code)

---

## SEKTION B — SOLL_STILL_SEIN (zulässige Vereinfachungen, Lektorat darf NICHT eingreifen)

### B1 · vulkan_l1 · s024
Claim: „Wir nennen diese warmen Quellen Geysire."
Vereinfachung: „warm" statt „heiß" — Abschwächung für S1 (4–6 Jahre), kein Widerspruch.
Kontext relativiert (s026: „Das Wasser ist auch sehr heiß").
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B2 · vulkan_l2 · s029–s030
Claim: „Zuerst trieben Pflanzensamen über das Meer. Später nisteten Vögel…"
Vereinfachung: 75 % der Pflanzen kamen via Vögel (nicht via Meer). Der Artikel behauptet aber
nicht, Meer sei der Hauptweg — er beschreibt die zeitliche Sequenz (Meer zuerst, korrekt laut
Quelle). Auslassung der Mengenanteile ≠ Widerspruch.
Alte Regeln: KORRIGIERT ✗ → FALSE POSITIVE
Neue Eingriffsgrenze (Commit 0a39bf8): sollte SILENT ergeben — zu validieren im Re-Lauf.
Lektorat-Ist (pre-0a39bf8): KORRIGIERT ✗
Verdikt: FALSE POSITIVE (alte Regeln) — Erwartung: TRUE NEGATIVE (neue Regeln)

### B3 · vulkan_l3 · s015
Claim: „So entstehen oft meist sechseckige Basaltsäulen."
Vereinfachung: Doppeleinschränkung „oft meist" ist stilistisch inkohärent, faktisch korrekt.
Stilprobleme fallen nicht unter die Eingriffsgrenze.
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B4 · vulkan_l3 · s033
Claim: „Zuerst trieben Samen der Salzmiere und des Meersenfes über das Meer an die Strände."
Vereinfachung: Quelle: Meersenf 1963, Salzmiere 1967. „und"-Verknüpfung impliziert keine
interne Sequenz; „Zuerst" bezieht sich auf Meer- vs. Vogel-Transport, nicht auf
Pflanzenreihenfolge. Kein Widerspruch.
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B5 · vulkan_l2 · s019
Claim: „Fast zweitausend Jahre lang blieb die Stadt vergessen."
Vereinfachung: 79–1748 = ca. 1669 Jahre. „Fast zweitausend" zulässige Abrundung für S2.
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B6 · titanic_l2 · s010
Claim: „Nach etwa zweieinhalb Stunden zerbrach der Riese in zwei Teile"
Vereinfachung: Tatsächlich ca. 2 Std. 40 Min. „Zweieinhalb Stunden" = akzeptable Näherung für S2.
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B7 · titanic_l2 · s007
Claim: „Der harte Eisberg riss mehrere Löcher unter Wasser in die dicke Außenwand aus Stahl."
Vereinfachung: Tatsächliche Mechanik komplexer (Nietenversagen, Verformung). Für S2 akzeptable
Vereinfachung; keine Widerspruchsbehauptung.
Lektorat-Ist: SILENT ✓
Verdikt: TRUE NEGATIVE

### B8 · ww2_l2 · gesamt
Alle Claims grounded, 0 Findings korrekt.
Lektorat-Ist: SILENT gesamt ✓
Verdikt: TRUE NEGATIVE

---

## SEKTION C — GRENZFÄLLE (Lektorat-Verhalten akzeptabel, Entscheidung kontextabhängig)

### C1 · vulkan_l3 · s024 + s026
Claim: „Kurz nach Mitternacht brach die riesige Säule in sich zusammen. […] Sie verschütteten die
römischen Städte Pompeji und Herculaneum meterhoch."
Status: Vergröberung eines mehrstufigen Prozesses (Herculaneum: 1. Strom; Pompeji: 6. Strom).
Kein Widerspruch, sondern zeitliche Kompression. „Verschütteten" ist faktisch korrekt.
Erwartetes Verhalten: SILENT oder PRÜFEN ohne Eingriff
Lektorat-Ist: PRÜFEN mit korrektur_neu: null → akzeptabel; unter neuer Eingriffsgrenze eher SILENT.
Verdikt: GRENZFALL akzeptiert

---

## BASELINE-MESSUNG (pre-Commit 0a39bf8)

| Kategorie | Fälle | Anzahl |
|---|---|---|
| True Positives | A1, A2, A3 | 3 |
| False Negatives | A4, A5, A6* | 3 |
| True Negatives | B1, B3, B4, B5, B6, B7, B8 | 7 |
| False Positives | B2 | 1 |

Recall = 3 / (3+3) = **50 %** (Ziel: ≥ 70 %)
FPR    = 1 / (1+7) = **12,5 %** (Ziel: ≤ 15 %)

*A6 vorbehaltlich Volltext-Prüfung (s. oben).

---

## DIAGNOSE: DREI RECALL-MISS-TYPEN

Das Lektorat liest die vollen Wikipedia-Texte (primary_text + companion_texts aus
stage1_checkpoint.json). Alle drei Misses hatten also die relevanten Quelltexte zur Verfügung.
Die Ursachen sind struktureller, nicht parametrischer Natur:

**Typ 2 — Ungedeckter Zusatz innerhalb eines belegten Satzes (A4)**
Hauptprädikat quellengedeckt; ein spezifisches Detail (Ortsangabe „geschützte Buchten") ist es
nicht. Der holistische Ansatz akzeptiert den Satz, weil das Kernprädikat stimmt.
Fix: Claim-weise Prüfung muss Adjektive / Ortsangaben / Detailattribute explizit gegen den
Volltext testen — nicht nur das Hauptprädikat.

**Typ 3 — Cross-source-Inkonsistenz bei starkem Quantor (A5)**
source_passage (#6) belegt Höhe und Bautyp des Vesuvs, nicht „völlig unvorbereitet". Die
Gegenstelle (Vorzeichen-Passage in Pompeji-Volltext) liegt im Snapshot, wurde aber vom Lektorat
nicht aktiv gesucht. In vulkan_l2 (A1) wurde derselbe Fehler korrekt geflaggt — inkonsistentes
Verhalten bei starken Quantoren (völlig, immer, alle, nie).
Fix: Bei starken Quantoren muss das Lektorat explizit nach Gegenbelegen im Volltext suchen,
nicht nur den nächsten bestätigenden Beleg finden.

**Typ 1 — Claim ohne source_passage-Eintrag (A6)**
Architektur-Hinweis: Das Lektorat liest ohnehin den Volltext — der fehlende source_passage-Eintrag
ist kein Hindernis für die Prüfung. A6 ist ein Typ-1-Miss nur insofern, als der Generator keinen
Anker gesetzt hat. Das Lektorat muss bei spezifischen Zahlen/Eigennamen ohne erkennbare
Quellendeckung im Volltext explizit suchen und PRÜFEN setzen, wenn es nichts findet.

**Gemeinsame Konsequenz:** Recall-Problem ist NICHT durch temp oder Eingriffsgrenze lösbar.
Es erfordert eine claim-weise Prüfarchitektur:
1. Artikel in Einzelclaims zerlegen
2. Für jeden Claim mit starken Quantoren oder Detailattributen: aktive Suche im Volltext nach
   Belegen UND Gegenbelegen
3. Für Claims mit spezifischen Zahlen/Namen ohne Volltext-Treffer: automatisch PRÜFEN

---

## OFFENE VERIFIKATION

- A6: Volltext-Prüfung ob „Perlen-Experiment" (Heimaey, 10 Millionen, 1 %) im Surtsey-Wikipedia-
  Snapshot (stage1_checkpoint.json) vorkommt → falls ja: A6 wird B-Kandidat, GT korrigieren.
- Re-Lauf mit Commit 0a39bf8 (temp=0 + neue Eingriffsgrenze): B2 erwartet als TRUE NEGATIVE;
  A4/A5 weiterhin als FALSE NEGATIVE erwartet (strukturelle Ursache, nicht durch Parameter behebbar).
