# Wissensfreund — STATUS
<!-- updated: 2026-06-16T17:32:46Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**gemini_client.py: Robustes Retry (2026-06-16)** ← AKTUELL

Exponentielles Backoff + Jitter für alle synchronen Gemini-Calls:
- 503 UNAVAILABLE / 429 RESOURCE_EXHAUSTED → 5 Versuche, Wartezeiten 10/20/40/80/160s + Jitter 0-5s
- 400 Bad Request / 404 Not Found → sofort raise, KEIN Retry
- Logging je Retry: "503/429 bei [call_name] modell, Versuch N/5, warte Xs"
- Finaler Fehler enthält Modellname + Versuchsanzahl + letzten Exception-Text
- Neuer optionaler Parameter `call_name=""` für Kontext im Log
- 14 Unit-Tests (temp/_test_retry.py), alle grün ✅
  - 6× _is_retriable_error (503/429/quota/rate → True; 400/404 → False)
  - 4× Retry-Verhalten (5× fail → raise; 3. Versuch OK; 429 auch retried; Backoff-Zeiten exakt)
  - 2× No-Retry (400, 404 → 0 sleep-Calls, 1 gen-Call)
  - 2× Fehlermeldungsqualität (Modell + Versuche im Text)

Hintergrund: gemini-3.5-flash liefert persistent 503 (neues GA-Modell, serverseitige
Überlastung, betrifft alle Nutzer). Stage-2-Batch ebenfalls blockiert (leere Responses /
extreme Latenz). Stage-2-Diagnose offen (siehe unten).

---

**Stage 2 Generierung + Opus-Cap-Fix + custom_id-Bug (2026-06-16)**

### Stage 2 implementiert (run_batch.py)
- Gemini Context Cache je Thema (stable prefix via _split_grounded_user_message)
- 3 InlinedRequests je Thema (Stufe 1/2/3), cache=NEIN (forced fallback, s.u.)
- Variable Suffix (_gen2_variable_suffix): AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL +
  source_passages-Wrapper (Ausgabe als {article, source_passages})
- Post-Processing: JSON-Parse (Wrapper-first, Fallback plain), Wortzahl-Guard (2 Trim-Pässe),
  Box-Guard, validate_article, _set_is_hero, source_passages eingebettet, cost_tracker

**PRODUKTIONSKONFIGURATION Stage 2 (fix, nicht verhandelbar):**
Modell: gemini-3.5-flash + ThinkingLevel.MEDIUM + max_output_tokens=32768.
Thinking ist Pflicht für Artikelqualität — darf nicht zur Bug-Umgehung abgeschaltet werden.

### Stage-2-Diagnose-Status (2026-06-16)
- Elefant Durchstich Stage 1: ✅ (28 Bilder)
- Stage 2 Batch (no-cache): nach 1,5h abgebrochen — Gemini-3.5-flash überlastet
- Stage 2 Sync-Test: 5× 503 UNAVAILABLE — Modell für Sync-Calls nicht erreichbar
- URSACHE: gemini-3.5-flash neu GA, serverseitige Kapazitätsengpässe
- TODO: Sync-Test wiederholen sobald Modell stabil (Stunden bis Tage)

### Opus-Recheck: OPUS_CAP=18 + Sicherheitsgarantie (run_batch.py)
- `OPUS_CAP = max(APPEAL_TARGET.values()) + 3 = 18`
- Sensible Themen: `data["images"] = accepted[:OPUS_CAP]` → Stage 2 nur aus Opus-geprüftem Pool
- Nicht-sensibel: alle akzeptierten; grenzfall-Bilder (max 18) → Opus
- Spartacus-Verifikation: 10 Bilder → Opus ✅, custom_id-Bug gefixt ✅

### custom_id-Bug gefixt
Anthropic-Batch erfordert `^[a-zA-Z0-9_-]{1,64}$`.
Fix: `re.sub(r"[^a-zA-Z0-9_-]", "_", filename)[:41]`, Key max 63 Zeichen.

---

## Gemini Stage-2 — offener Diagnoseschritt

### ERLEDIGT
- **Robustes Retry (gemini_client.py):** 5 Versuche, Backoff 10/20/40/80/160s + Jitter 0-5s,
  400/404 ohne Retry, klare Fehlermeldung mit Modell + Versuchsanzahl. 14 Tests grün.

