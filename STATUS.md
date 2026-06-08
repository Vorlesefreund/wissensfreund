# Wissensfreund — STATUS
<!-- updated: 2026-06-08T15:23:23Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**R2-Upload abgeschlossen (2026-06-08)** ← AKTUELL
- 10 Artikel + 17 Index-/Meta-Dateien in Bucket `wissensfreund-articles` hochgeladen
- Basis-URL: https://pub-a4cddbe0f7104b91ae193707a08ff0d2.r2.dev
- upload_articles.py: dotenv-Laden + rclone via winget installiert + Windows-Path-Bug gefixt

**⚠️ R2-KOEXISTENZ-PROBLEM aufgetreten:**
- rclone sync hat 3546 bestehende Dateien (staging/articles_zim/) GELÖSCHT
- Diese ZIM-Artikel sind weg — vor dem nächsten Upload prüfen ob sie anderweitig gesichert sind
- Fix nötig: rclone sync durch rclone copy ersetzen ODER gezielten Bucket-Pfad nutzen

**Tatsächliche meta.id in R2 (Gemini nutzt Wikipedia-Titel als Slug):**
- articles/bienen_l1.json (nicht biene_l1)
- articles/demokratie_l1.json · demokratie_l2.json · demokratie_l3.json
- articles/indigene_voelker_l1.json · indigene_voelker_l2.json
- articles/indigene_voelker_amerikas_l3.json
- articles/motor_l1.json · motor_l2.json
- articles/tropischer_regenwald_l1.json (nicht dschungel_l1)

**5 Artikel fehlgeschlagen (Gemini Free-Tier Quota)**
- biene_l2: JSON-Parse-Fehler · biene_l3: Validation (img_index=None) → _errors/
- motor_l3, dschungel_l2, dschungel_l3: Quota erschöpft → nach Reset nachgenerieren

---

## ⚠️ DRINGEND: R2-Koexistenz-Fix
rclone sync löscht alles was nicht im Staging ist. Fix-Optionen:
1. `rclone copy` statt `rclone sync` (empfohlen für Koexistenz)
2. Eigenen Sub-Pfad nutzen: `r2:wissensfreund-articles/wf_articles/`
→ in upload_articles.py ändern BEVOR nächster Upload

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)
**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — `scrape_out/` prüfen, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **R2-Koexistenz FIXEN** (rclone copy statt sync) vor nächstem Upload
- **5 fehlende Artikel nachgenerieren** (nach Quota-Reset):
  `python scripts/generate_articles.py --model flash --jobs-dir jobs/test_5topics
  --out-dir articles/test_5topics --batch 0001`
- **meta.id-Konvention**: Gemini nutzt Wikipedia-Slug statt Job-ID — angleichen
- **Lektorat-Pipeline-Integration** · **Related Terms**

### Mittel
- **Bilder-Patch mit KI** (braucht ANTHROPIC_API_KEY)
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3)

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
