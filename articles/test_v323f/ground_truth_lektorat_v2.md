# Ground Truth — Wissensfreund Lektorat (GT_v2)

Erstellt: 2026-06-24 | Claude Chat | Basis: test_v323f (Overfitting-Check)
Themen: Zugvögel, Demokratie, Sklaverei | 9 Artikel | Stand 3 Lektorat-Regeln

---

## SEKTION A — SOLL_FLAGGEN (9 Fälle)

### A1 · zugvögel_l1 · K1
Claim: „Der vorderste Vogel zeigt den anderen Vögeln den Weg."
Fehler: Quelle belegt nur Energieersparnis durch Auftrieb — keine Wegweisung.
Lektorat: KORRIGIERT ✓ | Verdikt: TRUE POSITIVE

### A2 · zugvögel_l1 · P1 (wow-Box)
Claim: „Er flog mehrere Tage lang, ohne ein einziges Mal zu landen!"
Fehler: „Mehrere Tage" ungedeckt — kein source_passage nennt Dauer; Strecke belegt, Tageszahl nicht.
Lektorat: PRÜFEN ✓ | Verdikt: TRUE POSITIVE

### A3 · zugvögel_l3 · P5
Claim: „Junge Indigofinken müssen die Orientierung am Sternenhimmel erst durch Beobachtung der
Sternen-Rotation erlernen."
Fehler: Cross-source-Kombination — Sternen-Rotation aus allgemeiner Vogelnavigations-Passage;
für Indigofinken belegt: Sternenhimmel sehen müssen, nicht explizit Rotations-Mechanismus.
Lektorat: PRÜFEN ✓ | Verdikt: TRUE POSITIVE

### A4 · sklaverei_l2 · K2
Claim: „Ein Gladiator war ein Schausteller, der im alten Rom mit Waffen kämpfen musste."
Fehler: „Schausteller" verharmlosend und ungedeckt — Quelle: Gladiatorenschule, Kämpfe auf
Leben und Tod. Prompt-Regel P3 greift exakt.
Lektorat: KORRIGIERT ✓ | Verdikt: TRUE POSITIVE

### A5 · sklaverei_l2 · P3
Claim: „Oft wurden diese Waren und Sklaven auf einer großen Dreiecksroute über das Meer
getauscht."
Fehler: Quelle bezeichnet Dreieckshandels-Modell explizit als „unangemessen und nicht neutral";
nur geringer Teil der Fahrten folgte diesem Muster. Artikel präsentiert Modell als Fakt.
Lektorat: PRÜFEN ✓ | Verdikt: TRUE POSITIVE

### A6 · sklaverei_l3 · S1
Claim: „…wodurch der Kontakt zur Familie für immer abriss."
Fehler: „für immer" ungedeckter Zusatz — Quelle: „der Kontakt riss dadurch ab" (ohne Temporalangabe).
Lektorat: SILENT ✓ | Verdikt: TRUE POSITIVE

### A7 · sklaverei_l3 · S3
Claim: „Schon als Fünfjährige musste Harriet schwer arbeiten"
Fehler: Quelle: „fünf oder sechs Jahren" — „als Fünfjährige" ist falsche Präzision,
tilgt quelleninterne Unsicherheit.
Lektorat: SILENT ✓ | Verdikt: TRUE POSITIVE

### A8 · sklaverei_l3 · K4
Claim: „…um ihre Familie und andere Sklaven zu retten."
Fehler: „ihre Familie" als Rückkehr-Motiv ungedeckt — Quelle belegt „anderen Sklaven" (allgemein)
und „mehr als 70 Menschen." Familien-Fokus ist ungedeckter Zusatz.
Lektorat: KORRIGIERT ✓ | Verdikt: TRUE POSITIVE

### A9 · sklaverei_l3 · P6
Claim: „der thrakische Gladiator Spartacus…aus einer Kampfschule"
Fehler: Quelle markiert „thrakisch" explizit als „letztlich aber nur Vermutung."
Artikel präsentiert als Fakt. „Kampfschule" vs. „Gladiatorenschule" — sachlich vertretbar
aber Abweichung vom belegten Begriff.
Lektorat: PRÜFEN ✓ | Verdikt: TRUE POSITIVE

---

## SEKTION B — SOLL_STILL_SEIN (8 False Positives)

### B1 · zugvögel_l1 · S2
Claim: „ruht sich aus" → „schläft"
Ursache FP: Synonym-Verstoß — „sinngemäße Deckung genügt"; VERBOTEN laut Prompt.
Lektorat: SILENT → FALSE POSITIVE

### B2 · zugvögel_l3 · S1
Claim: „über 12.000 Kilometer" → „knackte die 12.000-Kilometer-Marke"
Ursache FP: Synonym-Verstoß — bedeutungsidentisch.
Lektorat: SILENT → FALSE POSITIVE

### B3 · zugvögel_l3 · S2
Claim: „jedoch" entfernt
Ursache FP: Stileingriff — Fügewort ist keine Faktenbehauptung.
Lektorat: SILENT → FALSE POSITIVE

