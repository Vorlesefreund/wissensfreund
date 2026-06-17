# Wissensfreund — STATUS
<!-- updated: 2026-06-17T06:15:11Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Schema-Konsistenz Stage 2 (2026-06-17)** ← AKTUELL

### source_passages kanonisch ins Schema (Prompt-Widerspruch behoben)
- `_gen2_variable_suffix()` sendete eigene Wrapper-Anweisung `{article, source_passages}` die dem
  `output_format`-Block im System-Prompt widersprach. ThinkingLevel.MEDIUM folgte dem System-Prompt,
  kein Thinking der User-Message → instabil (A=0 SP, B=18 SP im ersten A/B-Test).
- Fix: `source_passages` als kanonisches Feld ins Schema von `v3.23_production.md` aufgenommen.
  `_gen2_variable_suffix()` auf `_variable_suffix()` vereinfacht (kein Wrapper mehr).
- Verifikation (Elefant S2, synchron, 2026-06-17): A-MEDIUM sp=12 ✅ B-NOTHINK sp=? (Modell-Output
  hatte eingebettetes Newline-Steuerzeichen im JSON → Parse-Fehler, nicht Code-Problem).
  A-MEDIUM beweist: Widerspruch behoben.

### A/B-Test ThinkingLevel.MEDIUM vs. kein Thinking (korrekt ausgewertet)
| | A — MEDIUM | B — kein Thinking |
|---|---|---|
| Dauer | 75s | 23s (3.2× schneller) |
| Wörter Fließtext | 307 | ~290 |
| Sections | 4 | 4 |
| Boxes | 2 (wow + stimmt_das) | 2 (wow + stimmt_das) |
| source_passages | 12 ✅ | 18 ✅ (1. Lauf) / Parse-Fehler (2. Lauf) |
- Beide Varianten folgen BOX_PLAN korrekt, produzieren vollständige Artikel.
- Frühere "0 Boxes"-Meldung war Parse-Script-Bug (art['boxes'] statt sections[].boxes[]).
- temp/_read_ab.py korrigiert: section_role/heading, boxes aus sections[].boxes[] aggregiert.

### Quiz + stimmt_das Box: Schema-Mismatch App↔Prompt (OFFEN, noch nicht gefixt)
Prompt/Modell generieren — App-Parser erwartet:
- `quiz.questions[x].text` → App liest `j['question']` → Quizfragen LEER in App ❌
- `boxes[x].reveal_text` → App liest `j['explanation']` → stimmt_das-Auflösung LEER ❌
- `boxes[x].reveal_mode: "auto"` (String) → App: `j['reveal_mode'] == true` → immer false ❌
- tts_compose.py liest korrekt `reveal_text` → ALIGNED mit Prompt.
ENTSCHEIDUNG OFFEN: Prompt anpassen (`text`→`question`, `reveal_text`→`explanation`) ODER
App-Dart anpassen (wf_article.dart) — tts_compose.py würde bei Prompt-Änderung brechen.
Empfehlung: App-Dart fixen (ein File, tts_compose.py bleibt unangetastet).

**Mistral-Modellvergleich Elefant S2 (2026-06-16)**

`temp/mistral_test_elefant_s2.py` — synchroner Vergleichstest vs. Gemini-Produktionspfad.
Gleicher System-Prompt v3.23b, gleiche Quelltexte (Stage-1-Checkpoint), gleicher User-Message-Aufbau.

### mistral-large-latest (mistral-large-3, $2/$6 pro 1M)
- finish_reason: stop ✅, Dauer 145s, Input=70.098 / Output=7.296 Tokens, Kosten $0.184
- Wortzahl: **574 / Ziel 280–400** (43% über Deckel) — Prompt-Tuning fehlt für Mistral
- Schema-Abweichungen (3, alle fixbar per Post-Processing):
  - `box.type` statt `box.box_type` (App-Parser bricht)
  - `quiz` als `{"questions":[...]}` statt flaches Array
  - Box-Key `warnung` statt `warn`
- Inhalt: sehr gut — Kindwelt-Brücken (Kühlschrank, Wasserflaschen, Ventilator), gute stimmt_das-Box (Mäuse-Mythos), 25 source_passages mit echten WP-Zitaten, S2-Register flüssig
- Artikel gespeichert: `articles/test_modelcompare2/mistral-large-3_elefant_s2.json`

