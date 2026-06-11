# Wissensfreund — STATUS
<!-- updated: 2026-06-11T19:25:52Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Wortbudget-Design finalisiert + Lemma-Härtung (2026-06-11)** ← AKTUELL

### TEIL 1 — Wortbudget-Kalibrierung (Ergebnis aus 33 Themen)
wc=0.20 optimal | fasc_norm=(flash−1)/9 | klex_norm=clamp((klex_w−180)/1180,0,1)

| wc   | MAE₁₃ | MAE₂₀ | MAE₃₃       |
|------|-------|-------|-------------|
| 0.00 | 0.662 | 0.920 | 0.818       |
| 0.20 | 0.692 | 0.875 | **0.803** ← |
| 0.35 | 0.738 | 0.910 | 0.842       |

### TEIL 2 — Finalisiertes Wortbudget-Design (noch NICHT verdrahtet)

**Formel:**
```
importance_S = 0.80 · fasc_S + 0.20 · cov_S
  S1-cov  = mini_norm   (Mini-Klexikon-Länge, normiert)
  S2/S3-cov = klex_norm (Klexikon-Länge, normiert)
  fehlt cov → nur fasc_S (reweight auf 1.0, kein 0-Fallback)
```

**Klexikon-Abwesenheits-Deckel (NUR S2/S3, NUR bei echter Abwesenheit):**
```
score_gedeckelt = min(score, 0.5·score + 1.5)
  → 5→4.0, 4→3.5, 3→3.0 (ab 3 unverändert)
```

**S1-Deckel via Mini-Klexikon: NICHT anwenden**
→ Mini-Klexikon hat nur 1.512 Artikel (Schwellenwert: >4.000) — siehe Diagnose unten
→ S1 bleibt beim weichen Coverage-Signal (mini_norm, wo vorhanden)

**Wortziel:** `target_S = Wlo + importance_S · (Whi − Wlo)` | **KEIN vol_cap**
Bänder: S1[50,250] / S2[80,400] / S3[100,650]

Material-Realität bei GENERIERUNG: aufs Ziel zuschreiben, kürzer wenn Quellen dünn.
**PADDING VERBOTEN** (hart im Generator-Prompt). Optional: QA-Flag "Gesamt-Quelle dünn".

### TEIL 3 — Lemma-Härtung (2026-06-11, fertig)

`resolve_lemma(session, query)` in `generate_articles.py` implementiert (nach `_clean_wikipedia_text`).
Exportiert — direkt von anderen Skripten importierbar.

**Probe-Ergebnis** (6 Fälle, `scripts/_lemma_probe.py`):

| Thema     | Aufgelöst             | Vol      | Quelle   | Flags                       |
|-----------|-----------------------|----------|----------|-----------------------------|
| Schiffe   | Schiff                |  19.936  | search   | DOPPELBEDEUTUNG (Hatnote)   |
| Seefahrer | Liste von Seefahrern  |  11.010  | redirect | LISTENARTIKEL ✓             |
| Eis       | Eis                   |  66.119  | direct   | DOPPELBEDEUTUNG ✓           |
| Elefant   | Elefanten             | 218.797  | redirect | DOPPELBEDEUTUNG (BKS-Panel) |
| Vulkan    | Vulkan                |  29.013  | direct   | DOPPELBEDEUTUNG (BKS exist) |
| Hund      | Haushund              | 139.249  | redirect | DOPPELBEDEUTUNG (BKS exist) |

Hinweise:
- Schiffe: "Schiffe" hat keinen WP-Redirect → Suche findet "Schiff" korrekt
- Elefant: "Elefant (Begriffsklärung)" existiert (Wehrmacht-Panzer) → technisch korrekt
- Vulkan/Hund: BKS-Schwesterseiten existieren → korrekt; in Kinderkontext ggf. ignorierbar

### TEIL 4 — Diagnose Klexikon / Mini-Klexikon (2026-06-11, read-only)

**Klexikon (5.696 Artikel):**
- Süßigkeiten: NICHT vorhanden → nächste: Schokolade ✓, Zucker ✓, Karamell ✓, Kaugummi ✓
- Seefahrer: NICHT vorhanden → nächste: Seemann ✓, Matrose ✓

**Mini-Klexikon (miniklexikon.zum.de): 1.512 Inhaltsseiten** (vs. Klexikon 5.696)
- Süßigkeiten: NICHT vorhanden → nächste: Schokolade ✓
- Seefahrer: NICHT vorhanden → kein Seemann/Matrose im S-Bereich sichtbar
- Schiff: vorhanden ✓ (Schiffe: nicht vorhanden)

**Entscheidung S1-Deckel:** NICHT anwenden — 1.512 << 4.000 Schwelle.

**Vorher (2026-06-11):** Wortbudget-Kalibrierung + BKS-Guard + 503-Härtung ✓

---

## 🔴 Nächster Schritt

**Formel verdrahten**: statische WORTZIEL_TABLE in `generate_grounded.py` (Z.86–96) ersetzen
durch dynamische imp_S-Berechnung (wc=0.20, fasc_S, klex_norm/mini_norm, Klexikon-Abwesenheitsdeckel).
Vorher: `resolve_lemma` in Pipeline-Call integrieren (vor `fetch_wikipedia_text`).

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Formel verdrahten** (WORTZIEL_TABLE → dynamische imp_S, wc=0.20, Abwesenheitsdeckel S2/S3)
- **resolve_lemma in Pipeline**: vor jedem `fetch_wikipedia_text`-Aufruf in `generate_grounded.py` einbauen
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit (Thinking frisst Budget)

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug (python scripts/ statt python root)
