# Wissensfreund — STATUS
<!-- updated: 2026-06-09T14:02:59Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Kompass-Pipeline + Lauf: Indianer L1/L2/L3 (2026-06-09)** ← AKTUELL
- Phase 1 auf freien Kompass umgestellt (kein Link-Pool mehr)
- Companion-Validierung: Wikipedia-Existenz + Redirect-Auflösung via MediaWiki API
- Phase 1 einmalig pro Thema; Quellblock über alle 3 Stufen geteilt + gecacht
- AGE_LEVEL am Ende der User-Message → stabiler Prefix für Gemini-Caching

**Befund Kompass-Lauf (gemini-3.5-flash, --skip-images → articles/test_compass/):**
- Kompass-Vorschlag (roh): Tipi, Totempfahl, Sitting Bull, Amerikanischer Bison, Pueblo (Siedlung)
- Aufgelöst: Totempfahl → Wappenpfahl
- Verworfen: keine
- Validiert (final): **Tipi, Wappenpfahl, Sitting Bull, Amerikanischer Bison, Pueblo (Siedlung)**
- Phase 1 lief EINMAL (nicht 3×); alle 3 Stufen teilen denselben Quellblock
- L1: 23 Sätze | L2: 28 Sätze | L3: 45 Sätze | alle ohne Fehler
- Review-HTML: articles/test_compass/_review.html (lokal)

**v3.21-Lebendigkeits-Paket + test_v321 (2026-06-09):**
- Prompt v3.21, 3 Artikel Indianer L1/L2/L3 | companions=[] (Phase-1-503 wg. Modell-Last)

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung Kompass-Artikel**: articles/test_compass/_review.html
- Tipi und Wappenpfahl erstmals als Companions erreichbar — Qualitätsgewinn prüfen
- ⛔ KEIN Lektorat, KEIN Upload vor Sichtung

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_compass vs. test_v321 (ohne Companions) — Kompass-Effekt
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1 (test_grounded)
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## Pipeline-Architektur (Referenz)

| Skript | Rolle | Status |
|---|---|---|
| `prepare_articles.py` | Batch-Vorbereitung (Job-JSONs) | Produktion |
| `generate_articles.py` | Artikel-Generierung (Claude/Gemini) | Produktion |
| `upload_articles.py` | Index + R2-Upload | Produktion |
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + v3.21-Prompt | Aktiv (Entwicklung) |
| `batch_run.py` | POC: Gemini Batch API (5 Testartikel) | Veraltet, nicht Produktionspfad |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (Montag 03:00 UTC)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
