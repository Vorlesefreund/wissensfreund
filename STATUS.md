# Wissensfreund — STATUS
<!-- updated: 2026-06-09T04:07:51Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**generate_grounded.py: FIX 1/2/3 implementiert + getestet (2026-06-08/09)** ← AKTUELL
- FIX 1: thema (Anzeigetitel) vs. primaer_wikipedia (Faktenquelle) getrennt
  - meta.title IMMER aus thema — "Indianer"-Bug verhindert
  - build_user_message nutzt thema als ARTICLE_TITLE
- FIX 2: Zwei-Phasen-Generierung bereits vorhanden, bestätigt
- FIX 3: Bildpool-Caps: Primär max 20, Companion max 6, Gesamt max 40
  - Sequentieller Download (kein prefetch_images) — verhindert Wikimedia-IP-Block
  - 10s Sleep zwischen Downloads, 300s Cooldown nach 3 Fehlern
- TEST (5 Artikel): 0 generiert — ausschließlich Infrastruktur-Fehler:
  - indianer_l1/l2: Gemini Flash 503 ×3 um Mitternacht (Spitzenlast)
  - indianer_l3/biene_l3/demokratie_l1: DNS-Fehler ab 01:09 (getaddrinfo failed)
- Code-Korrektheit BESTÄTIGT durch Phase-1-Logs:
  - Bildpool-Caps korrekt: Indianer=17(≤20), Kolumbus=6(≤6)
  - Companion-Qualität top: l2=[Indianer Nordamerikas, Besiedlung Amerikas, Kolumbus, Ackerbau]
  - thema="Indianer" in allen Headern

**image_vision_filter.py: Rate-Limit-Fix v2 (2026-06-08)**
- generator=images: 1 API-Request pro Artikel statt 2
- Download-Cache .cache/downloads/{md5}{ext} + Metadaten-Cache image_meta_cache.json
- maxlag=5, 2 parallele Worker (nur standalone run())
- Biene-Test: 1 Wikimedia-API-Request, 12/12 aus Cache, 0 429s

---

## 🔴 Nächster Schritt (Hoch)

**Re-Run generate_grounded.py** (tagsüber, nach Wikimedia-IP-Cooldown):
```
python scripts/generate_grounded.py --articles indianer_l1 indianer_l2 indianer_l3 biene_l3 demokratie_l1
```
- 17 Bilder im Cache (.cache/downloads/) → Indianer-Runs schneller
- Erwartete Laufzeit: ~15-30 Min je Artikel (hauptsächlich Vision-Phase)
- Prüfen: meta.title="Indianer", Companions, Bildanzahl, Inhalt aus Quelltext

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Re-Run generate_grounded.py** (s.o.) → Artikel fertigstellen
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln + Bilder
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)

### Mittel
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **indianer_l2 review**: 14 Sätze statt 15 Minimum (nach Re-Run prüfen)
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
