# Wissensfreund — STATUS
<!-- updated: 2026-06-17T22:40:00Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**mini_s2_v3d: Stage 2 + Stage 3 mit v3.23d abgeschlossen (2026-06-17)** ← AKTUELL

Verzeichnis: `articles/mini_s2_v3d/`
6 Themen × 3 Stufen = 18 Artikel. Generator-Prompt v3.23d (Regeln 43–46).

### Lektorat-Ergebnisse (18/18)

| Artikel | S | K | P | | Artikel | S | K | P |
|---|---|---|---|---|---|---|---|---|
| elefant_l1 | 0 | 0 | 0 | | dinosaurier_l1 | 0 | 0 | 0 |
| elefant_l2 | 0 | 0 | 0 | | dinosaurier_l2 | 2 | 1 | 0 |
| elefant_l3 | 0 | 2 | 0 | | dinosaurier_l3 | 5 | 1 | 1 ⚠ |
| hund_l1 | 1 | 0 | 0 | | vulkan_l1 | 0 | 0 | 0 |
| hund_l2 | 1 | 0 | 0 | | vulkan_l2 | 0 | 0 | 0 |
| hund_l3 | 0 | 2 | 0 | | vulkan_l3 | 2 | 0 | 2 ⚠ |
| spartacus_l1 | 0 | 0 | 0 | | zwk_l1 | 1 | 0 | 0 |
| spartacus_l2 | 2 | 0 | 0 | | zwk_l2 | 4 | 0 | 1 ⚠ |
| spartacus_l3 | 1 | 1 | 0 | | zwk_l3 | 0 | 0 | 0 |
| **GESAMT** | **19** | **7** | **4** | | | | | |

### Vergleich v3.23b → v3.23d (Spartacus+Hund+ZWK, 8→9 Artikel)

| Metrik | v3.23b | v3.23d | Delta |
|---|---|---|---|
| KORRIGIERT | 6 | 3 | **−50%** ✅ |
| PRÜFEN | 3 | 1 | **−67%** ✅ |
| SILENT | 10 | 10 | ±0 |

### PRÜFEN-Analyse (4 total)

| Fall | Artikel | Befund | Typ |
|---|---|---|---|
| Archaeopteryx-Flug | dinosaurier_l3 | reveal_text-Box behauptet Fliegen — Quelle sagt nicht so einfach | LEGITIM |
| Plinius Augenzeuge | vulkan_l3 | «aus sicherer Entfernung» vs. WP: Plinius war in Misenum, kein Direktzeuge | LEGITIM |
| Geysire Yellowstone | vulkan_l3 | Einbau fehlgeschlagen (Satz nicht gefunden in Artikel-JSON) | TECHNISCH |
| Bletchley Park | zwk_l2 | «Landhaus Bletchley Park» — Bletchley IST in ZWK-Quelle (Pos 74%), aber Framing fraglich | BORDERLINE |

### Generator-Regelprüfung

| Regel | Ziel | Befund |
|---|---|---|
| 43 — Keine erfundenen Traits | «teilte gerecht» weg? | ⚠️ Kern-Fakt belegt (Appian: «gleichmäßig verteilt»). Lektorat fängt Intensifier «absolut» als SILENT ab. Box-Titel «Teilen macht Freude» noch frei. |
| 44 — Beim Thema bleiben | Kein Dingo-Statistik-Exkurs? | ✅ hund_l2 komplett clean; hund_l3: Dingo sachlich erwähnt, Statistik-Exkurs weg. Lektorat korrigiert verbliebene Welpendefinition. |
| 45 — Kein Modellwissen | Kein Bletchley/Turing aus Training? | ✅ Bletchley Park IST im ZWK-Primärtext (Pos 74%). Korrekte Quellennutzung. |
| 46 — Sensible Themen ernst | Keine Verharmlosung ZWK? | ✅ ZWK l1/l2/l3 sauber — kein kindischer Schluss, kein Anne-Frank-Du-Vergleich, kein Verharmlosungs-Framing. |

