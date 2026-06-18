# Wissensfreund — STATUS
<!-- updated: 2026-06-18T05:41:48Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Regel 43 Sentiment-Framing + Review-Docs v3e (2026-06-18)** ← AKTUELL

### Regel 43 erweitert (v3.23e)
Generator-Prompt + Lektorat-System: Sentiment-Framing belegter Fakten verboten.
- Box-Titel: Beschreibungen, keine Wertungen («Wie Spartacus die Beute teilte» ✓, «Teilen macht Freude» ✗)
- Intensifier über Quelle hinaus verboten («gleichmäßig» → nicht «ganz gerecht» / «absolut»)
- Neutrale Quellbegriffe beibehalten («Beute» bleibt «Beute», nicht «Schätze»)

Spartacus-Test (mini_s2_v3e):
- l1: 1 SILENT (sauber) ✅
- l2: 2 KORRIGIERT (70→78 Männer, 6.000 Kreuze — faktische Präzisierungen) ✅
- l3: 4 KORRIGIERT + 1 PRÜFEN ⚠ — alle legitim:
  - «um Neid zu verhindern» → erfundenes Motiv entfernt ✅
  - «wollten weiterplündern» → «Plündern» als Motiv nicht belegt ✅
  - «bekanntesten» → «bekanntesten und gefährlichsten» ✅
  - **«völlig gleichmäßig» → «gleichmäßig» — Rule 43 greift!** ✅
  - PRÜFEN: «siebzig» vs. widersprüchliche Quellangaben

Qualität erhalten: Kein «Teilen macht Freude», kein «Schätze», kein «absolut» — Text bleibt lebendig.

### Word-Review-Dokumente (6 .docx)
Output: `articles/mini_s2_v3e/review/`
- Spartacus: aus mini_s2_v3e
- Elefant, Hund, Dinosaurier, Vulkan, ZWK: aus mini_s2_v3d
- Alle 6 erstellt ✅

---

## mini_s2_v3d: Ergebnisse (Referenz)

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

---

## Lektorat-Retrieval VERIFIZIERT (2026-06-17)

Tiefentest 15 Fakten / 3 Themen / 5 Positionsbänder: **0/15 false positives.**
**Option C nicht nötig. Volltext-Lektorat bleibt wie es ist.**

---

## Offen nach Priorität

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

## Pipeline-Zustand (Stand 2026-06-18)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig (reveal_text=null Fix) |
| Batch-Orchestrator Stage 1-3 | run_batch.py | ✅ 18/18 v3.23d + Spartacus v3.23e |
| Lektorat | lektorat_common.py | ✅ v3.23e Sentiment-Framing-Prüfung |
| Review-Docs | create_review_docs.py | ✅ --theme-lektorat Override |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| R2-Upload | upload_articles.py | ✅ lauffähig |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet |

Catalog: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
