# Wissensfreund — STATUS
<!-- updated: 2026-06-10T13:44:06Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Phase-2-Parallelisierung + Lektorat-Sync + Cache-Verifikation (2026-06-10)** ← AKTUELL

### Phase 2 parallel (concurrent.futures)
- `generate_grounded.py`: `ThreadPoolExecutor(max_workers=len(topic_jobs))` — alle Stufen gleichzeitig.
  Reihenfolge nach age_level sortiert vor Lektorat. Wandzeit L1-L3: ~96s (war ~131s sequenziell).

### Lektorat Sync als Default (--lektorat-batch für Batch-API)
- `lektorat_common.py`: `run_lektorat_sync` — sequenziell, direkte API-Calls (kein Polling).
  Sequenziell BEWUSST: L1 schreibt Anthropic-KV-Cache (create=60765), L2+L3 lesen ihn (read=60765).
- `generate_grounded.py`: Default = `run_lektorat_sync`; `--lektorat-batch` → `run_lektorat_batch`.
  Lektorat-Wandzeit: ~212s sequenziell (Batch war ~134s, aber dort kein garantierter Cache-Hit).

### Gemini-Cache Fix: system_instruction-Konflikt
- `gemini_client.py`: Bei `cached_content` wird `system_instruction` NICHT in GenerateContentConfig
  gesetzt (API 400 sonst — system_instruction muss im Cache stehen, nicht doppelt im Request).

### Cache-Verifikation (Lauf Indianer L1-L3, --skip-images)
- Gemini: `prompt=54905, cached=54858` → **99,9 % Cache-Hit** | nur 128 Zeichen Suffix gesendet.
- Anthropic: L1 `create=60765 read=0` → L2 `create=0 read=60765` → L3 `create=0 read=60765` ✓.

### Vorgänger: Prompt-Caching Grundaufbau + Catch-Test-Fix (2026-06-10)
- Caching: build_lektorat_parts, run_lektorat_batch mit cache_control, _split_grounded_user_message,
  try_create_gemini_cache, generate_one_level(gemini_cache=...). Catch-Test: 4/4 ✓.
- Stufe-2-Prompt: BELEGT-BEDINGUNG, VERBUND-REGEL. Catch-Test-Fix: box.text-Bug, ["Schrift"].

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle

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
