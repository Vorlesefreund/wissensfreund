# Wissensfreund — STATUS
<!-- updated: 2026-06-10T05:23:48Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**v3.23 + test_v323 (2026-06-10)** ← AKTUELL
Prompt v3.23-Änderungen:
- WORTZIEL-Feld (Pipeline berechnet min–max aus Stufe × Appeal, injiziert explizit)
- Regionen-Ausgewogenheit history_person/Nordamerika (Reservate, Internate, Landraub)
- Companion-Cap gestaffelt: niedrig=4, mittel=5, hoch=6
Code-Änderungen generate_grounded.py:
- resolve_appeal(): Klexikon-Quartil → Job-Wert → Default "mittel"
- count_article_words(): Fließtext + Boxen ohne Quiz
- WORTZIEL im variablen Suffix der User-Message
- Wortzahl-Check + Retry wenn < Untergrenze; review_flag wenn Retry auch zu kurz
- Companion-Cap appealabhängig
Befund test_v323 (gemini-3.5-flash, Indianer, --skip-images):
- Appeal: high (klexikon-quartil) | Companions: Tipi, Wappenpfahl, Bison, Traumfänger, Inka
- L1: 200 Wörter (Ziel 150–250) | L2: 358 (Ziel 250–400) | L3: 613 (Ziel 350–650)
- Kein Retry nötig | method='gemini-3.5-flash/medium/v3.23'
- Review-HTML: articles/test_v323/_review.html (lokal)

**Robustness-Check + test_compass3b (2026-06-09)**
- FAILED_NO_COMPANIONS-Abbruch wenn Phase 1 keine Companions liefert
- Companions: Tipi, Wappenpfahl, Bison, Wigwam und Wickiup, Traumfänger | L1:24/L2:23/L3:36 Sätze

**Kompass-Pipeline + Lauf: Indianer L1/L2/L3 (2026-06-09)**
- Phase 1 auf freien Kompass umgestellt; Companion-Validierung + Redirect-Auflösung; Phase 1 einmalig pro Thema
- test_compass: Tipi, Wappenpfahl, Sitting Bull, Bison, Pueblo | L1: 23/L2: 28/L3: 45 Sätze
- test_compass3: Tipi, Wappenpfahl, Kolumbus, Bison, Maya | L1: 22/L2: 28/L3: 46 Sätze
- v3.22-Kerndefinition: [Kerndefinition aus der Einleitung — Pflicht] im Prompt ergänzt

**v3.22-Kerndefinition + test_compass2 (2026-06-09)**
- Prompt v3.22: [Kerndefinition aus der Einleitung — Pflicht] + Kompass-Spannweite
- Kompass-Vorschlag: Tipi, Totempfahl, Federhaube, Maya, Inka
- Aufgelöst: Totempfahl → Wappenpfahl; Federhaube: nur 154 Zeichen (Stub-Artikel)
- Final: Tipi, Wappenpfahl, Federhaube, Maya, **Inka** — meso-/südamerikanisch vertreten
- method='gemini-3.5-flash/medium/v3.22' | L1: 25 Sätze | L2: 25 | L3: 43
- Review-HTML: articles/test_compass2/_review.html (lokal)

**v3.21-Lebendigkeits-Paket + test_v321 (2026-06-09):**
- Prompt v3.21, 3 Artikel Indianer L1/L2/L3 | companions=[] (Phase-1-503 wg. Modell-Last)

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung v3.23-Artikel**: articles/test_v323/_review.html
- WORTZIEL erstmals explizit (L1:200/L2:358/L3:613 Wörter — alle im Korridor)
- Regionen-Ausgewogenheit Nordamerika prüfen (Reservate/Internate in L3?)
- ⛔ KEIN Lektorat, KEIN Upload vor Sichtung

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_v323 vs. test_compass3b — Qualitätsgewinn durch explizites WORTZIEL?
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1 (test_grounded)
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## Pipeline-Architektur (Referenz)

| Skript | Rolle | Status |
|---|---|---|
| `prepare_articles.py` | Batch-Vorbereitung (Job-JSONs) | Produktion |
| `generate_articles.py` | Artikel-Generierung (Claude/Gemini) | Produktion |
| `upload_articles.py` | Index + R2-Upload | Produktion |
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + v3.21-Prompt | Aktiv (Entwicklung) |
| `batch_run.py` | POC: Gemini Batch API (5 Testartikel) | Veraltet, nicht Produktionspfad |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (Montag 03:00 UTC)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
