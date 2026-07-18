# TTS-Produktions-Pipeline — reproduzierbar (Stand 2026-07-18)

Ein committeter Befehl von der (gegengelesenen) Segmentierung bis zum fertigen
`*_NicoVC.m4a`. Ersetzt die früher von Hand gefahrenen Scratchpad-Schritte, die
den Leonardo-Lauf unreproduzierbar gemacht hatten.

Orchestrator: [`scripts/produce_story.py`](scripts/produce_story.py).
Qualitätslogik (unverändert): `tts_story.py` (Segmentierung „mit Tags", Schnitt,
RMS-Pegel), `scripts/tts_batch.py` (Batch + Emotions-Eskalation), `scripts/tts_qa.py`
(Stille-/Tempo-/Transkript-Gate). Pod-Seite: [`pod/`](pod/README.md).

## Die drei Phasen

```
synth  (lokal, CPU)   Segmentierung → Gemini-Batch-Synthese + QA + Emotions-
                      Eskalation → Gegenlese-WAV + Manifest + PCM-Cache,
                      danach CACHE-FLATTEN auf Basis-Temp 0.3.
vc     (Pod, GPU)     Payload aus dem Repo bauen → RunPod erstellen → hochladen
                      → do_vc.sh (OpenVoice-VC, rich_ref.wav, tau 0.7) →
                      herunterladen → Pod TERMINIEREN → WAV → m4a.
all                   synth, dann vc.
```

## Befehle

**Alles auf einmal** (frozen, gegengelesene Segmentierung):
```bash
python scripts/produce_story.py all \
    --seg-file articles/leo_mittags_20260718/leo_mittags_segmentierung.json \
    --titel Leonardo \
    --run-dir articles/leo_prod_<datum> \
    --nico-ref <ordner-mit-rich_ref.wav> \
    --out "C:/Users/Andreas/Desktop/Leonardo_NicoVC.m4a"
```

**Getrennt** (erst lokal gegenlesen, Pod erst nach Freigabe — spart GPU-Geld):
```bash
# 1) lokal: QA-Render + pod-fertiger Cache
python scripts/produce_story.py synth --seg-file ... --titel Leonardo --run-dir DIR
#    → DIR/Leonardo.wav anhören
# 2) Pod-VC + m4a
python scripts/produce_story.py vc --run-dir DIR --titel Leonardo --nico-ref ... --out OUT.m4a
```

**Nur Payload prüfen, ohne Pod-Kosten:** `vc … --dry-run`.

Aus roher Prosa statt Segmentierung: `--story-file story.txt` (wird EINMALIG
segmentiert und als `DIR/seg.json` eingefroren; danach nie neu segmentiert).

## Warum der Flatten-Schritt existiert

`tts_batch` rettet hängende Turns per Eskalation (Temp 0.3 → 0.5 → 0.6). Die
Temp geht in den Cache-Hash ein → ein eskalierter Turn liegt unter seinem
Eskalations-Key, nicht unter dem Basis-Key (0.3). Der Pod-`vertone` läuft bei
Temp 0.3 und sucht nur Basis-Keys — eskalierte Turns wären Cache-Misses und der
(mit Dummy-Key gebaute) Gemini-Client würde aufgerufen → Abbruch.

[`scripts/tts_flatten_cache.py`](scripts/tts_flatten_cache.py) kopiert jedes
Gewinn-PCM zusätzlich unter seinen Basis-Key. Danach trifft der Pod zu 100 % den
Cache (0 Gemini-Calls). Der Schlüssel wird über dieselbe `TtsRequest.build`
berechnet wie die Synthese — kein reimplementierter Hash. `produce_story synth`
bricht ab, wenn nach dem Flatten noch ein Basis-Key fehlt (kein halbes Audio zum
Pod).

## Was reproduzierbar ist — und was nicht

- **Qualität: ja.** Segmentierung „mit Tags", QA-Gate, Emotions-Eskalation und
  RMS-Pegel (deterministisch, längen-/ffmpeg-unabhängig) stecken in committetem,
  getestetem Code. Jeder Lauf liefert QA-saubere, einheitlich laute, vollständige
  Audios — oder bricht sauber ab (Vollständigkeits-Gate).
- **Bit-genau: nein.** Gemini-TTS ist stochastisch; zwei frische Läufe klingen
  minimal anders. Für **exakt** dieselbe Datei dienen die eingefrorenen
  Artefakte: `seg.json` + inhalts-hash-basierter PCM-Cache → VC + Pegel + Schnitt
  sind daraus deterministisch.
- **Pod-Zugang** (SSH-Key `runpod_nico`, `runpod_ctl.py`, `RUNPOD_API_KEY` in
  `.env`) liegt bewusst außerhalb des Repos (Geheimnis). Default-Pfad in
  `produce_story.py` (`--pod-zugang` überschreibt).

## Guard-Tests (deterministisch, kein Netz/Pod)

`python -X utf8 scripts/test_produce_pipeline.py` — Flatten (bit-genau,
idempotent, ehrliche Fehlermeldung) + Payload-Assembly (vollständig, verweigert
unvollständigen Cache). Dazu wie bisher `test_tts_batch.py`, `test_tts_qa.py`,
`test_tts_story_guards.py`.

## Kosten

Pod-VC (RTX 3090) ~$0,05/Lauf, wenige Minuten, Pod wird im `finally` immer
terminiert (Kontrolle: `runpod_ctl.py list`). Lokale Synthese: nur Wartezeit
(leere Gemini-Antworten kosten keine Output-Tokens). Batch ~0,12 €/Vertonung.

## Referenz-Lauf

`articles/leo_mittags_20260718/` (46 Turns, „mit Tags") →
`Desktop/_leo_final_20260717/Leonardo_FINAL_mitTags_NicoVC.m4a` (6:47). 17 Turns
eskaliert auf Temp 0.5, per Flatten auf Basis-Key kopiert; Pod 45/45 aus Cache.
Verwandt: [[STIMME_NICO_EINGEFROREN.md]] (Stimm-Rezept), [[STUFEN_UMBAU_PLAN.md]].
