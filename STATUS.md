# Wissensfreund — STATUS
<!-- updated: 2026-06-16T08:39:10Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Baustein 2: catalog-Connector + cost_tracker vollständig verdrahtet (2026-06-16)** ← AKTUELL

### Was gebaut wurde

**generate_grounded.py** — Neue Flags + Catalog-Connector:
- `--catalog Vulkan Biene ...` → Themen aus catalog_full.json (dynamisch)
- `--catalog-rank N` → Top-N nach production_rank
- `--stufen 1 2 3` → welche Stufen generieren (default: alle)
- `--run-id minitest` → cost_tracker run-id (default: Zeitstempel)
- `--dry-run` → zeigt Jobs + Eignungs-Gate, kein API-Call
- `_build_catalog_jobs()` + `_load_catalog_rank_jobs()` aus catalog_full.json
- Dry-Run getestet: `Vulkan` → 3 Jobs, `Beschneidung` → nur S3 (age_floor korrekt)

**cost_tracker.py** — Komplett verdrahtet an allen 6 KI-Stellen:
- `kompass`: select_companions_raw() usage_metadata
- `article_gen`: generate_one_level() nach call_gemini() (Erst + Retry)
- `trim`: _trim_article_to_cap() → gemini_client._last_usage
- `box_repair`: _box_repair_pass() → gemini_client._last_usage
- `vision`: analyze_with_vision() → usage_metadata je Bild
- `lektorat`: run_lektorat_sync() → usage_by_id je Artikel-ID

**gemini_client.py**: `global _last_usage` korrekt deklariert (SyntaxError behoben)

**image_vision_filter.py**: `analyze_with_vision()` gibt `(dict|None, usage_dict)` zurück

**lektorat_common.py**: `run_lektorat_sync()` gibt `(results, usage_by_id)` zurück

---

**Baustein 1: cost_tracker.py v2 (TTS-Preis, 2026-06-16)**
- TTS: $1.00/1M Input, $20.00/1M Audio-Tok, 25 Tok/Sek (ai.google.dev, Jun 2026)
- Selbsttest 180s: $0.0906 ✅
- Statische Projektion: 4346×3×180s = $1173 TTS-Output

---

## Gerade in Arbeit

Nichts aktiv.

---

## Offen nach Priorität

### Baustein 3 — tts_produce.py (Produktions-TTS)
compose → tagging (gemini-2.5-flash-lite) → gemini-3.1-flash-tts-preview → WAV/MP3 → R2

### Baustein 4 — Quiz-Vertonung
5–6 TTS-Schnipsel je Frage (Frage / A/B/C / Feedback richtig / Feedback falsch+Lösung / Erfolgsmeldung)

### Baustein 5 — Mini-Orchestrator (run_mini.py)
5 Themen × 3 Stufen end-to-end: Artikel + Lektorat + Bilder + TTS + R2

### Offene Audio-Entscheidungen (Andreas)
1. Iapetus-Qualität im Audio-Review bestätigen (tts_audio_compare.html)
2. Feste Tag-Palette vs. freie Tags — was klingt besser?
3. Tagging-Modell: gemini-3.5-flash (503-anfällig) vs. gemini-2.5-flash-lite (stabil)

### Sonstiges
- categories_backlog.json → categories-Array je Artikel (spätere Phase)
- Flutter WfArticleListScreen + 3-flash-preview L3 Fix

---

## Pipeline-Zustand (Stand 2026-06-16)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig, gemini-3.5-flash |
| Bild-Vision | image_vision_filter.py | ✅ lauffähig, gemini-2.5-flash |
| TTS-Vorlesetext | tts_compose.py | ✅ lauffähig |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| R2-Upload | upload_articles.py | ✅ lauffähig |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet (Baustein 1+2) |
| Orchestrator | run_mini.py | ❌ fehlt |

### Catalog (final)
catalog_full.json: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
eignung_verdicts.json: 738 Verdicts (exclude/age_floor/framing_note) ✅
Ergiebigkeit: ergiebigkeit_scores.json, 134 Anker, Wortziel-Kurve kalibriert ✅
