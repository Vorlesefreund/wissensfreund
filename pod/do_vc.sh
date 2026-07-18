#!/usr/bin/env bash
# do_vc.sh — Pod-Seite der Produktion: OpenVoice bootstrappen, dann die
# INTEGRIERTE tts_story.vertone() über den (geflatteten) PCM-Cache laufen lassen.
#
# WICHTIG — Reproduzierbarkeit:
#  * KEIN --tts-temperature: vertone nutzt die Default-Basis-Temperatur (0.3),
#    exakt die, auf die scripts/tts_flatten_cache.py den Cache geflattet hat.
#    Nur so ist JEDER Turn ein Cache-Treffer und der Gemini-Client (Dummy-Key)
#    wird NIE aufgerufen.
#  * --no-qa: faster-whisper ist auf dem Pod nicht installiert; die QA lief
#    schon lokal (Phase synth). VC ist deterministisch, braucht kein QA.
#
# Erwartete Payload in /workspace/run: seg.json, pcm_cache/ (geflattet),
# nico_ref/rich_ref.wav, tts_story.py, tts_batch.py, tts_qa.py, nico_vc.py,
# bootstrap_openvoice.sh, do_vc.sh.
set -e
cd /workspace/run

TITEL="${STORY_TITEL:-story}"

echo "########## BOOTSTRAP OpenVoice ##########"
bash bootstrap_openvoice.sh

echo "########## VC-LAUF (alle Turns aus Cache, VC nur auf Kind-Turns) ##########"
export GEMINI_API_KEY=dummy         # vertone baut den Client, ruft ihn aber nie (alles gecacht)
python tts_story.py \
  --seg-file seg.json \
  --pcm-cache pcm_cache \
  --nico-ref nico_ref \
  --nico-ckpt /workspace/checkpoints_v2/converter \
  --openvoice-path /workspace/OpenVoice \
  --no-qa \
  --titel "$TITEL" \
  --out-dir out

echo "########## ERGEBNIS ##########"
ls -la out/
# harte Kontrolle: es MUSS ein nicht-triviales WAV entstanden sein
WAV="out/${TITEL}.wav"
if [ ! -s "$WAV" ]; then
  echo "FEHLER: $WAV fehlt oder ist leer — VC-Lauf gescheitert." >&2
  exit 1
fi
echo "########## FERTIG ##########"
