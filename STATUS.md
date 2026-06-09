# Wissensfreund — STATUS
<!-- updated: 2026-06-09T10:27:16Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Modell-Vergleichslauf: 4/4 Artikel generiert (2026-06-09)** ← AKTUELL
- Themen: Indianer + Biene | Stufe 3 | Bild-Pipeline deaktiviert
- Modelle: gemini-2.5-flash vs. gemini-3.5-flash (beide thinking=medium)
- Output: `articles/test_compare/` (lokal, nicht committed)
- Ergebnisse:

| Datei | Wörter | Sätze | Boxes | Companions |
|---|---|---|---|---|
| biene_2-5-flash_l3 | 558 | 38 | 3 | Westl. Honigbiene, Wildbiene, Hummeln, Bestäuber |
| biene_3-5-flash_l3 | 465 | 31 | 3 | Bienenkönigin, Hummeln, Wildbiene, Imker |
| indianer_2-5-flash_l3 | 587 | 31 | 4 | Kolumbus, Beringia, Ackerbau, Indianer Nordamerikas |
| indianer_3-5-flash_l3 | 485 | 30 | 3 | Indianer Nordamerikas, Besiedlung Amerikas, Azteken |

- Review-HTML: `articles/test_compare/_review.html` — Chips zeigen Modell-Methode als Chip
- Beobachtung: 2.5-flash wählt andere Companions als 3.5-flash, 2.5-flash schreibt ~20% mehr Wörter

**generate_grounded.py + gemini_client.py: Modell wählbar (Commit ac9404b)**
- `--gen-model`, `--skip-images`, `--output-dir` Args
- ThinkingConfig modellspezifisch: 2.5-flash → `thinking_budget`, 3.5-flash → `thinking_level=MEDIUM`
- `meta.generation_method` = "gemini-X.X-flash/medium" gesetzt

**render_review_html.py: Report-JSONs werden jetzt gefiltert (Commit folgt)**
- `*_report.json` werden beim Glob übersprungen

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung der Vergleichsartikel**:
- Datei: `articles/test_compare/_review.html` (lokal, 46 KB, 4 Artikel)
- Im Browser öffnen — 2.5-flash vs 3.5-flash direkt nebeneinander (Chip im Header)
- ⛔ KEIN Upload vor Sichtung

**batch_run.py Re-Run für biene_l3 + demokratie_l1** (test_grounded):
- Fix für Wikipedia-429 bereits drin
- `python scripts/batch_run.py`

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** Vergleichsartikel (s.o.)
- **Sichtung** indianer_l1/l2/l3 aus test_grounded
- **batch_run.py Re-Run** für biene_l3 + demokratie_l1
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **indianer_l2**: 20 Sätze — über Minimum, kein review_flag

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2 — vor Aktivierung löschen

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
