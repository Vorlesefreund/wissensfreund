# Wissensfreund — STATUS
<!-- updated: 2026-06-18T09:51:46Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Zuletzt abgeschlossen

**Generalisierungstest: 4 neue Themen (generalize_test) — ABGESCHLOSSEN (2026-06-18)**

Ergebnisse: articles/generalize_test/ (articles + lektorat + review)
Word-Docs: articles/generalize_test/review/ (Wikinger, Blauwal, Pest, Photosynthese)

### Lektorat-Last generalize_test (v3.23f) vs. v3d-Baseline

| Artikel        | S | K | P | | Artikel          | S | K | P |
|---|---|---|---|---|---|---|---|---|
| wikinger_l1    | 1 | 2 | 1⚠| | photosynthese_l1 | 0 | 0 | 0 |
| wikinger_l2    | 0 | 0 | 0 | | photosynthese_l2 | 0 | 1 | 0 |
| wikinger_l3    | 3 | 2 | 1⚠| | photosynthese_l3 | 2 | 1 | 0 |
| blauwal_l1     | 0 | 0 | 0 | | pest_l1          | 1 | 0 | 1⚠|
| blauwal_l2     | 2 | 1 | 0 | | pest_l2          | 0 | 0 | 0 |
| blauwal_l3     | 2 | 1 | 0 | | pest_l3          | 5 | 1 | 0 |
| **GESAMT**     |**16**|**9**|**3**| | v3d-Baseline (18 Art.) |19|7|4|

Normiert: v3.23f 1,33S/1Art — v3d 1,05S/1Art | K: 0,75 vs 0,39 | P: 0,25 vs 0,22

### Evaluation der 3 Prinzipien + 1 Strategie

**P1 Substanz:** Generator produzierte für die 4 neuen Themen keine Tautologien/Leerformeln.
Kein einziger P1-Fund im Lektorat — Prinzip greift im Generator (kein Stoff zum Flaggen).

**P2 Vergleiche:** Alle generierten Vergleiche verwendeten eindeutige Bezugsobjekte
(«drei große Busse», «kleines Auto»). Keine P2-Korrektur nötig. Prinzip im Generator wirksam.

**P3 Ton/Epoche:** Lektorat korrekt: «Schätze» → «Reichtum» (Framing, wikinger_l1),
Helme «völlig glatt gestaltet» → «hatten keine Hörner» (sachliche Anachronismus-Korrektur).
Pest-Ton: angemessen ernst, keine Verharmlosung. Kein P3-Überkorrektur-Fall.

**S1 Kern-Strategie:** Pest_l1 fokussiert (1S+1P total), kein Nebenschauplatz-Problem.
Wikinger_l1 ähnlich einfach (1S+2K+1P). Keine S1-Überladung sichtbar.

**3 PRÜFEN-Flags** sind legitime Fakten-Fragen (kein P1/P2/P3-induziertes Überflaggen):
- wikinger_l1: Drachenkopf «guten Geister erschrecken» (Quelle: «vertreiben/aufbringen»)
- wikinger_l3: Opfer «unter freiem Himmel» (Quelle belegt Ort nicht explizit)
- pest_l1: «goldene Säule in Wien» (Quelle nennt keine goldene Säule)

**Fazit:** Prinzipien greifen im Generator, kein Overfitting. Lektorat-Last stabil.
Der höhere K-Wert (9 vs 7) spiegelt echte Sach-Korrekturen (Zahlenwerte, Superlative),
nicht Über-Korrekturen durch neue Prinzipien.

---

**Generator v3.23f: Einzelfunde → 3 Prinzipien + 1 Strategie (2026-06-18)**

- **P1 Substanz-Test** in CALLOUT-BOXEN: «Wenn diese Box/Satz gestrichen würde — verlöre das Kind etwas?»
- **P3 Ton/Epoche**: Rule 46 von «Verniedlichung» zu vollständigem Prinzip erweitert
- **P2 Vergleiche**: Neue Rule 47 (eindeutiges Bezugsobjekt + rechnerisch korrekt + stufenkonsistent)
- **S1 Kern-Strategie**: SCHWERE INHALTE S1 erweitert — Kern destillieren, Nebenschauplätze vermeiden
- Lektorat: FRAMING-TON-EPOCHENPASSUNG + SUBSTANZ-PRÜFUNG + VERGLEICHE neu

---

## mini_s2_v3d: Referenzergebnisse

| Artikel | S | K | P | | Artikel | S | K | P |
|---|---|---|---|---|---|---|---|---|
| elefant_l1 | 0 | 0 | 0 | | dinosaurier_l1 | 0 | 0 | 0 |
| elefant_l2 | 0 | 0 | 0 | | dinosaurier_l2 | 2 | 1 | 0 |
| elefant_l3 | 0 | 2 | 0 | | dinosaurier_l3 | 5 | 1 | 1 ⚠ |
| hund_l1 | 1 | 0 | 0 | | vulkan_l1 | 0 | 0 | 0 |
| hund_l2 | 1 | 0 | 0 | | vulkan_l2 | 0 | 0 | 0 |
| hund_l3 | 0 | 2 | 0 | | vulkan_l3 | 2 | 0 | 2 ⚠ |
| spartacus_l1 | 0 | 0 | 0 | | zwk_l1 | 1 | 0 | 0 |
| spartacus_l2 | 2 | 0 | 0 | | zwk_l2 | 4 | 0 | 1 ⚠ |
| spartacus_l3 | 1 | 1 | 0 | | zwk_l3 | 0 | 0 | 0 |
| **GESAMT** | **19** | **7** | **4** | | | | | |

---

## Offen nach Priorität

### Baustein 3 — tts_produce.py (Produktions-TTS)
### Baustein 4 — Quiz-Vertonung
### Flutter/App-Fixes (WfArticleListScreen, Quiz/stimmt_das schema mismatch)

---

## Pipeline-Zustand (Stand 2026-06-18)

| Baustein | Datei | Status |
|---|---|---|
| Artikel-Generierung | generate_grounded.py | ✅ lauffähig |
| Generator-Prompt | v3.23_production.md | ✅ v3.23f (P1/P2/P3/S1) |
| Lektorat-System | lektorat_common.py | ✅ v3.23f (Framing+Ton+Substanz+Vergleiche) |
| Batch Stage 1-3 | run_batch.py | ✅ generalize_test abgeschlossen |
| Review-Docs | create_review_docs.py | ✅ --themen + --theme-lektorat |
| TTS-Generierung | tts_produce.py | ❌ fehlt |
| Cost-Tracking | cost_tracker.py | ✅ verdrahtet |

Catalog: **4346 primary**, 213 Leuchtturm, 563 sensibel, 56 exclude
