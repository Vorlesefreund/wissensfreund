# Wissensfreund — STATUS
<!-- updated: 2026-06-14T16:36:46Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Round-3 + Merge (2026-06-14): 11/12 R3-Calls erfolgreich (Tiere R3-C: nur 7 Themen, Avoid-List=636 erschöpft). Merge: 3968 primary / 162 reserve / 27 exclude / 479 sensibel / 194 Leuchtturm.** ← AKTUELL

Gebiets-Breakdown (primary):
Tiere 807 | Berühmte Personen 294 | Länder 250 | Naturwiss 246 | Pflanzen 239 |
Technik 221 | Geschichte 217 | Sport 212 | Kunst 184 | Essen 180 |
Körper 167 | Gesellschaft 147 | Erde 126 | Grundbegriffe 120 | Deutsche Städte 110 |
Märchen 102 | Naturräume 100 | Weltstädte 100 | Religion 83 | Weltall 63

**catalog_delta_r2.py + Annotation-Fix (2026-06-14): Delta-Excel mit 916 R2-Einträgen (79 sensibel, 5 manuell/grün).**

**catalog_manual.json: 5 Geschichte-Themen (Rank 182–302). Merge: 3432 primary / 96 reserve / 30 exclude.**

**Round-2 + Merge: 11/11 R2-Calls, 3427 primary / 96 reserve / 30 exclude, 431 sensibel, 177 Leuchtturm.**

**Katalog-Batch-Lauf abgeschlossen: 24/24 Gebiete, 3274 Themen roh, 3170 primary / 104 reserve, 447 sensibel, 179 Leuchtturm.**

### Pipeline-Zustand (generate_grounded.py, Stand 2026-06-12)
Ergiebigkeit verdrahtet ✅ | resolve_lemma im Hauptloop ✅ | Doppelbedeutungs-Direktive ✅
Wortzahl-Guard ✅ | Box-Verteilungs-Guard ✅ | Eignungs-Gate ✅
System-Prompt: v3.23b-production | Modell: gemini-3.5-flash

### Ergiebigkeits-Modell (Detail → WISSEN_ARTIKEL_PIPELINE.md)
`target_S = Wlo + frac·(Whi−Wlo), frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250] S2[80,400] S3[100,650]. Rater = Opus per API, Anker: 134 Themen.

---

## 🔴 Nächster Schritt

**Nächster Schritt:** catalog_review.xlsx öffnen → FREIGABE-Spalte befüllen (479 sensibel + 27 exclude prüfen) → eignung_verdicts.json generieren.
Tiere 807 primary (größtes Gebiet). Berühmte Personen 294, Länder 250, Naturwiss 246, Pflanzen 239.

---

## 🔴 Offene Punkte (nach Priorität)

Katalog Excel-Freigabe (479 sensibel + 27 exclude → eignung_verdicts.json) — nächster Chat
Dedup (Hai=Haie, Deutschland 3×, Zigarette=Zigaretten; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); test_modelcompare2 Sichtung; Flutter WfArticleListScreen
