#!/usr/bin/env python3
"""
Builds images_medium.zip: 800px-wide versions of all licensed Klexikon images.

Steps:
  1. Read media_licenses.json for permitted image filenames
  2. Fetch images_medium_manifest.json from R2 to see what's already cached
  3. Query Wikimedia Commons for 800px thumbnail URLs (batched, rate-limited)
  4. Download only new/missing images
  5. Fetch the existing images_medium.zip from R2, add new images, re-pack
  6. Write updated manifest; workflow uploads both to R2

Output:
  images_medium.zip          — ZIP with entries images/{filename} (max 2 GB)
  images_medium_manifest.json — {filename: {size, downloaded}} tracking dict

Run locally:
  LICENSES_FILE=media_licenses.json python scripts/download_images.py

GitHub Actions: see .github/workflows/update_image_licenses.yml (images job)
Requires: pip install requests
"""

import json
import os
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

LICENSES_FILE  = Path(os.environ.get("LICENSES_FILE", "media_licenses.json"))
MANIFEST_FILE  = Path("images_medium_manifest.json")
OUTPUT_ZIP     = Path("images_medium.zip")
EXISTING_ZIP   = Path("images_medium_existing.zip")
DOWNLOAD_DIR   = Path("image_downloads")
ZIM_VERSION    = os.environ.get("ZIM_VERSION", "unknown")
R2_BASE_URL    = os.environ.get("R2_BASE_URL", "").rstrip("/")
MAX_IMAGES     = int(os.environ.get("MAX_IMAGES", "0"))  # 0 = all

COMMONS_API    = "https://commons.wikimedia.org/w/api.php"
UA             = "WissensfreundApp/1.0 (image-downloader; github.com/Vorlesefreund/wissensfreund)"

BATCH_SIZE     = 50
API_DELAY      = 1.5    # seconds between API batches
DOWNLOAD_DELAY = 0.5    # seconds between file downloads
MAX_ZIP_BYTES  = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_IMG_BYTES  = 3 * 1024 * 1024           # 3 MB per image

