#!/usr/bin/env python3
"""
build_image_zips.py — Hash-basierte Bild-ZIPs aus article_image_map.json

INPUT:  article_image_map.json (Vollrun von scrape_klexikon_images.py)
OUTPUT: images_thumb.zip    (300px, Schlüssel = {hash})
        images_standard.zip (800px, Schlüssel = {hash})
        build_summary.json
        skipped.log

Jedes Bild wird von Wikimedia Commons als Thumbnail heruntergeladen
(Special:FilePath?width=N) und direkt in das ZIP geschrieben.

Env:
  IMAGE_MAP       Pfad zu article_image_map.json  (default: article_image_map.json)
  DELAY           Pause zwischen Downloads in Sek  (default: 0.15)
  MAX_IMAGES      Testlimit, 0 = alle             (default: 0)
  MIN_SUCCESS_PCT Mindest-Erfolgsquote in %        (default: 85)
  SHARD_INDEX     Shard-Index 0-basiert            (default: 0)
  SHARD_COUNT     Gesamtzahl Shards                (default: 1)
  SKIP_UPLOAD     1 = kein R2-Upload               (default: 0)
"""

import json
import os
import sys
import time
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

IMAGE_MAP       = Path(os.environ.get("IMAGE_MAP",       "article_image_map.json"))
DELAY           = float(os.environ.get("DELAY",          "0.15"))
MAX_IMAGES      = int(os.environ.get("MAX_IMAGES",        "0"))
MIN_SUCCESS_PCT = int(os.environ.get("MIN_SUCCESS_PCT",   "85"))
SHARD_INDEX     = int(os.environ.get("SHARD_INDEX",       "0"))
SHARD_COUNT     = int(os.environ.get("SHARD_COUNT",       "1"))

TIERS = [
    ("thumb",    300, "images_thumb.zip"),
    ("standard", 800, "images_standard.zip"),
]

# Dateitypen die keine sinnvollen Bild-Thumbnails liefern
SKIP_EXTS = {".webm", ".ogv", ".mp4", ".ogg", ".oga", ".wav", ".mp3", ".opus", ".pdf"}

COMMONS_BASE = "https://commons.wikimedia.org/wiki/Special:FilePath/{fn}?width={w}"
HEADERS = {"User-Agent": "Wissensfreund-App/1.0 (educational children's app; az@expansionssupport.de)"}

LOG_INTERVAL = 500  # Zwischenstand alle N Bilder


def load_unique_pairs(path: Path) -> list[tuple[str, str]]:
    """Liest article_image_map.json und gibt eindeutige (hash, filename) Paare zurück."""
    data = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for art in data:
        for img in art.get("data", []):
            h  = img.get("hash")
            fn = img.get("filename", "")
            if not h or not fn:
                continue
            if h in seen:
                continue
            seen.add(h)
            pairs.append((h, fn))
    return pairs


def download(filename: str, width: int) -> bytes | None:
    """Lädt Thumbnail von Wikimedia Commons. Gibt None bei Fehler zurück."""
    url = COMMONS_BASE.format(fn=quote(filename.replace(" ", "_"), safe=""), w=width)
    req = Request(url, headers=HEADERS)
    for attempt in range(2):
        try:
            with urlopen(req, timeout=30) as r:
                data = r.read()
                if len(data) < 500:        # leere oder kaputte Antwort
                    return None
                return data
        except HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"  429 — warte {wait}s …", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  HTTP {e.code}: {filename}", file=sys.stderr)
            return None
        except URLError as e:
            print(f"  URLError: {filename}: {e}", file=sys.stderr)
            return None
    return None


def estimate_runtime(n: int) -> str:
    sec = n * 2 * (DELAY + 0.35)   # 2 Größen, geschätzt 0.35s Netzwerkzeit
    if sec < 60:
        return f"{sec:.0f}s"
    if sec < 3600:
        return f"{sec/60:.0f} min"
    return f"{sec/3600:.1f}h"


