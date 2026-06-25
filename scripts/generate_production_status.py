#!/usr/bin/env python3
"""generate_production_status.py — Produktions-Übersicht über alle Läufe.

Scannt articles/<run_dir>/articles/ + articles/<run_dir>/lektorat/ und baut eine
Übersicht, in welchem Stadium jedes Thema+Stufe steckt.

Stadium (eskalierend): produziert < lektoriert < reviewed < vertont < auf_app
  - produziert : Artikel-JSON existiert
  - lektoriert : Lektorat-JSON existiert
  - reviewed   : alle findings haben review_decision (nicht OFFEN/leer)
  - vertont    : WAV in <run_dir>/audio/ oder ./audio/ existiert
  - auf_app    : noch nicht implementiert (immer False)

Aufruf:  python scripts/generate_production_status.py
Output:  production_status.json (Repo-Root), JSON-Array sortiert nach thema, stufe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "articles"

_NA = (None, "", "OFFEN", "offen")


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _stufe_from_id(aid: str) -> str:
    if "_l" in aid:
        return "l" + aid.rpartition("_l")[2]
    return "?"


def _thema_from(meta: dict, aid: str) -> str:
    if meta.get("title"):
        return meta["title"]
    return aid.rpartition("_l")[0] or aid


def _find_wav(run_dir: Path, aid: str) -> str | None:
    for base in (run_dir / "audio", ROOT / "audio"):
        if base.is_dir():
            hits = sorted(base.glob(f"{aid}*.wav"))
            if hits:
                return str(hits[0].relative_to(ROOT)).replace("\\", "/")
    return None


def _review_complete(lekt: dict) -> bool:
    findings = (lekt.get("pruefbericht", {}) or {}).get("findings", []) or []
    return all(f.get("review_decision") not in _NA for f in findings)


def build() -> list[dict]:
    entries: list[dict] = []
    if not ARTICLES.is_dir():
        return entries

    for run_dir in sorted(p for p in ARTICLES.iterdir() if p.is_dir()):
        art_dir = run_dir / "articles"
        lekt_dir = run_dir / "lektorat"
        # alle artikel_ids aus beiden Quellen
        ids: set[str] = set()
        if art_dir.is_dir():
            ids |= {p.stem for p in art_dir.glob("*.json")}
        if lekt_dir.is_dir():
            ids |= {p.name[len("lektorat_"):-len(".json")] for p in lekt_dir.glob("lektorat_*.json")}
        if not ids:
            continue

        for aid in sorted(ids):
            art_path  = art_dir / f"{aid}.json"
            lekt_path = lekt_dir / f"lektorat_{aid}.json"
            art  = _load(art_path) if art_path.exists() else None
            lekt = _load(lekt_path) if lekt_path.exists() else None
            src  = lekt or art or {}
            meta = src.get("meta", {})

            review_complete = bool(lekt) and _review_complete(lekt)
            wav = _find_wav(run_dir, aid)

            # Stadium (höchstes erreichtes)
            stadium = "produziert" if art else None
            if lekt:
                stadium = "lektoriert"
            if lekt and review_complete:
                stadium = "reviewed"
            if wav:
                stadium = "vertont"
            if stadium is None:
                stadium = "lektoriert" if lekt else "produziert"

            entries.append({
                "thema":            _thema_from(meta, aid),
                "stufe":            _stufe_from_id(aid),
                "artikel_id":       meta.get("id", aid),
                "run_dir":          run_dir.name,
                "stadium":          stadium,
                "review_complete":  review_complete,
                "word_count":       meta.get("word_count"),
                "review_flag":      meta.get("review_flag", False),
                "tts_wav":          wav,
                "auf_app":          False,
                "generated_at":     meta.get("generated_at"),
            })

    entries.sort(key=lambda e: (e["thema"].lower(), e["stufe"]))
    return entries


def main() -> int:
    entries = build()
    out = ROOT / "production_status.json"
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(entries)
    reviewed = sum(1 for e in entries if e["stadium"] in ("reviewed", "vertont", "auf_app"))
    vertont = sum(1 for e in entries if e["stadium"] in ("vertont", "auf_app"))
    flags = sum(1 for e in entries if e["review_flag"])
    print(f"production_status.json geschrieben: {out}")
    print(f"  {total} Artikel total | {reviewed} reviewed (oder weiter) | {vertont} vertont | {flags} review_flag")
    # Stadium-Verteilung
    from collections import Counter
    dist = Counter(e["stadium"] for e in entries)
    print("  Stadium-Verteilung:", dict(sorted(dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
