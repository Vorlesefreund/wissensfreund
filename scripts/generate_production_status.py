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
    """WAV nur unter exaktem Produktions-Namen <aid>_artikel.wav (run_dir oder R2-Pfad)."""
    for base in (run_dir / "audio", ROOT / "audio"):
        cand = base / f"{aid}_artikel.wav"
        if cand.is_file():
            return str(cand.relative_to(ROOT)).replace("\\", "/")
    return None


def _id_in_marker(data, aid: str) -> bool:
    """Flexibel: Liste mit aid · Dict {aid: truthy} · Dict mit 'approved'/'ids'-Liste."""
    if data is None:
        return False
    if isinstance(data, list):
        return aid in data
    if isinstance(data, dict):
        if aid in data:
            return bool(data[aid])
        for key in ("approved", "ids", "articles", "on_app"):
            v = data.get(key)
            if isinstance(v, list) and aid in v:
                return True
            if isinstance(v, dict) and bool(v.get(aid)):
                return True
    return False


def _editorial_approved(run_dir: Path, aid: str, _cache: dict) -> bool:
    key = run_dir / "editorial_approved.json"
    if key not in _cache:
        _cache[key] = _load(key)
    return _id_in_marker(_cache[key], aid)


def _on_app(run_dir: Path, aid: str, _cache: dict) -> bool:
    key = run_dir / "on_app.json"
    if key not in _cache:
        _cache[key] = _load(key)
    return _id_in_marker(_cache[key], aid)


def _review_counts(lekt: dict | None) -> tuple[int, int, bool]:
    """(findings_total, findings_reviewed, is_reviewed) gemäß Stadium-2-Regel.

    findings>0  → reviewed wenn ALLE ein review_decision != OFFEN haben.
    findings==0 → reviewed NUR wenn pruefbericht/meta.reviewed_at gesetzt ODER
                  explizites Flag lektorat_reviewed:true. Leere findings[] allein
                  reichen NICHT.
    """
    if not lekt:
        return 0, 0, False
    pb = lekt.get("pruefbericht", {}) or {}
    findings = pb.get("findings", []) or []
    total = len(findings)
    reviewed = sum(1 for f in findings if f.get("review_decision") not in _NA)
    if total > 0:
        return total, reviewed, reviewed == total
    reviewed_at = pb.get("reviewed_at") or (lekt.get("meta", {}) or {}).get("reviewed_at")
    explicit = bool(lekt.get("lektorat_reviewed") or pb.get("lektorat_reviewed"))
    return 0, 0, bool(reviewed_at) or explicit


def build() -> list[dict]:
    entries: list[dict] = []
    if not ARTICLES.is_dir():
        return entries

    marker_cache: dict = {}
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

            hat_lektorat = bool(lekt)
            both = bool(art) and bool(lekt)
            f_total, f_reviewed, is_reviewed = _review_counts(lekt)
            wav = _find_wav(run_dir, aid)
            ed_approved = _editorial_approved(run_dir, aid, marker_cache)
            on_app = _on_app(run_dir, aid, marker_cache)

            # Stadium (höchstes erreichtes; jedes setzt das vorherige voraus)
            if both:
                stadium = "produziert"
            elif art:
                stadium = "nur_artikel"      # ohne Lektorat: noch nicht Stadium 1
            else:
                stadium = "nur_lektorat"     # Edge: Lektorat ohne Artikel-JSON
            if both and is_reviewed:
                stadium = "lektorat_reviewed"
            if ed_approved:
                stadium = "editorial_review"
            if wav:
                stadium = "vertont"
            if on_app:
                stadium = "auf_app"

            entries.append({
                "thema":            _thema_from(meta, aid),
                "stufe":            _stufe_from_id(aid),
                "artikel_id":       meta.get("id", aid),
                "run_dir":          run_dir.name,
                "stadium":          stadium,
                "review_complete":  is_reviewed,
                "word_count":       meta.get("word_count"),
                "review_flag":      meta.get("review_flag", False),
                "tts_wav":          wav,
                "auf_app":          on_app,
                "generated_at":     meta.get("generated_at"),
                "stadium_details": {
                    "hat_lektorat":       hat_lektorat,
                    "findings_total":     f_total,
                    "findings_reviewed":  f_reviewed,
                    "editorial_approved": ed_approved,
                    "tts_wav":            wav,
                    "auf_app":            on_app,
                },
            })

    entries.sort(key=lambda e: (e["thema"].lower(), e["stufe"]))
    return entries


def main() -> int:
    entries = build()
    out = ROOT / "production_status.json"
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    DURCH = ("lektorat_reviewed", "editorial_review", "vertont", "auf_app")
    total = len(entries)
    reviewed = sum(1 for e in entries if e["stadium"] in DURCH)
    editorial = sum(1 for e in entries if e["stadium"] in ("editorial_review", "vertont", "auf_app"))
    vertont = sum(1 for e in entries if e["stadium"] in ("vertont", "auf_app"))
    flags = sum(1 for e in entries if e["review_flag"])
    print(f"production_status.json geschrieben: {out}")
    print(f"  {total} Artikel total | {reviewed} lektorat_reviewed (oder weiter) | "
          f"{editorial} editorial_review+ | {vertont} vertont | {flags} review_flag")
    # Stadium-Verteilung
    from collections import Counter
    dist = Counter(e["stadium"] for e in entries)
    print("  Stadium-Verteilung:", dict(sorted(dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
