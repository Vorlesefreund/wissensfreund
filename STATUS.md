# Wissensfreund — STATUS
<!-- updated: 2026-07-15T10:46:32Z -->
<!-- Ältere Banner-Historie → STATUS_ARCHIV.md · Wissen → WISSEN_*.md · Details → PROJEKTDOKUMENT.md -->

**Wissensfreund:** Flutter-App für Kinder (3 Altersstufen: S1 4–6, S2 7–9, S3 10–12),
KI-generierte Artikel streng aus geladenem Artikel-Quelltext (nie Trainingswissen).
Zwei Pipelines nebeneinander: alter Monolith (Produktion) + neue modulare Pass-Pipeline
(`scripts/pipeline_new.py` / `lektorat_new.py`, Fallback-sicher, JSON-Schema unverändert).

## Zuletzt abgeschlossen (Stand 2026-07-14)

- **Audio-Streaming-Umbau (Premium-Vertonung) — Track A + B M2 am Tablet validiert:**
  Vertonung wird künftig **pro Artikel gestreamt** (AAC .m4a von R2, on-device gecacht),
  NICHT als Riesen-WAV-Bündel (skaliert bei 5.000 Art. nicht: 13–36 GB). Auf R2 kostet das
  fast nichts (Egress $0, Speicher ~$0,30/Mon). **flutter_tts bleibt Gratis-Fallback** (offline,
  alle); die schönen Stimmen = **Plus/Premium**. Wortgenaue Markierung in Modus A/B/C über ein
  **Timing-Sidecar** (`positionStream` → `_ttsCursor`, gleiche grüne Markierung, Bild-Sync).
  - Track A: `scripts/compress_narration.py` (WAV→AAC 48k + `narration_index.json`, keyt nach
    voller `article_id` = App `_articleId`); `upload_articles.py` lädt den m4a-Ordner inkl. Index.
  - Track B: `lib/services/narration_service.dart` (Streaming `LockCachingAudioSource` + Cache
    + Wort-Timeline + nutzer-Cache-Cap) + Provider-Verdrahtung **streng additiv** (Handy-Pfad
    byte-identisch, Regression bestätigt). Init ZIM-unabhängig in `main.dart`.
  - **E2E am Galaxy Tab getestet** (elefant_l2, Platzhalter-Audio + proportionales Test-Sidecar):
    Streaming läuft, Cursor trackt Audioposition in Echtzeit, Bild-Auto-Weiterschaltung, stabil.
  - Commits: `7d198a1` (A) · `2eea9e9`/`babaf56` (B-Foundation) · `8018c74` (M2) · `f0df7ce` (init).
  - **Offen:** M1 Forced Alignment (`align_narration.py`, WhisperX auf RunPod → echte Wort-Zeiten
    statt proportional; **GPU-Kosten → Freigabe nötig**); Cache-Cap-Regler in „Speicher & Qualität";
    opt-in Leuchtturm-Offline-Paket (Plus); echter Vertonungs→compress→align→upload-Durchlauf.
    Details: `Desktop\wissensfreund_audio_umbau_plan.md`. Budgets: [[reference-media-storage-budget]].

- **Tablet-Version gestartet (App, 2026-07-14):** Fundament `lib/utils/responsive.dart`
  (`isTablet` shortestSide≥600 / `isLandscape` / `MaxWidthCenter`), **rein additiv — Handy-Modus
  unberührt** (User-Regel: jede Handy-Änderung vorher absprechen). Screen **„Internet & Daten" neu**
  (Handy+Tablet, mit Freigabe): 3 Karten WLAN/Mobilfunk/Wissensspeicher, einheitliche Typo, ehrliche
  Erklärtexte, „Stand: Mai 2026" statt interner ZIM-Kennung. Getestet per adb am echten Galaxy Tab
  S10 FE (`R52Y30B9GVD`). Plan/Screen-Inventar: `Desktop\wissensfreund_tablet_strategie.html`.
  Entschieden: voller Tablet-Modus inkl. Querformat für Lesemodi (A/B/C); Home-Kachel-Umbau danach.
- **Screen „Speicher & Qualität" komplett (Handy+Tablet, freigegeben):** Tablet-zentriert (`TabletMaxWidth`);
  neue Speicher-Übersicht oben (Bilderanzahl + belegte MB + freier Gerätespeicher via `getFreeStorageBytes`
  + rote Warnung < 1,5 GB frei); interner „(aus ZIM)"-Begriff raus. **Freeze-Bug behoben**: `_extractZipTo`
  (`image_library_service`) lief synchron auf dem UI-Isolate → Balken fror bei 100 % → jetzt yield alle 40
  Dateien, „wird entpackt…" läuft sichtbar. **Paketgrößen zentralisiert**: alle MB/GB-Anzeigen leiten aus
  `AssetConfig.image*SizeBytes` ab (einzige Quelle; 545 MB ist **Platzhalter** — Onboarding rechnet mit
  141 MB ZIP, echte Zahl offen bis Voll-Paket). **Onboarding**: 300px-Download jetzt Pflicht (Skip nur bei
  zu wenig Platz → WLAN-Weg bleibt offen; `first_run_screen`). **Audio bleibt Stream/on-demand** (offline
  undenkbar: 5.000 Art.×3 Stufen ≈ 13–36 GB komprimiert; heute noch unkomprimiertes WAV 24kHz = 2,88 MB/min).
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