IMAGE_EXTS     = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict | None:
    """GET url, return parsed JSON or None on error/404."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [warn] fetch_json({url}): {e}")
        return None


def query_thumbnail_urls(filenames: list[str]) -> dict[str, str]:
    """
    Query Wikimedia Commons for 800px thumbnail URLs.
    Returns {bare_filename: url}.  Files not on Commons are omitted.
    """
    result: dict[str, str] = {}
    batches = [filenames[i:i + BATCH_SIZE] for i in range(0, len(filenames), BATCH_SIZE)]
    for idx, batch in enumerate(batches, 1):
        print(f"  URL batch {idx}/{len(batches)} ({len(batch)} files)...", end=" ", flush=True)
        try:
            r = requests.get(
                COMMONS_API,
                params={
                    "action":     "query",
                    "titles":     "|".join(f"File:{f}" for f in batch),
                    "prop":       "imageinfo",
                    "iiprop":     "url",
                    "iiurlwidth": 800,
                    "format":     "json",
                },
                headers={"User-Agent": UA},
                timeout=30,
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            found = 0
            for page in pages.values():
                title = page.get("title", "").removeprefix("File:")
                infos = page.get("imageinfo") or []
                if infos:
                    url = infos[0].get("thumburl") or infos[0].get("url") or ""
                    if url:
                        result[title] = url
                        found += 1
            print(f"ok ({found} URLs, {len(result)} total)")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(API_DELAY)
    return result


def download_image(url: str, dest: Path) -> int:
    """
    Download url to dest.  Returns byte count on success, 0 on skip,
    or -1 as a signal to abort all further downloads (rate-limited).
    """
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30, stream=True)
        if r.status_code == 429:
            print("429 — warte 60 s...", end=" ", flush=True)
            time.sleep(60)
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30, stream=True)
        if r.status_code == 429:
            print("ABORT (429 anhaeltend — Rate-Limit aktiv)")
            return -1
        r.raise_for_status()

        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > MAX_IMG_BYTES:
                print(f"SKIP (>{MAX_IMG_BYTES // 1_048_576} MB)", end=" ")
                return 0

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bytes(buf))
        return len(buf)
    except Exception as e:
        print(f"ERROR: {e}", end=" ")
        return 0


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not LICENSES_FILE.exists():
        print(f"ERROR: {LICENSES_FILE} not found — run generate_license_json.py first",
              file=sys.stderr)
        sys.exit(1)

    # ── 1. Load permitted image list ──────────────────────────────────────────
    license_data   = json.loads(LICENSES_FILE.read_text(encoding="utf-8"))
    images_section = license_data.get("images", {})
    permitted = [
        fn for fn, info in images_section.items()
        if info.get("allowed") and Path(fn).suffix.lower() in IMAGE_EXTS
    ]
    if MAX_IMAGES > 0:
        permitted = permitted[:MAX_IMAGES]
        print(f"[test mode] Limiting to {MAX_IMAGES} images")
    print(f"Permitted images: {len(permitted)}")

    # ── 2. Load existing manifest from R2 ────────────────────────────────────
    cached: dict[str, dict] = {}
    if R2_BASE_URL:
        manifest_url = f"{R2_BASE_URL}/images_medium_manifest.json"
        print(f"Fetching manifest: {manifest_url}")
        remote = fetch_json(manifest_url)
        if remote:
            cached = remote.get("images", {})
            print(f"  Manifest: {len(cached)} cached images")
        else:
            print("  Manifest not found — first run, rebuilding from scratch")

    # ── 3. Determine new / missing images ────────────────────────────────────
    new_filenames = [fn for fn in permitted if fn not in cached]
    print(f"New images: {len(new_filenames)} of {len(permitted)}")

    # ── 4. Resolve 800px URLs from Wikimedia Commons ──────────────────────────
    new_urls: dict[str, str] = {}
    if new_filenames:
        print(f"Querying Wikimedia Commons for {len(new_filenames)} thumbnail URLs...")
        new_urls = query_thumbnail_urls(new_filenames)
        print(f"Resolved {len(new_urls)} URLs")

    # ── 5. Download new images ────────────────────────────────────────────────
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    downloaded: dict[str, Path] = {}
    rate_abort = False

    for fn, url in new_urls.items():
        if rate_abort:
            break
        dest = DOWNLOAD_DIR / fn
        print(f"  {fn}...", end=" ", flush=True)
        size = download_image(url, dest)
        if size == -1:
            rate_abort = True
            break
        if size > 0:
            downloaded[fn] = dest
            cached[fn] = {"size": size, "downloaded": date.today().isoformat()}
            print(f"ok ({size // 1024} KB)")
        else:
            print("skipped")
        time.sleep(DOWNLOAD_DELAY)

    print(f"\nDownloaded {len(downloaded)} new images")
    if rate_abort:
        print("  Note: downloads aborted early due to rate-limit; rest will be fetched next run")

    # ── 6. Fetch existing ZIP from R2 (only if we have changes to add) ────────
    if R2_BASE_URL and (downloaded or not OUTPUT_ZIP.exists()):
        zip_url = f"{R2_BASE_URL}/images_medium.zip"
        print(f"Fetching existing ZIP from R2...")
        try:
            r = requests.get(zip_url, headers={"User-Agent": UA}, stream=True, timeout=600)
            if r.status_code == 200:
                with open(EXISTING_ZIP, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        f.write(chunk)
                print(f"  Got {EXISTING_ZIP.stat().st_size // 1_048_576} MB")
            elif r.status_code == 404:
                print("  No ZIP on R2 yet (first run)")
            else:
                print(f"  HTTP {r.status_code} — skip")
        except Exception as e:
            print(f"  ERROR: {e} — continuing without old zip")

    if not downloaded and not EXISTING_ZIP.exists():
        print("\nNothing to do — ZIP is up to date.")
        # Still write an updated manifest if we have one
        if cached:
            _write_manifest(cached)
        return

    # ── 7. Rebuild ZIP: existing entries + new images ─────────────────────────
    total_uncompressed = 0
    entry_count = 0
    skipped_count = 0

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_STORED) as zf_out:
        # Copy existing entries (skip any that we just re-downloaded)
        if EXISTING_ZIP.exists():
            with zipfile.ZipFile(EXISTING_ZIP, "r") as zf_in:
                for info in zf_in.infolist():
                    bare = info.filename.removeprefix("images/")
                    if bare in downloaded:
                        continue  # will be added fresh below
                    data = zf_in.read(info.filename)
                    if total_uncompressed + len(data) > MAX_ZIP_BYTES:
                        skipped_count += 1
                        continue
                    zf_out.writestr(f"images/{bare}", data)
                    total_uncompressed += len(data)
                    entry_count += 1

        # Add freshly downloaded images
        for fn, path in downloaded.items():
            data = path.read_bytes()
            if total_uncompressed + len(data) > MAX_ZIP_BYTES:
                skipped_count += 1
                continue
            zf_out.writestr(f"images/{fn}", data)
            total_uncompressed += len(data)
            entry_count += 1

    zip_mb = OUTPUT_ZIP.stat().st_size // 1_048_576
    print(f"\nZIP: {entry_count} images, {zip_mb} MB")
    if skipped_count:
        print(f"  Skipped {skipped_count} images (2 GB limit reached)")

    # ── 8. Write updated manifest ──────────────────────────────────────────────
    _write_manifest(cached)


def _write_manifest(images: dict) -> None:
    manifest = {
        "generated":   date.today().isoformat(),
        "zim_version": ZIM_VERSION,
        "images":      images,
    }
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Manifest: {len(images)} images → {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
