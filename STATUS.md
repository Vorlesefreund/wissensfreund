# Wissensfreund — STATUS
<!-- updated: 2026-06-05T20:58:37Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**klexikon_appeal_quartil.json + Pipeline-Integration (2026-06-05)**
- 1.000 Einträge: Q1/high (>5.000 Views 2022 + Top-10 2025) = 277; Q2/medium = 723
- Kein Wikipedia-Proxy — nur Klexikon-eigene Daten (Hilfe:Meistbesuchte_Artikel_2022 + Top-10-2025)
- ~2.600+ Artikel ohne Signal bekommen null (Feld weggelassen; Generator schätzt selbst)
- Slug-Normierung: Umlaute + Sonderzeichen; bekannte Plural→Singular-Mappings
- `scripts/build_klexikon_appeal.py`: einmaliges Build-Skript (Daten eingebettet), Dry-Run-Option
- `scripts/prepare_articles.py`: lädt JSON beim Start, setzt KLEXIKON_AUFRUF_QUARTIL="1"/"2"
  pro Job-Eintrag, lässt Feld weg bei kein Treffer. Auch _is_free_license() auf FAL+NC/ND-Stand
- Commit: 6254a21, gepusht

**FAL-Lizenz in Bild-Whitelist + NC/ND-Ausschluss (2026-06-05)**
- Kalibrier-Harness fand: Elephant_feces_in_the_wildlife.jpg (FAL) war fälschlich reject
- FAL/LAL/Free Art/Licence Art Libre in _is_free_license() ergänzt (3 Stellen)
- patch_article_images_v1.py: Lizenzfilter-Schritt nach fetch_commons_metadata() neu ergänzt
- WISSEN_BILDER.md: Doku-Fehler korrigiert + Kalibrier-Notiz Pilot Elefant

**Dokumentations-Checkpoint (2026-06-04)**
- WISSEN_ARTIKEL_PIPELINE.md reconciled, WISSEN_BILDER.md ergänzt
- STATUS.md ist einziger Handover-Kanal

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored` in wissensfreund_app
3. Dann Ordner löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Code↔v3.4-Prompt-Abgleich (nächste Aufgabe):** `generate_articles.py` sendet v3.2-Felder;
  v3.4 erwartet TOPIC_APPEAL, TOPIC_FAMILIARITY, WIKIPEDIA_LINKS, ARTICLE_INDEX, IMAGE_METADATA.
  Details: WISSEN_ARTIKEL_PIPELINE.md § System-Prompt-Versionslinie.
  Mapping: KLEXIKON_AUFRUF_QUARTIL → TOPIC_APPEAL (quartil 1 → "high", 2 → "medium", fehlt → "low")
  Außerdem: TOPIC_INTEREST → TOPIC_FAMILIARITY umbenennen? Klären.
- **Selbst produzierte Artikel** — Pipeline starten nach Prompt-Abgleich
- **Fehlende kanonische Prompt-Datei:** wissensfreund_system_prompt.md (ohne Versionssuffix)
  existiert nicht → Workflow-Variable zeigt darauf → Pipeline würde scheitern

### Mittel
- **Content-Sicherheitsfilter Bilder entscheiden (Kinderschutz):**
  Stufen 2+3 fehlen als aktiver Code-Filter. Vor Bilder-Patch-Run klären.
  Details: WISSEN_BILDER.md § Content-Sicherheit
- **Bilder-Patch** (patch_article_images_v1.py): erst nach Kinderschutz-Entscheidung
- **R2-Koexistenz:** upload_articles.py nutzt rclone sync → ZIM + WF-Artikel überschreiben sich.
  Getrennte Präfixe implementieren vor Pilot.
- **Epoch-Guard TTS-Callbacks**, **Mode B Lupe**, **Sound-Thumbnails** (App-Feinschliff)

### Niedrig / Klärungsbedarf
- Primärkategorie-Konvention, Box-Key (myth/stimmt/stimmt_das), ZIM→JSON Decode-Cap,
  Kiosk/Screen-Pinning, STT-Routing, Fire-OS, Bild-Tier-Werte

---

## 🧊 Reserve / auf Eis

- **Klexikon-Quiz-Run** (generate_quizzes.py): Auto-Trigger entfernt (2cc9779).
  Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen.

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline, Gemini-TTS-Idee
- Links/Topic-Tree, Upgrade-Dialog, Plus/Premium-Design
