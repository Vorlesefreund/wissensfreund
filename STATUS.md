# Wissensfreund — STATUS
<!-- updated: 2026-06-09T12:59:11Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**v3.21-Lebendigkeits-Paket: Prompt + Generierungs-Run (2026-06-09)** ← AKTUELL
- Prompt: `wissensfreund_generator_prompt_v3.21_production.md` (HAKEN, Lebendige Überschriften, Lebenswelt-Brücke, Klischee-dann-Auflösung)
- v3.20 archiviert → `_alt/`
- 3 Artikel generiert: Indianer L1/L2/L3 | gemini-3.5-flash | --skip-images → `articles/test_v321/`
- Phase 1: 503×3 für alle drei (Modell-Lastspitze) → companions=[] in allen drei
- Phase 2: erfolgreich | Überschriften leben: "Ein großer Irrtum", "Geniale Bauern und große Städte"
- Review-HTML: `articles/test_v321/_review.html` (lokal, 3 Artikel)

**Modell-Vergleichslauf vollständig: 12/12 Artikel (2026-06-09)**
- Themen: Indianer + Biene | Stufen 1–3 | beide Modelle | textonly (--skip-images)
- Output: `articles/test_compare/_review.html` (lokal, 12 Artikel, Sortierung: Thema→Stufe→Modell)

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung Vorher-Nachher**: v3.20 (test_compare) vs. v3.21 (test_v321) — Indianer L1/L2/L3
- ⛔ KEIN Lektorat, KEIN Upload vor Sichtung
- Einschränkung: alle v3.21-Artikel ohne Companions (Phase-1-503) — reiner Prompt-Effekt sichtbar

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** v3.20 vs. v3.21 Vergleich (s.o.)
- **batch_run.py Re-Run** biene_l3 + demokratie_l1 (test_grounded)
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **v3.21-Re-Run mit Companions**: wenn 3.5-flash-Phase-1-503s nachlassen (oder auf 2.5-flash wechseln)
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **Phase-1-Robustheit**: MAX_LINK_LIST > 300 oder alphabetisch neu ordnen (Tipi/Prärieindianer nicht erreichbar)

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
