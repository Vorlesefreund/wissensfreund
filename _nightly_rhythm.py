#!/usr/bin/env python3
"""Nachtlauf-Runner (off-peak, meidet Gemini-503-Mittagsspitzen).

Generiert die Arbeits-Themen als Hörspiel mit dem aktuellen Prompt B
(Rahmen-Wit + Frequenz-Regel) und aktivem Kind-Turn-Guard, dann baut er
die Review-Docx in den festen Desktop-Standard-Ordner.

Als Python-Runner geschrieben (nicht als PowerShell-Argument-Kette), damit
Umlaut-Themen sauber durchkommen. Wird per Windows-Scheduler nachts gestartet.
"""
from __future__ import annotations
import os, sys, subprocess, datetime, pathlib

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT   = pathlib.Path(__file__).resolve().parent
PY     = sys.executable
THEMEN = ["Vulkan", "Dinosaurier", "Spielzeug"]
DATE   = datetime.date.today().isoformat()
STAMP  = DATE.replace("-", "")

OUTDIR = ROOT / "articles" / f"bakeoff_nacht_{STAMP}"
DESK   = pathlib.Path.home() / "Desktop" / "Wissensfreund_Review" / f"{DATE}_Nachtlauf"
LOG    = ROOT / "articles" / f"_nacht_{STAMP}.log"
DESK.mkdir(parents=True, exist_ok=True)

env = {**os.environ}


def run(cmd: list[str], logfh) -> int:
    logfh.write(f"\n$ {' '.join(cmd)}\n"); logfh.flush()
    return subprocess.run(cmd, cwd=str(ROOT), env=env,
                          stdout=logfh, stderr=subprocess.STDOUT).returncode


def main() -> int:
    with open(LOG, "w", encoding="utf-8") as logfh:
        logfh.write(f"Nachtlauf {DATE}  Themen={THEMEN}\n")
        gen_rc = run([
            PY, "scripts/generate_grounded.py",
            "--catalog", *THEMEN,
            "--typen", "hoerspiel",
            "--gen-model", "gemini-3.5-flash",
            "--hoerspiel-prompt", "wissensfreund_hoerspiel_prompt_v2_B.md",
            "--skip-images", "--skip-lektorat",
            "--output-dir", str(OUTDIR),
            "--run-id", f"nacht_{STAMP}",
        ], logfh)
        logfh.write(f"\n[generate] rc={gen_rc}\n")

        docx_rc = run([
            PY, "scripts/generate_review_docx.py", str(OUTDIR),
            "--output", str(DESK / f"Nachtlauf_{DATE}.docx"),
        ], logfh)
        logfh.write(f"[docx] rc={docx_rc}\n")
        logfh.write(f"\nFERTIG. Artikel: {OUTDIR}\nDocx: {DESK}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
