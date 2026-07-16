# Wissensfreund — STATUS
<!-- updated: 2026-07-16T17:30:52Z -->
<!-- Ältere Stände (verbatim) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder (Stufen S1 4–6, S2 7–9, S3 10–12), KI-Artikel streng aus
geladenem Artikel-Quelltext (nie Trainingswissen). Zwei Pipelines: alter Monolith (Produktion) + neue
modulare Pass-Pipeline (`scripts/pipeline_new.py`, Fallback-sicher).

## Zuletzt abgeschlossen (2026-07-16)

- **STIMME EINGEFROREN** (PO-Abnahme) → **`STIMME_NICO_EINGEFROREN.md`** ist die Wahrheitsquelle.
  Rezept: Flash-TTS **Puck neutral + temperature 0.3** → **OpenVoice v2, tau 0.7**, Referenz
  **`rich_ref.wav` ALLEIN** + loudnorm −16. `temperature 0.3` kam per **Hörurteil**, nicht per Messung:
  nach der VC ist die Tonhöhe temperature-unabhängig ruhig (±2–11 Hz) — entschieden hat der VORTRAG
  (OpenVoice überträgt nur Klangfarbe; Betonung kommt aus dem Flash-Original und überlebt die VC).
  Das Dokument enthält ein Playbook „wenn die Stimme schwankt" (3 Hebel, Referenz-Set zuerst).
  Samples: `Desktop/_nico_temp_vergleich`. Commits `232cfa9` · `f9812e2` · `04ed3b0` · `4655712`.
- **Kein Artefakt ohne Vollständigkeit** (`59554db` · `232cfa9`): `vertone()` bricht jetzt ab, wenn
  (a) Kind-Turns ohne VC gerendert würden (rohes Puck ist ein Platzhalter, klingt erwachsen) oder
  (b) ein Turn nicht vertont wurde. Beides fiel vorher still durch — im GPU-Lauf verschwanden **7 von
  23 Turns** unbemerkt, inkl. Erzähler-Einstieg. `manifest["vollstaendig"]` = die prüfbare Fahne;
  CLI endet mit exit 1. Notausgänge `--allow-raw-kind` / `--allow-incomplete` nur für Tests.
- **TTS-Calls gehärtet:** `timeout=60000` in `tts_story` UND beiden Client-Stellen in `tts_produce.py`
  (= Produktionspfad, Stage 4; hing bisher unbegrenzt). Im Feld bestätigt: ein Call hing, wurde nach
  60 s gekappt statt den Lauf einzufrieren.
- **Nico-VC auf echter GPU belegt** (RunPod A40, Pod terminiert): Converter lädt (24 s), Kind-Turns
  werden umgefärbt, Zwang schlägt nicht fehlalarmig an. Der 37-Turn-Render wurde NICHT fertig —
  504/503-Sturm. Kosten ~0,60 €.
- **Batch-Synthese gebaut** (`scripts/tts_batch.py`, `a2ac2e0`/`0f7e48f`): `vertone()` läuft jetzt per
  **Standard über Batch** (Cache + Nachreich-Runden), `--sync` bleibt zum Iterieren. Verifiziert:
  **Batch kann Audio** (`audio/l16; 24000; mono`) — **aber `JOB_STATE_SUCCEEDED` heißt NICHT „alles da"**
  (1 von 2 Antworten leer, `finish_reason=OTHER`, ohne Fehlerfeld). Daher Runden-Schleife + Einzelprüfung
  jeder Antwort. **Das Gate greift VOR der VC** (keine GPU-Arbeit an Unvollständigem). Details:
  WISSEN_ARTIKEL_PIPELINE.md.
- **Früher am Tag:** Read-Along am Tablet fertig (Hörspiel-Render + Forced Alignment, PO: „Stimme ist
  ok so") · die VC ist der Tonhöhen-Normalisierer → N=1, kein Best-of-N · TTS-Kosten verifiziert
  (Batch ~0,12 €/Vertonung; Start 2.000–2.500 × 2 Stufen ≈ 470–590 €). → STATUS_ARCHIV.md.

## Gerade in Arbeit / Nächster Schritt

- Nichts angefangen. Batch-Pfad ist verdrahtet + getestet, aber gegen die echte API nur mit **2 Sätzen**
  verifiziert — ein echter 37-Turn-Batch-Lauf ist nie gelaufen (dauert Stunden, nicht Minuten).

## Offen nach Priorität

1. **DU: Backup der Sprachaufnahmen (~25 MB).** `Documents\Audioaufzeichnungen\` (18 MB, 104 m4a =
   Originalaufnahmen des Sohnes IN DIESEM ALTER) + `Desktop\_nico_clone\ref_clips\` (6 MB = die
   abgenommene Referenz, **nicht nachbaubar** — kein Skript erzeugt sie). Geprüft: **OneDrive ist leer,
   Desktop/Documents nicht dorthin umgeleitet → es gibt KEIN Backup.** Externe Platte/privater Cloud-
   Ordner; **NICHT ins Repo** (öffentlich!). Ohne diese Dateien ist die eingefrorene Stimme weg.
2. **Echter Batch-Lauf** (37 Turns, Leonardo) → dann VC-Stufe getrennt auf EINEM Pod. Zielbild:
   Synthese ohne GPU → PCM-Cache → ein Pod färbt alle Kind-Zeilen am Stück um (~1–3 $ statt ~50 $).
3. **`verify_project_facts.py`:** 1 Hart-FAIL ist Verify-Drift — Regel erwartet beim Vision-Modell noch
   `claude-sonnet-5`, `stage_models.py` steht bewusst auf `gemini-2.5-flash-lite` (Kostenentscheidung).
4. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button „Leonardo (Vorlese-Test)" in
   `home_screen.dart`, TEMP-Prints in `_prepareNarration`.
5. **Phase 5:** `--pipeline`-Default auf `new` umstellen (nach Nachtlauf-Auswertung).
6. **Tablet-Pass:** Kinderschutz / Plus & Premium / Menü / Profile tablet-zentrieren
   (`TabletMaxWidth`), danach Lesemodi A/B/C. Onboarding einmal am Tablet durchklicken.
7. **Kleineres:** echte 300px-Paketgröße → `AssetConfig` (545 MB ist Platzhalter) · Cache-Cap-Regler ·
   Leuchtturm-Offline-Paket · Modellwahl Pass 2 schärfen · Validierungsordner sind Wegwerf.
