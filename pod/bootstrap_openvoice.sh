#!/usr/bin/env bash
# bootstrap_openvoice.sh — richtet OpenVoice v2 (ToneColorConverter) auf einem
# frischen RunPod ein. Idempotent: erneutes Ausführen überspringt vorhandene Teile.
# Image-Annahme: runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04.
set -e
cd /workspace
echo "=== ffmpeg ==="
apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1
echo "=== OpenVoice klonen (NICHT pip install -e .) ==="
[ -d OpenVoice ] || git clone -q https://github.com/myshell-ai/OpenVoice
echo "=== Python-Deps ==="
pip install -q librosa soundfile wavmark huggingface_hub inflect unidecode \
    eng_to_ipa pypinyin cn2an jieba python-dotenv google-genai 2>&1 | tail -2
echo "=== Checkpoints (converter) ==="
python - << 'PY'
from huggingface_hub import snapshot_download
snapshot_download('myshell-ai/OpenVoiceV2', allow_patterns=['converter/*'], local_dir='/workspace/checkpoints_v2')
print("checkpoints ok")
PY
ls -la /workspace/checkpoints_v2/converter/
echo "=== BOOTSTRAP FERTIG ==="
