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

## Der einzige verbliebene Hebel (bewusst NICHT gezogen)

Ein **größeres Referenz-Set** (mehrere saubere Clips statt einem) könnte den Rest-Unterschied
zwischen Sätzen glätten (s1 ~330 Hz vs s2 ~280 Hz — die VC gleicht INNERHALB eines Satzes stark
an, ZWISCHEN Sätzen bleibt Spielraum). Kostet nur GPU-Minuten.

**Nicht gezogen, weil:** ein neues Referenz-Set = ein anderes Timbre = neue Abnahme nötig. Die
aktuelle Stimme ist abgenommen. Erst ziehen, wenn beim echten Mehr-Themen-Lauf tatsächlich
Schwankung auffällt — sonst optimieren wir gegen eine Zahl statt gegen ein Problem.
