# Wissensfreund — STATUS
<!-- updated: 2026-06-06T14:02:30Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Pipeline v3.8 + Lektorat v2 (2026-06-06)**
- wissensfreund_system_prompt_v3.8.md erstellt (Basis: v3.7(4), alle 5 Änderungen aus Änderungsdokument)
  1. Belegtreue: Gedächtnis-Sonderregel (Einzelleistung ≠ allgemeine Fähigkeit)
  2. Callout-Regeln: Box-Eigenständigkeit (kein Satzfortsatz des Vorgängerabsatzes)
  3. Häufige Fehler #7 (Intro↔stimmt_das-Widerspruch) + #8 (Konfabulierte Komposita) + Kurz-Check erweitert
  4. Schlussschritt: 4-Zeilen-Fließtext → strukturierte 15-Zeilen-Checkliste
  5. Sprachregeln: Prosa-Rhythmus-Bullet nach „Handwerk:"
- generate_articles.py Docstring: --system-prompt Beispiel auf v3.8 aktualisiert
- wissensfreund_lektorat_v2.md liegt korrekt im Repo (kein Archivieren nötig, keine v1 vorhanden)
- KORREKTUR: Lektorat war nie in generate_articles.py integriert — nur ein call_claude_api()-Aufruf.
  Lektorat läuft als manueller Standalone-Prompt.

**v3.7-Vertrag: generate_articles.py + Prompt-Archiv bereinigt (2026-06-05)**
- build_user_message() auf v3.7; wissensfreund_system_prompt_v3.7(4).md als kanonische v3.7-Datei
- SLUG_ALIASES: einstein, mozart, beethoven u.a.; JSON: 1000→1018 Einträge; WF-Lücken: 64→46

**klexikon_appeal_quartil.json + Pipeline-Integration (2026-06-05)**
- 1.000 Einträge: Q1/high = 277; Q2/medium = 723
- prepare_articles.py: setzt KLEXIKON_AUFRUF_QUARTIL pro Job-Eintrag

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored` in wissensfreund_app
3. Dann Ordner löschen

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Mozart-Neulauf mit v3.8 + Lektorat v2 ausstehend** — erster Validierungsrun der neuen Prompts
- **Lektorat-Pipeline-Integration zurückgestellt** bis Generator- und Lektorats-Prompt stabil
  (Lektorat läuft vorerst als manueller Standalone-Prompt)
- **Related Terms** (WIKIPEDIA_LINKS + ARTICLE_INDEX): prepare_articles.py befüllt sie noch nicht;
  generate_articles.py überspringt sie lautlos. Details: CLAUDE_CHAT_NOTIZEN.md
- **Kanonische Prompt-Datei für CI/Workflow:** `--system-prompt` braucht expliziten Pfad.
  Aktuell: `wissensfreund_system_prompt_v3.8.md`.

### Mittel
- **Content-Sicherheitsfilter Bilder** (Stufen 2+3 fehlen als Code-Filter, vor Bilder-Patch-Run klären)
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
