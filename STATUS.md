# Wissensfreund — STATUS
<!-- updated: 2026-06-11T14:06:35Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Wortbudget-Kalibrierung Dry-Run (2026-06-11)** ← AKTUELL

### TEIL 1 — wc-Kalibrierung (33 Themen)
fasc_norm=(flash−1)/9 | klex_norm=clamp((klex_w−180)/1180,0,1)
importance=(1−wc)·fasc_norm + wc·klex_norm | pred=round(1+4·imp,1) | MAE vs. Andreas (1–5)

| wc   | MAE₁₃ | MAE₂₀ | MAE₃₃       |
|------|-------|-------|-------------|
| 0.00 | 0.662 | 0.920 | 0.818       |
| 0.20 | 0.692 | 0.875 | **0.803** ← |
| 0.35 | 0.738 | 0.910 | 0.842       |
| 0.50 | 0.823 | 0.970 | 0.912       |
| 0.65 | 0.923 | 1.010 | 0.976       |

→ **wc=0.20 optimal** (kombiniert). Klexikon korrigiert Ausreißer: Eis Flash10→4.1≈Andreas4.0,
  Krankenschwester exakt 3.5. Klexikon schadet bei 13 Kalibrierthemen leicht (0.662→0.692).

### TEIL 2 — Wortziele je Stufe (wc=0.20, S1[50,250] S2[80,400] S3[100,650])
imp_S=0.80·fasc_S+0.20·cov_S | S1-cov=mini_norm | S2/S3-cov=klex_norm
vol_cap=Wlo+min(wp/1800,1)·(Whi−Wlo) | wort=round(min(target,vol_cap))

| Thema           |  S1 |  S2 |  S3 | Hinweis      |
|-----------------|-----|-----|-----|--------------|
| Lego            | 250 | 400 | 589 |              |
| Süßigkeiten     | 128 | 205 | 315 | vol_cap      |
| Eis             | 233 | 339 | 497 |              |
| Seefahrer       | 193 | 309 | 493 | vol_cap      |
| Pangolin        | 183 | 329 | 528 | fasc-fb      |
| Schiffe         | 185 | 306 | 439 |              |
| Hades           | 117 | 279 | 492 | S1 fasc-fb   |
| Jahreszeiten    | 166 | 260 | 359 |              |
| Schule          | 181 | 250 | 342 |              |
| Krankenschw.    | 139 | 279 | 491 | S1 fasc-fb   |
| Kinderrechte    | 118 | 171 | 355 |              |
| Pupille         |  94 | 165 | 296 | S1 fasc-fb   |
| Viereck         | 125 | 175 | 214 |              |
| Brennessel      | 117 | 142 | 207 | S1 fasc-fb   |
| Airbag          |  72 | 146 | 312 | S1 fasc-fb   |
| Düsseldorf      |  98 | 120 | 217 |              |
| VW              |  72 | 116 | 222 | fasc-fb alle |
| Zigaretten      |  50 | 145 | 309 | S1 fasc-fb   |
| Kühlschrank     |  94 | 135 | 145 |              |
| Fasten          |  77 | 124 | 225 |              |

fasc-fb = kein Mini/Klexikon → Fallback auf fasc | vol_cap = WP-Artikel zu kurz

### Architektur-Stand Wortbudget
- Faszination (Flash) dominant (80 %), Klexikon-Coverage kleiner Korrekturfaktor (20 %)
- WP-Volumen NUR als harter Deckel (vol_cap)
- Bänder linear: S1[50,250] / S2[80,400] / S3[100,650]

**Vorher (2026-06-10):** BKS-Guard ✓ | 503-Härtung Phase-2-sequenziell ✓ | Gemini-Cache+finally ✓

---

## 🔴 Nächster Schritt

**Formel verdrahten**: statische WORTZIEL_TABLE in `generate_grounded.py` (Z.86–96) ersetzen
durch dynamische imp_S-Berechnung (wc=0.20, fasc_S, klex_norm/mini_norm, vol_cap).
Vorher Lemma-Härtung: Plural/Listen/Doppelsinn absichern (Seefahrer=Liste→WP dünn).

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Formel verdrahten** (statische WORTZIEL_TABLE → dynamische imp_S-Berechnung, wc=0.20)
- **Lemma-Härtung**: Plural/Listen/Doppelsinn in generate_grounded.py / generate_articles.py
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit (Thinking frisst Budget)

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug (python scripts/ statt python root)
