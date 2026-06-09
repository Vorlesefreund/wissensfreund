# Wissensfreund — STATUS
<!-- updated: 2026-06-09T11:42:32Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Modell-Vergleichslauf vollständig: 12/12 Artikel (2026-06-09)** ← AKTUELL
- Themen: Indianer + Biene | Stufen 1–3 | beide Modelle | textonly (--skip-images)
- Output: `articles/test_compare/_review.html` (lokal, 12 Artikel, Sortierung: Thema→Stufe→Modell)
- 2 Artikel ohne Companions (Phase-1-503 nach 3×Retry): indianer_3-5-flash_l1, biene_3-5-flash_l2

| Datei | L | Sätze | Companions |
|---|---|---|---|
| biene_2-5-flash_l1 | 1 | 18 | Westl. Honigbiene, Wildbiene, Bestäuber, Honig |
| biene_2-5-flash_l2 | 2 | 25 | Westl. Honigbiene, Wildbiene (2 × 429) |
| biene_2-5-flash_l3 | 3 | 38 | Westl. Honigbiene, Wildbiene, Hummeln, Bestäuber |
| biene_3-5-flash_l1 | 1 | 22 | Honig, Hummeln, Bienenkönigin |
| biene_3-5-flash_l2 | 2 | 24 | — (Phase-1-503) |
| biene_3-5-flash_l3 | 3 | 31 | Bienenkönigin, Hummeln, Wildbiene, Imker |
| indianer_2-5-flash_l1 | 1 | 25 | Ackerbau, Azteken, Kartoffel, Bisons |
| indianer_2-5-flash_l2 | 2 | 20 | Kolumbus, Besiedlung Amerikas, Ackerbau, Azteken |
| indianer_2-5-flash_l3 | 3 | 31 | Kolumbus, Beringia, Ackerbau, Indianer Nordamerikas |
| indianer_3-5-flash_l1 | 1 | 23 | — (Phase-1-503) |
| indianer_3-5-flash_l2 | 2 | 25 | Kolumbus, Amerikanischer Bison, Azteken |
| indianer_3-5-flash_l3 | 3 | 30 | Indianer Nordamerikas, Besiedlung Amerikas, Azteken |

**Beobachtungen:**
- 2.5-flash: mehr Sätze (Biene L3: 38 vs. 31), tendenziell mehr Text
- 3.5-flash: 503s auf Phase 1 häufiger als 2.5-flash bei Lastspitzen
- ThinkingConfig korrekt geloggt: 2.5-flash → thinking_budget, 3.5-flash → thinking_level=MEDIUM

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung der Vergleichsartikel**:
- Datei: `articles/test_compare/_review.html` (lokal, Thema→Stufe→Modell sortiert)
- Stufenleiter je Modell direkt untereinander
- ⛔ KEIN Upload vor Sichtung

**batch_run.py Re-Run für biene_l3 + demokratie_l1** (test_grounded):
- `python scripts/batch_run.py`

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** Vergleichsartikel (s.o.)
- **Sichtung** indianer_l1/l2/l3 aus test_grounded
- **batch_run.py Re-Run** biene_l3 + demokratie_l1
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln

### Mittel
- **Lektorat-Pipeline-Integration** (manueller Standalone-Prompt)
- **Related Terms**: prepare_articles.py befüllt sie noch nicht
- **biene_3-5-flash_l2 + indianer_3-5-flash_l1**: ggf. mit Companions neu generieren

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
