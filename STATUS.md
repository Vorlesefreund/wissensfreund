# Wissensfreund — STATUS
<!-- updated: 2026-06-09T07:11:00Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**image_vision_filter.py: Wurzelfix Wikimedia-Rate-Limit (Commit 6c4c159, 2026-06-09)**
- Originale statt Thumbnails laden → kein Thumb-Generierungs-Trigger → 0×429
- Pillow LANCZOS lokal auf 800px + 300px skalieren, als JPEG cachen
- 1 persistente requests.Session, User-Agent auf allen Requests
- TIF/SVG: 1280px-Thumb als Fallback (_wikimedia_thumb_url, ohne API-Call)
- Test: 30/30 Indianer-Originale, 0×429, 1 Wikimedia-API-Request

**batch_run.py + dashboard.html: Gemini Batch API POC (2026-06-09 LAUFEND)**
- Batch API bestätigt: `client.batches.create(model, src=list[InlinedRequest])` funktioniert
- Batch-Job läuft: batches/cjzuctd806xqvv45wsjwnjz2bng8kr915pkh (Phase 1, 3 Artikel)
- Dashboard: http://localhost:8080/dashboard.html (HTTP-Server auf :8080)
- Bekanntes Problem: Wikipedia-429 bei biene_l3 + demokratie_l1 (Fix: Dedup + Delays)
- Fix bereits in batch_run.py: seen_wp-Dedup + 1s/0.5s Sleep zwischen Fetches

---

## 🔄 Gerade in Arbeit

**batch_run.py Hintergrund-Run (brox0bax2)** — Phase 1 Batch PENDING (09:09 gestartet)
- 3 Artikel in Phase 1: indianer_l1 + l2 + l3
- biene_l3 + demokratie_l1 ausgefallen (Wikipedia-429, Fix im Code)
- Warte auf JOB_STATE_SUCCEEDED

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **batch_run.py Re-Run** (nach Fix): alle 5 Artikel, sobald laufender Batch abgeschlossen
- **Sichtung generierter Artikel** (nach batch_run.py): meta.title, Companions, Bildpool
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **indianer_l2 review**: 14 Sätze statt 15 Minimum

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