### B4 · zugvögel_l3 · S4
Claim: Vogelberingung-Erklärung angehängt zu quellengedecktem Satz
Ursache FP: Additive Korrektur — Original korrekt; UNVOLLSTÄNDIGKEIT IST KEIN FEHLER.
Lektorat: SILENT → FALSE POSITIVE

### B5 · demokratie_l3 · K1
Claim: „wenige/viele" → Prozentzahlen ergänzt
Ursache FP: Additive Präzision bei korrekter Aussage — „wenige" (8 %) und „viele" (39 %) sind
sachlich richtig; Korrektions-Prinzip: Minimaler Eingriff verletzt.
Lektorat: KORRIGIERT → FALSE POSITIVE

### B6 · sklaverei_l2 · S1
Claim: „über siebzig" → „mehr als siebzig"
Ursache FP: Synonym-Verstoß — bedeutungsidentisch; VERBOTEN laut Prompt.
Lektorat: SILENT → FALSE POSITIVE

### B7 · sklaverei_l3 · S2
Claim: „die Familie" → Harriet Green + andere Sklaven + freie Schwarze
Ursache FP: Additive Anreicherung zulässiger Vereinfachung — „die Familie" (Harriet Green = Mutter)
ist nicht falsch; UNVOLLSTÄNDIGKEIT IST KEIN FEHLER.
Lektorat: SILENT → FALSE POSITIVE

### B8 · sklaverei_l3 · S5
Claim: „zwei Jahre später" → „im Jahr 71 v. Chr." ergänzt
Ursache FP: Additive Präzision bei korrekter Relativangabe (73−2=71 korrekt).
Lektorat: SILENT → FALSE POSITIVE

---

## SEKTION C — GRENZFÄLLE

### C1 · zugvögel_l3 · S3
Claim: „24 Stunden am Tag" → „theoretisch 24 Stunden"
Quelle: „theoretisch" in Klammern; Artikel-„kann" ist bereits Modal. SILENT knapp vertretbar,
unter Eingriffsgrenze eher kein Flag nötig. Lektorat-Verhalten: akzeptabel.

---

## BASELINE-MESSUNG GT_v2

| Kategorie        | Fälle         | Anzahl |
|------------------|---------------|--------|
| True Positives   | A1–A9         | 9      |
| False Negatives  | —             | 0      |
| True Negatives   | 0-Findings (4 Artikel) | 4 Artikel |
| False Positives  | B1–B8         | 8      |
| Grenzfälle       | C1            | 1      |

Recall    = 9/9  = 100 % (Ziel ≥ 70 % ✓)
Precision = 9/17 =  53 % ⚠ (innerhalb Findings: fast jedes zweite unnötig)

---

## DIAGNOSE: FP-MUSTER

Kein FP ist durch neue Detailattribut- oder Quantoren-Regeln verursacht.
Alle neuen Regeln erzeugten ausschließlich TPs.

FP-Typen:

**Typ SYNONYM** (B1, B2, B3, B6):
Prompt-Abschnitt „KONKRET VERBOTEN: Synonym-Austausch" existiert — Modell befolgt ihn
inkonsistent. Anker fehlt am Entscheidungsmoment.

**Typ ADDITIV** (B4, B5, B7, B8):
UNVOLLSTÄNDIGKEIT IST KEIN FEHLER + Korrektions-Prinzip „Minimaler Eingriff" existieren —
Modell fügt trotzdem Information zu richtigen Sätzen hinzu.

Praktische Konsequenz: Andreas würde im Review-Tool 17 Findings sehen,
davon 8 unnötig (47 % Rauschen).

Fix-Richtung: Keine neuen Regeln nötig — bestehende Regeln brauchen konkrete Negativ-Beispiele
direkt an der Verletzungs-Stelle (nahe am Entscheidungsmoment, nicht nur im Prinzipien-Block).

---

## STATUS

GT_v2 abgeschlossen 2026-06-24.

Stand 3 (dd98942): Recall 100 %, Precision 53 % — bester erreichter Stand.

Stand 4 (2026-06-24, ROLLBACK):
Prompt-Tuning-Versuch für Precision (Negativ-Beispiele in KONKRET VERBOTEN +
UNVOLLSTÄNDIGKEIT) gescheitert:
  - FPs: 7/8 weiterhin geflaggt; Beispiele wörtlich ignoriert
  - Recall-Regression: A3 (Indigofinken) + A7 (Fünfjährige) verloren → Recall 78 %
  - Neue FPs entstanden (4 zusätzliche)
  - Befund: holistische Lektorat-Architektur wählt wechselnde Findings-Teilmenge;
    Prompt-Ergänzungen verschieben Aufmerksamkeit, beheben keine systematischen FPs
  → Rollback auf Stand 3. Kein weiterer Prompt-Tuning-Versuch für Precision.

Precision-Fix erfordert claim-weise Architektur (wie Recall-Umbau).
Kurzfristig: Baustein 2 (HTML-Review-Tool) macht FPs im Review handhabbar.
