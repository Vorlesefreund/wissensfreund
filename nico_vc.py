#!/usr/bin/env python3
"""nico_vc.py — Nicos Stimme per Voice-Conversion (OpenVoice v2, MIT).

Färbt fertiges Flash-TTS-Audio (Quelle: Prebuilt-Kinderstimme wie Puck) auf die
Klangfarbe des Sohnes um. Deutsch/Aussprache/Betonung stammen aus dem Flash-Audio,
die Klangfarbe aus den Referenz-Clips — deshalb kein Trainings-/Aussprache-Problem.

Wird von tts_story.py als optionaler Kind-Turn-Converter genutzt (Standard: aus).
Signatur eines Converters: ``(pcm: bytes, sample_rate: int) -> bytes`` (PCM s16le mono).

BRAUCHT eine GPU + OpenVoice + Checkpoints — läuft NICHT auf dem normalen
Generierungs-PC. Vorgesehen für den GPU-Batch-Job (gemietete GPU / Pod), wo
OpenVoice installiert ist. Setup (bewährt):
    git clone https://github.com/myshell-ai/OpenVoice        # NICHT pip install -e .
    pip install librosa soundfile wavmark huggingface_hub inflect unidecode \
                eng_to_ipa pypinyin cn2an jieba            # + apt install ffmpeg
    python -c "from huggingface_hub import snapshot_download; \
        snapshot_download('myshell-ai/OpenVoiceV2', allow_patterns=['converter/*'], local_dir='checkpoints_v2')"
Aufruf dann z. B.:
    python -X utf8 tts_story.py --story-file story.txt --titel Leonardo --out-dir OUT \
        --nico-ref son_clips --nico-ckpt checkpoints_v2/converter \
        --openvoice-path ./OpenVoice --nico-tau 0.7
"""
from __future__ import annotations
import glob
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


class OpenVoiceNicoConverter:
    """Lädt OpenVoice + das Ziel-Timbre (Sohn) EINMAL und färbt dann pro Aufruf um.

    ref_dir  : Ordner mit sauberen Sohn-Referenz-WAVs (das Ziel-Timbre; alle werden
               zu EINEM Sprecher-Embedding gemittelt — mehr saubere Clips = stabiler).
    ckpt_dir : OpenVoice-converter-Ordner mit config.json + checkpoint.pth.
    tau      : VC-Stärke (0.7 = vom User freigegeben; höher → mehr Sohn-Timbre).
    """

    def __init__(self, ref_dir, ckpt_dir, tau: float = 0.7,
                 device: str = "cuda", openvoice_path: str | None = None):
        if openvoice_path:
            sys.path.insert(0, str(openvoice_path))
        from openvoice.api import ToneColorConverter  # erst hier importieren (GPU-seitig)

        ckpt = Path(ckpt_dir)
        self.tau = tau
        self.tcc = ToneColorConverter(str(ckpt / "config.json"), device=device)
        self.tcc.load_ckpt(str(ckpt / "checkpoint.pth"))

        refs = sorted(glob.glob(str(Path(ref_dir) / "*.wav")))
        if not refs:
            raise FileNotFoundError(f"Keine Referenz-WAVs in {ref_dir}")
        self.tgt_se = self.tcc.extract_se(refs)   # Ziel-Timbre (Sohn) — einmal
        print(f"  [nico_vc] Ziel-Timbre aus {len(refs)} Clips, tau={tau}")

    def __call__(self, pcm: bytes, sample_rate: int) -> bytes:
        """Färbt ein PCM-Segment (s16le mono) um und gibt PCM (gleiche SR) zurück."""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.wav"
            out = Path(td) / "out.wav"
            with wave.open(str(src), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
                wf.writeframes(pcm)
            src_se = self.tcc.extract_se([str(src)])
            self.tcc.convert(audio_src_path=str(src), src_se=src_se, tgt_se=self.tgt_se,
                             output_path=str(out), tau=self.tau, message="@Nico")
            # OpenVoice schreibt evtl. mit anderer SR → auf sample_rate s16le mono zurück
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(out), "-ar", str(sample_rate), "-ac", "1",
                 "-f", "s16le", "-"], capture_output=True)
            return r.stdout
