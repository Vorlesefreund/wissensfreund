# Wissensfreund — STATUS
<!-- updated: 2026-06-08T13:41:15Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Pipeline v3.20 Setup abgeschlossen (2026-06-08)** ← AKTUELL
- `wissensfreund_generator_prompt_v3.20_production.md`: JSON-Ausgabeformat, planung-Block zuerst,
  Schema v1.0, s001 global fortlaufend, img_index -1 erlaubt
- `scripts/generate_articles.py`: 4 Fixes: planung-Strip vor JSON-Parse, --system-prompt Default,
  img_index -1 im Validator erlaubt, generated_at aus Validator-Pflichtfeldern entfernt
- `scripts/test_batch_5topics.json`: 5 Themen als Referenz-Format
- `jobs/test_5topics/batch_0001.json`: 15 Jobs (5 × 3 Stufen) für generate_articles.py
- `articles/test_5topics/`: Output-Verzeichnis angelegt
- SCHRITT 4–6 ausstehend: brauchen ANTHROPIC_API_KEY + R2-Credentials

**Generator v3.19 + Lektorat v2.9 in main gemergt (2026-06-08)**
- v3.19: themenneutrale Bereicherungs-Links, BEREICHERUNGS_LINKS-Feld, Primärartikel-Regel
- v2.9: Planungs-Check prüft planung-Block-Konsistenz vor Durchgang A

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored`
3. Dann Ordner löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch — Pipeline-Testlauf ausstehend
- **SCHRITT 4**: 15 Artikel generieren — `! $env:ANTHROPIC_API_KEY="sk-..."` setzen, dann:
  `python scripts/generate_articles.py --jobs-dir jobs/test_5topics --out-dir articles/test_5topics --batch 0001`
- **SCHRITT 5**: Bilder patchen — `python scripts/patch_article_images_v1.py --articles-dir articles/test_5topics/`
- **SCHRITT 6**: R2-Upload — `python scripts/upload_articles.py --articles-dir articles/test_5topics/` (CF_R2_* setzen)
- **Flash-Testlauf v3.19 auf Römer** — dann Modellentscheidung
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Mittel
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3 fehlen als Code-Filter)
- **R2-Koexistenz:** upload_articles.py rclone sync überschreibt ZIM + WF-Artikel
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Gemini-TTS-Idee, Links/Topic-Tree, Upgrade-Dialog
