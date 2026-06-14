# Wissensfreund — STATUS
<!-- updated: 2026-06-14T20:45:06Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**sound_sourcing.py v1 angelegt (2026-06-14).** ← AKTUELL
- 40 Ambient-Kategorien (Natur/Gesellschaft/Geschichte/Technik/Besonderes)
- 30 Spot-Kategorien (Tiere, Fahrzeuge, Effekte)
- Workflow: `--phase search` → HTML-Review → `sound_approvals_*.json` → `--phase finalize`
- Freesound API, nur CC0-Lizenzen, Preview-MP3-Downloads
- Abhängigkeit: `requests` (bereits installiert 2.32.5)
- Nächster Schritt: FREESOUND_API_KEY in `.env` eintragen, dann `python sound_sourcing.py --phase search --type ambient`

**generate_grounded.py: eignung_verdicts.json vollständig verdrahtet (2026-06-14).**
- Bug 1 gefixt: `_load_eignung()` normiert Keys auf `.lower()` → Lookup trifft jetzt
- Bug 2 gefixt: `eignung_for()` liest neues Schema (`exclude:true` statt `eignung:"exclude"`)
- Dry-Run bestanden: exclude/age_floor=3/framing_note alle korrekt

**eignung_verdicts.json + categories_backlog.json (2026-06-14): 738 Verdicts (42 exclude, 231 age_floor>1, 529 framing_note). 118 categories_backlog.**

**Round-3 + Merge (2026-06-14): 3968 primary / 162 reserve / 27 exclude / 479 sensibel / 194 Leuchtturm.**

Gebiets-Breakdown (primary):
Tiere 807 | Berühmte Personen 294 | Länder 250 | Naturwiss 246 | Pflanzen 239 |
Technik 221 | Geschichte 217 | Sport 212 | Kunst 184 | Essen 180 |
Körper 167 | Gesellschaft 147 | Erde 126 | Grundbegriffe 120 | Deutsche Städte 110 |
Märchen 102 | Naturräume 100 | Weltstädte 100 | Religion 83 | Weltall 63

### Pipeline-Zustand (generate_grounded.py, Stand 2026-06-14)
Ergiebigkeit verdrahtet ✅ | resolve_lemma im Hauptloop ✅ | Doppelbedeutungs-Direktive ✅
Wortzahl-Guard ✅ | Box-Verteilungs-Guard ✅ | Eignungs-Gate ✅ (vollständig)
eignung_verdicts.json: 738 Verdicts, exclude+age_floor+framing_note alle aktiv
System-Prompt: v3.23b-production | Modell: gemini-3.5-flash

### Ergiebigkeits-Modell (Detail → WISSEN_ARTIKEL_PIPELINE.md)
`target_S = Wlo + frac·(Whi−Wlo), frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250] S2[80,400] S3[100,650]. Rater = Opus per API, Anker: 134 Themen.

---

## 🔴 Nächster Schritt

**Pilot-Bulk-Lauf** (z.B. 50–100 Themen aus catalog_full.json) mit der vollständigen Pipeline:
generate_grounded.py aus catalog_full.json → exclude-Filter, age_floor, framing_note aktiv.

---

## 🔴 Offene Punkte (nach Priorität)

Pilot-Bulk-Lauf (50–100 Themen, vollständige Pipeline) — nächster Chat
categories_backlog.json → categories-Array je Artikel (spätere Phase)
Dedup (Hai=Haie, Deutschland 3×; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); Flutter WfArticleListScreen
