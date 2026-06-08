# Wissensfreund — STATUS
<!-- updated: 2026-06-08T19:59:11Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**image_vision_filter.py: Rate-Limit-Fix v2 (2026-06-08)** ← AKTUELL
- generator=images: 1 API-Request pro Artikel statt 2 (Wikipedia+Commons→nur Wikipedia)
- Lokaler Download-Cache: .cache/downloads/{md5}{ext} — Biene-Test: 12/12 aus Cache
- Lokaler Metadaten-Cache: .cache/image_meta_cache.json
- maxlag=5 + Retry-After-Header-Handling
- 2 parallele Download-Worker (ThreadPoolExecutor)
- Ergebnis "Biene": 1 Wikimedia-API-Request gesamt, 0 Wikimedia-Downloads, 0 429s
- Vergleich: vorher 2 Requests + bis zu 160s Retry-Schleife pro Bild

**url_context-Test + image_vision_filter.py (2026-06-08)**
- TEIL A: url_context empirisch verifiziert (commit 84041a8)
  - Primär-Fetch: URL_RETRIEVAL_STATUS_SUCCESS bestätigt
  - Sekundär-Links: Tool lehnt ab ("url does not match prompt")
  - Befund: url_context fetcht NUR explizit im Prompt genannte URLs
  - Konsequenz: Option B (Text-Injektion) bleibt richtiger Produktions-Weg
  - WISSEN_ARTIKEL_PIPELINE.md: Link-Folgen-Mechanismus + Befund dokumentiert
- TEIL B: image_vision_filter.py Rate-Limit-Fix (commit 84041a8)
  - User-Agent mit Kontakt-Mail (Wikimedia-Policy)
  - Backoff 10/30/60s, 4 Versuche, 2s Pause, Gemini-503-Retry
  - Test: 6/10 Bienen-Bilder akzeptiert, 0 Download-Fehler

**image_vision_filter.py (2026-06-08):**
- Neues Skript: Vision-basierter Bild-Filter via Gemini Flash (thinking_budget=0)
- Kindgerecht + Relevanz(0-10) + hero_tauglich pro Bild
- Dateiname-/Lizenz-Vorfilter, Hero-Auswahl, Ranking
- Speichert: articles/test_5topics/_images/{thema}_images.json

**Flash thinking=medium + IMAGE_METADATA im Generator (2026-06-08)**
- 15 Artikel mit echten Wikimedia-Bildern (Ø 4,2/Artikel)
- Datei: → File: Normalisierung für Wikimedia-Commons-API

**R2-Zustand (wissensfreund-articles)**
Basis-URL: https://pub-a4cddbe0f7104b91ae193707a08ff0d2.r2.dev
15 Artikel: biene/demokratie/dschungel/indianer/motor je l1/l2/l3

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln + Bilder prüfen
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Mittel
- **url_context Option A vollständig**: COMPANION_URL_1/2 in User-Message + url_context aktiv
  (Alternative zu Option B; Aufwand: generate_articles.py + System-Prompt anpassen)
- **Option B Begleitartikel**: generate_articles.py pre-fetcht 1-2 Wikipedia-Links,
  injiziert als WIKIPEDIA_TEXT_2/3 (empfohlener Ausbau-Pfad)
- **indianer_l2 review**: 14 Sätze statt 15 Minimum
- **Bilder-Qualität**: indianer_l1-l3 nur 1-3 Bilder
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
