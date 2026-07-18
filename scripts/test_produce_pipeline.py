#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_produce_pipeline.py — Guard-Tests für die reproduzierbare Produktions-Pipeline.

Deterministisch, KEIN Netz, KEIN Pod, KEIN Gemini. Prüft die beiden Repo-Teile,
die früher als Wegwerf-Scratchpad-Schritte liefen und den Lauf unreproduzierbar
machten:

  1. tts_flatten_cache.flatten  — eskalierte Cache-PCMs korrekt auf den Basis-Key
     (Temp 0.3) kopieren; bit-genau; idempotent; fehlende Quelle ehrlich melden.
  2. produce_story.assemble_payload — vollständige Pod-Payload aus dem Repo bauen
     und einen NICHT pod-fertigen Cache verweigern (statt still halbes Audio zu
     schicken).

Lauf:  python -X utf8 scripts/test_produce_pipeline.py
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tts_flatten_cache as FL
import tts_story as T
import produce_story as PS

FAILS: list[str] = []


def check(bed: bool, msg: str) -> None:
    print(("  ok  " if bed else " FAIL ") + msg)
    if not bed:
        FAILS.append(msg)


# ── Fixtures ─────────────────────────────────────────────────────────────────────
def _pcm(marker: int, n: int = 4800) -> bytes:
    """Deterministisches Pseudo-PCM (s16le mono), pro Marker eindeutig."""
    return bytes(((marker * 7 + i) % 256 for i in range(n * 2)))


def _seg() -> dict:
    return {
        "cast": {"kind": {"name": "Theo", "geschlecht": "m"},
                 "erwachsener": {"name": "Oma Rina", "geschlecht": "w"}},
        "turns": [
            {"rolle": "erzähler", "text": "Oma Rina blättert im Buch.", "szene": True, "emotion": ""},
            {"rolle": "kind", "text": "Wer ist das?", "szene": False, "emotion": ""},
            {"rolle": "erwachsener", "text": "Das ist die Mona Lisa.", "szene": False, "emotion": ""},
            {"rolle": "erzähler", "text": "Oma Rina lacht.", "szene": False, "emotion": "fröhlich"},
        ],
    }


def _build_cache(cache: Path, seg: dict, temps: list[float]) -> dict:
    """Legt pro Turn EIN gewonnenes PCM unter dem Key seiner Gewinn-Temperatur ab.

    Gibt das Manifest zurück (turns mit i + temp), wie es der lokale Synthese-Lauf
    schreibt. temps[i] = die Temperatur, unter der Turn i gewonnen hat.
    """
    cache.mkdir(parents=True, exist_ok=True)
    cast = seg["cast"]
    manifest_turns = []
    for i, turn in enumerate(seg["turns"]):
        temp = temps[i]
        key = FL._key_for(turn, cast, temp)
        (cache / f"{key}.pcm").write_bytes(_pcm(i))
        manifest_turns.append({"i": i, "rolle": turn["rolle"], "temp": temp})
    return {"turns": manifest_turns}


# ── Tests ────────────────────────────────────────────────────────────────────────
def test_flatten_basic(tmp: Path) -> None:
    print("\n[1] flatten: eskalierte Turns → Basis-Key, bit-genau")
    seg = _seg()
    cache = tmp / "c1"
    # Turn 0,1 gewinnen bei Basis 0.3; Turn 2 eskaliert auf 0.5; Turn 3 auf 0.6
    manifest = _build_cache(cache, seg, [0.3, 0.3, 0.5, 0.6])
    check(len(FL.coverage(seg, cache)) == 2, "vorher: 2 Basis-Key-Miss (Turn 2,3 eskaliert)")

    st = FL.flatten(seg, manifest, cache)
    check(st["n_kopiert"] == 2, f"2 kopiert (ist {st['n_kopiert']})")
    check(st["n_schon_da"] == 2, f"2 bereits Basis-Key (ist {st['n_schon_da']})")
    check(st["n_fehlend"] == 0, "0 Quell-PCM fehlend")
    check(FL.coverage(seg, cache) == [], "nachher: 0 Basis-Key-Miss (pod-ready)")

    # Bit-Gleichheit: Basis-Key-PCM von Turn 2 == das ursprünglich unter 0.5 abgelegte
    cast = seg["cast"]
    bk = FL._key_for(seg["turns"][2], cast, 0.3)
    ek = FL._key_for(seg["turns"][2], cast, 0.5)
    check((cache / f"{bk}.pcm").read_bytes() == (cache / f"{ek}.pcm").read_bytes(),
          "Turn 2: Basis-Key-Bytes == Eskalations-Key-Bytes")
    check((cache / f"{bk}.pcm").read_bytes() == _pcm(2), "Turn 2: exakt das Gewinn-PCM")


