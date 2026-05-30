#!/usr/bin/env python3
"""
build_image_zips.py — Hash-basierte Bild-ZIPs aus article_image_map.json

Optimierungen v3:
  - Direkte Thumbnail-URL (MD5 des Dateinamens) — kein HTTP-Redirect
  - OUTER_WORKERS Bilder werden gleichzeitig heruntergeladen
  - Pro Bild: Thumb (300px) und Standard (800px) parallel (2 Threads)
  - requests.Session mit Connection-Pooling

INPUT:  article_image_map.json
OUTPUT: images_thumb.zip, images_standard.zip, build_summary.json, skipped.log

Env:
  IMAGE_MAP         article_image_map.json       (default: article_image_map.json)
  DELAY             Pause pro Worker nach Download(default: 0.1)
  MAX_IMAGES        Testlimit, 0=alle            (default: 0)
  MIN_SUCCESS_PCT   Mindest-Erfolgsquote %       (default: 85)
  SHARD_INDEX       0-basiert                    (default: 0)
  SHARD_COUNT       Gesamtzahl Shards            (default: 1)
  OUTER_WORKERS     Parallele Bild-Downloads     (default: 10)
"""

import hashlib
import json
import os
import random
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

IMAGE_MAP       = Path(os.environ.get("IMAGE_MAP",        "article_image_map.json"))
DELAY           = float(os.environ.get("DELAY",           "0.1"))
MAX_IMAGES      = int(os.environ.get("MAX_IMAGES",         "0"))
MIN_SUCCESS_PCT = int(os.environ.get("MIN_SUCCESS_PCT",    "85"))
SHARD_INDEX     = int(os.environ.get("SHARD_INDEX",        "0"))
SHARD_COUNT     = int(os.environ.get("SHARD_COUNT",        "1"))
OUTER_WORKERS   = int(os.environ.get("OUTER_WORKERS",      "5"))

UA = "Wissensfreund-App/1.0 (educational children's app; az@expansionssupport.de)"
SKIP_EXTS = {".webm", ".ogv", ".mp4", ".ogg", ".oga", ".wav", ".mp3", ".opus", ".pdf"}
LOG_INTERVAL = 200

# ── HTTP Session mit Connection-Pooling ──────────────────────────────────────

_session = requests.Session()
_session.headers["User-Agent"] = UA
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=40)
_session.mount("https://", _adapter)
_session.mount("http://",  _adapter)


def _direct_url(filename: str, width: int) -> str:
    """Berechnet Wikimedia-Thumbnail-URL direkt aus MD5(Dateiname) — kein HTTP-Redirect."""
    name = filename.replace(" ", "_")
    md5  = hashlib.md5(name.encode("utf-8")).hexdigest()
    fn_e = quote(name, safe="")
    return (f"https://upload.wikimedia.org/wikipedia/commons/thumb"
            f"/{md5[0]}/{md5[:2]}/{fn_e}/{width}px-{fn_e}")


def _fallback_url(filename: str, width: int) -> str:
    name = filename.replace(" ", "_")
    return (f"https://commons.wikimedia.org/wiki/Special:FilePath"
            f"/{quote(name, safe='')}?width={width}")


def _download_one(filename: str, width: int) -> bytes | None:
    """Lädt ein Thumbnail herunter. Direkter URL zuerst, Fallback auf Special:FilePath."""
    for url in (_direct_url(filename, width), _fallback_url(filename, width)):
        for attempt in range(3):
            try:
                r = _session.get(url, timeout=30, allow_redirects=True)
                if r.status_code == 200 and len(r.content) >= 500:
                    return r.content
                if r.status_code == 404:
                    break           # nächste URL versuchen
                if r.status_code == 429:
                    base = 60 * (attempt + 1)
                    # Jitter verhindert synchrone Retry-Stürme bei parallelen Workern
                    wait = base + random.uniform(0, base * 0.5)
                    print(f"  429 — warte {wait:.0f}s …", file=sys.stderr)
                    time.sleep(wait)
                    continue
                break               # anderer Fehler → nächste URL
            except Exception as e:
                print(f"  WARN {filename} w={width}: {e}", file=sys.stderr)
                break
    return None


def _download_pair(args: tuple[str, str]) -> tuple[str, str, bytes | None, bytes | None]:
    """Lädt Thumb (300px) und Standard (800px) gleichzeitig herunter."""
    h, fn = args
    # Zufälliger Start-Offset verhindert den initialen Thundering-Herd-Burst
    time.sleep(random.uniform(0, 2.0))
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_thumb = ex.submit(_download_one, fn, 300)
        f_std   = ex.submit(_download_one, fn, 800)
        thumb = f_thumb.result()
        std   = f_std.result()
    time.sleep(DELAY)
    return h, fn, thumb, std


# ── Artikel-Map laden ─────────────────────────────────────────────────────────

