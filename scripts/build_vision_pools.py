#!/usr/bin/env python3
"""build_vision_pools.py — zeigt den FINALEN Bildpool je Thema und Modell
(nach Akzeptanz relevanz≥4/ab_stufe≠0 + Motiv-Dedup + Relevanz-Sortierung).
Bilder via Special:FilePath (360px). So sieht man, was real in den Artikel-Pool käme.

  python -X utf8 scripts/build_vision_pools.py \
      --json articles/vision_compare_20260710.json \
      --out "C:/Users/Andreas/Desktop/_vision_pools_20260710.html"
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from urllib.parse import quote


def _src(fn: str) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(fn)}?width=360"


def _card(p):
    hero = p.get("hero")
    badge = '<span class=hero>HERO</span>' if hero else ""
    return (f'<div class="card{" heroc" if hero else ""}">'
            f'<img loading=lazy src="{_src(p["filename"])}" alt="">'
            f'<div class=meta>r{p.get("relevanz","?")} · Q{p.get("bildqualitaet","?")} · S{p.get("ab_stufe","?")} {badge}</div>'
            f'<div class=fn>{p["filename"][:54]}</div>'
            f'<div class=desc>{(p.get("beschreibung") or "")[:80]}</div></div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", nargs="*", default=None, help="Teilmenge der Modelle (default: alle)")
    args = ap.parse_args()

    r = json.loads(Path(args.json).read_text(encoding="utf-8"))
    models = args.models or r["models"]

    html = ["<meta charset=utf-8><title>Finale Bildpools</title><style>",
            "body{font-family:sans-serif;margin:20px;background:#fafafa}",
            "h1{font-size:20px} h2{margin-top:34px;border-bottom:2px solid #ccc}",
            "h3{margin:20px 0 6px}",
            ".grid{display:flex;flex-wrap:wrap;gap:12px}",
            ".card{width:210px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:7px;font-size:11px}",
            ".card.heroc{border:2px solid #d48806;background:#fffbe6}",
            ".card img{width:100%;height:150px;object-fit:contain;background:#eee;border-radius:4px}",
            ".meta{font-weight:bold;margin:5px 0 2px} .hero{color:#fff;background:#d48806;padding:0 5px;border-radius:3px;margin-left:4px}",
            ".fn{word-break:break-all;color:#333} .desc{color:#777;margin-top:3px}",
            ".note{color:#555;font-size:13px;margin:6px 0 14px}</style>",
            "<h1>Finale Bildpools je Thema &amp; Modell</h1>",
            "<p class=note>Was nach Akzeptanz (Relevanz ≥ 4, altersfreigegeben) + Motiv-Dedup + "
            "Relevanz-Sortierung real im Pool landet. Reihenfolge = Relevanz absteigend. "
            "Gelb umrandet = Hero-Kandidat.</p>"]

    for thema, th in r["themen"].items():
        html.append(f"<h2>{thema}</h2>")
        for m in models:
            pool = th["pools"][m]
            html.append(f"<h3>{m} — {len(pool)} Bilder im Pool</h3><div class=grid>")
            for p in pool:
                html.append(_card(p))
            html.append("</div>")

    Path(args.out).write_text("\n".join(html), encoding="utf-8")
    print(f"OK -> {args.out}")
    for thema, th in r["themen"].items():
        sizes = " | ".join(f"{m.split('-')[0]}={len(th['pools'][m])}" for m in models)
        print(f"  {thema}: {sizes}")


if __name__ == "__main__":
    main()
