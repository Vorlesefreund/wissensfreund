# Wissensfreund — STATUS
<!-- updated: 2026-07-07T09:05:50Z -->
<!-- Ältere Banner-Historie → STATUS_ARCHIV.md · Wissen → WISSEN_*.md · Details → PROJEKTDOKUMENT.md -->

**Wissensfreund:** Flutter-App für Kinder (3 Altersstufen: S1 4–6, S2 7–9, S3 10–12),
KI-generierte Artikel streng aus geladenem Artikel-Quelltext (nie Trainingswissen).
Zwei Pipelines nebeneinander: alter Monolith (Produktion) + neue modulare Pass-Pipeline
(`scripts/pipeline_new.py` / `lektorat_new.py`, Fallback-sicher, JSON-Schema unverändert).

## Zuletzt abgeschlossen (Stand 2026-07-07)

- **Listen-Konsolidierung „Ein Brett" (Phase A/B/C):** `catalog_review_master.xlsx` ist die
  EINZIGE Datei zum Arbeiten. **Workflow:** Master editieren → `python -X utf8 scripts/build_all.py`
  erzeugt alle abgeleiteten Listen (catalog_full/reserve, eignung_exclude, ergiebigkeit_scores)
  + Sheet „Produktion" (generiert/lektoriert/vertont je Thema/Stufe). catalog_full wird jetzt AUS
  dem Master abgeleitet (kein catalog_review.xlsx-Rückwärts-Nebeneffekt mehr).
  Commits `f5b6d36` (A) · `f8f35d5` (B) · `ccc4175` (C). Alter `catalog_merge.py` bleibt Fallback.
- **Katalog-Gaps:** 11 verifizierte Audit-Lücken (Wikipedia-Deckung) in `catalog_manual.json` aufgenommen
  + triagiert (9 include, Todesstrafe/Zeugen Jehovas exclude); „Moldau"→„Moldawien". Abgelöste
  Review-XLSX + Audit-Snapshots nach `archiv/`. Commits `f1c8f8b` · `247aa49`.
- **Neue Pipeline Phase 0–4** komplett+committet, Vulkan e2e validiert; **Feinschliff** (Bild-Alt-Texte,
  S1/S2-Ton, S3-Quiz) + **SVG-Diagramme (Fix B)**. `verify_project_facts` durchgehend 0 Hart-FAIL.

## Gerade in Arbeit / Nächster Schritt

- **Die 6 bereits generierten Artikel neu produzieren** (Dinosaurier/Elefant/Hund/Spartacus/Vulkan/
  Zweiter Weltkrieg) auf der NEUEN Pipeline. Voraussetzung: Phase 5 (Pipeline-Default `new`) +
  stabiles gemini-3.5-flash. KEIN Voll-Katalog-Lauf.

## Offen nach Priorität

1. **Phase 5:** `--pipeline`-Default auf `new` umstellen — nach breiterer Multi-Themen-Validierung.
2. **Verifikation (gemini-3.5-flash-503-blockiert):** WWII-Ton (nüchtern?) + Einstiegs-Streuung über
   mehrere Themen; SVG-Vision-Akzeptanz (Fix B) end-to-end.
3. **Modellwahl Pass 2** empirisch schärfen.
4. Nicht-committete Validierungsordner (`articles/wwii_new_*`, `vulkan_new_demo` …) sind Wegwerf.

## Historie & Details

Ältere Stände (Juni–Anfang Juli: TTS-Pipeline end-to-end, Weg-B-Rückbau, Stage-1/2/3-Resilienz,
Companion-Faszination/Vielfalt, Lektorat-Bausteine, Review-Workflow) → **STATUS_ARCHIV.md** (verbatim)
· `git log STATUS.md` · **PROJEKTDOKUMENT.md** (Entscheidungs-Log + Roadmap).