def main() -> None:
    if not IMAGE_MAP.exists():
        print(f"ERROR: IMAGE_MAP={IMAGE_MAP} nicht gefunden", file=sys.stderr)
        sys.exit(1)

    print(f"Lade {IMAGE_MAP} …")
    all_pairs = load_unique_pairs(IMAGE_MAP)
    print(f"  Eindeutige (hash, filename) Paare: {len(all_pairs)}")

    # Shard-Filter (interleaved wie bestehende Pipeline)
    pairs = [p for i, p in enumerate(all_pairs) if i % SHARD_COUNT == SHARD_INDEX]
    if SHARD_COUNT > 1:
        print(f"  Shard {SHARD_INDEX}/{SHARD_COUNT}: {len(pairs)} Paare")

    # Nicht-Bild-Formate herausfiltern
    skipped_fmt: list[str] = []
    filtered = []
    for h, fn in pairs:
        ext = Path(fn).suffix.lower()
        if ext in SKIP_EXTS:
            skipped_fmt.append(fn)
        else:
            filtered.append((h, fn))
    if skipped_fmt:
        print(f"  Übersprungen (kein Bildformat): {len(skipped_fmt)}")
    pairs = filtered

    if MAX_IMAGES and len(pairs) > MAX_IMAGES:
        print(f"  MAX_IMAGES={MAX_IMAGES}: kürze auf {MAX_IMAGES}")
        pairs = pairs[:MAX_IMAGES]

    n = len(pairs)
    print(f"\n{'='*65}")
    print(f"Zu downloaden: {n} Bilder × 2 Auflösungen = {n*2} Requests")
    print(f"Geschätzte Laufzeit: {estimate_runtime(n)}  (DELAY={DELAY}s)")
    print(f"Plausibilitätsschwelle: ≥{MIN_SUCCESS_PCT}%")
    print(f"{'='*65}\n")

    counts    = {name: 0  for name, _, _ in TIERS}
    failures  = {name: [] for name, _, _ in TIERS}
    skipped_dl: list[str] = []

    zips = {
        name: zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED)
        for name, _, zip_path in TIERS
    }

    t_start = time.monotonic()
    for i, (h, fn) in enumerate(pairs, 1):
        for tier_name, width, _ in TIERS:
            data = download(fn, width)
            time.sleep(DELAY)
            if data is None:
                failures[tier_name].append(fn)
                if tier_name == TIERS[0][0]:   # nur einmal pro Bild loggen
                    skipped_dl.append(fn)
            else:
                zips[tier_name].writestr(h, data)
                counts[tier_name] += 1

        if i % LOG_INTERVAL == 0 or i == n:
            elapsed = time.monotonic() - t_start
            rate    = i / elapsed if elapsed > 0 else 0
            eta     = (n - i) / rate if rate > 0 else 0
            print(f"  [{i:>5}/{n}] "
                  f"thumb={counts['thumb']}  std={counts['standard']}  "
                  f"fail={len(failures['thumb'])}  "
                  f"elapsed={elapsed:.0f}s  ETA={eta:.0f}s")

    for z in zips.values():
        z.close()

    # ── Plausibilitätsprüfung ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("ERGEBNIS")
    print(f"{'='*65}")
    for name, width, zip_path in TIERS:
        pct = counts[name] * 100 // max(n, 1)
        size_mb = Path(zip_path).stat().st_size // 1_048_576 if Path(zip_path).exists() else 0
        print(f"  {name:10s}: {counts[name]:>5}/{n}  ({pct}%)  {size_mb} MB  → {zip_path}")

    thumb_pct = counts["thumb"] * 100 // max(n, 1)
    plausible = thumb_pct >= MIN_SUCCESS_PCT

    # ── skipped.log ───────────────────────────────────────────────────────────
    skipped_all = skipped_fmt + skipped_dl
    with open("skipped.log", "w", encoding="utf-8") as f:
        f.write(f"# Übersprungene Bilder — Shard {SHARD_INDEX}/{SHARD_COUNT}\n")
        f.write(f"# Format-Filter: {len(skipped_fmt)}\n")
        f.write(f"# Download-Fehler: {len(skipped_dl)}\n\n")
        for fn in skipped_fmt:
            f.write(f"FORMAT\t{fn}\n")
        for fn in skipped_dl:
            f.write(f"FAIL\t{fn}\n")
    print(f"  skipped.log: {len(skipped_all)} Einträge")

    # ── build_summary.json ────────────────────────────────────────────────────
    summary = {
        "shard":              SHARD_INDEX,
        "shard_count":        SHARD_COUNT,
        "total_pairs":        n,
        "downloaded_thumb":   counts["thumb"],
        "downloaded_standard": counts["standard"],
        "skipped_format":     len(skipped_fmt),
        "skipped_download":   len(skipped_dl),
        "success_pct_thumb":  thumb_pct,
        "plausibility":       "OK" if plausible else "FAIL",
        "generated":          date.today().isoformat(),
    }
    Path("build_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  build_summary.json geschrieben")

    if not plausible:
        print(f"\n⚠️  PLAUSIBILITÄT FEHLGESCHLAGEN: {thumb_pct}% < {MIN_SUCCESS_PCT}%")
        print(f"   → ZIPs NICHT nach R2 hochladen!")
        sys.exit(1)

    print(f"\n✓ Plausibilität OK ({thumb_pct}% ≥ {MIN_SUCCESS_PCT}%)")


if __name__ == "__main__":
    main()
