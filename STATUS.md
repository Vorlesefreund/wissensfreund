# Wissensfreund — STATUS
<!-- updated: 2026-06-08T14:57:56Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Pipeline v3.20 production: 10/15 Artikel mit Flash generiert (2026-06-08)** ← AKTUELL
- 10 Artikel in articles/test_5topics/ (biene_l1, demokratie_l1-l3, dschungel_l1,
  indianer_l1-l3, motor_l1-l2) — Bilder gepacht (Fallback ohne KI)
- Staging OK: upload_staging_test/ (10 Artikel, Indices für alle Kategorien)
- **R2-Upload ausstehend**: CF_R2_ACCESS_KEY_ID / CF_R2_SECRET_ACCESS_KEY / CF_ACCOUNT_ID setzen
  dann: `python scripts/upload_articles.py --articles-dir articles/test_5topics/
  --topic-tree wissensfreund_topic_tree.json`
- Fixes in dieser Session: redirects=1 in fetch_wikipedia_text, ThinkingConfig(budget=0)
  in gemini_client, ValueError-Handler, upload_articles.py Windows-Path-Bug

**5 Artikel fehlgeschlagen (Gemini Free-Tier Quota: 20 req/Tag erschöpft)**
- biene_l2: JSON-Parse-Fehler (trailing comma im Modell-Output)
- biene_l3: Validierungsfehler (img_index=None) → in _errors/
- motor_l3, dschungel_l2, dschungel_l3: Quota erschöpft → morgen erneut ausführen

**Gemini Flash API integriert (2026-06-08)**
- gemini_client.py: call_gemini(), Rate-Limit-Retry (3×60s), ThinkingConfig(budget=0)
- generate_articles.py: --model sonnet|flash, --test-connection, redirects=1

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)
**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — `scrape_out/` prüfen, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **5 fehlende Artikel nachgenerieren** (morgen, Quota Reset):
  `python scripts/generate_articles.py --model flash --jobs-dir jobs/test_5topics
  --out-dir articles/test_5topics --batch 0001`
- **R2-Upload**: CF_R2_ACCESS_KEY_ID / CF_R2_SECRET_ACCESS_KEY / CF_ACCOUNT_ID setzen
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Mittel
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3 fehlen als Code-Filter)
- **R2-Koexistenz:** upload_articles.py rclone sync überschreibt ZIM + WF-Artikel
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**
- **Bilder-Patch mit KI** (braucht ANTHROPIC_API_KEY für call_claude_image_filter)

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
