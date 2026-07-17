# Wissensfreund — STATUS
<!-- updated: 2026-07-17T21:44:08Z -->
<!-- Ältere Stände (verbatim) → STATUS_ARCHIV.md · `git log STATUS.md` · Wissen → WISSEN_*.md -->
<!-- Entscheidungs-Log + Roadmap → PROJEKTDOKUMENT.md · Stimm-Rezept → STIMME_NICO_EINGEFROREN.md -->

**Wissensfreund:** Flutter-App für Kinder (Stufen S1 4–6, S2 7–9, S3 10–12), KI-Artikel streng aus
geladenem Artikel-Quelltext (nie Trainingswissen). Zwei Pipelines: alter Monolith (Produktion) + neue
modulare Pass-Pipeline (`scripts/pipeline_new.py`, Fallback-sicher).

## Zuletzt abgeschlossen (2026-07-17 spät)

- **ZWEI vom PO gehörte Defekte im „finalen" Hörspiel ganz behoben** (`3e76ed8`, Tests grün).
  Der PO hörte: (a) nach „wer ist das?" ~1 min **hohes Rauschen**, nochmal nach „…die Tinte
  verschmieren"; (b) **das Lachen fehlt** bei „Oma Rina lacht", Oma später in **anderer, ernsterer
  Tonlage**. Diagnose deckte sich exakt: **Fehler 1** = 2 Turns (i=2 mit **97 %** Stille/54 s, i=29 mit
  82 %/14,5 s) — die alte QA prüfte Sprechdauer/Pegel EINZELN, nie den **Stille-ANTEIL**, also rutschten
  sie durch, und die VC machte aus der Stille Rauschen. **Fehler 2** = 8 Emotions-Turns (u.a. i=18
  „amüsiert, lachend", i=33 „nachdenklich, ernst"), die per **Präfix-Verlust** gerettet wurden — der
  Stil-Präfix TRÄGT die Emotion, ihn wegzulassen killt sie.
- **Fix 1:** QA prüft jetzt `MAX_STILLE_ANTEIL` (0.65) + `trim_stille()` VOR der VC (Rest-Stille wird
  nicht mehr umgefärbt). **Fix 2:** `eskalationsleiter` ist pro Turn **emotions-abhängig** und
  `batch_synthesize` eskaliert **PRO Turn** (eigener Versuchszähler/eigene Leiter, nicht mehr global
  pro Runde): Emotions-Turns ziehen erst `temperature` hoch (0.3→0.5→0.6, **Präfix bleibt**) und opfern
  ihn ganz zuletzt; emotionsfreie lassen ihn früh weg (billiger, hält Betonung). Tests: Sektion 7
  (emotions-abhängige Leiter, gegenläufige Reihenfolge) + **7d Integrationstest** (2 Turns folgen in
  EINEM Fake-Client-Lauf verschiedenen Leitern) + Sektion 8 (Stille-Anteil/Trim). → [[reference_tts_gotchas]].
- **Fix im echten Lauf bestätigt** (`articles/leo_fix_20260717`, läuft noch): i=29 kam mit **71 % Stille
  zurück und wurde von der neuen QA abgelehnt** (vorher durchgerutscht); die Emotions-Turns degenerieren
  bei 0.3+Präfix und **eskalieren mit behaltenem Präfix** statt sofort bare. i=2 ging von 97 % → 43 %
  Stille (echte 1,9 s Sprache). **Batch-Queue heute Nacht extrem träge: ~38 min/Runde.**
- **NÄCHSTER SCHRITT (echtes Geld, PO-Warnung Pflicht):** wenn die 10 Turns sauber neu im Cache sind,
  Pod-VC neu rechnen → korrigiertes Finale. 10 defekte Alt-PCMs liegen in
  `pcm_cache/_defekt_backup_20260717/`.

## Zuletzt abgeschlossen (2026-07-17)

