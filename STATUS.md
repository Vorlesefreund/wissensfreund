# Wissensfreund — STATUS
<!-- updated: 2026-07-16T14:03:05Z -->
<!-- Ältere Banner-Historie → STATUS_ARCHIV.md · Wissen → WISSEN_*.md · Details → PROJEKTDOKUMENT.md -->

**Wissensfreund:** Flutter-App für Kinder (Stufen S1 4–6, S2 7–9, S3 10–12), KI-Artikel streng aus
geladenem Artikel-Quelltext (nie Trainingswissen). Zwei Pipelines nebeneinander: alter Monolith
(Produktion) + neue modulare Pass-Pipeline (`scripts/pipeline_new.py`, Fallback-sicher).

## Zuletzt abgeschlossen (2026-07-16)

- **Read-Along am Tablet fertig — freigegebener Hörspiel-Render + echte Wort-Zeiten.**
  Artikel `leo_mit_tags_l2` = `Leonardo_v2_Hoerspiel_Emotion.mp3` (395,3 s, Nico-VC-Stimme, Theo 316 Hz).
  Lese-Text = gesprochener Text (Prosa mit Tags + „…"), Wort-Lupe per **Forced Alignment** (torchaudio
  MMS_FA, CPU, 773 Wörter, bad_offset=0). Deploy OHNE APK-Rebuild über den `wf_articles`-Cache-Pfad.
  PO-Urteil: „Stimme ist ok so". Weg + Gotchas: WISSEN_ARTIKEL_PIPELINE.md.
- **Emotions-Regression gefixt:** `feed_for` gab den Rollen-Grundstil zurück und verwarf damit die
  per-Zeile-`emotion` für ALLE Zitate („Oma Rina lacht." → Oma sprach ohne Lachen). Jetzt wird
  `unit_style` durchgereicht. Zusätzlich persistenter PCM-Cache → kein Stimm-Drift bei Rebuilds.
- **Stimmen-Stabilität geklärt (Nacht-Test 02:00 + Nachlauf):** **Die OpenVoice-VC (tau 0.7) ist selbst
  der Tonhöhen-Normalisierer** — Quell-Streuung erbt sich NICHT durch (rohes Puck ±54 Hz → Nico nach VC
  **±11 Hz über fünf verschiedene Texte**, 311 Hz Kinderlage). Folge: für Kind-Zeilen **N=1, kein
  Best-of-N, kein temperature-Tuning nötig**. Das ursprüngliche „Theo kippt in eine Erwachsenenstimme"
  war schlicht der rohe Puck-Platzhalter OHNE VC.
- **Verworfen:** `seed` (wird nicht honoriert, ±12–37 Hz trotz fixem seed) · F0-Post-Processing
  (librosa/rubberband: Zahl besser, Klang schlechter — Nachhall/Phasing, Blind-Test bestätigt).
- **TTS-Kosten verifiziert:** 3.1-flash-tts = $1/$20 pro 1M, **Batch −50 %**; real 32 Audio-Tokens/s
  → **~0,12 €/Vertonung (Batch, N=1)**. Start-Katalog 2.000–2.500 Art. × 2 Stufen ≈ **470–590 €**;
  Vollausbau 4.000–5.000 ≈ 940–1.180 €. Einmalig, kein laufender Betrieb. **Entscheidung: Batch, N=1.**
  Flash ist auch nachts überlastet (viele 504/503) → Batch faktisch Pflicht.
- **Früher im Juli:** Audio-Streaming-Umbau (m4a von R2 + Timing-Sidecar, Track A+B am Tablet validiert)
  · Tablet-Fundament `responsive.dart` (rein additiv, Handy-Modus unberührt) · Screens „Internet & Daten"
  + „Speicher & Qualität" · Nico-VC in `tts_story.py` integriert (`nico_vc.py`, Standard AUS) ·
  Listen-Konsolidierung „Ein Brett" (`catalog_review_master.xlsx` + `build_all.py`) · neue Pipeline
  Phase 0–4 komplett. Verbatim → STATUS_ARCHIV.md.

## Gerade in Arbeit / Nächster Schritt

- Nichts offen angefangen — Read-Along-Strang ist abgeschlossen und am Gerät bestätigt.

## Offen nach Priorität

1. **Nico-VC in `tts_story.py.vertone()` verdrahten** (GPU zur Synthese-Zeit), damit nie wieder ein roher
   Puck-Platzhalter in einen Build rutscht. Kosten vorher nennen. Details: [[project_voice_strategy]].
2. **`tts_story.py._tts_call` härten (0 €):** Client-`timeout=60000` (Produktionsbug — ein Call kann heute
   unbegrenzt hängen) + optional `temperature=0.3` für Erzähler/Erwachsene (die haben keine VC).
3. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button „Leonardo (Vorlese-Test)" in
   `home_screen.dart`, TEMP-Diagnose-Prints in `_prepareNarration`.
4. **Phase 5:** `--pipeline`-Default auf `new` umstellen (nach Nachtlauf-Auswertung).
5. **Tablet-Pass, Screen für Screen:** Kinderschutz / Plus & Premium / Menü / Profile / Neues Profil
   tablet-zentrieren (`TabletMaxWidth`). Danach Lesemodi A/B/C (Klexikon-Daten nicht anfassen).
6. Onboarding-Pflichtweg einmal am Tablet durchklicken (Profil-Reset nötig).
7. Echte 300px-Paketgröße bestimmen → `AssetConfig`-Konstante (545 MB ist Platzhalter).
8. Cache-Cap-Regler in „Speicher & Qualität" + opt-in Leuchtturm-Offline-Paket (Plus).
9. Modellwahl Pass 2 empirisch schärfen.
10. Aufräumen: Scheduled Task `Wissensfreund_Stimmtest_Nacht` ist verbraucht (NextRun leer) → löschbar.
    Nicht-committete Validierungsordner (`articles/wwii_new_*`, `vulkan_new_demo` …) sind Wegwerf.

## Historie & Details

Ältere Stände (Juni–Mitte Juli) → **STATUS_ARCHIV.md** (verbatim) · `git log STATUS.md` ·
**PROJEKTDOKUMENT.md** (Entscheidungs-Log + Roadmap).
