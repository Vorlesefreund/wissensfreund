# Wissensfreund — STATUS
<!-- updated: 2026-06-16T10:52:00Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**run_batch.py: Batch-Orchestrator, Stage 1 vollständig (2026-06-16)** ← AKTUELL

### Was gebaut wurde

**scripts/run_batch.py** — neuer Batch-Orchestrator (KEIN synchroner Mini-Lauf):

Stage-Reihenfolge (Vision VOR Generierung):

**Stage 1 SOURCING — vollständig implementiert:**
- WP-Fetch + Lemma (sync) pro Thema
- Kompass-Batch (Gemini, gemini-3.5-flash, InlinedRequest)
- Companion-Fetch + Validierung (sync)
- Image-Download (sync, 0.5s-Sleep statt 10s, kein Gemini-Echtzeit-Call)
- Vision-Batch (Gemini, gemini-2.5-flash, Base64 inline, Chunking 500/Batch)
- Conservative Upgrade (confidence=niedrig + ab_stufe=1 → 2, lokal)
- Opus-Recheck (Anthropic Batch, claude-opus-4-8, nur sensibel + confidence=niedrig)
- Checkpoint-Save (stage1_checkpoint.json), Resume-fähig

**Stage 2 GENERIERUNG — Gerüst mit TODOs:**
- Gemini Batch + Context Cache (stable prefix)
- select_images_for_stufe + variable suffix je Stufe
- Post-Processing: Wortzahl-Guard + Box-Guard (synchron)

**Stage 3 LEKTORAT — Gerüst mit TODOs:**
- Anthropic Message Batches, 2 Pässe (source_passages + Nachschlag)
- cache_control: ephemeral auf System-Prompt

**Stage 4 TTS — Stub:** wartet auf tts_produce.py

**scripts/WISSEN_PIPELINE_PRODUKTION.md** — neu erstellt (Batch-Architektur-Doku)

### Dry-Run bestätigt

```
python scripts/run_batch.py --themen "Elefant" "Hund" "Dinosaurier" "Vulkan" "Tabak" --dry-run
→ Tabak nicht in catalog → 4 Themen
→ Stage 1: 4 Kompass-Requests, ~160 Vision-Requests, 0 sensibel (kein Opus)
→ Stage 2: 12 Requests (4 × 3), Context Cache geplant
→ Exit 0 ✅
```

Hinweis: Tabak nicht in catalog_full.json → wird übersprungen (nicht exclude, einfach fehlend).
Für echten Opus-Recheck-Test: sensibel=True Thema wie "Indianer" oder "Demokratie" nutzen.

---

**Opus-Recheck nur für unsichere Bilder sensibler Themen (~$50 statt ~$200, 2026-06-16)**

---

## Gerade in Arbeit

Nichts aktiv. Nächster Schritt: Stage 2 (Generierung) implementieren ODER Stage 1 echt für 5 Themen testen.

---

## Offen nach Priorität

### run_batch.py Stage 2 — GENERIERUNG (TODO)
Gemini Batch + Context Cache, select_images_for_stufe, Wortzahl/Box-Guard.
Importiert aus generate_grounded.py: try_create_gemini_cache, _split_grounded_user_message,
_trim_article_to_cap, _box_repair_pass.

### run_batch.py Stage 3 — LEKTORAT (TODO)
Anthropic Message Batches, 2 Pässe (source_passages + volle Companion-Texte).

### Baustein 3 — tts_produce.py (Produktions-TTS)
compose → tagging (gemini-2.5-flash-lite) → gemini-3.1-flash-tts-preview → WAV/MP3 → R2

### Baustein 4 — Quiz-Vertonung

### Offene Audio-Entscheidungen (Andreas)
1. Iapetus-Qualität im Audio-Review bestätigen (tts_audio_compare.html)
2. Feste Tag-Palette vs. freie Tags
3. Tagging-Modell: gemini-3.5-flash vs. gemini-2.5-flash-lite

### Sonstiges
- categories_backlog.json → categories-Array je Artikel
- Flutter WfArticleListScreen + 3-flash-preview L3 Fix

---

## Pipeline-Zustand (Stand 2026-06-16)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig, synchron |
| Batch-Orchestrator Stage 1 | run_batch.py | ✅ Stage 1 komplett |
| Batch-Orchestrator Stage 2-4 | run_batch.py | ⏳ Gerüst (TODOs) |
| Bild-Vision | image_vision_filter.py | ✅ lauffähig |
| TTS-Vorlesetext | tts_compose.py | ✅ lauffähig |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| R2-Upload | upload_articles.py | ✅ lauffähig |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet |
| Orchestrator Sync | (run_mini.py) | ❌ fehlt, durch run_batch.py ersetzt |

### Catalog (final)
catalog_full.json: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
eignung_verdicts.json: 738 Verdicts ✅
Ergiebigkeit: ergiebigkeit_scores.json, 134 Anker ✅
