# Wissensfreund — STATUS
<!-- updated: 2026-06-17T18:27:06Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Generator v3.23d + Lektorat-Fehlerfixes + mini_s2_v3 Testlauf (2026-06-17)** ← AKTUELL

### A: Generator-Prompt v3.23d (wissensfreund_generator_prompt_v3.23_production.md)

4 neue Belegtreue-Regeln in EISERNE REGEL + HÄUFIGE FEHLER (Einträge 43–46):

| Regel | Ziel |
|---|---|
| 43 — Keine erfundenen Charakterzüge | «teilte gerecht», «immer freundlich» → verboten |
| 44 — Beim Thema bleiben | Dingo-Lautäußerungs-Statistik im Hunde-Artikel → verboten |
| 45 — Kein Modell-Detailwissen | Alan Turing/Bletchley nicht aus Training ergänzen |
| 46 — Sensible Themen ernst nehmen | Keine kindlichen Schlüsse, keine pietätlosen Du-Vergleiche |

Regeln auch in der EISERNE REGEL-Sektion als Fließtext verankert.

### B: Lektorat-Fehlerfixes (lektorat_common.py LEKTORAT_SYSTEM)

**Fall 1 — SELBSTKONSISTENZ-PFLICHT** (in ENTSCHEIDUNGSPRINZIP):
Wenn Begründung kein Handlungsbedarf → Verdict MUSS «kein Flag» sein, NICHT PRÜFEN.
Konkret: «fast einen Meter» bei 95 cm belegt → kein PRÜFEN, weil Begründung self-consistent.

**Fall 2 — SINNGEMÄSSE BELEGE** (in GROUNDING-REGEL):
«fliehen» wird durch «verlassen gefährdetes Gebiet» gedeckt — Wortgleichheit nicht nötig.
Verhindert false-positive PRÜFEN bei synonym-belegten Aussagen.

### C: mini_s2_v3 Testlauf (Spartacus, Hund, Zweiter Weltkrieg × 3 Stufen)

⚠️ Artikel wurden mit v3.23b generiert (Stage 2 lief parallel zur Prompt-Änderung).
Test prüft daher: Lektorat-Qualität auf v3.23b-Output; Generator-Issues als Baseline bestätigt.

| Artikel | SILENT | KORRIGIERT | PRÜFEN |
|---|---|---|---|
| spartacus_l1 | 0 | 0 | 0 |
| spartacus_l2 | — | — | — (JSON-Parse-Fehler Gemini 503) |
| spartacus_l3 | 1 | 1 | **2** ⚠️ |
| hund_l1 | 0 | 0 | 0 |
| hund_l2 | 0 | 2 | **1** ⚠️ |
| hund_l3 | 4 | 0 | 0 |
| zweiter_weltkrieg_l1 | 0 | 0 | 0 |
| zweiter_weltkrieg_l2 | 3 | 0 | 0 |
| zweiter_weltkrieg_l3 | 2 | 3 | 0 |
| **Gesamt (8/9)** | **10** | **6** | **3** |

**PRÜFEN-Analyse (alle 3 legitim):**
- hund_l2: «Forscher haben herausgefunden» vs. Quelle «wendet dagegen ein» → Pädagogischer Kern (Fall 2 der PRÜFEN-Ausnahmen) ✅
- spartacus_l3: «gleichmäßig verteilt» Einbau fehlgeschlagen (auto-correction konnte Satz nicht finden) + Zwei-Quellen-Widerspruch («zwangen zur Umkehr» vs. «ungeklärte Gründe») ✅

**Generator-Violations in v3.23b bestätigt (Ziel für v3.23d-Test):**
- Spartacus S1: «teilte ganz gerecht» → Rule 43 target ✅
- Spartacus S3: «absolut gleichmäßig» → Rule 43 target ✅
- Hund S2: Dingo Lautäußerungs-Statistik (5%/65%) im Artikel → Rule 44 target ✅
- WW2: kein naiver Schluss («Frieden gelernt»), keine pietätlosen Du-Vergleiche ✅

**Zweiter Weltkrieg Qualität (altersgerecht, ernst, ohne Verharmlosung):**
ZWK-L3 Schlusssatz: «Nach dem Krieg gründeten die Siegerstaaten die Vereinten Nationen» ✅
Anne Frank: in warnung-Box, seriös behandelt ✅ — kein «du auch Tagebuch schreiben»-Vergleich ✅

---

**Lektorat v4 Vollständig-Lauf mini_lektorat_v32: 18/18, Word-Dokumente (2026-06-17)**

| Thema | S1 S/K/P | S2 S/K/P | S3 S/K/P |
|---|---|---|---|
| **Elefant** | 0/0/0 | 0/0/0 | 2/2/0 |
| **Hund** | 2/0/0 | 1/1/1 | 0/1/0 |
| **Dinosaurier** | 2/0/0 | 0/0/0 | 2/0/1 |
| **Vulkan** | 0/0/0 | 2/2/1 | 0/0/0 |
| **Spartacus** | 0/0/0 | 1/1/0 | 1/1/1 |
| **ZWK** | 1/0/0 | 1/0/1 | 3/1/1 |
| **Gesamt** | **5/0/0** | **5/4/2** | **8/5/3** |

v3.1→v4: PRÜFEN 39→6 (−85%). Kein Artikel >1 PRÜFEN. ✅

---

## Gerade in Arbeit / Offen nach Priorität

### TODO sofort: v3.23d an frischen Artikeln verifizieren
Spartacus-l2 neu generieren (JSON-Parse-Fehler Gemini 503, trailing comma).
Dann Stage 2 neu für Spartacus mit v3.23d → prüfen ob «gleichmäßig» verschwindet.

### TODO: Chicxulub-Krater als Dinosaurier-Companion (Stage 1)
stage1_checkpoint.json — Companion für Dinosaurier um Chicxulub-Krater erweitern.
Begründung: «mindestens 26 Grad» Claim hat keinen Quellbeleg (Companion fehlt).
Nicht Teil von mini_s2_v3 — separater Stage-1-Update nötig.

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
- Quiz/stimmt_das App-Dart-Fix (wf_article.dart) — schema mismatch noch offen

---

## Pipeline-Zustand (Stand 2026-06-17)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig, synchron |
| Batch-Orchestrator Stage 1 | run_batch.py | ✅ Stage 1 komplett |
| Batch-Orchestrator Stage 2 | run_batch.py | ✅ Mini-Lauf 18/18, Batch verifiziert |
| Batch-Orchestrator Stage 3 | run_batch.py | ✅ Mini-Lauf 18/18, Batch+pending_batches.json |
| Batch-Orchestrator Stage 4 | run_batch.py | ⏳ Gerüst (TODO) |
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
