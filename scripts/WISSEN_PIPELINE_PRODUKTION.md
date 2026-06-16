# WISSEN_PIPELINE_PRODUKTION.md
<!-- erstellt: 2026-06-16 -->

## Bild-Tier-Architektur (final, 2026-06-16)

### Auflösungen auf R2 (3 Tiers pro Bild)

| Tier | Auflösung | Quelle |
|------|-----------|--------|
| Standard | 300px JPEG | lokal skaliert aus 1600px-Download |
| Plus/Prem | 800px JPEG | lokal skaliert aus 1600px-Download |
| Max | 1600px JPEG | CDN-Thumbnail-Download (iiurlwidth=1600) |

R2-Pfad-Schema: `bilder/{thema_slug}/{filename_slug}_{width}.jpg`
Beispiel: `bilder/elefant/Afrikanischer_Elefant_800.jpg`

### App-Auslieferung nach Nutzer-Tier

| Nutzer-Tier | Hero-Bild | Weitere Bilder | 1600px |
|-------------|-----------|----------------|--------|
| Standard (gratis) | 800px offline | 300px offline | — |
| Plus / Premium | 800px offline | 800px offline | on-demand, nur WLAN, temporär |

### Speicher-Schätzung

| Szenario | KB/Artikel | 100 Artikel |
|----------|-----------|-------------|
| Standard (Hero 800 + Rest 300) | ~520 KB | ~52 MB |
| Plus/Prem offline (alle 800) | ~1.760 KB | ~176 MB |
| Server gesamt (300+800+1600 × 15k Bilder) | — | ~9 GB |

### Hero-Bild-Regel

1. Primär: `hero_candidate=true` aus Vision-Filter
2. Falls mehrere: höchste `relevanz`-Punktzahl
3. Falls keines: erstes akzeptiertes Bild in img_index-Reihenfolge
4. **Stufenregel**: Hero-Auswahl NACH ab_stufe-Filter — `ab_stufe <= stufe` muss gelten.
   Kein ab_stufe=2-Bild als Hero in einem S1-Artikel.

### JSON-Schema: Bilder im Artikel-JSON

```json
{
  "images": [
    {
      "img_index": 0,
      "filename": "Afrikanischer_Elefant.jpg",
      "wikimedia_id": "File:Afrikanischer Elefant.jpg",
      "original_url": "https://upload.wikimedia.org/wikipedia/commons/…/Afrikanischer_Elefant.jpg",
      "license": "CC BY-SA 4.0",
      "license_author": "Max Mustermann",
      "ab_stufe": 1,
      "relevanz": 9,
      "hero_candidate": true,
      "confidence": "hoch",
      "beschreibung": "Afrikanischer Elefant in der Savanne.",
      "is_hero": true,
      "tiers": {
        "300":  "bilder/elefant/Afrikanischer_Elefant_300.jpg",
        "800":  "bilder/elefant/Afrikanischer_Elefant_800.jpg",
        "1600": "bilder/elefant/Afrikanischer_Elefant_1600.jpg"
      }
    }
  ]
}
```

**Felder:**
- `img_index`: Reihenfolge im Artikel (0-basiert, nach Stufenfilter)
- `is_hero`: genau ein Bild pro Artikel+Stufe hat `true` (das 800px-Hauptbild bei Standard)
- `tiers.300/800/1600`: R2-Pfade (relativ zur R2-Basis-URL), alle drei immer vorhanden
- `original_url`: Wikimedia-Quell-URL (für Lizenz-Attribution)

---

## Batch-Orchestrator: run_batch.py

### Stage-Reihenfolge (KORREKT — Vision VOR Generierung)

```
Stage 1 — SOURCING
  WP-Fetch + Lemma (sync)
  → Kompass-Batch (Gemini, gemini-3.5-flash)
  → Companion-Fetch + Validierung (sync)
  → Image-Download (sync, 0.5s-Sleep, kein 10s-Wait)
  → Vision-Batch (Gemini, gemini-2.5-flash, ab_stufe 0/1/2/3)
  → Conservative Upgrade (confidence=niedrig + ab_stufe=1 → 2, lokal)
  → Opus-Recheck (Anthropic Batch, claude-opus-4-8, nur sensibel + confidence=niedrig)
  Ergebnis: topics_data[thema] = {primary_text, companions, companion_texts, images}

Stage 2 — GENERIERUNG (TODO)
  Für jedes Thema: Gemini Context Cache (stable prefix)
  Für jedes Thema × Stufe: select_images_for_stufe + variable suffix
  → Gemini Batch (gemini-3.5-flash, ThinkingLevel.MEDIUM)
  Post-Processing: Wortzahl-Guard + Box-Guard (synchron, lokal)

Stage 3 — LEKTORAT (TODO)
  Pass 1: source_passages (schlank) oder Companion-Volltexte
  → Anthropic Batch (claude-sonnet-4-6, cache_control: ephemeral)
  Pass 2: Nachschlag für passagen_ausreichend=false
  → annotate_article_lektorat()

Stage 4 — TTS (Stub)
  ThreadPool via tts_produce.py (nächster Baustein)
  Wichtig: tts_audio_sec an cost_tracker melden
```

