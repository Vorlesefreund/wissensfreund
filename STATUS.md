# Wissensfreund — STATUS
<!-- updated: 2026-06-08T15:34:33Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**R2-Koexistenz + meta.id-Fix (2026-06-08)** ← AKTUELL
- upload_articles.py: rclone sync → rclone copy (löscht nie Bestandsdaten)
- generate_articles.py: meta.id = article_id aus dem Job-Batch erzwungen
- indigene_voelker_l3.json: meta.id korrigiert + altes indigene_voelker_amerikas_l3.json aus R2 gelöscht
- R2 articles/ Verzeichnis jetzt konsistent (10 Artikel, alle korrekt benannt)

**R2-Zustand (wissensfreund-articles, Basis-URL: https://pub-a4cddbe0f7104b91ae193707a08ff0d2.r2.dev)**
- articles/bienen_l1.json
- articles/demokratie_l1.json · l2.json · l3.json
- articles/indigene_voelker_l1.json · l2.json · l3.json
- articles/motor_l1.json · l2.json
- articles/tropischer_regenwald_l1.json

**Pipeline v3.20: 10/15 Artikel generiert (2026-06-08)**
- 5 Artikel fehlgeschlagen: biene_l2 (JSON-Fehler), biene_l3 (_errors/),
  motor_l3/dschungel_l2/l3 (Gemini Free-Tier Quota: 20 req/Tag)
- Nach Quota-Reset nachgenerieren (Checkpoint überspringt erledigte 10)

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)
**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — `scrape_out/` prüfen, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **5 fehlende Artikel nachgenerieren** (nach Quota-Reset):
  `python scripts/generate_articles.py --model flash --jobs-dir jobs/test_5topics
  --out-dir articles/test_5topics --batch 0001`
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
