#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""produce_story.py — reproduzierbarer End-to-End-Lauf: Prosa/Segmentierung → fertiges m4a.

Zieht die früher von Hand gefahrenen Schritte (lokale Batch-Synthese + QA,
Cache-Flatten, Pod-Voice-Conversion, Abmischen) zu EINEM committeten Befehl
zusammen. Die Qualitätslogik (Segmentierung „mit Tags", QA-Gate, Emotions-
Eskalation, RMS-Pegel) steckt in tts_story.py/tts_batch.py/tts_qa.py; dieses
Skript ist der deterministische Kleber drumherum.

PHASEN
------
  synth  (lokal, CPU):  tts_story.vertone (QA an, OHNE VC) → Gegenlese-WAV +
                        Manifest + PCM-Cache, danach Flatten auf Basis-Temp 0.3.
                        Ergebnis: ein pod-fertiges Run-Verzeichnis.
  vc     (Pod, GPU):    Payload bauen → RunPod erstellen → hochladen → do_vc.sh
                        (OpenVoice-VC über den geflatteten Cache) → herunterladen
                        → Pod TERMINIEREN → WAV nach m4a.
  all    :              synth, dann vc.

TYPISCHER LAUF (frozen, gegengelesene Segmentierung)
    python scripts/produce_story.py all \\
        --seg-file articles/leo_mittags_20260718/leo_mittags_segmentierung.json \\
        --titel Leonardo \\
        --run-dir articles/leo_prod_<datum> \\
        --nico-ref <ordner-mit-rich_ref.wav> \\
        --out "C:/Users/Andreas/Desktop/Leonardo_NicoVC.m4a"

Nur gegenlesen (Phase synth), Pod erst nach Freigabe:
    python scripts/produce_story.py synth --seg-file ... --titel Leonardo --run-dir ...
    # WAV in <run-dir> anhören, dann:
    python scripts/produce_story.py vc --run-dir ... --titel Leonardo --nico-ref ... --out ...

REPRODUZIERBARKEIT
------------------
* Segmentierung wird als run-dir/seg.json EINGEFROREN (aus --seg-file kopiert
  oder aus --story-file einmalig erzeugt) — nie zur Laufzeit neu segmentiert.
* Der PCM-Cache ist inhalts-hash-basiert; gecachte Turns reproduzieren bit-genau.
  Eine frische Synthese liefert ANDERES, aber immer QA-sauberes Audio.