### Batch-API-Mechanik

#### Gemini Batch
- SDK: `client.batches.create(model=..., src=[types.InlinedRequest(...)])`
- `types.InlinedRequest(contents=..., config=GenerateContentConfig(...), metadata={"key": ...})`
- Multimodal (Vision): `contents=types.Content(role="user", parts=[Part.from_bytes(...), Part.from_text(...)])`
- Poll: `client.batches.get(name=batch_name)` → `batch.state.value`
- Ergebnisse: `batch.dest.inlined_responses` (Liste von InlinedResponse)
- Preis: 50% von Standard ($0.75/1M Input, $4.50/1M Output für gemini-3.5-flash)
- SLA: 24h Ziel, max 48h; danach expired
- Context Cache + Batch: ✅ kompatibel — `cached_content=cache_name` in `GenerateContentConfig`

#### Anthropic Batch
- SDK: `client.messages.batches.create(requests=[{custom_id, params}])`
- Prompt Caching + Batch: ✅ kompatibel — `cache_control: ephemeral` auf System-Block
- Poll: `client.messages.batches.retrieve(batch_id)` → `processing_status == "ended"`
- Ergebnisse: `client.messages.batches.results(batch_id)` (Iterator)
- Preis: 50% von Standard (claude-sonnet-4-6: $1.50/1M Input, $7.50/1M Output)
- SLA: meist <1h, max 24h; Ergebnisse 29 Tage abrufbar

### Checkpoint/Resume

Jede Stage speichert bei Abschluss:
- `{out_dir}/stage1_checkpoint.json` → `{"status": "done", "topics": {...}}`
- `{out_dir}/stage2_checkpoint.json` → `{"status": "done", "articles": {...}}`
- `{out_dir}/stage3_checkpoint.json` → `{"status": "done", "lektorat_results": {...}}`

Beim Start: Checkpoint vorhanden + status=done → Stage überspringen.

### Kosten-Schätzung Vollkatalog (4346 Themen × 3 Stufen)

| Stage | Modell | Modus | Schätzung |
|---|---|---|---|
| Kompass | gemini-3.5-flash | Batch | ~$10 |
| Vision | gemini-2.5-flash | Batch | ~$15 |
| Opus-Recheck | claude-opus-4-8 | Batch | ~$25 |
| Artikel | gemini-3.5-flash | Batch + Cache | ~$40 |
| Lektorat | claude-sonnet-4-6 | Batch + Cache | ~$30 |
| TTS | gemini-tts | Online | ~$1173 |

### Vision-Batch Chunking

`VISION_CHUNK_SIZE = 500` — max InlinedRequests pro Batch-Job.
- Mini-Lauf (5 Themen × 40 Bilder = 200) → 1 Chunk
- Vollkatalog (4346 × 40 = 174K) → ~348 Chunks (separate Batch-Jobs)
- Jeder InlinedRequest enthält Base64-JPEG inline (~100-200KB)

### Modell-Zuordnung

| Schritt | Modell | Thinking |
|---|---|---|
| Kompass | gemini-3.5-flash | ThinkingLevel.MEDIUM |
| Vision | gemini-2.5-flash | thinking_budget=0 |
| Artikel-Gen | gemini-3.5-flash | ThinkingLevel.MEDIUM |
| Trim/Box-Repair | gemini-3.5-flash | ThinkingLevel.MEDIUM |
| Opus-Recheck | claude-opus-4-8 | - |
| Lektorat | claude-sonnet-4-6 | - |

### Wichtige Funktionen (importiert aus generate_grounded.py)

Für Stage 2 (Generierung):
- `try_create_gemini_cache(client, model, system_prompt, stable_prefix)` → cache_name
- `_split_grounded_user_message(job, primary_text, companion_texts, valid_companions, images)` → (stable, variable)
- `select_images_for_stufe(pool, stufe, appeal)` → gefilterte Liste
- `_variable_suffix(job, wmax)` → variabler Suffix-String
- `wortziel_for(thema, level)` → (wmin, wmax, source)
- `count_article_words(article)` → int
- `_box_lint(article)` → Verstoßgrund | None
- `_trim_article_to_cap(article, wmax, model, thinking_config)` → (article, word_count)
- `_box_repair_pass(article, model, thinking_config)` → article

### Bekannte Einschränkungen

- Tabak (und andere exclude-Themen) nicht in catalog_full.json → werden übersprungen
- resolve_lemma() macht Gemini-Call auch im dry-run (Flash-Doppelbedeutungs-Check)
- Vision-Batch: Bilder als Base64 inline → Chunk-Größe 500 für Speicherschutz
- Stage 2-4 noch nicht implementiert (Gerüst mit TODOs)
