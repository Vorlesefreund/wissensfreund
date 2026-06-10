# Wissensfreund — STATUS
<!-- updated: 2026-06-10T12:33:46Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Prompt-Caching aktiviert — Kosten-Hebel (2026-06-10)** ← AKTUELL

### A) Anthropic-Lektorat — Caching
- `scripts/lektorat_common.py`:
  - `build_lektorat_parts(article, sources_block) -> (sources_prefix, article_task)`: stabiler
    Quellblock (System + Primär + Companions) als ERSTER Block mit `cache_control: ephemeral`.
  - `run_lektorat_batch` auf `parts_by_id: dict[str, tuple[str,str]]` umgestellt.
    System-Prompt ebenfalls mit `cache_control: ephemeral`.
    Usage-Logging je Ergebnis: `tokens in=%d create=%d read=%d out=%d`.
- `scripts/generate_grounded.py`: Lektorat-Aufruf nutzt `build_lektorat_parts` statt `build_lektorat_prompt`.
- Catch-Test nach Umbau: **4/4** | K1–K4 stabil | K5/K6 borderline-FP (wie erwartet, pre-existing) ✓.

### B) Gemini-Generierung — Context Cache
- `scripts/gemini_client.py`: `cached_content: str | None = None` Param in `call_gemini`; usage_metadata-Log.
- `scripts/generate_grounded.py`:
  - `_split_grounded_user_message(job, ...) -> (stable_prefix, variable_suffix)`: trennt stabilen
    Quellblock (Artikeltexte) vom variablen Suffix (AGE_LEVEL + WORTZIEL).
  - `try_create_gemini_cache(client, model, system_prompt, stable_prefix) -> str | None`:
    erstellt Gemini Context Cache (TTL 1h), graceful Fallback bei Fehler.
  - Hauptschleife: `try_create_gemini_cache` einmal je Thema nach Phase 1 aufgerufen.
    `generate_one_level(gemini_cache=...)` — bei Cache-Hit: nur variable_suffix gesendet,
    stabiler Prefix aus Cache gelesen (~75 % Token-Einsparung erwartet). Fallback = voller Kontext.

### C) Vorgänger-Meilensteine (Stufe 2 + Catch-Test-Fix, 2026-06-10)
- Stufe-2-Prompt: BELEGT-BEDINGUNG, VERBUND-REGEL, Färbungs-Regel.
- Catch-Test-Fix: box.text-Bug, match_begriffe=["Schrift"], --compare-Flag, VERIFIER_DEFAULT=Sonnet.
- Smoke-Test Indianer L1–L3: L1 0A/2V/1E | L2 0A/1V/0E | L3 0A/4V/1E.

---

## 🔴 Nächster Schritt (Hoch)

**Caching-Verifikation** — Lauf mit `--skip-images` isoliert (keine API-Konkurrenz):
- Bestätigen: Anthropic cache_read_input_tokens > 0 ab 2. Lektorat-Call im Batch.
- Bestätigen: Gemini cached_content_token_count > 0 in Stufe 2+3 (wenn Cache verfügbar).
- Baseline-Vergleich: Kosten vor/nach (Timing + Token-Log).

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
