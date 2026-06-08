# Wissensfreund — STATUS
<!-- updated: 2026-06-08T12:10:23Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Generator v3.19 + Lektorat v2.9 in main gemergt (2026-06-08)** ← AKTIV
- Generator v3.19 + Lektorat v2.9 sind in main gemergt. Beide Feature-Branches gelöscht.
- v3.19: allgemeine Bereicherungs-Link-Logik (themenneutral); BEREICHERUNGS_LINKS-Feld im
  planung-Block; Primärartikel-Regel bei Begriffsklärung; allgemeiner Salienz-Check
- v2.9: Planungs-Check prüft planung-Block-Konsistenz vor Durchgang A
- wissensfreund_generator_prompt_v3.18_neutral.md → _alt/ archiviert
- Nächster Schritt: Flash (mittel) mit v3.19 auf Römer re-testen, dann Modellentscheidung

**Generator v3.16 + Lektorat v2.7: Einzel-Quelle/Boxen/nur-Trigger (2026-06-08)** ← überholt
- wissensfreund_generator_prompt_v3.16_neutral.md: Einzel-Quelle, Box-Budget, nur-PFLICHT-TRIGGER
- wissensfreund_lektorat_v2.md (v2.7): Durchgang A + B spiegeln Generator v3.16

**Pipeline v3.8 + Lektorat v2 (2026-06-06)**
- wissensfreund_system_prompt_v3.8.md (5 Änderungen); Lektorat manueller Standalone-Prompt

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored`
3. Dann Ordner löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Flash-Testlauf v3.19 auf Römer (mittel)** — dann Modellentscheidung
- **Lektorat-Pipeline-Integration zurückgestellt** (manueller Standalone-Prompt)
- **Related Terms** (WIKIPEDIA_LINKS + ARTICLE_INDEX): prepare_articles.py befüllt sie noch nicht
- **Kanonische Prompt-Datei für CI:** `wissensfreund_system_prompt_v3.8.md`

### Mittel
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3 fehlen als Code-Filter)
- **Bilder-Patch**: erst nach Kinderschutz-Entscheidung
- **R2-Koexistenz:** upload_articles.py rclone sync überschreibt ZIM + WF-Artikel
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails**

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap, Kiosk/Screen-Pinning

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Gemini-TTS-Idee, Links/Topic-Tree, Upgrade-Dialog
