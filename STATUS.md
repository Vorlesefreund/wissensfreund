# Wissensfreund — STATUS
<!-- updated: 2026-07-16T14:14:10Z -->
<!-- Ältere Stände (verbatim) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md -->

**Wissensfreund:** Flutter-App für Kinder (Stufen S1 4–6, S2 7–9, S3 10–12), KI-Artikel streng aus
geladenem Artikel-Quelltext (nie Trainingswissen). Zwei Pipelines: alter Monolith (Produktion) + neue
modulare Pass-Pipeline (`scripts/pipeline_new.py`, Fallback-sicher).

## Zuletzt abgeschlossen (2026-07-16)

- **Nico-VC-Zwang + TTS-Härtung (`tts_story.py` / `tts_produce.py`):** **Rohes Puck kann nicht mehr in
  einen Build rutschen** — `vertone()` bricht ab, sobald Kind-Turns da sind und kein Converter gesetzt ist;
  ein VC-Fehler bricht AB statt still auf die Platzhalter-Stimme zurückzufallen. Notausgang nur bewusst per
  `--allow-raw-kind` (stempelt `raw_kind` + Warnung; Manifest trägt `nico_vc`/`raw_kind_turns`).
  **Timeout `60000`** in `tts_story.vertone` UND an beiden Client-Stellen in `tts_produce.py` (= der
  Produktionspfad, Stage 4 in `run_batch`; hing bisher unbegrenzt). **`temperature=0.3`** nur für Turns
  OHNE VC (`_temperature_for`) — Kind+VC behält den Default, damit der Vortrag nicht eingeebnet wird;
  CLI `--tts-temperature`. 20 Guard-Tests grün (ohne API), `py_compile` OK. `tts_produce` klanglich
  unverändert (nur Timeout).
- **Read-Along am Tablet fertig — freigegebener Hörspiel-Render + echte Wort-Zeiten.** Artikel
  `leo_mit_tags_l2` = `Leonardo_v2_Hoerspiel_Emotion.mp3` (395,3 s, Nico-VC-Stimme, Theo 316 Hz).
  Lese-Text = gesprochener Text (Prosa mit Tags + „…"), Wort-Lupe per **Forced Alignment** (torchaudio
  MMS_FA, CPU, 773 Wörter, bad_offset=0). Deploy OHNE APK-Rebuild über den `wf_articles`-Cache-Pfad.
  PO-Urteil: „Stimme ist ok so". Zuvor: Emotions-Regression gefixt + persistenter PCM-Cache gegen
  Stimm-Drift. Weg + Gotchas: WISSEN_ARTIKEL_PIPELINE.md.
- **Stimmen-Stabilität geklärt (Nacht-Test 02:00 + Nachlauf):** **Die OpenVoice-VC (tau 0.7) ist selbst
  der Tonhöhen-Normalisierer** — Quell-Streuung erbt sich NICHT durch (rohes Puck ±54 Hz → Nico nach VC
  **±11 Hz über fünf verschiedene Texte**, 311 Hz Kinderlage). Folge: für Kind-Zeilen **N=1, kein
  Best-of-N, kein temperature-Tuning nötig**. Das ursprüngliche „Theo kippt in eine Erwachsenenstimme"
  war schlicht der rohe Puck-Platzhalter OHNE VC. **Verworfen:** `seed` (wird nicht honoriert) ·
  F0-Post-Processing (Zahl besser, Klang schlechter — Nachhall/Phasing, Blind-Test bestätigt).
- **TTS-Kosten verifiziert:** 3.1-flash-tts = $1/$20 pro 1M, **Batch −50 %**; real 32 Audio-Tokens/s
  → **~0,12 €/Vertonung (Batch, N=1)**. Start-Katalog 2.000–2.500 Art. × 2 Stufen ≈ **470–590 €**;
  Vollausbau 4.000–5.000 ≈ 940–1.180 €. Einmalig, kein laufender Betrieb. **Entscheidung: Batch, N=1.**
  Flash ist auch nachts überlastet (viele 504/503) → Batch faktisch Pflicht.
- **Früher im Juli** (Details → STATUS_ARCHIV.md): Audio-Streaming-Umbau (m4a von R2 + Timing-Sidecar) ·
  Tablet-Fundament `responsive.dart` (additiv, Handy-Modus unberührt) · Screens „Internet & Daten" +
  „Speicher & Qualität" · `nico_vc.py` · „Ein Brett" (`build_all.py`) · neue Pipeline Phase 0–4.

## Gerade in Arbeit / Nächster Schritt

- Nichts offen angefangen — Read-Along + TTS-Härtung sind abgeschlossen, Read-Along am Gerät bestätigt.

## Offen nach Priorität

1. **Nico-VC end-to-end auf echter GPU fahren** (`--nico-ref`/`--nico-ckpt`, OpenVoice). Die Naht + der
   Zwang stehen und sind getestet, der integrierte Lauf lief aber noch nie durch. Kosten vorher nennen.
   Danach: `temperature=0.3` bei Erzähler/Erwachsenen einmal gegenhören (könnte Vortrag glätten — nur an
   der Tonhöhe gemessen, nicht am Ausdruck). Details: [[project_voice_strategy]].
2. **`verify_project_facts.py`:** 1 Hart-FAIL ist Verify-Drift, kein Code-Fehler — die Regel erwartet beim
   Vision-Modell noch `claude-sonnet-5`, `stage_models.py` steht bewusst auf `gemini-2.5-flash-lite`
   (Kostenentscheidung). Regel angleichen.
3. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button „Leonardo (Vorlese-Test)" in
   `home_screen.dart`, TEMP-Diagnose-Prints in `_prepareNarration`.
4. **Phase 5:** `--pipeline`-Default auf `new` umstellen (nach Nachtlauf-Auswertung).
5. **Tablet-Pass, Screen für Screen:** Kinderschutz / Plus & Premium / Menü / Profile / Neues Profil
   tablet-zentrieren (`TabletMaxWidth`). Danach Lesemodi A/B/C (Klexikon-Daten nicht anfassen).
   Dazu: Onboarding-Pflichtweg einmal am Tablet durchklicken (Profil-Reset nötig).
6. **Kleineres:** echte 300px-Paketgröße → `AssetConfig` (545 MB ist Platzhalter) · Cache-Cap-Regler in
   „Speicher & Qualität" + opt-in Leuchtturm-Offline-Paket (Plus) · Modellwahl Pass 2 empirisch schärfen ·
   Task `Wissensfreund_Stimmtest_Nacht` verbraucht → löschbar · Validierungsordner (`articles/wwii_new_*`,
   `vulkan_new_demo` …) sind Wegwerf.
