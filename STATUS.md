# Wissensfreund — STATUS
<!-- updated: 2026-06-08T18:11:18Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Flash thinking=medium + IMAGE_METADATA im Generator (2026-06-08)** ← AKTUELL
- gemini_client.py: thinking_budget=0 → 8192 (Medium)
- generate_articles.py: AVAILABLE_IMAGES im Prompt — Flash wählt Bilder direkt
- Bug fix: Datei: → File: Normalisierung für Wikimedia-Commons-API
- Bug fix: .webm/.ogv/.svg gefiltert, stärkere Prefix/Substring-Filter
- fetch_images_for_article: max 30 Bilder, 429-Retry eingebaut
- validate_article: img_index-Obergrenze dynamisch (len(images[])-1)
- patch_article_images_v1.py: als Legacy-Tool markiert (nicht mehr für neue Artikel)
- 15 Artikel neu generiert mit echten Wikimedia-Bildern (Ø 4,2/Artikel, alle mit Hero)
- upload_articles.py: rclone auto-discovery (WinGet) — kein manueller PATH nötig

**R2-Zustand (wissensfreund-articles)**
Basis-URL: https://pub-a4cddbe0f7104b91ae193707a08ff0d2.r2.dev

articles/ — 15 Artikel mit echten Bildern:
- biene_l1 (7) · biene_l2 (5) · biene_l3 (8)
- demokratie_l1 (4) · demokratie_l2 (3) · demokratie_l3 (5)
- dschungel_l1 (2) · dschungel_l2 (6) · dschungel_l3 (10)
- indianer_l1 (1) · indianer_l2 (3, review) · indianer_l3 (2)
- motor_l1 (1) · motor_l2 (3) · motor_l3 (3)

index/global.json · level_1/2/3.json · cat_*.json · sub_*.json · new.json · topic_tree.json

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)
**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — `scrape_out/` prüfen, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln + Bilder prüfen
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Mittel
- **indianer_l2 review**: 14 Sätze statt 15 Minimum — ggf. Prompt-Tuning oder Minimum senken
- **Bilder-Qualität**: indianer_l1-l3 haben nur 1-3 Bilder (Wikipedia arm an Fotos)
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
