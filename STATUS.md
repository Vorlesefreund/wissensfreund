# Wissensfreund — STATUS
<!-- updated: 2026-07-14T12:35:31Z -->
<!-- Ältere Banner-Historie → STATUS_ARCHIV.md · Wissen → WISSEN_*.md · Details → PROJEKTDOKUMENT.md -->

**Wissensfreund:** Flutter-App für Kinder (3 Altersstufen: S1 4–6, S2 7–9, S3 10–12),
KI-generierte Artikel streng aus geladenem Artikel-Quelltext (nie Trainingswissen).
Zwei Pipelines nebeneinander: alter Monolith (Produktion) + neue modulare Pass-Pipeline
(`scripts/pipeline_new.py` / `lektorat_new.py`, Fallback-sicher, JSON-Schema unverändert).

## Zuletzt abgeschlossen (Stand 2026-07-14)

- **Tablet-Version gestartet (App, 2026-07-14):** Fundament `lib/utils/responsive.dart`
  (`isTablet` shortestSide≥600 / `isLandscape` / `MaxWidthCenter`), **rein additiv — Handy-Modus
  unberührt** (User-Regel: jede Handy-Änderung vorher absprechen). Screen **„Internet & Daten" neu**
  (Handy+Tablet, mit Freigabe): 3 Karten WLAN/Mobilfunk/Wissensspeicher, einheitliche Typo, ehrliche
  Erklärtexte, „Stand: Mai 2026" statt interner ZIM-Kennung. Getestet per adb am echten Galaxy Tab
  S10 FE (`R52Y30B9GVD`). Plan/Screen-Inventar: `Desktop\wissensfreund_tablet_strategie.html`.
  Entschieden: voller Tablet-Modus inkl. Querformat für Lesemodi (A/B/C); Home-Kachel-Umbau danach.
- **5-Fixes-Batch (Review-Feedback batch_new_20260710):**
  (1) **Lektorat-Modell → `claude-sonnet-5`** (besser + günstiger als sonnet-4-6; `stage_models`, `lektorat_common`, `verify`).
  (2) **Review-Docx** zeigt Korrekturen sauber: finaler Satz einmal als Body, Änderung als klein gesetzte Notiz (keine Scheindopplung) — `generate_review_docx._render_tracked_change`.
  (3) **Lektorat-Beleg-Gate** um `typ`=WIDERSPRUCH/UNGEDECKT erweitert: Streichung quellfremder Details wird jetzt angewandt (verifiziert: Phrase im Alt-Satz, weg im Neu-Satz, nicht in Quelle); + Sinn/Zahlen-Regel (falsche Zahl → belegte Zahl, nie zu Unfug verkürzen).
  (4) **PASS3 stimmt_das** enger (nur echte verbreitete Irrtümer, keine Datums-/Detailfragen); **PASS1/PASS2** Abschnitts-Reihenfolge (Bedeutung/Symbol ans Ende) + weiche Übergänge.
  (5) **Bild**: Hero muss Person/Tätigkeit zeigen (Gladiator statt Helm), Caption nur Sichtbares (keine erfundenen Rauchwolken).
  Alle kompiliert, `verify` = 0 Hart-FAIL, Streichungs-Logik + Docx-Rendering smoke-getestet.
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
- **Resilienz-Härtung (`cf1ffaf`):** Cache-Ablauf-Fallback in `pipeline_new._call_pass` (403 „CachedContent
  not found" → voller Kontext statt Hart-Abbruch; behebt die Kaskade, die zuvor 17/18 Artikel killte) +
  10-min Client-Timeout (Gemini-SDK hat keins → Server-Stall hing endlos) + breiteres `is_transient`-Retry
  (Timeout/Deadline/Connection/overloaded) in gemini_client/run_batch/generate_grounded/image_vision_filter.
- **Cache-TTL 30min → 6h (`c846e57`):** Caches werden vorab für alle Themen erzeugt → müssen ganze
  Batch-Laufzeit überleben; Gemini akzeptiert 6h/12h (getestet).

## Gerade in Arbeit / Nächster Schritt

- **Tablet-Pass (App), Screen für Screen:** nächste Formular-Screens (Kinderschutz / Speicher &
  Qualität / Plus & Premium) tablet-zentrieren (`_tabletConstrain` / `MaxWidthCenter`) + ggf. gleiche
  Aufräum-Kur. Danach Lesemodi A/B/C — brauchen Wissensspeicher auf dem Tablet (**Klexikon-Daten nicht
  anfassen**, User-Wunsch). Bildschirm bleibt beim Testen wach: `adb ... svc power stayon usb`.
- **Nico-Stimme (Voice-Cloning, 2026-07-14):** Erster LoRA-Fine-Tune-Lauf auf RunPod (RTX 3090,
  Chatterbox MIT) **validiert** — Pipeline Datensatz→Training→Inferenz läuft durch, Ergebnis =
  Kinderstimme in sauberem Deutsch (`Desktop\_nico_clone\nico_finetune_v1.mp3`). Nur 5,5 Min Daten
  → einige Sätze früh „forcing EOS"-abgeschnitten (erwartet). **Offen:** ~25–30 Min mehr Aufnahmen
  (User heute Abend) → echter Qualitätslauf. Pod läuft WARM weiter (~$0,22/h, User-Freigabe).
  Reconnect + Ablauf: `Desktop\_nico_clone\pod_zugang\RECONNECT.md`. Strategie: [[project_voice_strategy]]
  (Erwachsene=Gemini Flash TTS, Nico=geklonte Sohn-Stimme). **Pod-Terminierung nicht vergessen**, wenn fertig.
- **Nachtlauf geplant: 2026-07-08 03:00 Berlin** (Scheduled Task `WF_NightlyRerun_20260708`, Frühfenster
  laut 503-Monitor am ruhigsten). Die 6 Themen (Dinosaurier/Elefant/Hund/Spartacus/Vulkan/Zweiter Weltkrieg)
  × 3 Stufen, `--pipeline new`, Stages 1–3 (Gen+Lektorat, kein TTS) → `articles/batch_new_20260708`,
  Review-Docx → `Desktop\_review_batch_new_20260708.docx`, Log → `articles/batch_new_20260708/run.log`.
  Wrapper: `_nightly_rerun_20260708.ps1` (Repo-Root, nicht committet; `PYTHONUTF8=1` gegen cp1252-Crash).
- **Auswertung morgen früh:** Läuft alles sauber (18/18) → Phase 5 (Default `new`) freigeben.

## Offen nach Priorität

1. **Phase 5:** `--pipeline`-Default auf `new` umstellen — nach erfolgreicher Nachtlauf-Auswertung.
2. **Verifikation:** WWII-Ton (nüchtern?) + Einstiegs-Streuung über mehrere Themen; SVG-Vision-Akzeptanz
   (Fix B) end-to-end — kommt aus dem Nachtlauf.
3. **Modellwahl Pass 2** empirisch schärfen.
4. Nicht-committete Validierungsordner (`articles/wwii_new_*`, `vulkan_new_demo` …) sind Wegwerf.

## Historie & Details

Ältere Stände (Juni–Anfang Juli: TTS-Pipeline end-to-end, Weg-B-Rückbau, Stage-1/2/3-Resilienz,
Companion-Faszination/Vielfalt, Lektorat-Bausteine, Review-Workflow) → **STATUS_ARCHIV.md** (verbatim)
· `git log STATUS.md` · **PROJEKTDOKUMENT.md** (Entscheidungs-Log + Roadmap).
