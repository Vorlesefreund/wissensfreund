#!/usr/bin/env python3
"""build_vision_visual.py — HTML-Bildvergleich Sonnet↔flash-lite.
Trennt ehrlich: ECHTE flash-lite-Ablehnung (möglicher Verlust) vs. nur anderes
Foto desselben Motivs (Motiv-Dedup, kein Verlust). Bilder via Special:FilePath (360px).

  python -X utf8 scripts/build_vision_visual.py \
      --json articles/vision_compare_20260710.json \
      --out "C:/Users/Andreas/Desktop/_vision_compare_bilder_20260710.html"
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from urllib.parse import quote


def _src(filename: str) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=360"


def _card(fn, va, vb, reason=""):
    def tag(v):
        if "error" in v:
            return "<span class=err>ERR (kein Urteil)</span>"
        return (f"S{v.get('ab_stufe','-')} · r{v.get('relevanz','-')}"
                + (" · HERO" if v.get('hero') else "")
                + (" · <b>im Pool</b>" if v.get('im_pool') else " · raus")
                + (" · <span class=block>GESPERRT</span>" if v.get('ab_stufe') == 0 else ""))
    rline = f'<div class=reason>{reason}</div>' if reason else ""
    return (f'<div class=card><img loading=lazy src="{_src(fn)}" alt="">'
            f'<div class=fn>{fn[:60]}</div>{rline}'
            f'<div class=v><span class=ml>Sonnet:</span> {tag(va)}</div>'
            f'<div class=v><span class=ml>flash-lite:</span> {tag(vb)}</div></div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r = json.loads(Path(args.json).read_text(encoding="utf-8"))
    a, b = r["models"]  # sonnet, flash-lite

    html = ["<meta charset=utf-8><title>Bildvergleich Sonnet vs flash-lite</title><style>",
            "body{font-family:sans-serif;margin:20px;background:#fafafa}",
            "h1{font-size:20px} h2{margin-top:34px;border-bottom:2px solid #ccc}",
            "h3{margin:22px 0 6px}",
            ".grid{display:flex;flex-wrap:wrap;gap:14px}",
            ".card{width:250px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px;font-size:12px}",
            ".card img{width:100%;height:170px;object-fit:contain;background:#eee;border-radius:4px}",
            ".fn{font-weight:bold;margin:6px 0 2px;word-break:break-all;font-size:11px}",
            ".reason{color:#b30000;font-size:11px;margin-bottom:4px}",
            ".v{margin:2px 0} .ml{display:inline-block;width:64px;color:#555}",
            ".err{color:#a00} .block{color:#fff;background:#c00;padding:0 4px;border-radius:3px}",
            ".note{color:#555;font-size:13px;margin:6px 0 14px}",
            ".legend{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px 14px;font-size:13px;margin:10px 0 20px}</style>",
            "<h1>Bildvergleich: verlieren wir mit flash-lite gute Bilder?</h1>",
            "<div class=legend><b>im Pool</b> = Relevanz ≥ 4 UND altersfreigegeben · "
            "<b>gesperrt</b> = Sicherheits-Sperre (für keine Altersstufe geeignet) · "
            "<b>raus</b> = altersokay, aber Relevanz &lt; 4 · <b>ERR</b> = kein Urteil.<br>"
            "Zwei Achsen: Sicherheit UND Relevanz — ein Bild kann relevant und trotzdem gesperrt sein.</div>"]

    for thema, th in r["themen"].items():
        rows = {x["filename"]: x for x in th["rows"]}
        pa = {p["filename"] for p in th["pools"][a]}
        pb = {p["filename"] for p in th["pools"][b]}
        reject, dedup = [], []
        for fn in pa - pb:
            vb = rows[fn]["verdicts"].get(b, {})
            if "error" in vb:
                reject.append((fn, "flash-lite: Fehler, kein Urteil (Transient)"))
            elif vb.get("ab_stufe") == 0:
                reject.append((fn, "flash-lite: als GESPERRT eingestuft (Sicherheit)"))
            elif not vb.get("im_pool") and vb.get("relevanz", 0) < 4:
                reject.append((fn, f"flash-lite: Relevanz nur {vb.get('relevanz')} (< 4)"))
            else:
                dedup.append(fn)  # flash-lite akzeptiert auch → Motiv-Dedup, kein Verlust

        html.append(f"<h2>{thema}</h2>")
        html.append(f"<h3>❗ Echte flash-lite-Ablehnung — hier evtl. Verlust ({len(reject)})</h3>")
        if reject:
            html.append("<div class=grid>")
            for fn, why in reject:
                row = rows.get(fn, {})
                html.append(_card(fn, row.get("verdicts", {}).get(a, {}),
                                  row.get("verdicts", {}).get(b, {}), why))
            html.append("</div>")
        else:
            html.append("<p class=note>— keine —</p>")
        html.append(f"<h3>≈ Nur anderes Foto desselben Motivs — flash-lite akzeptiert auch, KEIN Verlust ({len(dedup)})</h3>")
        html.append("<div class=grid>")
        for fn in dedup:
            row = rows.get(fn, {})
            html.append(_card(fn, row.get("verdicts", {}).get(a, {}), row.get("verdicts", {}).get(b, {})))
        html.append("</div>")

    Path(args.out).write_text("\n".join(html), encoding="utf-8")
    print(f"OK -> {args.out}")


if __name__ == "__main__":
    main()
