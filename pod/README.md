# pod/ — GPU-Seite der TTS-Produktions-Pipeline

Diese Dateien laufen **auf dem gemieteten RunPod** (GPU), nicht auf dem
Generierungs-PC. Sie sind die versionierte Single Source of Truth für den
Voice-Conversion-Schritt (Nicos Stimme). Früher lagen sie in einem
Session-Scratchpad — dadurch war der Produktionslauf nicht reproduzierbar.

| Datei | Zweck |
|-------|-------|
| `bootstrap_openvoice.sh` | Richtet OpenVoice v2 + Checkpoints auf frischem Pod ein (idempotent). |
| `nico_vc.py` | `OpenVoiceNicoConverter` — färbt Kind-Turns auf Nicos Timbre (rich_ref.wav, tau 0.7). |
| `do_vc.sh` | Bootstrap + `tts_story.vertone()` über den geflatteten Cache (Temp 0.3, `--no-qa`). |

**Aufgerufen wird das nicht von Hand**, sondern von
[`scripts/produce_story.py`](../scripts/produce_story.py) (Phase `vc`): das
Skript baut die Payload, erstellt den Pod, lädt hoch, startet `do_vc.sh`, lädt
das Ergebnis zurück und terminiert den Pod.

Warum VC auf dem Pod und nicht lokal: OpenVoice braucht eine CUDA-GPU. Der
restliche Lauf (Segmentierung, Gemini-Batch-Synthese, QA, Pegel) läuft lokal
auf der CPU. Details: [`../TTS_PRODUKTION_PIPELINE.md`](../TTS_PRODUKTION_PIPELINE.md).