### mistral-medium-latest (mistral-medium-3.5, $0.40/$2 pro 1M) — 3-Topic-Test (2026-06-16)
- Script: `temp/mistral_medium_3topics_s2.py` — Elefant, Vulkan, Indianer jeweils S2
- **ALLE 3 TOPICS: 429 Rate-Limit** — 5 Retries × 15 Min je Topic, alle erschöpft
- Rate-Limit persistiert 2h15min+ nach Large-Call (21:31–23:41+) → KEIN Stunden-Limit
- **Diagnose: Tages- oder Monats-Kontingent des API-Keys erschöpft** (Large-Call 77K Token)
- Timings: Elefant V1–V5 (21:31–22:31), Vulkan V1–V5 (22:36–23:36), Indianer V1+ (23:41+)
- Indianer-Wortziel-Quelle: ergiebigkeit (280–400), primary_text 107K Zeichen, 0 Bilder, 0 Companions
- **ECHTE URSACHE (17.06. morgens ermittelt):** Key-Tier hat **25.000 Tokens/Minute Limit**
  - System-Prompt: ~9K Tokens + kleinste User-Message (Vulkan): ~25K Tokens = ~34K gesamt
  - Jede Produktions-Message überschreitet das Minuten-Limit → sofort 429, unabhängig von Wartezeit
  - Bestätigt: kleine Test-Message (21 Tokens) → 200 OK ✅ | Vulkan 34K Tokens → sofort 429 ❌
  - `mistral-large-latest` hat offenbar separates/höheres Limit auf diesem Key-Tier
- **Response-Header:** `x-ratelimit-limit-tokens-minute: 25000` / `x-ratelimit-limit-req-minute: 50`
- **Schlussfolgerung:** mistral-medium-latest auf diesem Key-Tier für Produktions-Messages NICHT nutzbar
- **Optionen:** (a) Key-Tier upgraden auf ≥100K TPM, (b) Primary-only (keine Companions) testen ~14K Token

### gemini-3.5-flash
- Weiterhin 503 UNAVAILABLE — Situation unverändert

### Erkenntnisse Mistral-Integration
- `mistralai` SDK v2.4.11 installiert (from mistralai.client.sdk import Mistral)
- JSON-Mode: `ResponseFormat(type="json_object")` — kein strukturiertes Schema wie Gemini
- timeout_ms=360.000 nötig (Default 60s reicht nicht für 70K Input-Token)
- Schema-Keys weichen vom WF-Standard ab → Post-Processing-Schicht nötig bei Produktion
- Wortzahl-Overshoot deutet auf Prompt-Tuning-Bedarf hin (Gemini-optimierter Prompt)
- cost_tracker um Mistral-Preise erweitert (mistral-large-3, mistral-medium-3.5)

**gemini_client.py: Robustes Retry (2026-06-16)**

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

### ERLEDIGT (2026-06-17)
- Synchroner A/B-Test erfolgreich (Elefant S2): beide Varianten STOP, valider Output.
- **BESTÄTIGT:** Batch-Schicht-Bug (leere Responses) ≠ Generierungslogik-Bug.
- source_passages-Instabilität durch Prompt-Widerspruch erklärt und behoben.
- A/B-Qualitätsvergleich: MEDIUM reichhaltigerer Planungsblock, ähnliche Artikelqualität.
  Thinking-Entscheidung (MEDIUM beibehalten) bleibt Produktionskonfiguration.

### BEKANNTE STAGE-2-BEFUNDE (bereits gefixt)
- Truncation bei max_output_tokens=8192 → auf 32768 erhöht (Thinking-Tokens zählen ins Budget)
- ThinkingLevel.MEDIUM ist Pflicht (Qualität), darf nicht zur Bug-Umgehung abgeschaltet werden —
  nach irrtümlicher Deaktivierung wieder aktiviert
- Context-Cache (cached_content) funktioniert NICHT in Gemini-Batch-InlinedRequests →
  im Batch deaktiviert (Mehrkosten ~$70 Vollkatalog; Batch-Rabatt -50% bleibt Haupthebel)

### Mistral-Test-Ergebnis
Large 3 (Elefant S2): qualitativ stark, Schema-Abweichungen, 43% Wortzahl-Overshoot.
Medium 3.5 (3 Topics): alle 429 — Key-Tier-Limit 25K Tokens/min, Produktions-Messages 34–70K → nicht nutzbar.
→ Für Medium: Key-Tier upgraden (≥100K TPM) oder Primary-only-Test (14K Token).
→ Für Produktion (Large): Prompt-Tuning + Post-Processing-Schicht für Schema-Keys nötig.

---

## Gerade in Arbeit

**Quiz/stimmt_das App-Dart-Fix** — Entscheidung noch offen (s. Schema-Mismatch oben).
Empfehlung: wf_article.dart anpassen (j['question']→j['text'], j['explanation']→j['reveal_text'],
reveal_mode-Vergleich auf 'auto'-String), tts_compose.py bleibt unverändert.

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