- **URSACHE GEFUNDEN: `temperature` killt die TTS — nicht die Batch-API, nicht das Modell.**
  Kontrolliert gemessen (2 Stichproben, 32 Calls, Stimmen **Puck UND Iapetus**, gepaart/abwechselnd,
  Reihenfolge im Paar gedreht → Tageslast als Störfaktor ausgeschlossen, identischer Text):
  **ohne `temperature` 16/16 Audio, 0 Fehler · mit `temperature=0.3` nur 6/16** (Rest 504/500 bei 90 s).
  Der Parameter ist gültig, macht die Generierung aber so langsam, dass sie ins Timeout läuft.
  **EIN Fehler, ZWEI Masken:** Sync → 504/500; Batch kann kein Timeout melden → `finish_reason=OTHER`
  mit `parts=None`. Deshalb sah es wie ein Batch-Problem aus. Belege: `articles/leo_batch_20260716/
  temp_probe.log` + `temp_probe_paired.log`. **Dreifach unabhängig bestätigt:** (1) die Messung,
  (2) Batch-Job mit temp = 4 von 17 Einheiten, (3) Sync-Render mit temp stirbt bei Turn 12/37 —
  ohne temp **37/37, NULL Retries** (2.5 *und* 3.1). → [[reference_tts_gotchas]] korrigiert.
  Der Hinweis stand seit 16.07. in den Notizen („temperature-Requests zeitweise 504-instabil") und
  wurde mit „der Parameter ist aber gültig" abgetan — der Fehlschluss kostete einen halben Tag.
- **Auslöser der Fehlersuche war die PO-Frage** „warum lief die MP3 vom 15.07. fehlerfrei?" → Zeitstrahl:
  MP3 **15.07. 11:29**, Batch-Umstellung `a2ac2e0` **16.07. 19:27**, `temperature 0.3` `232cfa9`
  **16.07. 18:48**. Zwei Variablen am selben Abend geändert → der Verdacht traf den falschen Commit.
- **A/B-Renders für das PO-Ohr liegen auf dem Desktop** (`_tts_vergleich_20260717/`, + LIESMICH):
  `A_2.5flash_ohne_temp.m4a` vs `B_3.1flash_ohne_temp.m4a` — identische Segmentierung, beide ohne temp,
  beide 37/37. **OFFEN: PO-Hörurteil.** Theo klingt in beiden roh (kein GPU-Pod) → nur Erzähler/Oma
  bewerten. Zweite Hörfrage: `_nico_temp_vergleich/Nico_default_*` vs `Nico_t03_*` — **derselbe
  Vergleich wie am 16.07., aber jetzt mit Preisschild.** `temperature 0.3` ist Teil des eingefrorenen
  Rezepts (STIMME_NICO_EINGEFROREN.md) → Änderung nur per PO-Ohr, nicht per Messung.
- **tts_story.py gehärtet** (alles generisch): `sys.stdout.reconfigure(utf-8)` (cp1252-Konsole killte
  den Lauf an eigenen Prints) · `logging.basicConfig(INFO)` (die `Runde N/3`-Zeilen aus tts_batch wurden
  mangels Handler still verworfen — ein 6-h-Batch lief ohne jede Rückmeldung) · **Backoff 6→12→24…90 s
  + Jitter**, Retries 3→6 (starre 6 s waren gegen 500er-Wellen chancenlos) · `--seg-file` +
  `<titel>_segmentierung.json` (Seg ist NICHT deterministisch: ein Rerun verlor **10 von 30**
  Cache-Treffern durch Stil-Drift) · `pcm_cache/_index.json` + `_fehlgeschlagen.json` (Hash→Text;
  vorher war nach einem Abbruch nicht feststellbar, WELCHE Turns klemmten) · `--tts-model` für A/B.
  74 Guard-Tests grün.
- **Batch-Pfad ist rehabilitiert** (war nie kaputt) und das Vollständigkeits-Gate hat sich bewährt:
  Abbruch bei 30/37 **vor** der VC → keine GPU-Minute an Unvollständigem, kein Hörspiel mit 7 Löchern.

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

## Entscheidungen des PO (2026-07-17)

- **Modell bleibt 3.1** — 2.5 ist „ok, aber 3.1 ist besser" (per Ohr, A/B ohne temp).
- **`temperature 0.3` BLEIBT** — und der Grund ist wichtiger als gedacht: Es geht nicht um Klang,
  sondern um **Bedeutung**. Prosodie wird mitgewürfelt; bei 0.3 nimmt das Modell die kanonische
  Lesart (s2 „War Leonardo nur **Maler**?"), bei 0.6/default sampelt es eine andere Betonung
  („nur") — das fragt etwas anderes. **Der Vorzug und der Bug haben dieselbe Wurzel: Determinismus.**
  0.6 ist stabil (16/16), aber vom PO verworfen. → Ausfälle werden per Wiederholung erschlagen,
  nicht per Parameterwechsel. Kosten: Wartezeit, kein Geld (leere Antworten = keine Output-Tokens).
- **PO-Vorgabe:** „Stimme gut + konsistent, Aussprache zuverlässig, ohne viel manuellen Aufwand" —
  **der PO wird die 4.000–5.000 Audios NICHT anhören.** → automatische Prüfung ist Pflicht, s. Prio 1.

## Gerade in Arbeit / Nächster Schritt

- **Umgesetzt (Tests grün):** `MAX_ROUNDS` 3 → **10** (bei ~40 % Ausfall bleiben nach 3 Runden ~6 %
  = die 7 Löcher; nach 10 Promille) · **PCM-Cache gilt jetzt für BEIDE Pfade** (`_sync_pcm_cached`)
  — vorher warf ein Sync-Abbruch alle fertigen Turns weg; neuer Test 6d sichert das ab (2. Lauf =
  0 API-Calls; anderer temperature-Wert = kein Treffer).

## DURCHBRUCH: erster vollständiger Batch-Lauf 37/37 (2026-07-17)

**Ursache der Ausfälle war der STIL-PRÄFIX bei niedriger temperature — nicht temperature allein.**
Nachgewiesen im echten Lauf (`articles/leo_final_20260717`): 13 Turns waren bei `temperature 0.3`
**verschlossen** — zwei Runden unveränderter Wiederholung brachten 0 Treffer (Turn `7e7c1503`
scheiterte über beide Läufe ~6× an identischem Request). **Runde 3 mit demselben Text, derselben
temperature, nur OHNE Stil-Präfix: 10 von 13 durch. Runde 4: der Rest.** Alle 13 auf `temperature
0.3 ohne Stil-Präfix` — **die höheren Stufen (0.5/0.6/default) wurden NIE gebraucht.**

**Folge: das eingefrorene Rezept bleibt VOLLSTÄNDIG intakt.** Jeder der 37 Turns läuft auf
temperature 0.3, die PO-Betonung ist überall erhalten. Die 13 Ausnahmen unterscheiden sich nur
durch den fehlenden Stil-HINWEIS (Regieanweisung), nicht die temperature — und bei Nico trägt
ohnehin die VC den Charakter. **`[calm]`-Tags und temperature-Eskalation waren gar nicht nötig.**
Rückblick: der Bare-Text-Ausweg steckte seit dem 16.07. im Code — nur für den Safety-Block gezogen,
nicht für den Hänger. Passt zur Notiz vom 15.07. „Präfix + kurzes Fragment ist heikel" → drittes
Symptom derselben Wurzel (neben Füllwörtern und PROHIBITED_CONTENT).

**Die QA hat das erst sichtbar gemacht:** „Fünfhundert Jahre? Das ist uralt!" kam 3× als „500 Jahre?"
zurück (zweiter Satz weg, gültiges Audio, Ähnlichkeit 0.63) — ohne Gate ausgeliefert worden. Dazu
mehrere 44–56-s-Stille-Turns und ein 55-s-Turn mit nur 5,7 s hektischer Sprache (nur von der
Tempo-Regel gefangen, RMS hätte durchgelassen). Roh-Ausfallrate bestätigt: von den gelieferten
Audios war ~jedes 5. Müll mit Erfolgsmeldung.

**Eskalationsleiter** (`tts_batch.eskalationsleiter`, PO-Vorschlag): je 2 Runden 0.3 → 0.3-ohne-Stil
→ 0.5 → 0.6 → default. Billigster Verlust zuerst, PO-Kriterium (Betonung) zuletzt. Manifest führt je
Turn `temp`/`ohne_stil`/`eskaliert` → am Laufende Liste der Ausnahmen fürs PO-Ohr (hier: 13, alle
mildester Typ, müssen streng genommen nicht gehört werden). Artefakt: `leo_batch_final.wav` (37/37,
noch roh — Kind-Turns ohne VC, das ist der nächste Schritt).

## QUALITÄTS-GATE gebaut (`scripts/tts_qa.py`, 2026-07-17) — Tests grün

**Anlass:** `vertone()` prüfte nur, OB ein Turn Bytes hat. Sobald Bytes da sind, galt er als gut.
Bei 4.000–5.000 ungehörten Vertonungen war das die gefährlichste Lücke — alle Fehler sind STUMM.

**Beim Bauen sofort einen ECHTEN Defekt gefunden** (in `articles/leo_batch_20260716/pcm_cache`):
Ein Turn („Er hat nicht vier Arme, Theo…") kam als **54,4 s STILLE** zurück — RMS 20 (echte Turns:
984–3984), Whisper transkribiert Leerstring. Gültiger Audio-Blob, `JOB_STATE_SUCCEEDED`, vom alten
Gate als „vollständig" abgehakt. **Das ist die zweite Spielart der Degenerations-Schleife:** statt zu
hängen, liefert der Decoder minutenlang Stille-Token aus. Wäre als knappe Minute Nichts mitten in der
Geschichte ausgeliefert worden.

**Wie es greift:** bei der Synthese, VOR dem Cache-Schreiben und VOR der VC. Ausschuss verhält sich
wie eine leere Antwort → nicht cachen (ein kaputtes PCM im Cache wäre für immer ausgeliefert), ab in
die nächste Nachreich-Runde. Die Wiederhol-Maschinerie war schon da. Sync: `QA_VERSUCHE=3`.
Abschaltbar per `--no-qa` (nur für Tests). Kosten **0 €**, ~1 s/Turn (faster-whisper small, CPU,
int8; laeuft auf Python 3.14 — `pip install faster-whisper`).

**An 24 echten Turns kalibriert — gefangen:** Stille (RMS 20 vs. 984+) · Audio am falschen Turn
(zwei fast gleich lange Turns vertauscht → Ähnlichkeit 0.54 bei Schwelle 0.80) · kein Audio ·
Abbruch ≤60 % · Dehnungs-Schleifen. **Fehlalarme: 0 von 24.**
**NICHT gefangen (ehrliche Grenze, nicht per Schwelle behebbar — die Verteilungen ÜBERLAPPEN):**
angeschnittenes Ende bis ~30 % (bei 80 % abgeschnitten = Ähnlichkeit 0.874, **besser** als der
schlechteste echte Turn mit 0.832; Tempo: echt bis 4.45 W/s, bei 70 % abgeschnitten 4.33 W/s) ·
einzelne erfundene Füllwörter. Dafür braucht es ein anderes Verfahren, keine schärferen Zahlen.

**Zwei Konstruktionsfehler, die die Kalibrierung aufgedeckt hat:** (1) Dauer-Regel muss auf der
SPRECH-Zeit rechnen, nicht auf der Dateilänge — das Modell hängt Stille an („Wer ist das?" = 3 Wörter
in 7,4 s Datei, aber 1,3 s Sprache). (2) Ähnlichkeit auf ZEICHEN-Ebene, nicht Wort-Ebene: „Oma Rina"
vs. Whispers „O Marina" ist auf Wortebene 0.33 = Fehlalarm. Dazu Zahl-Normalisierung, weil Whisper
Ziffern schreibt und die Quelle ausschreibt („500" vs. „fünfhundert").

## Offen nach Priorität

1. **Batch-Lauf mit temp 0.3 + 10 Runden + QA verifizieren** (Erwartung: 37/37 sauber). Danach
   VC-Stufe getrennt auf EINEM Pod: Synthese ohne GPU → PCM-Cache → ein Pod färbt alle Kind-Zeilen
   am Stück um (~1–3 $ statt ~50 $). **Produktion = Batch** (PO bestätigt) und möglichst VIELE
   Artikel je Job: ein Job braucht ~70 Min unabhängig von der Menge → 10 Runden über den ganzen
   Katalog = ein Wochenendlauf, 10 Runden pro Artikel wären Wochen.
2. **ERLEDIGT — `zip`-Bug behoben:** `_zuordnen()` ordnet Antworten jetzt über `metadata["key"]` zu,
   `zip` nur noch als Fallback wenn kein metadata UND Anzahl exakt passt; sonst wird die Runde
   verworfen statt Audio am falschen Turn abzulegen. Tests in `test_tts_qa.py` Sektion 6.
3. **Timeout-Optimierung:** Erfolgreiche Calls brauchen 7–16 s, ein Hänger kommt NIE zurück (gemessen).
   `TTS_TIMEOUT_MS=60000` verschenkt pro Hänger ~45 s. 25–30 s wären ~3× schnellere Retries.
   Achtung: Tests prüfen die Konstante == 60000, und lange Turns brauchen evtl. mehr → erst messen.
4. **QA-Laufzeit im Maßstab:** ~1 s/Turn × 37 × 10.000 Vertonungen ≈ 100 h einkernig → über Kerne
   parallelisieren (oder Modell `base` prüfen). Einmalig, aber einplanen.
5. **`verify_project_facts.py`:** 1 Hart-FAIL ist Verify-Drift — Regel erwartet beim Vision-Modell noch
   `claude-sonnet-5`, `stage_models.py` steht bewusst auf `gemini-2.5-flash-lite` (Kostenentscheidung).
6. **Vor Release raus:** Debug-`isPlus`-Hook, Temp-Test-Button „Leonardo (Vorlese-Test)" in
   `home_screen.dart`, TEMP-Prints in `_prepareNarration`.
7. **Phase 5:** `--pipeline`-Default auf `new` umstellen (nach Nachtlauf-Auswertung).
8. **Tablet-Pass** (eigener Chat!): Kinderschutz / Plus & Premium / Menü / Profile tablet-zentrieren
   (`TabletMaxWidth`), danach Lesemodi A/B/C. Onboarding einmal am Tablet durchklicken.
   **Handy-Modus bleibt unangetastet** — jede Handy-Änderung vorher absprechen.
9. **Kleineres:** echte 300px-Paketgröße → `AssetConfig` (545 MB ist Platzhalter) · Cache-Cap-Regler ·
   Leuchtturm-Offline-Paket · Modellwahl Pass 2 schärfen · Validierungsordner sind Wegwerf.
