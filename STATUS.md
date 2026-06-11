# Wissensfreund — STATUS
<!-- updated: 2026-06-11T22:18:16Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**100er-Robustheitsprobe content_richness_v2 (2026-06-12)** ← AKTUELL

100 Zufalls-Klexikon-Titel (seed=42), 8 Anker, 1 Flash-Call → `scripts/fasc_cache_100.json`.
Top: Haie/Brachiosaurus/Hai Ø9.7, Chamäleon/Fossilien/Blackbeard Ø8.3 — plausibel.
Bottom: Arenhusen/Gatte Ø2.0, Bottrop/Vevey Ø2.7, Somatropin Ø2.7 — korrekt dünn.
Anker-Konsistenz: Brachiosaurus=Dinosaurier-Anker (Ø9.7✓), Erdmännchen=Elefant-Anker (Ø7.7✓).
Befund: Trennschärfe hält auf ungesehenen Titeln. Kein Defekt. Siehe Trennschärfe-Befund unten.

**Re-Scoring Inhaltsreichtum (content_richness_v2, 2026-06-12)**

Alle 33 Themen neu bewertet mit fixiertem Inhalts-Wortlaut (Peer-Status/Coolness explizit
ausgeschlossen). gemini-3.5-flash, ThinkingLevel.LOW, 1 Call → `scripts/importance_cache_33.json`.

### Finalisierte Formel (Wortbudget, noch NICHT verdrahtet)
```
fasc_norm_S  = (flash_S − 1) / 9
cov_norm_S1  = clamp((MiniW − 85)  / 150,  0, 1)   falls MiniW vorhanden
cov_norm_S23 = clamp((KlexW − 180) / 1180, 0, 1)   falls KlexW vorhanden
importance_S = 0.8·fasc_S + 0.2·cov_S   (fehlt cov → nur fasc)

Klexikon-Abwesenheits-Deckel, NUR S2/S3, NUR wenn KlexW fehlt:
  importance_S = min(importance_S, 0.25 + 0.5·importance_S)

target_S = Wlo + importance_S · (Whi − Wlo)
  S1[50,250] / S2[80,400] / S3[100,650]
Rang = 1 + 4 · mean(imp_S1, imp_S2, imp_S3)
```

### Rang-Tabelle 33 Themen — content_richness_v2 (* = Deckel S2/S3 aktiv)

| #  | Thema           | Rang | f:S1/S2/S3  |  W1 |  W2 |  W3 |
|----|-----------------|------|-------------|-----|-----|-----|
|  1 | Dinosaurier     | 4.64 | 10/10/9     | 250 | 372 | 552 |
|  2 | Vulkan          | 4.18 |  7/10/10    | 165 | 370 | 598 |
|  3 | Indianer        | 4.04 |   6/9/8     | 160 | 371 | 552 |
|  4 | Elefant         | 4.01 |   9/8/6     | 222 | 332 | 436 |
|  5 | Hund            | 3.97 |  10/8/6     | 221 | 328 | 428 |
|  6 | Feuerwehr       | 3.79 |  10/8/5     | 237 | 307 | 344 |
|  7 | Lego            | 3.74 |   8/9/7     | 206 | 302 | 421 | *
|  8 | Schiffe         | 3.66 |   7/8/8     | 167 | 306 | 488 |
|  9 | Fußball         | 3.65 |   6/8/8     | 158 | 311 | 497 |
| 10 | Ägypten         | 3.61 |  3/9/10     |  88 | 349 | 611 |
| 11 | Schmetterling   | 3.39 |   8/7/5     | 189 | 284 | 353 |
| 12 | Seefahrer       | 3.37 |  4/9/10     | 117 | 302 | 512 | * (LISTENARTIKEL)
| 13 | Hades           | 3.28 |  2/8/10     |  72 | 308 | 589 |
| 14 | Süßigkeiten     | 3.19 |   7/6/5     | 183 | 249 | 344 | *
| 15 | Kinderrechte    | 3.16 |   3/7/9     | 118 | 257 | 501 |
| 16 | Krankenschw.    | 3.13 |   5/5/6     | 139 | 250 | 442 |
| 17 | Mozart          | 2.88 |   3/6/8     |  86 | 248 | 487 |
| 18 | Pangolin        | 2.78 |   3/6/7     |  94 | 249 | 421 | *
| 19 | Regenbogen      | 2.70 |   7/5/4     | 172 | 201 | 259 |
| 20 | Beethoven       | 2.59 |   2/5/8     |  70 | 212 | 474 |
| 21 | Schule          | 2.57 |   5/4/4     | 145 | 193 | 293 |
| 22 | Jahreszeiten    | 2.56 |   6/4/3     | 148 | 203 | 262 |
| 23 | Eis             | 2.37 |   5/4/4     | 144 | 169 | 252 |
| 24 | Pupille         | 2.33 |   2/5/7     |  72 | 194 | 394 |
| 25 | VW              | 2.30 |   2/4/6     |  72 | 187 | 390 | *
| 26 | Airbag          | 2.29 |   2/5/6     |  72 | 203 | 361 |
| 27 | Brennessel      | 2.29 |   3/5/5     |  94 | 199 | 305 |
| 28 | Kühlschrank     | 2.20 |   2/4/5     |  72 | 191 | 340 |
| 29 | Zigaretten      | 2.13 |   1/3/6     |  50 | 173 | 407 |
| 30 | Fasten          | 2.02 |   1/3/5     |  77 | 153 | 322 |
| 31 | Apfel           | 1.90 |   4/3/2     | 114 | 151 | 172 |
| 32 | Düsseldorf      | 1.65 |   1/2/3     |  81 | 120 | 217 |
| 33 | Viereck         | 1.46 |   2/2/2     |  72 | 118 | 165 |

Größte Verschiebungen vs. v1 (Coolness-Framing):
- Indianer #8→#3 (+5): indigene Kulturen = echter Inhaltsreichtum
- Schmetterling #19→#11 (+8): Metamorphose/Migration war durch Coolness-Bias unterdrückt
- Vulkan #7→#2: konstant stark, jetzt noch mehr betont
- Eis #2→#23 (-21): war social-faszinierender als inhaltlich reich
- Süßigkeiten #3→#14 (-11): Coolness-Effekt enttarnt
- Mozart/Beethoven steigen: dramatische Lebensgeschichte = Inhaltsreichtum für S3

Pannenprüfung ✓: Viereck#33, Düsseldorf#32, Apfel#31, Fasten#30 (unten).
Indianer#3, Elefant#4, Schmetterling#11 (vernünftig). VW#25, Kühlschrank#28, Airbag#26, Pupille#24.

### Lemma-Härtung Flash-Doppelbedeutung (2026-06-11)
gemini-3.5-flash, ThinkingLevel.NONE. Direktive hart codiert (Hauptbedeutung zuerst):
"Erkläre zuerst {query} ({main_hint}), dann weiter unten {child_topic}."

---

## 🔴 Nächster Schritt

**Formel verdrahten**: WORTZIEL_TABLE in `generate_grounded.py` (Z.86–96) durch
dynamische imp_S-Berechnung ersetzen + `resolve_lemma` vor `fetch_wikipedia_text` einbauen.

---

## 🔴 Offene Punkte (nach Priorität)

- **Formel verdrahten** (imp_S dynamisch, Abwesenheitsdeckel S2/S3, kein vol_cap)
- **resolve_lemma in Pipeline**: vor `fetch_wikipedia_text` in `generate_grounded.py`
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit
- Flutter-App testen: WfArticleListScreen mit R2-Artikeln
