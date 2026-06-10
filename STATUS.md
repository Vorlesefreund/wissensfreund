# Wissensfreund — STATUS
<!-- updated: 2026-06-10T12:06:28Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Gegroundetes Lektorat Stufe 2 — Korrektur-Schicht + Catch-Test-Fix (2026-06-10)** ← AKTUELL

### Stufe 2 — Korrektur-Schicht
- `scripts/lektorat_common.py`: Stufe-2-Prompt mit Färbungs-Regel, BELEGT-BEDINGUNG (kein Implizit-Beleg),
  VERBUND-REGEL (zusammengesetzte Aussagen: ALLE Teile müssen einzeln direkt belegt sein).
  `build_pruefbericht` + `annotate_article_lektorat` mit Status {auto_angewandt/vorschlag_offen/eskaliert}.
  `_apply_auto_correction` (Jaccard ≥ 0.4), `_normalize_for_check` (NFKC).
- `scripts/generate_grounded.py`: `annotate_article_lektorat(article, verdicts, primary_text)`.
  Log: `angewandt:%d vorschlag:%d eskaliert:%d`. Naming-Fix: `effective_id = article_id` (deterministisch).
- `scripts/render_review_html.py`: Stufe-2-Prüfbericht-Panel (Original→Neu, status-basiert).

Stufe-2-Smoke-Test Indianer L1–L3 (gemini-3.5-flash, Batch msgbatch_01YQS7tpyxobGq23gQm9enYb):
- L1: 27 Aussagen | 0A/2V/1E | review_flag=True
- L2: 22 Aussagen | 0A/1V/0E | review_flag=True
- L3: 28 Aussagen | 0A/4V/1E | review_flag=True

### Catch-Test-Fix
- `scripts/run_lektorat_catchtest.py`:
  - Bug-Fix: `article_to_text` las `box.text` NICHT (nur `box.sentences`) → Slip L2 wurde nie geprüft.
  - Goldset L2 `match_begriffe`: ["Maya","Schrift"] → ["Schrift"] (vermeidet falschen Match auf "Maya oder Inka").
  - `--compare`-Flag: Standard-Lauf = nur Sonnet. Haiku/Gemini nur mit `--compare`.
  - VERIFIER_DEFAULT = [Sonnet] / VERIFIER_COMPARE = [Sonnet, Haiku, Gemini].
- Catch-Test Sonnet: **4/4** | FP 2/6 (K5 Grenzfall-wording, K6 Beringia-Grenzfall).
  Nur api.anthropic.com-Calls, null googleapis, kein Haiku im Standard-Lauf ✓.
- Mock/Stub-Befund bestätigt: Kein Mock/Stub/Offline-Fallback. Nur zwei bedingte Pfade:
  - Fehlt ANTHROPIC_API_KEY: Lektorat übersprungen (kein Fake-Output), generate_grounded.py:900–902.
  - Fehlt GEMINI_API_KEY: sys.exit(1), generate_grounded.py:895–897.

---

## 🔴 Nächster Schritt (Hoch)

**Laufzeit-Messung generate_grounded.py** (nach Abschluss aller laufenden Jobs, allein):
- Phase 1 (Companion-Vorschlag, Wikipedia-Fetches), Phase 2 (Generierung L1-L3), Lektorat L1-L3.
- Wandzeit je Phase, Batch-API vs. synchron, Prompt-Cache-Hits, Thinking-Anteil.
- User-Anforderung: isoliert laufen lassen (keine API-Konkurrenz).

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit setzen (Thinking frisst Budget)
- **Sichtung** test_v323 — WORTZIEL-Erstlauf
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug (python scripts/ statt python root)

---

## Pipeline-Architektur (Referenz)

| Skript | Rolle | Status |
|---|---|---|
| `prepare_articles.py` | Batch-Vorbereitung (Job-JSONs) | Produktion |
| `generate_articles.py` | Artikel-Generierung (Claude/Gemini) | Produktion |
| `upload_articles.py` | Index + R2-Upload | Produktion |
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + Lektorat | Aktiv (Entwicklung) |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (manuell, kein Schedule)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
