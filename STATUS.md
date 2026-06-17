# Wissensfreund — STATUS
<!-- updated: 2026-06-17T20:06:53Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Lektorat-Retrieval-Tiefentest + mini_s2_v3d Stage-2-Lauf gestartet (2026-06-17)**

### Lektorat-Retrieval VERIFIZIERT (2026-06-17)

Tiefentest: 15 Fakten × 3 Themen × 5 Positionsbänder (0–100% Textposition).

| Thema | False Positives | Primärtext | Kontextfüllung |
|---|---|---|---|
| Dinosaurier | 0/5 (0%) | 68k Zeichen | 21.8% |
| Elefant | 0/5 (0%) | 116k Zeichen | 28.2% |
| Zweiter Weltkrieg | 0/5 (0%) | 273k Zeichen | 48.6% |

**Fazit:**
- Keine Positionsabhängigkeit — selbst bei 89% Textposition und 48% Kontextfüllung findet Sonnet den Beleg zuverlässig.
- SILENT-Eintrag (ZWK Dünkirchen/68.000 Mann) = kein false positive, sondern Beleg gefunden + bestätigt.
- **Option C (Retrieval verbessern / Volltext kürzen) NICHT nötig.**
- **source_passages-Wegweiser fürs Lektorat NICHT nötig (Retrieval ist robust).**
- Volltext-Lektorat bleibt wie es ist.

### Generator v3.23d + Lektorat-Fehlerfixes (2026-06-17)

4 neue Belegtreue-Regeln (43–46) in EISERNE REGEL + HÄUFIGE FEHLER:
- 43: Keine erfundenen Charakterzüge/Tugenden
- 44: Beim Thema bleiben (kein Companion-Exkurs)
- 45: Kein Modell-Detailwissen (Namen/Zahlen nicht aus Training)
- 46: Sensible Themen ernst nehmen (keine Verniedlichung)

Lektorat-Fixes (lektorat_common.py):
- Fall 1 SELBSTKONSISTENZ-PFLICHT: Begründung schlägt Verdict
- Fall 2 SINNGEMÄSSE BELEGE: «fliehen» = «verlassen gefährdetes Gebiet»

---

## Gerade in Arbeit

**mini_s2_v3d — Stage-2-Lauf (v3.23d-Verifikation)** ← LÄUFT

Verzeichnis: `articles/mini_s2_v3d/`
Stage-1-Checkpoint von mini_s2_v3 kopiert (alle 6 Themen vorhanden).
Stage-2-Batch läuft: 6 Themen × 3 Stufen = 18 Artikel mit v3.23d-Prompt.

Prüfziele:
- Spartacus: kein «teilte Essen/Beute gerecht» mehr?
- Hund: kein Dingo-Statistik-Exkurs mehr?
- ZWK S1: kein «Teilen und Vertragen ist schöner» mehr?
- ZWK S2: kein «vielleicht schreibst du Tagebuch wie Anne Frank» mehr?
- ZWK: kein Bletchley Park / Alan Turing wenn nicht in Quelle?
- Artikel trotzdem noch lebendig?

---

## Offen nach Priorität

### TODO sofort: mini_s2_v3d Stage 3 (Lektorat)
Nach Stage-2-Abschluss: Stage 3 für alle 18 Artikel + neue Word-Dokumente.
Erwartung: deutlich weniger PRÜFEN/KORRIGIERT wegen weniger Generator-Angriffsfläche.

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
