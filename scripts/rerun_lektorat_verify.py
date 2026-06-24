#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lektorat-Re-Run auf verify_20260623b — GT_v1-Vergleich.

Erzeugt den Lektorat-Output der ausgewählten verify_20260623b-Artikel mit dem
AKTUELLEN Code-Stand (temp=0 + neue Eingriffsgrenze, Commit 0a39bf8), damit er
gegen articles/verify_20260623b/ground_truth_lektorat.md gemessen werden kann.

KEIN neuer Wikipedia-Fetch: Quelltexte stammen ausschließlich aus dem
Generierungs-Snapshot stage1_checkpoint.json (primary_text + companion_texts).
Das entspricht der Quellen-Grundregel (gegen den Generierungszeit-Snapshot prüfen).

Aufruf:  python scripts/rerun_lektorat_verify.py
Benötigt: ANTHROPIC_API_KEY in der Umgebung.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows-Konsole (cp1252) kann „→"/„Ü" sonst nicht drucken → UTF-8 erzwingen.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# scripts/ importierbar machen
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# .env aus Repo-Wurzel laden (gleicher Mechanismus wie run_batch.py)
try:
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR.parent / ".env")
except ImportError:
    pass

from lektorat_common import (          # noqa: E402
    build_grounded_sources_block,
    build_lektorat_parts,
    run_lektorat_sync,
    annotate_article_lektorat_v2,
)

# ── Lauf-Verzeichnis ──────────────────────────────────────────────────────────
REPO    = SCRIPT_DIR.parent
# Default: verify_20260623b; per CLI überschreibbar:  python rerun… <RUN_DIR>
RUN_DIR = sys.argv[1] if len(sys.argv) > 1 else "articles/verify_20260623b"


def _slug(topic_key: str) -> str:
    """Topic-Key → Datei-Slug (identisch zur run_batch.py-Logik)."""
    return topic_key.lower().replace(" ", "_").replace("/", "_")


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: ANTHROPIC_API_KEY fehlt in der Umgebung.", file=sys.stderr)
        return 2

    base       = (REPO / RUN_DIR).resolve()
    checkpoint = base / "stage1_checkpoint.json"
    art_dir    = base / "articles"
    out_dir    = base / "lektorat_rerun"

    print(f"RUN_DIR: {base}")
    if not checkpoint.exists():
        print(f"FEHLER: Snapshot fehlt: {checkpoint}", file=sys.stderr)
        return 2
    if not art_dir.is_dir():
        print(f"FEHLER: Artikel-Ordner fehlt: {art_dir}", file=sys.stderr)
        return 2

    cp = json.loads(checkpoint.read_text(encoding="utf-8"))
    topics = cp.get("topics", {})

    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Targets generisch aus Checkpoint × vorhandenen Artikel-JSONs ableiten ────
    # Für jedes Topic den Slug bilden und alle <slug>_l<n>.json im Artikel-Ordner
    # einsammeln. So ist das Skript für jeden Lauf-Ordner einsetzbar.
    targets: list[tuple[str, str, Path]] = []   # (aid, topic_key, art_path)
    for topic_key in topics:
        slug = _slug(topic_key)
        for art_path in sorted(art_dir.glob(f"{slug}_l*.json")):
            targets.append((art_path.stem, topic_key, art_path))

    if not targets:
        print("Keine passenden Artikel-JSONs zu Checkpoint-Topics gefunden.",
              file=sys.stderr)
        return 1

    # ── parts_by_id bauen (1 Lektorat-Call je Artikel) ──────────────────────────
    parts_by_id: dict[str, tuple[str, str]] = {}
    meta_by_id:  dict[str, dict] = {}   # aid -> {thema, stufe, art, art_path}

    for aid, topic_key, art_path in targets:
        data = topics.get(topic_key)
        if not data:
            print(f"  [{aid}] Topic '{topic_key}' fehlt im Snapshot — übersprungen")
            continue

        art = json.loads(art_path.read_text(encoding="utf-8"))

        primary_text = data.get("primary_text", "")
        companions   = data.get("valid_companions", [])
        comp_texts   = data.get("companion_texts", {})

        sources_block = build_grounded_sources_block(
            topic_key, primary_text, companions, comp_texts
        )
        sources_prefix, article_task = build_lektorat_parts(art, sources_block)
        parts_by_id[aid] = (sources_prefix, article_task)

        stufe = str(art.get("meta", {}).get("age_level", aid.rsplit("_l", 1)[-1]))
        meta_by_id[aid] = {
            "thema": topic_key, "stufe": stufe, "art": art, "art_path": art_path,
            "out_dir": out_dir,
            "n_companions": len([c for c in companions if comp_texts.get(c)]),
            "primary_chars": len(primary_text),
        }
        print(f"  [{aid}] vorbereitet (primary={len(primary_text)} Z., "
              f"{meta_by_id[aid]['n_companions']} Companions)")

    if not parts_by_id:
        print("Keine Artikel vorbereitet — Abbruch.", file=sys.stderr)
        return 1

    # ── Lektorat ausführen (temp=0 ist in run_lektorat_sync hartkodiert) ─────────
    print(f"\nLektorat-Sync läuft für {len(parts_by_id)} Artikel …\n")
    results, usage_by_id = run_lektorat_sync(parts_by_id, api_key)

    # ── Annotieren + speichern ──────────────────────────────────────────────────
    summary: list[dict] = []
    for aid, m in meta_by_id.items():
        lekt = results.get(aid, {"corrections": [], "pruefen": []})
        art  = m["art"]
        annotate_article_lektorat_v2(art, lekt, thema=m["thema"], stufe=m["stufe"])
        pb = art.get("pruefbericht", {})

        out_path = m["out_dir"] / f"{aid}_lektorat_rerun.json"
        out_path.write_text(
            json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append({
            "aid":          aid,
            "n_silent":     pb.get("n_silent", 0),
            "n_korrigiert": pb.get("n_korrigiert", 0),
            "n_pruefen":    pb.get("n_pruefen", 0),
            "findings":     pb.get("findings", []),
            "out":          out_path,
        })

    # ── Zusammenfassung ─────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("  RE-RUN ZUSAMMENFASSUNG (temp=0 + neue Eingriffsgrenze)")
    print("=" * 78)
    for s in summary:
        print(f"\n### {s['aid']}  →  "
              f"SILENT={s['n_silent']}  KORRIGIERT={s['n_korrigiert']}  "
              f"PRÜFEN={s['n_pruefen']}   ({len(s['findings'])} findings)")
        if not s["findings"]:
            print("    (keine findings)")
        for i, f in enumerate(s["findings"], 1):
            print(f"    [{i}] {json.dumps(f, ensure_ascii=False)}")
        print(f"    → {s['out']}")
    print("\n" + "=" * 78)
    tot = lambda k: sum(s[k] for s in summary)  # noqa: E731
    print(f"  GESAMT: SILENT={tot('n_silent')}  "
          f"KORRIGIERT={tot('n_korrigiert')}  PRÜFEN={tot('n_pruefen')}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
