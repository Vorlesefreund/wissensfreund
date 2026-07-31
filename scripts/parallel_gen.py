#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prozess-Parallel-Launcher fuer die Themen-Generierung.

Warum Prozesse statt Threads: generate_grounded haelt modul-globalen Zustand
(_LAST_KOMPASS_PLAN, _last_trim_usage, gemini_client._last_usage) — unter Threads
wuerden parallele Themen sich diesen Zustand gegenseitig ueberschreiben (Plan-/
Usage-Verwechslung). Getrennte Prozesse haben je eigene Globals → keine Races.

Jeder Worker bekommt ein EIGENES cost-Log (WF_COST_LOG), sonst korrumpiert der
Read-Modify-Write-Append die gemeinsame Datei. Danach werden die Logs gemergt und
EIN Cost-Report ausgegeben.

Beispiel:
  python scripts/parallel_gen.py --themen Biene Mond Ritter Vulkan Regen Pyramide \\
      --workers 3 --output-dir articles/partest_20260729 --run-id partest_20260729
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "generate_grounded.py"


def chunk_roundrobin(themen: list[str], w: int) -> list[list[str]]:
    buckets: list[list[str]] = [[] for _ in range(w)]
    for i, t in enumerate(themen):
        buckets[i % w].append(t)
    return [b for b in buckets if b]


def main() -> int:
    ap = argparse.ArgumentParser(description="Parallel-Launcher (Prozess-Ebene)")
    ap.add_argument("--themen", nargs="+", required=True, metavar="THEMA")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--typen", nargs="+", default=None,
                    help="Inhaltstypen an generate_grounded durchreichen (default: alle)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w = max(1, min(args.workers, len(args.themen)))
    buckets = chunk_roundrobin(args.themen, w)

    print(f"[parallel] {len(args.themen)} Themen auf {len(buckets)} Worker "
          f"(run_id={args.run_id}) → {out_dir}")
    for i, b in enumerate(buckets):
        print(f"  Worker {i}: {', '.join(b)}")

    procs = []
    t0 = time.time()
    for i, bucket in enumerate(buckets):
        env = dict(os.environ)
        env["WF_COST_LOG"] = str(out_dir / f"_cost_w{i}.json")
        env.pop("WF_PROMPT_VARIANT", None)          # BASE erzwingen (guter Stand)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [sys.executable, str(GEN), "--catalog", *bucket,
               "--output-dir", str(out_dir), "--run-id", args.run_id]
        if args.typen:
            cmd += ["--typen", *args.typen]
        wlog = open(out_dir / f"_worker{i}.log", "w", encoding="utf-8")
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=wlog, stderr=subprocess.STDOUT)
        procs.append((i, p, wlog, bucket))
        print(f"  [start] Worker {i} PID {p.pid}")

    # Auf alle warten (laufen echt parallel)
    results = []
    for i, p, wlog, bucket in procs:
        rc = p.wait()
        wlog.close()
        results.append((i, rc, bucket))
        print(f"  [done ] Worker {i} exit={rc}")
    wall = time.time() - t0

    # Ergebnis pruefen: welche Artikel-Dateien liegen vor?
    produced = sorted(f.name for f in out_dir.glob("*.json")
                      if not f.name.startswith("_") and not f.name.endswith("_report.json"))
    # Cost-Logs mergen
    merged: list = []
    for i, _, _ in results:
        cl = out_dir / f"_cost_w{i}.json"
        if cl.exists():
            try:
                merged += json.loads(cl.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [warn] cost-log w{i} nicht lesbar: {e}")
    merged_path = out_dir / "_cost_merged.json"
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    total_usd = sum(e.get("kosten_usd", 0) for e in merged)

    print("\n" + "=" * 60)
    print(f"  PARALLEL FERTIG — Wall-Clock: {wall/60:.1f} min ({wall:.0f}s)")
    print(f"  Worker: {len(buckets)} | Themen: {len(args.themen)} | "
          f"erzeugte Text-Dateien: {len(produced)}")
    print(f"  Kosten gesamt: ${total_usd:.4f}  (Detail: {merged_path.name})")
    fails = [b for i, rc, b in results if rc != 0]
    if fails:
        print(f"  WORKER MIT FEHLER-Exit: {fails}")
    print("=" * 60)
    print("  Cost-Report:  python cost_tracker.py --report   "
          f"(WF_COST_LOG={merged_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
