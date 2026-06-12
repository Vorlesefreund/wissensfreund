# Wissensfreund — STATUS
<!-- updated: 2026-06-12T10:26:48Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Pilot-Generierung 12 × 3 Stufen (2026-06-12)** ← AKTUELL

`temp/_pilot_gen.py` → `pilot_output/` (36 Markdown-Dateien + `pilot_wortzahlen.csv`).
36/36 Artikel, 0 Fehler, Laufzeit ~16 Min. Lemma-/BKS-Flags korrekt erkannt.
Hauptbefund: Ceiling-only-Formulierung → Modell schreibt systematisch zu kurz (S2/S3 oft −100–200).
Ursache: "bis zu X, nur so weit wie der Stoff trägt" → zwei Effekte vermischt:
  - Gewollter Stoff-Deckel (z. B. Wirtschaft 434/650 = korrekt, WP-Artikel zu dünn)
  - Ungewollte Vorsicht bei reichen Quellen (z. B. Hund S2 188/400, Dino S2 291/400)
Fix: WORTZIEL braucht Minimum-Boden: "Ziel: {min}–{max} Wörter. Wenn Stoff für {max} reicht →
  schreib bis dahin. Kürzer als {min} nur wenn Wikipedia-Stoff wirklich erschöpft."

**Wortbudget-Kalibrierung abgeschlossen (2026-06-11/12)**

33 Themen re-scored mit content_richness_v2 (Peer-Status/Coolness explizit ausgeschlossen).
100er-Robustheitsprobe (seed=42, 8 Anker) → Trennschärfe hält auf ungesehenen Titeln.
5-Dimensionen-Dekomposition (134 Themen) → dims_cache.json + wortbudget_dimensionen_138.xlsx.
MAE-Analyse: wc=0 optimal (kein Coverage-Signal nötig bei content_richness_v2).

### Finalisierte Formel (wc=0, noch NICHT in generate_grounded.py verdrahtet)
```
fasc_norm_S  = (flash_S − 1) / 9
importance_S = fasc_norm_S              ← wc=0 optimal

Klexikon-Abwesenheits-Deckel, NUR S2/S3, NUR wenn KlexW fehlt:
  importance_S = min(importance_S, 0.25 + 0.5·importance_S)
  (5 Themen: Pangolin, Seefahrer, Lego, Süßigkeiten, VW)

target_S = Wlo + importance_S · (Whi−Wlo)
  S1[50,250] / S2[80,400] / S3[100,650]
Rang = 1 + 4 · mean(imp_S1, imp_S2, imp_S3)
```

### Rang-Tabelle 33 (Pilot-Themen fett)
| # | Thema | f:S1/S2/S3 | **W1/W2/W3** |
|---|---|---|---|
| 1 | Dinosaurier | 10/10/9 | **250/400/650** |
| 2 | Vulkan | 7/10/10 | **217/400/650** |
| 3 | Indianer | 6/9/8 | **183/400/650** |
| 4 | Elefant | 9/8/6 | **250/400/650** |
| 5 | Hund | 10/8/6 | **250/400/650** |
| 9 | Fußball | 6/8/8 | **183/400/650** |
| 11 | Schmetterling | 8/7/5 | **217/347/467** |
| 18 | Pangolin | 3/6/7 | **117/293/467** |
| 24 | Düsseldorf | 1/2/3 | **217/400/650** |
| 28 | Kühlschrank | 2/4/5 | **83/240/375** |
| 29 | Wirtschaft (test) | — | **117/347/650** |
| 33 | Viereck | 2/2/2 | **117/187/283** |

---

## 🔴 Nächster Schritt (höchste Priorität)

**WORTZIEL-Instruktion in generate_grounded.py reparieren:**
Zeile ~664 in `build_grounded_user_message()` → Minimum-Boden ergänzen:
```
WORTZIEL: {wmin}–{wmax} Wörter. Wenn der Stoff für {wmax} reicht, schreib bis dahin.
Kürzer als {wmin} nur wenn der Wikipedia-Stoff wirklich erschöpft ist — nicht aufblähen.
```
Dann: WORTZIEL_TABLE durch dynamische imp_S-Berechnung aus importance_cache_33.json ersetzen.

---

## 🔴 Offene Punkte (nach Priorität)

1. **WORTZIEL-Fix** + **Formel verdrahten** (imp_S dynamisch, Abwesenheitsdeckel S2/S3)
2. **resolve_lemma in generate_grounded.py** einbauen (vor fetch_wikipedia_text, Z. 746)
3. **Pilotartikel reviewen** → pilot_output/*.md + pilot_wortzahlen.csv
4. **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
5. **3-flash-preview L3 Fix**: max_output_tokens explizit
6. Flutter-App testen: WfArticleListScreen mit R2-Artikeln
