# WISSEN_PIPELINE_PRODUKTION.md
<!-- erstellt: 2026-06-16 -->

## Bild-Tier-Architektur (final, 2026-06-16)

### Grundprinzip: Produktion ≠ Auslieferung

**Produktion** erzeugt immer alle drei Auflösungen — unabhängig davon, was die App später
ausliefert. Alle Tiers liegen in R2 bereit; die App wählt per Nutzer-Tier (und für
Standard-Hero per App-Konfig) welche URL sie lädt. Kein Pipeline-Neulauf nötig für
Auslieferungs-Änderungen.

### Auflösungen auf R2 (3 Tiers, immer alle produziert)

| Auflösung | Quelle | R2-Suffix |
|-----------|--------|-----------|
| 300px JPEG | lokal skaliert aus 1600px-Download | `_300.jpg` |
| 800px JPEG | lokal skaliert aus 1600px-Download | `_800.jpg` |
| 1600px JPEG | CDN-Thumbnail-Download (iiurlwidth=1600) | `_1600.jpg` |

R2-Pfad-Schema: `bilder/{thema_slug}/{filename_slug}_{width}.jpg`
Beispiel: `bilder/elefant/Afrikanischer_Elefant_800.jpg`

### App-Auslieferung nach Nutzer-Tier

| Nutzer-Tier | Hero-Bild | Weitere Bilder | 1600px |
|-------------|-----------|----------------|--------|
| Standard (gratis) | **STANDARD_HERO_RES** (Config) | 300px offline | — |
| Plus / Premium | 800px offline | 800px offline | on-demand, nur WLAN, temporär |

**STANDARD_HERO_RES** — App-Konfigurationswert, offen bis Andreas die fertige App
am echten Eindruck bewertet:
- Default (vorerst): **300px** (konservativ, spart Datenvolumen)
- Option: **800px** (stärkerer erster Eindruck, mehr Produktreiz)
- Umstellbar OHNE Neuproduktion — alle Auflösungen liegen bereits in R2.

### Speicher-Schätzung

| Szenario | KB/Artikel | 100 Artikel |
|----------|-----------|-------------|
| Standard, Hero 300px (Default) | ~520 KB | ~52 MB |
| Standard, Hero 800px (Option) | ~780 KB | ~78 MB |
| Plus/Prem offline (alle 800px) | ~1.760 KB | ~176 MB |
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
- `is_hero`: genau ein Bild pro Artikel+Stufe hat `true` — welche Auflösung davon
  ausgeliefert wird, bestimmt STANDARD_HERO_RES in der App, nicht das JSON
- `tiers.300/800/1600`: R2-Pfade (relativ zur R2-Basis-URL), alle drei immer vorhanden
- `original_url`: Wikimedia-Quell-URL (für Lizenz-Attribution, getrennt von Download-Quelle)

---

## grenzfall-Signal (2026-06-16)

### Problem (behoben)

Das alte `confidence`-Feld war strukturell kaputt: Das Modell entschied zuerst `ab_stufe`,
bewertetedann retrospektiv seine eigene Entscheidung → fast immer "hoch". Befund Mini-Lauf:
181 Bilder, hoch=146, mittel=1, **niedrig=0** — auch `Polio_sequelle.jpg` (Kind mit
Lähmungsfolgen) und `RougeoleDP.jpg` (Kind mit Masernausschlag am ganzen Körper) bekamen
`confidence="hoch"`. Beide Sicherheitsschichten (Conservative Upgrade + Opus-Recheck)
wurden damit nie ausgelöst.

### Lösung: grenzfall-Feld VOR ab_stufe

Der Vision-Prompt wurde umstrukturiert. Das Modell beantwortet jetzt in dieser Reihenfolge:

1. **SCHRITT 1 — grenzfall-Prüfung** (vor der Alterseinstufung):
   Explizite Checkliste heikler Merkmale:
   - sichtbares Leid, Schmerz, Krankheit oder Verletzung an Menschen/Tieren
   - Krankheitssymptome am Körper (Ausschlag, Lähmung, Wunden, Deformationen)
   - medizinische Eingriffe (Spritzen, Operationen, Verbände)
   - Tod, Sterben, Trauer, Trauma
   - historisch ernste Darstellungen (Krieg, Gewalt, Unterdrückung)
   - Nacktheit (unabhängig vom Kontext)
   - beängstigende/belastende Szenen für Kinder unter 12

