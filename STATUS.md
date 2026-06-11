# Wissensfreund — STATUS
<!-- updated: 2026-06-11T20:19:59Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Rang-Re-Run 33 + Lemma-Härtung Flash (2026-06-11)** ← AKTUELL

### Finalisierte Formel (Wortbudget, noch NICHT verdrahtet)
```
fasc_norm_S  = (flash_S − 1) / 9
cov_norm_S1  = clamp((MiniW − 85)  / 150,  0, 1)   falls MiniW vorhanden
cov_norm_S23 = clamp((KlexW − 180) / 1180, 0, 1)   falls KlexW vorhanden
importance_S = 0.8·fasc_S + 0.2·cov_S   (fehlt cov → nur fasc)

Klexikon-Abwesenheits-Deckel, NUR S2/S3, NUR wenn KlexW fehlt (—), KEINE Ausnahmen:
  importance_S = min(importance_S, 0.25 + 0.5·importance_S)
  → Deckel beißt wenn imp > 0.5: z.B. 1.0→0.75, 0.889→0.694
  → Kein S1-Deckel (nie)

target_S = Wlo + importance_S · (Whi − Wlo)   KEIN vol_cap
  S1[50,250] / S2[80,400] / S3[100,650]

Rang = 1 + 4 · mean(imp_S1, imp_S2, imp_S3)
```

### Rang-Tabelle 33 Themen (* = Deckel S2/S3 aktiv)

| #  | Thema           | Rang | S1  | S2  | S3  |
|----|-----------------|------|-----|-----|-----|
|  1 | Dinosaurier     | 4.76 | 250 | 372 | 601 |
|  2 | Hund            | 4.68 | 221 | 384 | 623 |
|  3 | Elefant         | 4.49 | 222 | 361 | 583 |
|  4 | Eis             | 4.26 | 233 | 339 | 497 |
|  5 | Feuerwehr       | 4.26 | 220 | 336 | 539 |
|  6 | Lego            | 4.26 | 250 | 320 | 482 | *
|  7 | Süßigkeiten     | 4.26 | 250 | 320 | 482 | *
|  8 | Indianer        | 4.16 | 195 | 343 | 552 |
|  9 | Seefahrer       | 3.89 | 206 | 302 | 482 | * (→ LISTENARTIKEL, moot)
| 10 | Fußball         | 3.89 | 194 | 311 | 497 |
| 11 | Ägypten         | 3.85 | 177 | 320 | 513 |
| 12 | Schiffe         | 3.66 | 185 | 306 | 439 |
| 13 | Pangolin        | 3.59 | 183 | 284 | 451 | *
| 14 | Vulkan          | 3.47 | 165 | 285 | 452 |
| 15 | Krankenschw.    | 3.37 | 139 | 279 | 491 |
| 16 | Regenbogen      | 3.29 | 172 | 258 | 406 |
| 17 | Hades           | 3.22 | 117 | 279 | 491 |
| 18 | Schule          | 3.17 | 181 | 249 | 342 |
| 19 | Schmetterling   | 3.15 | 153 | 256 | 402 |
| 20 | Jahreszeiten    | 3.15 | 166 | 259 | 360 |
| 21 | Kinderrechte    | 2.45 | 118 | 171 | 355 |
| 22 | Apfel           | 2.25 | 114 | 179 | 270 |
| 23 | Viereck         | 2.17 | 125 | 175 | 214 |
| 24 | Pupille         | 2.13 |  94 | 165 | 296 |
| 25 | Brennessel      | 1.96 | 117 | 142 | 207 |
| 26 | Airbag          | 1.94 |  72 | 146 | 312 |
| 27 | Mozart          | 1.93 |  86 | 163 | 243 |
| 28 | Beethoven       | 1.88 |  87 | 156 | 230 |
| 29 | Zigaretten      | 1.78 |  50 | 145 | 309 |
| 30 | Düsseldorf      | 1.77 |  98 | 120 | 217 |
| 31 | Fasten          | 1.67 |  77 | 124 | 225 |
| 32 | Kühlschrank     | 1.63 |  94 | 135 | 145 |
| 33 | VW              | 1.59 |  72 | 116 | 222 | * (Deckel beißt nicht, imp<0.5)

Schnitzer-Check: Lego/Süßigkeiten (#6/7, 4.26) — ohne Deckel wären beide #1 (S2=400, S3=548).
Deckel schiebt korrekt auf S2=320, S3=482. Keine groben Schnitzer erkennbar.

### Lemma-Härtung Flash-Doppelbedeutung (2026-06-11)
`_flash_check_doppelbedeutung()` in `generate_articles.py` (gemini-2.5-flash, thinking_budget=0).
BKS-Schwester / Hatnote = Pre-Filter; Flash-Urteil a/b/c ersetzt strukturelles Flag.
Probe: Schiffe→a, Eis→b (Direktive: Speiseeis zuerst, child_lemma=Speiseeis), Elefant/Vulkan/Hund→a.

---

## 🔴 Nächster Schritt

**Formel verdrahten**: WORTZIEL_TABLE in `generate_grounded.py` (Z.86–96) durch
dynamische imp_S-Berechnung ersetzen + `resolve_lemma` vor `fetch_wikipedia_text` einbauen.

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Formel verdrahten** (imp_S dynamisch, Abwesenheitsdeckel S2/S3, kein vol_cap)
- **resolve_lemma in Pipeline**: vor `fetch_wikipedia_text` in `generate_grounded.py`
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug
