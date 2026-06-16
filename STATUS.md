# Wissensfreund — STATUS
<!-- updated: 2026-06-16T14:28:09Z -->
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
Mini-Lauf final: Elefant, Hund, Dinosaurier, Vulkan, Spartacus, Zweiter Weltkrieg (6 Themen).

---

**Bild-Tier-Architektur final festgelegt (2026-06-16)**

Server (R2): 300px / 800px / 1600px — immer alle drei produziert, unabhängig von Auslieferung.
Auslieferung = App-Konfig (nicht Produktion) → kein Pipeline-Neulauf bei Config-Änderung.
Standard: Hero via STANDARD_HERO_RES (Config, Default 300px, offen bis App-Test), Rest 300px.
Plus/Prem: alle 800px offline + 1600px on-demand WLAN (temporär).
Hero-Regel: hero_candidate=true + höchste relevanz, NACH ab_stufe-Filter (ab_stufe <= stufe).
JSON-Schema + R2-Pfade + STANDARD_HERO_RES-Erklärung in WISSEN_PIPELINE_PRODUKTION.md.

Offene Punkte Vollkatalog-Bilder:
- ~174k Bilder @ 3s = ~145h einmaliger Download (akzeptabel, einmalig)
- R2-Upload-Integration: kommt mit Baustein-Upload-Schritt (upload_articles.py erweitern)
- STANDARD_HERO_RES: offen bis Andreas die fertige App am echten Eindruck bewertet (300 vs 800)

---

**Opus-Recheck nur für unsichere Bilder sensibler Themen (~$50 statt ~$200, 2026-06-16)**

---

## Zuletzt abgeschlossen

**Stage 2 Generierung + Opus-Cap-Fix + custom_id-Bug (2026-06-16)** ← AKTUELL

### Stage 2 implementiert (run_batch.py)
- Gemini Context Cache je Thema (stable prefix via _split_grounded_user_message)
- 3 InlinedRequests je Thema (Stufe 1/2/3), cache=JA auf alle wenn Cache erstellt
- Variable Suffix (_gen2_variable_suffix): AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL +
  source_passages-Wrapper (Ausgabe als {article, source_passages})
- Post-Processing: JSON-Parse (Wrapper-first, Fallback plain), Wortzahl-Guard (2 Trim-Pässe),
  Box-Guard, validate_article, _set_is_hero, source_passages eingebettet, cost_tracker

**PRODUKTIONSKONFIGURATION Stage 2 (fix, nicht verhandelbar):**
Modell: gemini-3.5-flash + ThinkingLevel.MEDIUM + max_output_tokens=32768.
Thinking ist Pflicht für Artikelqualität — darf nicht zur Bug-Umgehung abgeschaltet werden.
Truncation bei 8192 war ein Budget-Problem (Thinking-Tokens zählen ins Output-Budget);
gelöst durch 32768. NICHT durch Thinking-Abschaltung.

- Elefant Durchstich: Stage 1 ✅ (28 Bilder S1=18 S2=9 S3=1)
- Stage 2 Testlauf (ohne Thinking, Baseline): läuft (bihr1of8o)
- Stage 2 echter Lauf (mit Thinking MEDIUM + 32768): geplant direkt danach

### Opus-Recheck: OPUS_CAP=18 + Sicherheitsgarantie (run_batch.py)
Problem: Opus prüfte alle akzeptierten Bilder (bis 40), Stage 2 cappt aber auf
APPEAL_TARGET (15/10/6). Bis zu 25 Opus-Calls umsonst.

Lösung mit Sicherheitsgarantie:
- `OPUS_CAP = max(APPEAL_TARGET.values()) + 3 = 18`
- Sensible Themen: `data["images"] = accepted[:OPUS_CAP]` — Stage 2 zieht AUSSCHLIESSLICH
  aus diesen ≤18 Opus-geprüften Bildern. Keine ungeprüften Bilder in Artikeln.
- Nicht-sensibel: alle akzeptierten in data["images"], nur grenzfall=true-Bilder (max 18)
  → Opus.
- Opus läuft auf top-18 nach Relevanz (bereits nach relevanz-Sort).

Verifikation Spartacus (sensibel, appeal=medium):
- 10 Bilder → Opus (alle, da 10 < 18-Cap) ✅ custom_id-Bug gefixt → 200 OK
- 1 gesperrt: Spartacus_statue_by_Denis_Foyatier.jpg ✅ (Beobachtungspunkt bestätigt)
- 7× S3→S2, 1× S3→S1 → Pool: 9 Bilder (S1=2, S2=7) — genug für alle 3 Stufen ✅
- Kostenschätzung Opus Vollkatalog: ~$30 (statt vorher ~$100)

### custom_id-Bug gefixt (run_batch.py)
Anthropic-Batch erlaubt nur `^[a-zA-Z0-9_-]{1,64}$`.
Punkte in Dateinamen (z.B. `Elefant.jpg`) brachen custom_id.
Fix: `re.sub(r"[^a-zA-Z0-9_-]", "_", filename)[:41]`, Key max 63 Zeichen.

### KRITISCHER FIX (zuvor): confidence-Signal → grenzfall-Feld
- grenzfall-Prüfung VOR ab_stufe (7-Punkt-Checkliste im Vision-Prompt)
- Conservative Upgrade: grenzfall=true + ab_stufe=1 → 2
- Verifikation Impfung: Polio_sequelle.jpg + RougeoleDP.jpg → GESPERRT ✅

## Gerade in Arbeit

**Elefant Stage 2 Batch läuft** (Gemini-Batch ~15-20 Min)
→ Ergebnis: Wortzahl vs. Ziel, sections/quiz/boxes, source_passages, is_hero

---

## Batch-Härtung VOR Großlauf (Pflicht, nicht Mini-Lauf)

Diese 4 Punkte sind **verbindliche Voraussetzung** für jeden Lauf über die 6 Mini-Themen hinaus.
Für den Mini-Lauf selbst nicht nötig (stabiles WLAN, 48h-Timeout, Downloads gecacht).
Befund aus Poll-Audit: run_batch.py hat keinen Netzwerk-Retry, keine Batch-ID-Persistenz,
keinen Resume-Punkt innerhalb Stage 1.

### 1. Batch-ID persistieren (`pending_batches.json`)
Nach JEDEM `client.batches.create()` (Gemini + Anthropic) sofort in `out_dir/pending_batches.json`
schreiben: `{batch_name, stage, run_id, timestamp, status}`.
**Grund**: Bei Prozess-Absturz ist der laufende (bereits bezahlte!) Batch verloren — kein Pointer
zum Abholen der Ergebnisse. Bei Vollkatalog-Mengen (~4k Themen) teuer und nicht wiederholbar.

### 2. Entkoppeltes Submit → Poll → Collect (`--resume`-Flag)
`run_batch.py --resume` liest `pending_batches.json`, prüft Status aller offenen Batches,
sammelt fertige Ergebnisse ein und setzt die Pipeline fort — ohne neu einzureichen.
Damit kann man einen Batch einreichen, den Prozess beenden, und SPÄTER die Ergebnisse abholen.

### 3. Netzwerk-Retry beim Poll
`try/except` um `client.batches.get()` und Anthropic-Poll-Call.
3 Retries mit Backoff (5s / 15s / 60s), dann erst Abbruch.
**Grund**: Eine transiente Netzwerk-Exception killt heute den gesamten Lauf — auch wenn der
Batch-Job auf Gemini-/Anthropic-Seite korrekt läuft.

### 4. Zwischen-Checkpoint in Stage 1
Nach WP-Fetch + Kompass-Batch + Companion-Fetch + Image-Download (VOR Vision-Submit)
einen `stage1_mid_checkpoint.json` schreiben.
Bei Neustart: Kompass + Downloads überspringen, direkt zum Vision-Submit.
**Grund**: Aktuell muss bei Absturz während Vision-Batch der gesamte Stage-1-Vorlauf
(~15 Min WP-Fetch + Kompass) wiederholt werden, obwohl die Image-Caches erhalten bleiben.

### 5. CACHE-TTL vs. BATCH-LATENZ (Großlauf-kritisch)
Context-Cache-TTL muss länger sein als die maximale Batch-Verarbeitungslatenz, sonst
läuft der Cache ab bevor Gemini die Requests verarbeitet → leere Antworten (still,
erst nach Stunden sichtbar). Mini-Lauf nutzt 3600s (1h). Beim Großlauf kann ein Batch
in Googles Queue mehrere Stunden warten → 3600s reicht evtl. nicht.
Vor Großlauf entscheiden:
- (a) Cache-TTL auf Gemini-Maximum setzen (TTL-Obergrenze für gemini-3.5-flash
  recherchieren), ODER
- (b) im Batch ganz auf Context-Cache verzichten (Batch-Rabatt −50% ist der
  Haupthebel; Cache −90% auf gecachten Teil ist Bonus, nicht zwingend) —
  vermeidet die Ablauf-Falle komplett, ODER
- (c) Implicit/automatisches Caching prüfen falls verfügbar.
Beim Mini-Lauf beobachten: kam bei Elefant nach dem 3600s-Fix eine vollständige
Antwort, oder weiter leer? Falls weiter leer → Cache-Strategie grundsätzlich überdenken.

---

## Offen nach Priorität

### run_batch.py Stage 3 — LEKTORAT (nächstes Ziel)
Anthropic Message Batches, 2 Pässe (source_passages + volle Companion-Texte).

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
