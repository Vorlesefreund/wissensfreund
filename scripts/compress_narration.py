#!/usr/bin/env python3
"""
compress_narration.py — Track A der Vertonungs-Auslieferung.

Wandelt die rohen TTS-Narrations-WAVs (24 kHz mono 16-bit ~2,88 MB/min) in
komprimiertes AAC-.m4a (~48 kbps mono) um und baut daraus `narration_index.json`.
Zweck: Auslieferung per Streaming von R2 statt riesiger WAV-Bündel.

Warum AAC .m4a: läuft nativ auf Android UND iOS (ein Encode für beide Plattformen),
just_audio spielt es ohne Zusatzbibliothek. Für Sprache reichen 48 kbps locker
(gemessen: 4,3-min-WAV 12 MB → ~1 MB).

Dateinamens-Konvention (aus tts_produce.py):
    {article_id}_l{level}_artikel.wav          — Artikel-Narration (immer)
    {article_id}_l{level}_{suffix}.wav         — Quiz-/Zusatz-Clips (suffix = quiz_...)

Ausgabe (Staging-Ordner):
    {article_id}_l{level}_artikel.m4a  (+ Clips)
    narration_index.json

Aufruf:
    python -X utf8 scripts/compress_narration.py \
        --in  articles/batch_output/audio \
        --out articles/batch_output/audio_m4a

Idempotent: bereits konvertierte, aktuelle .m4a werden übersprungen
(erneute Konvertierung nur, wenn die WAV neuer ist als die m4a).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# UTF-8-sichere Konsole (Windows cp1252 crasht sonst an ü / — / …).
if hasattr(sys.stdout, "buffer") and (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# {article_id}_l{level}_{kind}.wav  — id greedy, damit ids mit '_' (zweiter_weltkrieg) passen.
NAME_RE = re.compile(r"^(?P<id>.+)_l(?P<lvl>\d+)_(?P<kind>.+)\.wav$", re.IGNORECASE)


def find_ffmpeg(name: str) -> str:
    """ffmpeg/ffprobe aus PATH; sonst schlicht der Name (Fehler kommt beim Aufruf)."""
    import shutil
    return shutil.which(name) or name


FFMPEG = find_ffmpeg("ffmpeg")
FFPROBE = find_ffmpeg("ffprobe")


def probe_duration(path: Path) -> float:
    """Dauer in Sekunden via ffprobe (0.0 bei Fehler)."""
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return round(float(out), 1)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 0.0


def encode(src: Path, dst: Path, bitrate_k: int) -> bool:
    """WAV → AAC .m4a (mono, Sample-Rate der Quelle). True bei Erfolg."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
             "-c:a", "aac", "-b:a", f"{bitrate_k}k", "-ac", "1", str(dst)],
            check=True,
        )
        return dst.exists() and dst.stat().st_size > 0
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  FEHLER ffmpeg {src.name}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Track A: Narration-WAV → AAC .m4a + narration_index.json")
    ap.add_argument("--in", dest="in_dir", default="articles/batch_output/audio",
                    help="Ordner mit den *_artikel.wav / *_quiz_*.wav")
    ap.add_argument("--out", dest="out_dir", default="articles/batch_output/audio_m4a",
                    help="Staging-Ordner für .m4a + narration_index.json (Upload-Quelle)")
    ap.add_argument("--bitrate", type=int, default=48, help="AAC-Bitrate in kbps (Default 48)")
    ap.add_argument("--force", action="store_true", help="auch aktuelle .m4a neu erzeugen")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    if not in_dir.is_dir():
        print(f"Eingabeordner fehlt: {in_dir}")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    wavs = sorted(in_dir.glob("*.wav"))
    if not wavs:
        print(f"Keine .wav in {in_dir}")
        return 1

    # narration[id][stufe] = {file, dur_s, bytes}      (Artikel-Narration)
    # clips[id][stufe]     = [{suffix, file, dur_s, bytes}, ...]  (Quiz etc.)
    narration: dict[str, dict[str, dict]] = {}
    clips: dict[str, dict[str, list]] = {}

    total_wav = total_m4a = 0
    n_enc = n_skip = n_fail = 0

    for wav in wavs:
        m = NAME_RE.match(wav.name)
        if not m:
            print(f"  ? Namensschema unbekannt, übersprungen: {wav.name}")
            continue
        aid, lvl, kind = m["id"], m["lvl"], m["kind"]
        m4a = out_dir / f"{wav.stem}.m4a"

        # Idempotenz: aktuelle m4a behalten (außer --force).
        fresh = m4a.exists() and m4a.stat().st_mtime >= wav.stat().st_mtime
        if fresh and not args.force:
            n_skip += 1
        else:
            if not encode(wav, m4a, args.bitrate):
                n_fail += 1
                continue
            n_enc += 1

        total_wav += wav.stat().st_size
        total_m4a += m4a.stat().st_size
        rec = {"file": m4a.name, "dur_s": probe_duration(m4a), "bytes": m4a.stat().st_size}

        if kind.lower() == "artikel":
            narration.setdefault(aid, {})[lvl] = rec
        else:
            rec["suffix"] = kind
            clips.setdefault(aid, {}).setdefault(lvl, []).append(rec)

    index = {
        "generated": date.today().isoformat(),
        "format": "m4a",
        "codec": "aac",
        "bitrate_kbps": args.bitrate,
        "narration": narration,
        "clips": clips,
    }
    idx_path = out_dir / "narration_index.json"
    idx_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    mb = 1024 * 1024
    ratio = (total_wav / total_m4a) if total_m4a else 0
    print("\n── Fertig ─────────────────────────────────")
    print(f"  Konvertiert: {n_enc} | übersprungen: {n_skip} | Fehler: {n_fail}")
    print(f"  Artikel-Narrationen: {sum(len(v) for v in narration.values())} "
          f"({len(narration)} Themen)")
    print(f"  Clips: {sum(len(l) for v in clips.values() for l in v.values())}")
    print(f"  Größe: {total_wav/mb:.1f} MB WAV → {total_m4a/mb:.1f} MB m4a  (~{ratio:.1f}× kleiner)")
    print(f"  Index: {idx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
