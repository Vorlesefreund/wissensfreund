# Wissensfreund — STATUS
<!-- updated: 2026-06-11T20:41:02Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Rang-Re-Run 33 Themen — FRISCHE Flash-Scores (2026-06-11)** ← AKTUELL

Fresh gemini-3.5-flash Importance-Scores → `scripts/importance_cache_33.json`
Alle 33 Themen, 1 Call, S1/S2/S3 relativ zueinander bewertet.

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

### Rang-Tabelle 33 Themen mit frischen Scores (* = Deckel S2/S3 aktiv)

| #  | Thema           | Rang | f:S1/S2/S3  |  W1 |  W2 |  W3 |
|----|-----------------|------|-------------|-----|-----|-----|
|  1 | Dinosaurier     | 4.41 |  10/10/7    | 250 | 372 | 454 |
|  2 | Eis             | 4.38 |  10/10/10   | 233 | 339 | 546 |
|  3 | Süßigkeiten     | 4.33 |  10/10/10   | 250 | 320 | 512 | *
|  4 | Hund            | 4.32 |  10/9/8     | 221 | 356 | 525 |
|  5 | Lego            | 4.04 |  9/10/8     | 228 | 320 | 451 | *
|  6 | Fußball         | 3.89 |  5/9/10     | 141 | 340 | 595 |
|  7 | Vulkan          | 3.71 |  5/9/9      | 129 | 342 | 549 |
|  8 | Indianer        | 3.57 |  7/7/5      | 177 | 314 | 405 |
|  9 | Feuerwehr       | 3.55 |  10/7/4     | 237 | 279 | 295 |
| 10 | Elefant         | 3.54 |  9/6/4      | 222 | 276 | 338 |
| 11 | Seefahrer       | 3.52 |  7/8/7      | 183 | 284 | 421 | * (LISTENARTIKEL)
| 12 | Ägypten         | 3.26 |  2/8/9      |  70 | 320 | 562 |
| 13 | Hades           | 3.05 |  2/7/9      |  72 | 279 | 540 |
| 14 | Schiffe         | 2.71 |  6/5/4      | 150 | 220 | 292 |
| 15 | Regenbogen      | 2.70 |  8/5/3      | 189 | 201 | 211 |
| 16 | Schule          | 2.69 |  8/4/2      | 199 | 193 | 196 |
| 17 | Airbag          | 2.68 |  3/6/7      |  94 | 232 | 409 |
| 18 | Krankenschw.    | 2.66 |  5/4/3      | 139 | 222 | 295 |
| 19 | Schmetterling   | 2.56 |  7/4/2      | 171 | 199 | 206 |
| 20 | Kinderrechte    | 2.33 |  1/4/7      |  82 | 171 | 404 |
| 21 | Zigaretten      | 2.13 |  1/3/6      |  50 | 173 | 407 |
| 22 | Jahreszeiten    | 2.08 |  4/3/2      | 112 | 174 | 213 |
| 23 | Pangolin        | 2.04 |  2/4/4      |  72 | 187 | 283 | *
| 24 | Pupille         | 1.98 |  2/4/5      |  72 | 165 | 296 |
| 25 | Brennessel      | 1.93 |  3/4/3      |  94 | 171 | 207 |
| 26 | VW              | 1.89 |  2/3/4      |  72 | 151 | 283 | *
| 27 | Kühlschrank     | 1.63 |  3/2/1      |  94 | 135 | 145 |
| 28 | Mozart          | 1.58 |  1/2/3      |  51 | 134 | 243 |
| 29 | Apfel           | 1.54 |  3/2/1      |  96 | 122 | 123 |
| 30 | Beethoven       | 1.52 |  1/2/3      |  52 | 127 | 230 |
| 31 | Fasten          | 1.43 |  1/1/2      |  77 |  96 | 176 |
| 32 | Viereck         | 1.34 |  3/1/1      |  90 |  89 | 116 |
| 33 | Düsseldorf      | 1.30 |  1/1/1      |  81 |  91 | 119 |

Ägypten/Hades/Fußball/Vulkan: niedrig bei Kleinkind, stark bei S2/S3 → korrekte Altersverschiebung.

### Lemma-Härtung Flash-Doppelbedeutung (2026-06-11)
`_flash_check_doppelbedeutung()` — gemini-3.5-flash, ThinkingLevel.NONE.
Flash liefert NUR child_topic/child_lemma/main_hint. Direktive hart codiert (Hauptbedeutung zuerst):
"Erkläre zuerst {query} ({main_hint}), dann weiter unten {child_topic}."
Eis-Test: "Erkläre zuerst Eis (gefrorenes Wasser), dann weiter unten Speiseeis." ✓

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