def test_flatten_idempotent(tmp: Path) -> None:
    print("\n[2] flatten: idempotent (zweiter Lauf kopiert nichts mehr)")
    seg = _seg()
    cache = tmp / "c2"
    manifest = _build_cache(cache, seg, [0.3, 0.5, 0.5, 0.6])
    FL.flatten(seg, manifest, cache)
    st2 = FL.flatten(seg, manifest, cache)
    check(st2["n_kopiert"] == 0, f"zweiter Lauf: 0 kopiert (ist {st2['n_kopiert']})")
    check(st2["n_fehlend"] == 0, "zweiter Lauf: 0 fehlend")
    check(FL.coverage(seg, cache) == [], "weiterhin 0 Basis-Key-Miss")


def test_flatten_missing_source(tmp: Path) -> None:
    print("\n[3] flatten: fehlende Quelle wird ehrlich gemeldet (kein stiller Verlust)")
    seg = _seg()
    cache = tmp / "c3"
    manifest = _build_cache(cache, seg, [0.3, 0.3, 0.5, 0.6])
    # Quell-PCM von Turn 2 (0.5) löschen → Basis-Key nicht herstellbar
    cast = seg["cast"]
    (cache / f"{FL._key_for(seg['turns'][2], cast, 0.5)}.pcm").unlink()
    st = FL.flatten(seg, manifest, cache)
    check(st["n_fehlend"] == 1 and st["fehlend"][0]["i"] == 2, "Turn 2 als fehlend gemeldet")
    check(2 in FL.coverage(seg, cache), "Turn 2 bleibt Basis-Key-Miss")


def test_assemble_payload(tmp: Path) -> None:
    print("\n[4] assemble_payload: vollständige Payload aus dem Repo")
    seg = _seg()
    run_dir = tmp / "run4"
    (run_dir).mkdir(parents=True)
    (run_dir / "seg.json").write_text(json.dumps(seg, ensure_ascii=False), encoding="utf-8")
    cache = run_dir / "pcm_cache"
    manifest = _build_cache(cache, seg, [0.3, 0.5, 0.5, 0.6])
    FL.flatten(seg, manifest, cache)

    ref_dir = tmp / "nref"
    ref_dir.mkdir()
    (ref_dir / "rich_ref.wav").write_bytes(b"RIFF0000WAVEfake")

    payload = tmp / "payload" / "run"
    PS.assemble_payload(run_dir, payload, ref_dir, base_temp=T.TTS_TEMPERATURE)

    erwartet = ["seg.json", "nico_ref/rich_ref.wav", "tts_story.py", "tts_batch.py",
                "tts_qa.py", "nico_vc.py", "bootstrap_openvoice.sh", "do_vc.sh"]
    for rel in erwartet:
        check((payload / rel).exists(), f"Payload enthält {rel}")
    n_pcm = len(list((payload / "pcm_cache").glob("*.pcm")))
    check(n_pcm >= len(seg["turns"]), f"Payload-Cache ≥ {len(seg['turns'])} PCM (ist {n_pcm})")
    # Payload-Code == Repo-Code (Single Source of Truth)
    check((payload / "tts_story.py").read_bytes() == (REPO / "tts_story.py").read_bytes(),
          "tts_story.py im Payload == Repo-Version")
    check((payload / "do_vc.sh").read_bytes() == (REPO / "pod" / "do_vc.sh").read_bytes(),
          "do_vc.sh im Payload == pod/-Version")


def test_assemble_refuses_incomplete(tmp: Path) -> None:
    print("\n[5] assemble_payload: verweigert NICHT pod-fertigen Cache")
    seg = _seg()
    run_dir = tmp / "run5"
    run_dir.mkdir(parents=True)
    (run_dir / "seg.json").write_text(json.dumps(seg, ensure_ascii=False), encoding="utf-8")
    cache = run_dir / "pcm_cache"
    # eskalierten Cache OHNE flatten → Turn 1..3 haben keinen Basis-Key
    _build_cache(cache, seg, [0.3, 0.5, 0.5, 0.6])
    ref_dir = tmp / "nref5"; ref_dir.mkdir()
    (ref_dir / "rich_ref.wav").write_bytes(b"RIFFfake")
    try:
        PS.assemble_payload(run_dir, tmp / "p5" / "run", ref_dir, base_temp=T.TTS_TEMPERATURE)
        check(False, "hätte RuntimeError werfen müssen")
    except RuntimeError as e:
        check("nicht pod-ready" in str(e).lower() or "miss" in str(e).lower(),
              "RuntimeError wegen unvollständigem Cache")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    tmp = Path(tempfile.mkdtemp(prefix="prodpipe_"))
    try:
        test_flatten_basic(tmp)
        test_flatten_idempotent(tmp)
        test_flatten_missing_source(tmp)
        test_assemble_payload(tmp)
        test_assemble_refuses_incomplete(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("ALLE TESTS PASS" if not FAILS else f"{len(FAILS)} FEHLGESCHLAGEN:"))
    for f in FAILS:
        print("  - " + f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