### Qualität (lebendig?)

Artikel-Headings zeigen unveränderte Lebendigkeit:
- Hund l3: «Vom wilden Wolf zum treuen Begleiter»
- Vulkan l3: «Unter unseren Füßen brodelt es»
- ZWK l2: «Ein schwerer Sturm zieht auf»
- Dinosaurier l3: «Die Zeit der Riesenechsen»

Keine Trockenheit durch Einschränkungsregeln — Lebendigkeit erhalten. ✅

### Wichtige Lektorat-Korrekturen (Qualitätsnachweise)

- **Hund l3**: «Welpe bis 2–3 Monate» → KORRIGIERT zu «6–9 Monate» ✓
- **Hund l3**: Dingo-Statistik «5% Bellen» → KORRIGIERT zu «heulen und andere Laute» ✓
- **Elefant l3**: «ohne Knorpel» → KORRIGIERT: «Knorpel nur am Nasenansatz» ✓
- **ZWK l2**: «Mehr als 60 Staaten» → SILENT-Korrektur zu «Über 60» ✓
- **Spartacus l3**: «Via Appia ... nach Rom» → KORRIGIERT zu «von Rom nach Capua» ✓

---

## Lektorat-Retrieval VERIFIZIERT (2026-06-17)

Tiefentest 15 Fakten / 3 Themen / 5 Positionsbänder (0–100%): **0/15 false positives.**
- Keine Positionsabhängigkeit — selbst bei 89% Textposition und 48% Kontextfüllung findet Sonnet den Beleg.
- **Option C (Retrieval verbessern) NICHT nötig. Volltext-Lektorat bleibt wie es ist.**

---

## Offen nach Priorität

### Regel 43 Feinschliff (optional)
Box-Titel «Teilen macht Freude» und ähnliche Sentiment-Titel sind noch möglich.
Lektorat fängt faktische Embellishments ab (SILENT für «absolut»), aber Box-Titel-Framing nicht.
→ Prompt-Ergänzung: «Box-Titel sind keine Wertungen — nur beschreibende Überschriften.»
→ Entscheidung: Wie wichtig? Lektorat-Netz reicht für Fakten.

### Baustein 3 — tts_produce.py (Produktions-TTS)
compose → tagging (gemini-2.5-flash-lite) → gemini-3.1-flash-tts-preview → WAV/MP3 → R2

### Baustein 4 — Quiz-Vertonung

### Offene Audio-Entscheidungen (Andreas)
1. Iapetus-Qualität im Audio-Review bestätigen
2. Feste Tag-Palette vs. freie Tags
3. Tagging-Modell: gemini-3.5-flash vs. gemini-2.5-flash-lite

### Sonstiges
- categories_backlog.json → categories-Array je Artikel
- Flutter WfArticleListScreen + 3-flash-preview L3 Fix
- Quiz/stimmt_das App-Dart-Fix (wf_article.dart) — schema mismatch noch offen
- Chicxulub-Companion-Entscheidung: Option A (Kompass verbessern) vs. weiter Regel 45

---

## Pipeline-Zustand (Stand 2026-06-17)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig (reveal_text=null Fix) |
| Batch-Orchestrator Stage 1 | run_batch.py | ✅ Stage 1 komplett |
| Batch-Orchestrator Stage 2 | run_batch.py | ✅ Mini-Lauf 18/18 v3.23d |
| Batch-Orchestrator Stage 3 | run_batch.py | ✅ Mini-Lauf 18/18 v3.23d |
| Batch-Orchestrator Stage 4 | run_batch.py | ⏳ Gerüst (TODO) |
| Gemini-Retry | gemini_client.py | ✅ 503/429 Backoff + Jitter |
| Bild-Vision | image_vision_filter.py | ✅ lauffähig |
| TTS-Vorlesetext | tts_compose.py | ✅ lauffähig |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| R2-Upload | upload_articles.py | ✅ lauffähig |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet |

### Catalog (final)
catalog_full.json: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
