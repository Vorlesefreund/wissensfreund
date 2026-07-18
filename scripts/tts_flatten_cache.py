#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tts_flatten_cache.py — den PCM-Cache auf die Basis-Temperatur „flatten".

WARUM DAS EXISTIERT
-------------------
Der lokale Synthese-Lauf (tts_batch.batch_synthesize) rettet hängende Turns per
Eskalationsleiter: er erhöht die Temperatur (0.3 → 0.5 → 0.6). Die Stufen-
Temperatur geht in den Cache-Hash ein (``TTS_MODEL|voice|style|temperature|text``)
— ein eskalierter Turn liegt also unter seinem ESKALATIONS-Key (z. B. temp 0.5),
NICHT unter dem Basis-Key (temp 0.3).

Der Produktions-VC-Lauf auf dem Pod ruft ``tts_story.vertone()`` mit der Default-
Basis-Temperatur (0.3) auf und sucht deshalb NUR Basis-Keys. Eskalierte Turns
wären Cache-Misses → der (mit Dummy-Key gebaute) Gemini-Client würde aufgerufen
und der Lauf bräche ab.

Dieser Schritt kopiert das gewonnene PCM jedes Turns zusätzlich unter seinen
Basis-Key. Danach trifft ein frischer vertone bei Temp 0.3 zu 100 % den Cache —
0 Gemini-Calls auf dem Pod, voll reproduzierbar.

Früher war das ein Wegwerf-Skript im Session-Scratchpad → der Produktionslauf
nicht reproduzierbar. Jetzt committetes, getestetes Repo-Tooling.

WICHTIG: Wir reimplementieren den Hash NICHT — wir rufen dieselbe
``TtsRequest.build`` wie die Synthese. Damit sind die Keys per Konstruktion
identisch, egal welches Modell/Stil die build-Logik verwendet.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tts_story as T          # _voice_for / _style_for / TTS_TEMPERATURE
from tts_batch import TtsRequest


def _key_for(turn: dict, cast: dict, temperature) -> str:
    """Cache-Key eines Turns bei gegebener Temperatur — via die ECHTE build-Logik."""
    voice = T._voice_for(turn.get("rolle", "erzähler"), cast)
    style = T._style_for(turn.get("rolle", "erzähler"), turn)
    return TtsRequest.build(voice=voice, text=turn.get("text", ""),
                            style=style, temperature=temperature).key


def flatten(seg: dict, manifest: dict, cache_dir: Path,
            base_temp: float = T.TTS_TEMPERATURE) -> dict:
    """Kopiert jedes gewonnene Turn-PCM unter seinen Basis-Key (idempotent).

    seg      : Segmentierung (cast + turns).
    manifest : Render-Manifest aus dem lokalen Synthese-Lauf (turns mit i + temp).
    cache_dir: Ordner mit <key>.pcm.
    base_temp: Ziel-Basis-Temperatur (Default = TTS_TEMPERATURE = 0.3).

    Gibt eine Statistik zurück und wirft NIE stillschweigend etwas weg: fehlt ein
    Quell-PCM, landet der Turn in ``fehlend`` und der Aufrufer MUSS abbrechen.
    """
    cache_dir = Path(cache_dir)
    cast = seg.get("cast", {}) or {}
    turns = seg.get("turns", [])
    kopiert, schon_da, fehlend = [], [], []

    for m in manifest.get("turns", []):
        i = m.get("i")
        if i is None or i >= len(turns):
            continue
        turn = turns[i]
        src_temp = m.get("temp", base_temp)
        dst_key = _key_for(turn, cast, base_temp)
        dst = cache_dir / f"{dst_key}.pcm"
        if dst.exists() and dst.stat().st_size > 0:
            schon_da.append(i)
            continue
        src_key = _key_for(turn, cast, src_temp)
        src = cache_dir / f"{src_key}.pcm"
        if not (src.exists() and src.stat().st_size > 0):
            fehlend.append({"i": i, "src_temp": src_temp,
                            "src_key": src_key, "text": (turn.get("text") or "")[:60]})
            continue
        dst.write_bytes(src.read_bytes())
        kopiert.append({"i": i, "src_temp": src_temp,
                        "src_key": src_key, "dst_key": dst_key})

    _update_index(cache_dir, seg, cast, base_temp)
    return {"kopiert": kopiert, "schon_da": schon_da, "fehlend": fehlend,
            "n_kopiert": len(kopiert), "n_schon_da": len(schon_da),
            "n_fehlend": len(fehlend)}


def _update_index(cache_dir: Path, seg: dict, cast: dict, base_temp: float) -> None:
    """Best-effort: Basis-Keys in _index.json nachtragen (nur Diagnose, nicht load-bearing)."""
    idx_path = cache_dir / "_index.json"
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    except Exception:
        idx = {}
    for i, turn in enumerate(seg.get("turns", [])):
        k = _key_for(turn, cast, base_temp)
        idx.setdefault(k, {"turn": i, "rolle": turn.get("rolle"),
                           "voice": T._voice_for(turn.get("rolle", "erzähler"), cast),
                           "text": turn.get("text", "")})
    try:
        idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def coverage(seg: dict, cache_dir: Path, base_temp: float = T.TTS_TEMPERATURE) -> list[int]:
    """Turn-Indizes, deren Basis-Key NICHT im Cache liegt (0 = pod-ready)."""
    cache_dir = Path(cache_dir)
    cast = seg.get("cast", {}) or {}
    fehlt = []
    for i, turn in enumerate(seg.get("turns", [])):
        p = cache_dir / f"{_key_for(turn, cast, base_temp)}.pcm"
        if not (p.exists() and p.stat().st_size > 0):
            fehlt.append(i)
    return fehlt


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seg-file", required=True, help="Segmentierung (cast + turns)")
    ap.add_argument("--manifest", required=True, help="Render-Manifest des lokalen Synthese-Laufs")
    ap.add_argument("--pcm-cache", required=True, help="Cache-Ordner mit <key>.pcm")
    ap.add_argument("--base-temp", type=float, default=T.TTS_TEMPERATURE,
                    help=f"Basis-Temperatur (Default {T.TTS_TEMPERATURE})")
    a = ap.parse_args()

    seg = _load(a.seg_file)
    manifest = _load(a.manifest)
    cache = Path(a.pcm_cache)
    st = flatten(seg, manifest, cache, base_temp=a.base_temp)
    fehlt = coverage(seg, cache, base_temp=a.base_temp)
    print(f"Flatten: {st['n_kopiert']} kopiert, {st['n_schon_da']} bereits Basis-Key, "
          f"{st['n_fehlend']} Quell-PCM fehlend")
    if st["fehlend"]:
        for f in st["fehlend"]:
            print(f"  QUELLE FEHLT i={f['i']} temp={f['src_temp']} {f['text']!r}")
    print(f"Basis-Key-Abdeckung: {len(fehlt)} Turns ohne Basis-PCM {fehlt if fehlt else '(alle da)'}")
    # Nicht-null Exit, wenn nach dem Flatten noch Turns fehlen → kein Pod-Lauf starten.
    return 1 if fehlt else 0


if __name__ == "__main__":
    raise SystemExit(main())