2. **SCHRITT 2 — ab_stufe** (informiert durch grenzfall):
   - `grenzfall=true` → NIEMALS ab_stufe=1
   - Progressive Einstufung 2/3, GESPERRT (0) nur bei explizit nicht zumutbaren Inhalten

### Verifikation (Impfung, 14 Bilder):

| Bild | Vorher | Nachher |
|---|---|---|
| `Polio_sequelle.jpg` | [S2] hoch ❌ | **GESPERRT** ✅ |
| `RougeoleDP.jpg` | [S3] hoch ❌ | **GESPERRT** ✅ |
| `Immunization_retusche.jpg` | [S1] hoch ❌ | **[S3] grenzfall=true** ✅ |
| `Mai_Simu_Vasina_COVID-19.jpg` | [S1] hoch ❌ | **[S2] grenzfall=true** ✅ |
| `Vaccination-polio-india.jpg` | [S1] hoch ❌ | **[S2] grenzfall=true** ✅ |

### Neue Sicherheitslogik

**Conservative Upgrade (lokal, sofort):**
- `grenzfall=true AND ab_stufe=1` → automatisch `ab_stufe=2`
- (ersetzt: `confidence=niedrig AND ab_stufe=1`)

**Opus-Recheck-Trigger:**
- `sensibel=True` → ALLE akzeptierten Bilder des Themas → Opus
- `sensibel=False` → nur `grenzfall=true` Bilder → Opus
- (ersetzt: `sensibel AND confidence=niedrig`)

**`confidence`-Feld:** Bleibt im JSON (informativ), keine Logik hängt mehr daran.

---

## Batch-Orchestrator: run_batch.py

### Stage-Reihenfolge (KORREKT — Vision VOR Generierung)

```
Stage 1 — SOURCING
  WP-Fetch + Lemma (sync)
  → Kompass-Batch (Gemini, gemini-3.5-flash)
  → Companion-Fetch + Validierung (sync)
  → Image-Download (sync, 0.5s-Sleep, kein 10s-Wait)
  → Vision-Batch (Gemini, gemini-2.5-flash, ab_stufe 0/1/2/3 + grenzfall)
  → Conservative Upgrade (grenzfall=true + ab_stufe=1 → 2, lokal)
  → Opus-Recheck (Anthropic Batch, claude-opus-4-8):
       sensibel=True  → ALLE akzeptierten Bilder
       sensibel=False → nur grenzfall=true Bilder
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
| Opus-Recheck | claude-opus-4-8 | Batch | ~$40 |
| Artikel | gemini-3.5-flash | Batch + Cache | ~$40 |
| Lektorat | claude-sonnet-4-6 | Batch + Cache | ~$30 |
| TTS | gemini-tts | Online | ~$1173 |

### Vision-Batch Chunking

`VISION_CHUNK_SIZE = 500` — max InlinedRequests pro Batch-Job.
- Mini-Lauf (5 Themen × 40 Bilder = 200) → 1 Chunk
- Vollkatalog (4346 × 40 = 174K) → ~348 Chunks (separate Batch-Jobs)
- Jeder InlinedRequest enthält Base64-JPEG inline (~100-200KB)

### Modell-Zuordnung

| Schritt | Modell | Thinking | max_output_tokens |
|---|---|---|---|
| Kompass | gemini-3.5-flash | ThinkingLevel.MEDIUM | default |
| Vision | gemini-2.5-flash | thinking_budget=0 | default |
| Artikel-Gen (Batch) | gemini-3.5-flash | **ThinkingLevel.MEDIUM** (Pflicht!) | **32768** |
| Trim/Box-Repair (sync) | gemini-3.5-flash | ThinkingLevel.MEDIUM | default |
| Opus-Recheck | claude-opus-4-8 | - | 256 |
| Lektorat | claude-sonnet-4-6 | - | default |

**WICHTIG — Artikel-Generierung:** ThinkingLevel.MEDIUM ist Produktionskonfiguration und
darf NICHT zur Bug-Umgehung abgeschaltet werden. Truncation bei 8192 Token war ein
Budget-Problem (Thinking-Tokens zählen ins max_output_tokens-Budget). Gelöst durch 32768.
Bei 32768 ist genug Raum für Thinking-Tokens + vollständigen Artikel + source_passages.

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
