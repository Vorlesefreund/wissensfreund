# Wissensfreund — STATUS
<!-- updated: 2026-06-08T14:30:15Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Gemini Flash API integriert (2026-06-08)** ← AKTUELL
- `scripts/gemini_client.py`: call_gemini(system_prompt, user_message) via google-genai
  Modell: gemini-2.5-flash · temperature=0.6 · GEMINI_API_KEY aus .env
- `scripts/generate_articles.py`: --model sonnet|flash (Standard: sonnet)
  + --test-connection Flag für schnellen API-Check
- `.gitignore`: .env-Eintrag hinzugefügt (war vorher nicht ignoriert)
- Test erfolgreich: `--model flash --test-connection` → "Gemini Flash OK: OK"
- Nächster Schritt: Flash-Testlauf auf 5-Themen-Batch (ANTHROPIC_API_KEY für Sonnet noch offen)

**Pipeline v3.20 Setup abgeschlossen (2026-06-08)**
- `wissensfreund_generator_prompt_v3.20_production.md`: JSON-Ausgabeformat, planung-Block zuerst
- `scripts/generate_articles.py`: planung-Strip, --system-prompt Default, img_index -1 erlaubt
- `jobs/test_5topics/batch_0001.json`: 15 Jobs (5 × 3 Stufen)

**Generator v3.19 + Lektorat v2.9 in main gemergt (2026-06-08)**
- v3.19: themenneutrale Bereicherungs-Links · v2.9: Planungs-Check

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. `git status` + `git status --ignored`, dann löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch — Pipeline-Testlauf ausstehend
- **Flash-Testlauf 5 Themen**: `python scripts/generate_articles.py --model flash
  --jobs-dir jobs/test_5topics --out-dir articles/test_5topics --batch 0001`
  (kein ANTHROPIC_API_KEY nötig, GEMINI_API_KEY in .env vorhanden)
- **Sonnet-Testlauf**: `! $env:ANTHROPIC_API_KEY="sk-..."` setzen, dann --model sonnet
- **SCHRITT 5**: Bilder patchen — `python scripts/patch_article_images_v1.py --articles-dir articles/test_5topics/`
- **SCHRITT 6**: R2-Upload — CF_R2_* Credentials setzen, dann upload_articles.py
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
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
