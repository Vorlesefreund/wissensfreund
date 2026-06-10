# Wissensfreund — STATUS
<!-- updated: 2026-06-10T10:22:26Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Gegroundetes Lektorat Stufe 1 — Smoke-Test erfolgreich (2026-06-10)** ← AKTUELL
- `scripts/lektorat_common.py` (NEU): COMPANION_CHAR_CAP=30k, LEKTORAT_SYSTEM-Prompt mit Tier-Logik,
  build_grounded_sources_block, parse_lektorat_json (3-stufiger Fallback), annotate_article_lektorat,
  run_lektorat_batch (Anthropic Batch-API, max_tokens=16000).
- `scripts/generate_grounded.py`: --skip-lektorat, sources_block einmal pro Thema,
  Batch nach allen Stufen, [LEKTORAT N:A/V/E]-Log, GEMINI_MODEL-Default=gemini-3.5-flash.
- `scripts/run_lektorat_catchtest.py`: importiert aus lektorat_common (kein Drift).
- `scripts/render_review_html.py`: Prüfbericht-Panel mit Tier-Badges (AUTO=gelb, VORSCHLAG=orange, ESKALATION=rot).

Smoke-Test Indianer L1–L3 (gemini-3.5-flash, --skip-images, Batch msgbatch_01VySczot33):
- L1: 16 Aussagen | BELEGT:14 ÜB:2 | AUTO:2 | review_flag=False
- L2: 22 Aussagen | BELEGT:20 NB:1 ÜB:1 | AUTO:1 ESKALATION:1 | review_flag=True
- L3: 24 Aussagen | BELEGT:18 NB:4 ÜB:2 | AUTO:1 VORSCHLAG:4 ESKALATION:1 | review_flag=True

Parser-Fix: Dreistufiger Fallback (JSON-raw → _fix_inner_quotes → Strukturextraktion).
Root cause: Claude nutzt „Wort" (U+201E + U+0022) als dt. Anführungszeichen innerhalb
JSON-Strings; U+0022 terminiert den String vorzeitig. Fix: Case 1 „text"" → '" (inner " weg),
Case 2 „text" Text → replace mit '. Fallback: Strukturextraktion nach Schlüsselposition.

Review-HTML: articles/test_grounded/_review.html (lokal)

**artikel_pipeline.yml: schedule entfernt (2026-06-10)**
- `on: schedule` (cron "0 3 * * 1") entfernt — Pipeline läuft nicht mehr automatisch.

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung test_modelcompare2**: articles/test_modelcompare2/_review.html
- Qualitätsvergleich: 3.5-flash vs. 3.1-flash-lite (beide 3/3)
- 3-flash-preview L3 fehlt — ggf. mit max_output_tokens=16384 nachgenerieren
- ⛔ KEIN Upload vor Sichtung

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit setzen (Thinking frisst Budget)
- **Sichtung** test_v323 — WORTZIEL-Erstlauf
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Lektorat Stufe 2**: Auto-Korrektur-Schicht (Stufe 2 nach Stufe 1 Erkennung)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug (python scripts/ statt python root)

---

## Pipeline-Architektur (Referenz)

| Skript | Rolle | Status |
|---|---|---|
| `prepare_articles.py` | Batch-Vorbereitung (Job-JSONs) | Produktion |
| `generate_articles.py` | Artikel-Generierung (Claude/Gemini) | Produktion |
| `upload_articles.py` | Index + R2-Upload | Produktion |
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + Lektorat | Aktiv (Entwicklung) |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (manuell, kein Schedule)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
