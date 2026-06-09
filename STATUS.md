# Wissensfreund — STATUS
<!-- updated: 2026-06-09T09:36:21Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**render_review_html.py: Sichtungs-HTML-Generator (2026-06-09)** ← AKTUELL
- Wandelt Artikel-JSONs in druckfertige HTML-Sichtungsdatei um
- Alle Box-Typen (wow/fakt/stimmt_das/warnung), Quiz mit Antwort-Markierung, Bildliste
- Ausgabe: `articles/test_grounded/_review.html` (44 KB, 8 Artikel, nicht im Repo)
- Usage: `python scripts/render_review_html.py [--input <ordner>]`

**Gemini Batch API POC: 3/3 Artikel generiert (2026-06-09)**
- batch_run.py + dashboard.html implementiert und erfolgreich gelaufen
- **0 × 503 auf Batch-Calls** — Überlastungsproblem gelöst
- Gesamtlaufzeit: ~2h 6min (09:09–11:15)
  - Phase 1 Batch (Companion-Auswahl): ~33 Min
  - Bildpools + Companion-Texte: ~5 Min
  - Phase 2 Batch (Artikel-Generierung): ~47 Min
- Ergebnisse in articles/test_grounded/:
  - indianer_l1: title=Indianer | 2 sections | 11 sätze | 11 bilder | hero=En-chief-sitting-bull.jpg
  - indianer_l2: title=Indianer | 4 sections | 20 sätze | 9 bilder | hero=En-chief-sitting-bull.jpg
  - indianer_l3: title=Indianer | 6 sections | 30 sätze | 8 bilder | hero=En-chief-sitting-bull.jpg
  - review_flag=False bei allen drei — kein Lektorat-Pflicht-Flag
- biene_l3 + demokratie_l1: Wikipedia-429 beim Fetch (Fix committed: Dedup + Delays)

**image_vision_filter.py: Wurzelfix Wikimedia-Rate-Limit (Commit 6c4c159)**
- Originale statt Thumbnails → 0×429, 30/30 Downloads, 1 API-Request

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung der 3 generierten Artikel** (vor Upload):
- Datei: `articles/test_grounded/_review.html` (lokal, nicht im Repo)
- Im Browser öffnen oder drucken — alle Artikel auf eigenen Seiten
- Prüfen: Inhalt aus Wikipedia-Quelltext? Altersstufen-Sprache korrekt? Bilder sinnvoll?
- ⛔ KEIN Upload vor manueller Sichtung

**batch_run.py Re-Run für biene_l3 + demokratie_l1** (kurz nach Sichtung):
```
python scripts/batch_run.py
```
(Fix für Wikipedia-429 bereits drin — Dedup + 1s/0.5s Sleep)

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** indianer_l1/l2/l3 (s.o.)
- **batch_run.py Re-Run** für biene_l3 + demokratie_l1
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **indianer_l2**: 20 Sätze — über Minimum, kein review_flag

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
