# Wissensfreund — STATUS
<!-- updated: 2026-06-10T08:37:23Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Lektorat Catch-Test (2026-06-10)** ← AKTUELL
Goldset: 4 Slips (L1–L4) × 6 Kontrollen (K1–K6), handverifiziert.
Verifizierer-Ergebnis (tests/lektorat_catchtest_result.md, lokal):
- Claude Sonnet 4.6: Catch 4/4 | FP 1/6 (K6 Beringia — Grenzfall Formulierung)
- Claude Haiku 4.5:  Catch 2/4 | FP 0/6 (verpasst: L1 Pocahontas, L2 Maya)
- Gemini 2.5 Pro¹:  Catch 3/3 | FP 0/6 (¹L1 503-Abbruch — nicht auswertbar)
Fazit: Sonnet fängt alle, hat aber höchste FP-Rate. Haiku schärfer auf Kontrollen,
       blind auf subtile Quellen-Slips (ÜBERZOGEN/NICHT_BELEGT). Gemini teuer+langsam.
Infrastruktur: tests/lektorat_goldset.json + scripts/run_lektorat_catchtest.py
Anmerkung: gemini-3.1-pro → 404, Fallback gemini-2.5-pro. Primär-Input ungekürzt (kein Cap).

**Structured Output + Modell-Vergleich test_modelcompare2 (2026-06-10)**
3 Code-Fixes für fairen Modellvergleich:
- `gemini_client.py`: 6 Retries + Exponential Backoff (60/120/240/300s), response_mime_type + response_schema Parameter
- `generate_articles.py parse_article_json()`: Balanced-Brace-Extraktion (Trailing-Content wird ignoriert)
- `generate_grounded.py`: Structured Output Phase 1 (companions_schema) + Phase 2 (response_mime_type JSON)

Befund test_modelcompare2 (Indianer L1/L2/L3, --skip-images, v3.23):
- gemini-3.5-flash: 3/3 ✅ | 176/352/583W | Companions: Tipi, Wigwam+W., Sitting Bull, Bison, Wappenpfahl
- gemini-3.1-flash-lite: 3/3 ✅ | 160/301/387W | Companions: Indigene V., Tipi, Wappenpfahl, Büffel, Kanu (vorher 0/3 wegen Markdown-Output!)
- gemini-3-flash-preview: 2/3 ❌ | 222/374W/FAIL | L3 truncated (8233Z, kein '}') — Thinking frisst max_output_tokens

Alle Wortzahlen im WORTZIEL-Korridor (wo generiert). Review-HTML: articles/test_modelcompare2/_review.html (lokal)

**v3.23 + test_v323 (2026-06-10)**
- WORTZIEL explizit injiziert, Companion-Cap gestaffelt, Regionen-Ausgewogenheit Nordamerika
- L1: 200W / L2: 358W / L3: 613W — alle im Korridor | Appeal: high (klexikon-quartil)

**Robustness-Check + test_compass3b (2026-06-09)**
- FAILED_NO_COMPANIONS-Abbruch wenn Phase 1 keine Companions liefert

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung test_modelcompare2**: articles/test_modelcompare2/_review.html
- Qualitätsvergleich: 3.5-flash vs. 3.1-flash-lite (beide 3/3)
- 3-flash-preview L3 fehlt — ggf. mit max_output_tokens=16384 nachgenerieren
- ⛔ KEIN Lektorat, KEIN Upload vor Sichtung

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit setzen (Thinking frisst Budget)
- **Sichtung** test_v323 — WORTZIEL-Erstlauf (Regionen-Ausgewogenheit Nordamerika?)
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
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
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + v3.23 | Aktiv (Entwicklung) |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (Montag 03:00 UTC)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