def _load_pairs(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for art in data:
        for img in art.get("data", []):
            h  = img.get("hash")
            fn = img.get("filename", "")
            if h and fn and h not in seen:
                seen.add(h)
                pairs.append((h, fn))
    return pairs


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not IMAGE_MAP.exists():
        print(f"ERROR: {IMAGE_MAP} nicht gefunden", file=sys.stderr); sys.exit(1)

    print(f"Lade {IMAGE_MAP} …")
    all_pairs = _load_pairs(IMAGE_MAP)
    print(f"  Eindeutige Paare gesamt: {len(all_pairs)}")

    # Shard-Filter (interleaved)
    pairs = [p for i, p in enumerate(all_pairs) if i % SHARD_COUNT == SHARD_INDEX]
    if SHARD_COUNT > 1:
        print(f"  Shard {SHARD_INDEX}/{SHARD_COUNT}: {len(pairs)} Paare")

    # Format-Filter
    skipped_fmt = [fn for _, fn in pairs if Path(fn).suffix.lower() in SKIP_EXTS]
    pairs       = [(h, fn) for h, fn in pairs if Path(fn).suffix.lower() not in SKIP_EXTS]
    if skipped_fmt:
        print(f"  Übersprungen (kein Bildformat): {len(skipped_fmt)}")

    if MAX_IMAGES and len(pairs) > MAX_IMAGES:
        print(f"  MAX_IMAGES={MAX_IMAGES}")
        pairs = pairs[:MAX_IMAGES]

    n = len(pairs)
    # Laufzeitschätzung: ~10-20s/Bild (inkl. on-demand-Thumbnail-Generierung) / OUTER_WORKERS
    est_sec = n * 15 / OUTER_WORKERS
    est_min = est_sec / 60
    print(f"\n{'='*65}")
    print(f"Bilder: {n}  |  OUTER_WORKERS={OUTER_WORKERS}  |  DELAY={DELAY}s/Worker")
    print(f"Laufzeit-Schätzung: ~{est_min:.0f} Min (konservativ)")
    print(f"Plausibilitätsschwelle: ≥{MIN_SUCCESS_PCT}%")
    print(f"{'='*65}\n")

    counts   = {"thumb": 0, "standard": 0}
    failures = {"thumb": [], "standard": []}

    t_start = time.monotonic()

    with (zipfile.ZipFile("images_thumb.zip",    "w", zipfile.ZIP_STORED) as z_thumb,
          zipfile.ZipFile("images_standard.zip", "w", zipfile.ZIP_STORED) as z_std):

        with ThreadPoolExecutor(max_workers=OUTER_WORKERS) as pool:
            futures = {pool.submit(_download_pair, p): p for p in pairs}
            done = 0
            for future in as_completed(futures):
                done += 1
                h, fn, thumb, std = future.result()

                if thumb:
                    z_thumb.writestr(h, thumb)
                    counts["thumb"] += 1
                else:
                    failures["thumb"].append(fn)

                if std:
                    z_std.writestr(h, std)
                    counts["standard"] += 1
                else:
                    failures["standard"].append(fn)

                if done % LOG_INTERVAL == 0 or done == n:
                    elapsed = time.monotonic() - t_start
                    eta     = (n - done) * elapsed / done if done else 0
                    print(f"  [{done:>5}/{n}] thumb={counts['thumb']}  std={counts['standard']}"
                          f"  fail={len(failures['thumb'])}  elapsed={elapsed:.0f}s  ETA={eta:.0f}s")

    # ── Ergebnis ─────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    thumb_pct = counts["thumb"] * 100 // max(n, 1)
    for tier, zip_name in [("thumb", "images_thumb.zip"), ("standard", "images_standard.zip")]:
        pct  = counts[tier] * 100 // max(n, 1)
        size = Path(zip_name).stat().st_size // 1_048_576 if Path(zip_name).exists() else 0
        print(f"  {tier:10s}: {counts[tier]:>5}/{n}  ({pct}%)  {size} MB")

    skipped_dl = failures["thumb"]
    with open("skipped.log", "w", encoding="utf-8") as f:
        f.write(f"# Shard {SHARD_INDEX}/{SHARD_COUNT}  format={len(skipped_fmt)}  dl={len(skipped_dl)}\n")
        for fn in skipped_fmt: f.write(f"FORMAT\t{fn}\n")
        for fn in skipped_dl:  f.write(f"FAIL\t{fn}\n")

    summary = {
        "shard": SHARD_INDEX, "shard_count": SHARD_COUNT, "total_pairs": n,
        "downloaded_thumb": counts["thumb"], "downloaded_standard": counts["standard"],
        "skipped_format": len(skipped_fmt), "skipped_download": len(skipped_dl),
        "success_pct_thumb": thumb_pct,
        "plausibility": "OK" if thumb_pct >= MIN_SUCCESS_PCT else "FAIL",
        "generated": date.today().isoformat(),
    }
    Path("build_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  Plausibilität: {summary['plausibility']} ({thumb_pct}%)")
    if thumb_pct < MIN_SUCCESS_PCT:
        print(f"\n⚠️  FEHLGESCHLAGEN: {thumb_pct}% < {MIN_SUCCESS_PCT}% — kein Upload!")
        sys.exit(1)
    print("✓ Plausibilität OK")


if __name__ == "__main__":
    main()
