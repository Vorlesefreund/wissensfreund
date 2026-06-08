# Wissensfreund — STATUS
<!-- updated: 2026-06-08T16:28:00Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Complete 5-topic batch: alle 15 Artikel in R2 (2026-06-08)** ← AKTUELL
- Alle 15 Artikel generiert (Flash), Bilder gepatcht, in R2 hochgeladen
- img_index None→-1 Normalisierung in parse_article_json (generate_articles.py)
- motor_l3: aus _errors/ gerettet (38× img_index None normalisiert)
- rclone auto-discovery in upload_articles.py (WinGet-Pfad fallback)
- upload_articles.py: rclone copy (nie sync) — R2-Bestandsdaten bleiben erhalten

**R2-Zustand (wissensfreund-articles)**
Basis-URL: https://pub-a4cddbe0f7104b91ae193707a08ff0d2.r2.dev

articles/
- biene_l1.json · biene_l2.json · biene_l3.json
- demokratie_l1.json · demokratie_l2.json · demokratie_l3.json
- dschungel_l1.json · dschungel_l2.json · dschungel_l3.json
- indianer_l1.json · indianer_l2.json · indianer_l3.json
- motor_l1.json · motor_l2.json · motor_l3.json

index/global.json · level_1/2/3.json · cat_*.json · sub_*.json · new.json · topic_tree.json
meta/pipeline_run.json

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)
**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — `scrape_out/` prüfen, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Flutter-App: R2-Artikel anzeigen** — App auf die neuen JSON-Endpunkte umstellen
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Mittel
- **Bilder-Patch mit KI** (braucht ANTHROPIC_API_KEY für call_claude_image_filter)
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3 fehlen als Code-Filter)
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
