#!/usr/bin/env python3
"""nico_vc.py — Nicos Stimme per Voice-Conversion (OpenVoice v2, MIT).

Färbt fertiges Flash-TTS-Audio (Quelle: Prebuilt-Kinderstimme wie Puck) auf die
Klangfarbe des Sohnes um. Deutsch/Aussprache/Betonung stammen aus dem Flash-Audio,
die Klangfarbe aus den Referenz-Clips — deshalb kein Trainings-/Aussprache-Problem.

Wird von tts_story.py als optionaler Kind-Turn-Converter genutzt (Standard: aus).
Signatur eines Converters: ``(pcm: bytes, sample_rate: int) -> bytes`` (PCM s16le mono).

BRAUCHT eine GPU + OpenVoice + Checkpoints — läuft NICHT auf dem normalen
Generierungs-PC. Vorgesehen für den GPU-Batch-Job (gemietete GPU / Pod), wo
OpenVoice installiert ist (siehe bootstrap_openvoice.sh). Aufruf über do_vc.sh
bzw. scripts/produce_story.py (Phase vc).

Dieses File ist die Pod-Seite der Produktions-Pipeline — Single Source of Truth
liegt hier im Repo (pod/), NICHT mehr in einem Session-Scratchpad.
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
               Produktion nutzt genau rich_ref.wav (freigegeben 2026-07-16).
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