- **Tablet-Pass (App), Screen für Screen:** nächste Formular-Screens (Kinderschutz / Plus & Premium /
  Menü / Profile / Neues Profil) tablet-zentrieren (`TabletMaxWidth`) + ggf. gleiche Aufräum-Kur.
  Danach Lesemodi A/B/C — brauchen Wissensspeicher auf dem Tablet (**Klexikon-Daten nicht anfassen**,
  User-Wunsch). Bildschirm bleibt beim Testen wach: `adb ... svc power stayon usb`.
- **Onboarding-Pflicht noch am Tablet ansehen** (Profil-Reset nötig) — User wollte einmal durchklicken.
- **Audio nächster Schritt: M1 Forced Alignment** (`scripts/align_narration.py`, WhisperX auf RunPod)
  → echte Wort-Zeitstempel statt proportionalem Test-Sidecar; **GPU-Kosten, vor Lauf Freigabe**. Danach
  Cache-Cap-Regler in „Speicher & Qualität" + opt-in Leuchtturm-Offline-Paket + echter Vertonungslauf.
- **Offen (eigene Stränge, nicht ungefragt):** echte 300px-Paketgröße bestimmen → `AssetConfig`-Konstante
  aktualisieren (oder Anzeige auf `images_thumb_manifest.json` verdrahten).
- **Nico-Stimme (Voice-Conversion) — FREIGEGEBEN + in tts_story.py integriert (2026-07-15):**
  Fine-Tune verworfen. Finaler Weg (User-Freigabe „soll reichen"): **Gemini-Flash-TTS (Puck, neutral)
  → OpenVoice v2 (MIT) VC** auf Sohn-Referenz, **tau 0.7**; Tonhöhe landet automatisch in Kinderlage
  (~310 Hz). `tts_story.py` erweitert: (1) **Hörspiel-Segmentierung** (reine Sprech-Tags weg, unterbrochene
  Zitate zusammengezogen, echte Handlungen bleiben), (2) **`emotion`-Feld pro Turn** → `_style_for`
  (z. B. „Oma Rina lacht." → Folgesatz amüsiert; Trauriges → ernst), (3) **Bare-Text-Fallback** in
  `synth_pcm` gegen den Safety-Block (Stil-Präfix+Fragment = PROHIBITED_CONTENT; nackter Text läuft),
  (4) **VC-Naht in `vertone(nico_converter=…)`** + neues Modul **`nico_vc.py`** (OpenVoice-Converter,
  GPU-seitig) + CLI `--nico-ref/--nico-ckpt/--nico-tau/--openvoice-path` + loudnorm-Pegelangleich.
  Standard AUS → normale Pipeline unverändert; beide Pfade smoke-getestet, `py_compile` OK. Demo:
  `Desktop\_nico_clone\vc_test\STORY_KOMPLETT\Leonardo_v2_Hoerspiel_Emotion.mp3` (37 Turns, 6,6 Min).
  **Offen:** VC-Pfad auf echter GPU im integrierten `--nico-ref`-Lauf noch nicht end-to-end gefahren
  (OpenVoice-Logik selbst auf Pods bewährt). Details: [[project_voice_strategy]]. Alle Test-Pods terminiert.
- **Leonardo-Story am Tablet gelesen+gehört — Lupe-Sync bestätigt (2026-07-15):** Komplette Hörspiel-Story
  (37 Turns, Erzähler+Erwachsene+Kind) als WfArticle `assets/test/leonardo_da_vinci_l2.json` + Premium-m4a
  (395,3 s) + proportionales Timing-Sidecar aufs Galaxy Tab S10 FE (`R52Y30B9GVD`) gespielt (Flugmodus →
  Asset-Fallback, Debug-isPlus-Hook in `main.dart`, Temp-Button 🎨 in `home_screen.dart` → `ArticleScreen`).
  **Ergebnis:** Streaming läuft, grüne Lupe (Modus A) wandert satz-/phrasengenau mit der Audioposition mit
  (Frame 1 Satz 2 → Frame 2 Phrase „vor über fünfhundert Jahren, in Italien."), Bild-Sync, stabil.
  **Noch proportionales Sidecar** (Option 2) — Option 3 = echte Wort-Zeiten via Forced Alignment
  (`align_narration.py`, GPU) offen. Debug-Hook + Temp-Button vor Release wieder entfernen.
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