### OFFEN — wartet auf erreichbares gemini-3.5-flash
Aktuell: 503 UNAVAILABLE (serverseitige Überlastung, neues GA-Modell, recherchiert bestätigt —
nicht unser Code, betrifft alle Nutzer).

- **Synchroner Diagnose-Einzeltest Elefant S2** (temp/_sync_test_s2.py, bereit):
  Rohe Response zeigen: finish_reason, candidates leer/gefüllt, usage_metadata
  (prompt_tokens / candidates_tokens / thoughts_tokens).
  Ziel: "leere Batch-Antwort"-Problem isolieren — generiert das Modell selbst leer
  (dann Prompt/Schema/Logik-Bug) oder liegt der Fehler nur in der Batch-Schicht?
- **Bestes Zeitfenster:** 2–7 Uhr Pazifik = ca. 11–16 Uhr MESZ (503-Rate dann <5%)

### BEKANNTE STAGE-2-BEFUNDE (bereits gefixt)
- Truncation bei max_output_tokens=8192 → auf 32768 erhöht (Thinking-Tokens zählen ins Budget)
- ThinkingLevel.MEDIUM ist Pflicht (Qualität), darf nicht zur Bug-Umgehung abgeschaltet werden —
  nach irrtümlicher Deaktivierung wieder aktiviert
- Context-Cache (cached_content) funktioniert NICHT in Gemini-Batch-InlinedRequests →
  im Batch deaktiviert (Mehrkosten ~$70 Vollkatalog; Batch-Rabatt -50% bleibt Haupthebel)

### PARALLEL LÄUFT
Mistral-Alternativtest (Large 3 + Medium 3.5) in separatem Chat — Ergebnis fließt in
die Modellentscheidung ein.

---

## Gerade in Arbeit

**Stage-2-Diagnose ausstehend** — gemini-3.5-flash 503-Situation abwarten.
Sync-Test (temp/_sync_test_s2.py) bereit, sobald Modell erreichbar.

---

## Batch-Härtung VOR Großlauf (Pflicht, nicht Mini-Lauf)

### 1. Batch-ID persistieren (`pending_batches.json`)
Nach JEDEM `client.batches.create()` sofort in `out_dir/pending_batches.json` schreiben.

### 2. Entkoppeltes Submit → Poll → Collect (`--resume`-Flag)
`run_batch.py --resume` liest `pending_batches.json`, setzt Pipeline fort ohne Neueinreichen.

### 3. Netzwerk-Retry beim Poll
3 Retries mit Backoff (5s / 15s / 60s) um `client.batches.get()`.

### 4. Zwischen-Checkpoint in Stage 1
`stage1_mid_checkpoint.json` nach WP-Fetch + Kompass + Downloads (vor Vision-Submit).

### 5. CACHE-TTL vs. BATCH-LATENZ (Großlauf-kritisch)
Cache-TTL > Batch-Latenz; aktuell cache_name=None (forced) im Stage-2-Batch.
Vor Großlauf: (a) TTL-Maximum, (b) Cache komplett weglassen, oder (c) Implicit Caching.

---

## Offen nach Priorität

### Stage-2-Diagnose abschließen (nächstes Ziel)
Sync-Test mit gemini-3.5-flash sobald Modell stabil. Befund: Batch-Schicht-Bug vs.
Generierungslogik-Bug.

### run_batch.py Stage 3 — LEKTORAT
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
| Batch-Orchestrator Stage 2 | run_batch.py | ⏳ implementiert, Diagnose offen |
| Batch-Orchestrator Stage 3-4 | run_batch.py | ⏳ Gerüst (TODOs) |
| Gemini-Retry | gemini_client.py | ✅ 503/429 Backoff + Jitter, 14 Tests |
| Bild-Vision | image_vision_filter.py | ✅ lauffähig |
| TTS-Vorlesetext | tts_compose.py | ✅ lauffähig |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| R2-Upload | upload_articles.py | ✅ lauffähig |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet |

### Catalog (final)
catalog_full.json: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
eignung_verdicts.json: 738 Verdicts ✅
Ergiebigkeit: ergiebigkeit_scores.json, 134 Anker ✅
