# Nico-Stimme — EINGEFROREN am 2026-07-16

Vom Product Owner abgenommen. **Nicht ohne neue Abnahme ändern** — jede Änderung an einem der
Parameter unten ergibt eine ANDERE Stimme.

## Das Rezept

| Schritt | Festlegung |
|---|---|
| 1. Quelle | Gemini Flash TTS, Modell `gemini-3.1-flash-tts-preview` |
| 2. Stimme | **Puck** (Junge) / Leda (Mädchen) — nur Quelle für Aussprache + Sprechmelodie |
| 3. Stil | `STYLE["kind"]` (neutral, „neugieriges Kind"), + optional `emotion` je Turn |
| 4. **temperature** | **0.3** (`TTS_TEMPERATURE` in `tts_story.py`) |
| 5. Umfärbung | **OpenVoice v2** (MIT-Lizenz), `ToneColorConverter`, **tau = 0.7** |
| 6. **Referenz** | **`rich_ref.wav` ALLEIN** (80,1 s, 24 kHz mono) |
| 7. Pegel | `loudnorm=I=-16:TP=-1.5` je Turn (`_loudnorm`) |

Ergebnis: F0 ~272–330 Hz (Kinderlage), Streuung nach VC ±2–11 Hz.

## Wo die Referenz liegt — WICHTIG

`C:\Users\Andreas\Desktop\_nico_clone\ref_clips\rich_ref.wav`

**Diese Datei ist der Flaschenhals der ganzen Stimme.** Ohne sie ist Nico nicht reproduzierbar.
Sie lag bis 16.07. NUR in einem Temp-Verzeichnis und wäre beim Aufräumen verloren gewesen.

- **Gehört NICHT ins Repo** — das Repo ist ÖFFENTLICH (`Vorlesefreund/wissensfreund`), und das ist
  die Stimme eines Kindes. Niemals committen, auch nicht in einem privaten Unterordner „nur kurz".
- **Braucht ein Backup außerhalb des Desktops** (externe Platte / privater Cloud-Ordner). Aktuell
  existiert sie an genau EINER Stelle — ein Plattenfehler kostet die abgenommene Stimme.
- Rohaufnahmen (Quelle für ein evtl. neues Set): `Documents/Audioaufzeichnungen/` (104 × m4a).

**Gotcha:** `--nico-ref` mittelt ALLE WAVs im Ordner zu EINEM Embedding. Für das eingefrorene
Rezept darf nur `rich_ref.wav` im übergebenen Ordner liegen. Die anderen Clips in `ref_clips/`
sind Historie, kein Bestandteil des Rezepts.

## Warum genau diese Werte (damit niemand daran „optimiert")

- **temperature 0.3**: per Hörurteil des PO gewählt (Samples: `Desktop/_nico_temp_vergleich`,
  2 Sätze × 3 Stufen × 3 Nahmen). Die Tonhöhe taugt NICHT als Argument — nach der VC ist sie bei
  jeder Stufe gleich ruhig (±2–11 Hz). Entschieden hat der VORTRAG: OpenVoice überträgt nur die
  Klangfarbe, Betonung/Sprechmelodie kommen aus dem Flash-Original und überleben die VC.
- **tau 0.7**: durchgesweept (`vc_test/tau_sweep`), vom PO gewählt.
- **Puck bleibt**, obwohl es die unruhigste Quelle ist (roh 132–387 Hz!): die VC normalisiert das
  auf 272–330 Hz. Genau deshalb war der rohe Puck-Platzhalter damals eine „Erwachsenenstimme" —
  und deshalb erzwingt `vertone()` seit `59554db` die VC für Kind-Turns.

## Verworfen — nicht nochmal probieren

| Ansatz | Warum raus |
|---|---|
| `seed` | wird vom Modell IGNORIERT (fixer seed → weiter ±12–37 Hz). Kein Determinismus möglich. |
| Best-of-N | überflüssig — die VC normalisiert die Tonhöhe bereits (±2–11 Hz). |
| F0-Nachbearbeitung | klingt SCHLECHTER als das Original (librosa=Nachhall, rubberband=Phasing; Blind-Test 2/5 gegen 4/5). |
| Chatterbox Fine-Tune | verschlechtert deutsche Aussprache (ü/ö out-of-distribution). |
| CosyVoice2 | englischer Akzent. |

---

# WENN DIE STIMME ZU SEHR SCHWANKT — was wir noch versuchen können

Diese Seite ist für den Fall geschrieben, dass beim echten Hören über mehrere Themen auffällt:
„Nico schwankt." Dann NICHT blind herumschrauben — die meisten Hebel sind nachweislich tot
(s. „Verworfen" oben). Der Reihe nach:

## Hebel 1: Größeres Referenz-Set (der einzige echte, kostet nur GPU-Minuten)

**Warum das plausibel hilft.** Nicos Timbre steckt heute in EINEM Clip (`rich_ref.wav`, 80 s,
eine Aufnahme). `nico_vc.py` sagt es selbst: *„alle werden zu EINEM Sprecher-Embedding gemittelt
— mehr saubere Clips = stabiler"*. Ein Embedding aus einer einzigen Aufnahme trägt die Eigenheiten
genau dieser Aufnahme (Tagesform, Mikrofonabstand, Raum).

**Woran man sieht, dass da wirklich Luft ist.** Gemessen 2026-07-16 (Nico nach VC, je 3 Nahmen):

| | s1 „Fünfhundert Jahre? Das ist uralt!" | s2 „War Leonardo nur Maler?" |
|---|---|---|
| F0 nach VC | ~313–330 Hz | ~272–283 Hz |

**INNERHALB** eines Satzes bügelt die VC fast alles weg (±2–11 Hz). **ZWISCHEN** Sätzen bleiben
~50 Hz stehen. Das ist genau die Größenordnung, die man als „schwankt noch etwas" hört — und der
plausibelste Ansatzpunkt, weil das Ziel-Embedding die einzige Größe ist, die über alle Sätze
konstant sein sollte.

**Das Rezept.**
1. Rohmaterial: `Documents/Audioaufzeichnungen/` (104 × m4a). Nach 24 kHz mono WAV wandeln:
   `ffmpeg -i "Aufzeichnung (N).m4a" -ar 24000 -ac 1 take_N.wav`
2. Sauber auswählen — das ist der eigentliche Aufwand, nicht die Rechenzeit. Kriterien:
   kein Hall, kein Nebengeräusch, keine Übersteuerung, ruhige Sprechlage, verschiedene Sätze.
   Ziel: **5–10 Clips à 10–20 s aus VERSCHIEDENEN Aufnahmen** (Vielfalt ist der Punkt — sonst
   mittelt man dieselbe Eigenheit nur mehrfach).
3. Alle in EINEN Ordner, den an `--nico-ref` übergeben (die Funktion mittelt sie automatisch).
4. GPU-Pod (s. `Desktop/_nico_clone/pod_zugang/`), `bootstrap_openvoice.sh`, dann dieselben
   Sätze wie oben rendern.
5. **Messen UND hören**: bleibt der Abstand s1↔s2 unter ~50 Hz? Und klingt es noch nach Nico?

**Der Preis, den man dabei zahlt.** Ein neues Referenz-Set ist ein **anderes Timbre**. Die neue
Stimme muss neu abgenommen werden, und sie kann schlechter sein — mehr Clips heißt auch: mehr
Gelegenheit, Müll mit hineinzumitteln. Deshalb: **das alte Set NIE überschreiben**, neue Variante
parallel bauen, A/B gegen `rich_ref.wav` hören, und nur wechseln, wenn es hörbar besser ist.

## Hebel 2: tau nachjustieren (klein, riskant)

tau 0.7 wurde durchgesweept (`vc_test/tau_sweep`) und abgenommen. Höheres tau = mehr Sohn-Timbre =
stärkere Normalisierung, aber irgendwann Artefakte. Nur anfassen, wenn Hebel 1 nichts bringt, und
nur im A/B gegen den eingefrorenen Stand.

## Hebel 3: Best-of-N NUR auf Kind-Zeilen (teuer, letzte Wahl)

Mehrere Nahmen je Zeile, die mediannächste behalten. **Kostet Faktor 2–3 auf die Kind-Zeilen**
(Katalog-Auswirkung: s. Kostentabelle in `WISSEN_ARTIKEL_PIPELINE.md`). Wurde als überflüssig
eingestuft, WEIL die VC die Tonhöhe normalisiert — das gilt aber nur für die Tonhöhe. Wenn der
VORTRAG schwankt (Betonung, Tempo), ist Best-of-N mit Ohr-Richter der einzige Hebel, der dort
greift, denn Betonung kommt aus dem Flash-Original und überlebt die VC.

## Was NICHT hilft (nicht nochmal ausprobieren)

`seed` (wird ignoriert) · F0-Nachbearbeitung (klingt schlechter) · andere Quellstimme als Puck
(die VC normalisiert die Quelle ohnehin — Sadaltager war roh stabiler, nach VC egal) ·
Fine-Tune (deutsche Aussprache bricht).