* Der Pod bekommt EXAKT die Repo-Dateien (frisch assembliert), keine Scratchpad-
  Kopien. Payload = seg.json + geflatteter Cache + rich_ref.wav + die vier
  Code-Dateien + pod/*.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tts_flatten_cache as FL
import tts_story as T

# Pod-Zugang (SSH-Key + runpod_ctl.py) liegt bewusst AUSSERHALB des Repos
# (Geheimnis). Default = der eingerichtete Ordner; per --pod-zugang überschreibbar.
DEFAULT_POD_ZUGANG = Path(r"C:\Users\Andreas\Desktop\_nico_clone\pod_zugang")
DEFAULT_GPU_TYPE = "NVIDIA GeForce RTX 3090"
SSH_KEY_NAME = "runpod_nico"
POD_WAIT_TIMEOUT = 420          # s auf SSH-Ports warten
POD_POLL = 15


# ── Phase synth (lokal) ─────────────────────────────────────────────────────────
def _freeze_segmentierung(args, run_dir: Path) -> Path:
    """Legt run_dir/seg.json an (aus --seg-file kopiert oder aus --story-file erzeugt)."""
    seg_out = run_dir / "seg.json"
    if args.seg_file:
        seg = json.loads(Path(args.seg_file).read_text(encoding="utf-8"))
    elif args.story_file:
        story = Path(args.story_file).read_text(encoding="utf-8")
        print("Segmentiere frisch (einmalig, wird eingefroren) …")
        seg = T.segment_story(story, model=args.seg_model)
    else:
        sys.exit("Phase synth braucht --seg-file ODER --story-file.")
    if not seg.get("turns"):
        sys.exit("Segmentierung hat keine turns — Abbruch.")
    seg_out.write_text(json.dumps(seg, ensure_ascii=False, indent=2), encoding="utf-8")
    return seg_out


def phase_synth(args) -> None:
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    seg_file = _freeze_segmentierung(args, run_dir)
    seg = json.loads(seg_file.read_text(encoding="utf-8"))
    cache = run_dir / "pcm_cache"

    # Lokaler Lauf: QA AN, KEINE VC (nico-Args weggelassen) → reiner Gegenlese-Render.
    cmd = [sys.executable, "-X", "utf8", str(REPO / "tts_story.py"),
           "--seg-file", str(seg_file),
           "--pcm-cache", str(cache),
           "--titel", args.titel,
           "--out-dir", str(run_dir)]
    print("Lokale Synthese + QA (ohne VC):\n  " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode != 0:
        sys.exit(f"tts_story.py (Synthese) endete mit Code {r.returncode} — Abbruch.")

    manifest_file = run_dir / f"{args.titel}_manifest.json"
    if not manifest_file.exists():
        sys.exit(f"Manifest {manifest_file} fehlt — Synthese unvollständig.")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    st = FL.flatten(seg, manifest, cache, base_temp=args.base_temp)
    fehlt = FL.coverage(seg, cache, base_temp=args.base_temp)
    print(f"Flatten: {st['n_kopiert']} kopiert, {st['n_schon_da']} bereits Basis-Key, "
          f"{st['n_fehlend']} Quell-PCM fehlend · Basis-Key-Miss danach: {len(fehlt)}")
    if fehlt or st["fehlend"]:
        sys.exit(f"Cache nach Flatten NICHT vollständig (Miss={fehlt}, Quelle fehlt={st['fehlend']}) "
                 "— kein Pod-Lauf. Synthese erneut laufen lassen.")

    wav = run_dir / f"{args.titel}.wav"
    print(f"\nPhase synth OK. Gegenlese-WAV: {wav}")
    print(f"  Cache pod-ready (0 Basis-Key-Miss) in {cache}")


# ── Phase vc (Pod) ───────────────────────────────────────────────────────────────
def assemble_payload(run_dir: Path, payload_run: Path, nico_ref: Path,
                     base_temp: float) -> None:
    """Baut das Pod-Payload-Verzeichnis (== später /workspace/run) frisch aus dem Repo."""
    seg_file = run_dir / "seg.json"
    cache = run_dir / "pcm_cache"
    for pfad, was in [(seg_file, "seg.json"), (cache, "pcm_cache")]:
        if not pfad.exists():
            raise FileNotFoundError(f"{was} fehlt in {run_dir} — erst Phase synth laufen lassen.")
    seg = json.loads(seg_file.read_text(encoding="utf-8"))
    fehlt = FL.coverage(seg, cache, base_temp=base_temp)
    if fehlt:
        raise RuntimeError(f"Cache nicht pod-ready — Basis-Key-Miss bei Turns {fehlt}. "
                           "Phase synth (inkl. Flatten) wiederholen.")
    ref = _rich_ref(nico_ref)

    if payload_run.exists():
        shutil.rmtree(payload_run)
    payload_run.mkdir(parents=True)
    shutil.copy2(seg_file, payload_run / "seg.json")
    shutil.copytree(cache, payload_run / "pcm_cache")
    (payload_run / "nico_ref").mkdir()
    shutil.copy2(ref, payload_run / "nico_ref" / "rich_ref.wav")
    # Code: Single Source of Truth = Repo
    shutil.copy2(REPO / "tts_story.py", payload_run / "tts_story.py")
    shutil.copy2(REPO / "scripts" / "tts_batch.py", payload_run / "tts_batch.py")
    shutil.copy2(REPO / "scripts" / "tts_qa.py", payload_run / "tts_qa.py")
    for f in ("nico_vc.py", "bootstrap_openvoice.sh", "do_vc.sh"):
        shutil.copy2(REPO / "pod" / f, payload_run / f)


def _rich_ref(nico_ref: Path) -> Path:
    nico_ref = Path(nico_ref)
    if nico_ref.is_file():
        return nico_ref
    cand = nico_ref / "rich_ref.wav"
    if cand.exists():
        return cand
    wavs = sorted(nico_ref.glob("*.wav"))
    if not wavs:
        raise FileNotFoundError(f"Keine Referenz-WAV in {nico_ref} (erwartet rich_ref.wav).")
    return wavs[0]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _runpod(pod_zugang: Path, *args: str) -> str:
    r = _run([sys.executable, str(pod_zugang / "runpod_ctl.py"), *args], cwd=str(pod_zugang))
    if r.returncode != 0:
        raise RuntimeError(f"runpod_ctl {' '.join(args)} fehlgeschlagen:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def _parse_kv(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}=(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _ssh_base(pod_zugang: Path) -> list[str]:
    return ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-i", str(pod_zugang / SSH_KEY_NAME)]


def phase_vc(args) -> None:
    run_dir = Path(args.run_dir)
    pod_zugang = Path(args.pod_zugang)
    if not (pod_zugang / "runpod_ctl.py").exists():
        sys.exit(f"runpod_ctl.py nicht in {pod_zugang} — --pod-zugang setzen.")

    payload_run = run_dir / "pod_payload" / "run"
    print("Baue Pod-Payload aus dem Repo …")
    assemble_payload(run_dir, payload_run, Path(args.nico_ref), args.base_temp)
    n_pcm = len(list((payload_run / "pcm_cache").glob("*.pcm")))
    print(f"  Payload: seg.json + {n_pcm} PCM + rich_ref.wav + 4 Code-Dateien + pod/*")

    if args.dry_run:
        print(f"\n--dry-run: Payload liegt in {payload_run}. Kein Pod erstellt.")
        return

    print(f"Erstelle Pod ({args.gpu_type}) …")
    out = _runpod(pod_zugang, "create", args.gpu_type)
    pod_id = _parse_kv(out, "POD_ID")
    if not pod_id:
        sys.exit(f"Keine POD_ID von runpod_ctl:\n{out}")
    print(f"  POD_ID={pod_id}")

    try:
        host, port = _await_ssh(pod_zugang, pod_id)
        _pod_upload_run(pod_zugang, host, port, payload_run)
        _pod_execute(pod_zugang, host, port, args.titel)
        wav = run_dir / f"{args.titel}_NicoVC.wav"
        _pod_download(pod_zugang, host, port, args.titel, wav)
    finally:
        print(f"Terminiere Pod {pod_id} (stoppt Abrechnung) …")
        try:
            print("  " + _runpod(pod_zugang, "stop", pod_id).strip())
        except Exception as e:                       # Terminierung MUSS versucht werden
            print(f"  WARNUNG: stop fehlgeschlagen ({e}) — JETZT von Hand prüfen: "
                  f"python runpod_ctl.py list", file=sys.stderr)
        try:
            print("  Pod-Liste: " + _runpod(pod_zugang, "list").strip())
        except Exception:
            pass

    out_m4a = Path(args.out) if args.out else run_dir / f"{args.titel}_NicoVC.m4a"
    _to_m4a(wav, out_m4a)
    print(f"\nPhase vc OK. Fertiges Audio: {out_m4a}")


def _await_ssh(pod_zugang: Path, pod_id: str) -> tuple[str, str]:
    deadline = None
    waited = 0
    while waited < POD_WAIT_TIMEOUT:
        info = _runpod(pod_zugang, "info", pod_id)
        host = _parse_kv(info, "SSH_HOST")
        port = _parse_kv(info, "SSH_PORT")
        if host and port:
            print(f"  SSH bereit: root@{host}:{port} (nach {waited}s)")
            time.sleep(10)                # kurz setzen lassen, bis sshd wirklich lauscht
            return host, port
        time.sleep(POD_POLL)
        waited += POD_POLL
    raise TimeoutError(f"Pod {pod_id} hat nach {POD_WAIT_TIMEOUT}s keine SSH-Ports — abgebrochen.")


def _pod_upload_run(pod_zugang: Path, host: str, port: str, payload_run: Path) -> None:
    print("Lade Payload hoch (scp) …")
    # payload_run heißt 'run' → landet als /workspace/run
    cmd = ["scp", "-r", "-P", port, *_ssh_base(pod_zugang),
           str(payload_run), f"root@{host}:/workspace/"]
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"scp Upload fehlgeschlagen:\n{r.stdout}\n{r.stderr}")


def _pod_execute(pod_zugang: Path, host: str, port: str, titel: str) -> None:
    print("Starte do_vc.sh auf dem Pod (Bootstrap + VC) … (dauert einige Minuten)")
    remote = f"cd /workspace/run && STORY_TITEL='{titel}' bash do_vc.sh"
    cmd = ["ssh", *_ssh_base(pod_zugang), "-p", port, f"root@{host}", remote]
    r = subprocess.run(cmd)                          # Live-Ausgabe durchreichen
    if r.returncode != 0:
        raise RuntimeError(f"do_vc.sh auf dem Pod endete mit Code {r.returncode}.")


def _pod_download(pod_zugang: Path, host: str, port: str, titel: str, wav: Path) -> None:
    print("Lade Ergebnis herunter (scp) …")
    cmd = ["scp", "-P", port, *_ssh_base(pod_zugang),
           f"root@{host}:/workspace/run/out/{titel}.wav", str(wav)]
    r = _run(cmd)
    if r.returncode != 0 or not wav.exists() or wav.stat().st_size == 0:
        raise RuntimeError(f"scp Download fehlgeschlagen:\n{r.stdout}\n{r.stderr}")
    print(f"  {wav} ({wav.stat().st_size/1e6:.1f} MB)")


def _to_m4a(wav: Path, out_m4a: Path) -> None:
    out_m4a.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "128k", str(out_m4a)]
    r = _run(cmd)
    if r.returncode != 0 or not out_m4a.exists():
        raise RuntimeError(f"ffmpeg wav→m4a fehlgeschlagen:\n{r.stderr[-800:]}")


# ── CLI ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["synth", "vc", "all"], help="Welche Phase(n)")
    ap.add_argument("--run-dir", required=True, help="Arbeits-/Ausgabeverzeichnis des Laufs")
    ap.add_argument("--titel", default="story", help="Dateiname-Basis (WAV/Manifest/m4a)")
    ap.add_argument("--seg-file", help="Fertige, gegengelesene Segmentierung (Phase synth)")
    ap.add_argument("--story-file", help="Roh-Prosa (Phase synth, wird EINMALIG segmentiert)")
    ap.add_argument("--seg-model", default="claude-sonnet-5", help="Segmentierungsmodell (--story-file)")
    ap.add_argument("--nico-ref", help="Ordner mit rich_ref.wav (Phase vc)")
    ap.add_argument("--out", help="Ziel-m4a (Default <run-dir>/<titel>_NicoVC.m4a)")
    ap.add_argument("--base-temp", type=float, default=T.TTS_TEMPERATURE,
                    help=f"Basis-Temperatur für Flatten/Pod (Default {T.TTS_TEMPERATURE})")
    ap.add_argument("--gpu-type", default=DEFAULT_GPU_TYPE, help="RunPod GPU-Typ (Phase vc)")
    ap.add_argument("--pod-zugang", default=str(DEFAULT_POD_ZUGANG),
                    help="Ordner mit runpod_ctl.py + SSH-Key (außerhalb des Repos)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Phase vc: nur Payload bauen, keinen Pod erstellen")
    a = ap.parse_args()

    if a.phase in ("synth", "all"):
        phase_synth(a)
    if a.phase in ("vc", "all"):
        if not a.nico_ref:
            sys.exit("Phase vc braucht --nico-ref (Ordner mit rich_ref.wav).")
        phase_vc(a)


if __name__ == "__main__":
    main()
