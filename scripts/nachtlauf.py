#!/usr/bin/env python3
"""nachtlauf.py — Generierungslauf off-peak, mit Wiederholung gegen 503-Wellen.

gemini-3.5-flash ist tagsueber verlaesslich ueberlastet (503 UNAVAILABLE);
Laeufe um 03:00 gehen bisher immer durch. Dieser Runner startet den Generator,
wiederholt ihn bei Misserfolg mit Abstand und baut am Ende die Review-Docx in
den festen Desktop-Ordner.

Als Python-Runner geschrieben (nicht als PowerShell-Argument-Kette), damit
Umlaut-Themen sauber durchkommen. Wird per Windows-Scheduler gestartet.

  python -X utf8 scripts/nachtlauf.py --label Pass4 --themen Vulkan Dinosaurier Spielzeug
"""
from __future__ import annotations
import argparse, datetime, os, pathlib, subprocess, sys, time

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY   = sys.executable


def run(cmd: list[str], logfh) -> int:
    logfh.write(f"\n$ {' '.join(cmd)}\n")
    logfh.flush()
    return subprocess.run(cmd, cwd=str(ROOT), env={**os.environ},
                          stdout=logfh, stderr=subprocess.STDOUT).returncode


def artikel_zahl(outdir: pathlib.Path) -> int:
    """Fertige Artikel (ohne _report), um Erfolg unabhaengig vom Exit-Code zu messen."""
    if not outdir.is_dir():
        return 0
    return len([f for f in outdir.glob("*.json") if not f.name.endswith("_report.json")])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="Nachtlauf", help="Ordner-/Dateiname auf dem Desktop")
    ap.add_argument("--themen", nargs="+", default=["Vulkan", "Dinosaurier", "Spielzeug"])
    ap.add_argument("--typen", nargs="+", default=["hoerspiel", "erzaehltext"])
    ap.add_argument("--versuche", type=int, default=3, help="Generierungs-Anlaeufe")
    ap.add_argument("--pause", type=int, default=1800, help="Sekunden zwischen den Anlaeufen")
    ap.add_argument("--skip-images", action="store_true")
    args = ap.parse_args()

    date  = datetime.date.today().isoformat()
    stamp = date.replace("-", "")
    outdir = ROOT / "articles" / f"nacht_{args.label.lower()}_{stamp}"
    desk   = pathlib.Path.home() / "Desktop" / "Wissensfreund_Review" / f"{date}_{args.label}"
    log    = ROOT / "articles" / f"_nacht_{args.label.lower()}_{stamp}.log"
    desk.mkdir(parents=True, exist_ok=True)

    erwartet = len(args.themen) * len(args.typen)

    with open(log, "w", encoding="utf-8") as fh:
        fh.write(f"Nachtlauf '{args.label}' {date}\n"
                 f"  Themen : {args.themen}\n"
                 f"  Typen  : {args.typen}\n"
                 f"  erwartet: {erwartet} Artikel\n")

        gen = [PY, "scripts/generate_grounded.py",
               "--catalog", *args.themen,
               "--typen", *args.typen,
               "--gen-model", "gemini-3.5-flash",
               "--skip-lektorat",
               "--output-dir", str(outdir),
               "--run-id", f"nacht_{args.label.lower()}_{stamp}"]
        if args.skip_images:
            gen.append("--skip-images")

        # Erfolg an fertigen Artikeln messen, nicht am Exit-Code: der Generator
        # beendet sich auch dann mit 0, wenn einzelne Jobs an 503 gescheitert sind.
        for versuch in range(1, args.versuche + 1):
            fh.write(f"\n===== Anlauf {versuch}/{args.versuche} "
                     f"({datetime.datetime.now():%H:%M:%S}) =====\n")
            rc = run(gen, fh)
            fertig = artikel_zahl(outdir)
            fh.write(f"\n[generate] rc={rc}  fertige Artikel: {fertig}/{erwartet}\n")
            fh.flush()
            if fertig >= erwartet:
                fh.write("Vollstaendig — keine weiteren Anlaeufe noetig.\n")
                break
            if versuch < args.versuche:
                fh.write(f"Unvollstaendig — warte {args.pause}s und versuche erneut.\n")
                fh.flush()
                time.sleep(args.pause)

        fertig = artikel_zahl(outdir)
        if fertig:
            docx = desk / f"{args.label}_{fertig}-Artikel_{date}.docx"
            rc = run([PY, "scripts/generate_review_docx.py", str(outdir),
                      "--output", str(docx)], fh)
            fh.write(f"[docx] rc={rc} -> {docx}\n")
        else:
            fh.write("[docx] uebersprungen — kein einziger Artikel entstanden.\n")

        fh.write(f"\nFERTIG {datetime.datetime.now():%H:%M:%S}  "
                 f"{fertig}/{erwartet} Artikel\n  Artikel: {outdir}\n  Docx: {desk}\n")

    print(f"{fertig}/{erwartet} Artikel — Log: {log}")
    return 0 if fertig else 1


if __name__ == "__main__":
    raise SystemExit(main())
