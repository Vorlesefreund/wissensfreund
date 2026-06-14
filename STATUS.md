# Wissensfreund — STATUS
<!-- updated: 2026-06-14T19:25:43Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**eignung_verdicts.json + categories_backlog.json (2026-06-14): catalog_verdicts_parser.py v1. 738 Verdicts (42 exclude, 231 age_floor>1, 529 framing_note). 118 categories_backlog-Einträge.** ← AKTUELL

**catalog_manual: Durst ergänzt (6 manuelle Themen gesamt).**

**catalog_merge: Annotations-Quelle = catalog_review_master.xlsx (permanent fix). Master wird nie überschrieben.**

**Round-3 + Merge (2026-06-14): 3968 primary / 162 reserve / 27 exclude / 479 sensibel / 194 Leuchtturm.**

Gebiets-Breakdown (primary):
Tiere 807 | Berühmte Personen 294 | Länder 250 | Naturwiss 246 | Pflanzen 239 |
Technik 221 | Geschichte 217 | Sport 212 | Kunst 184 | Essen 180 |
Körper 167 | Gesellschaft 147 | Erde 126 | Grundbegriffe 120 | Deutsche Städte 110 |
Märchen 102 | Naturräume 100 | Weltstädte 100 | Religion 83 | Weltall 63

### Pipeline-Zustand (generate_grounded.py, Stand 2026-06-12)
Ergiebigkeit verdrahtet ✅ | resolve_lemma im Hauptloop ✅ | Doppelbedeutungs-Direktive ✅
Wortzahl-Guard ✅ | Box-Verteilungs-Guard ✅ | Eignungs-Gate ✅
System-Prompt: v3.23b-production | Modell: gemini-3.5-flash

### Ergiebigkeits-Modell (Detail → WISSEN_ARTIKEL_PIPELINE.md)
`target_S = Wlo + frac·(Whi−Wlo), frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250] S2[80,400] S3[100,650]. Rater = Opus per API, Anker: 134 Themen.

---

## 🔴 Nächster Schritt

**eignung_verdicts.json in generate_grounded.py laden** (ersetzt bisherigen eignung_verdicts.json-Loader/Fallback).
Prüfen: exclude-Themen werden gefiltert, age_floor + framing_note korrekt weitergegeben.

---

## 🔴 Offene Punkte (nach Priorität)

eignung_verdicts.json in Pipeline verdrahten (generate_grounded.py) — nächster Chat
categories_backlog.json → categories-Array je Artikel (spätere Phase)
Dedup (Hai=Haie, Deutschland 3×; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); Flutter WfArticleListScreen
