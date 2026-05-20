#!/usr/bin/env python3
"""
Generates image_licenses.json by:
  1. Opening the Klexikon ZIM file (via python-libzim)
  2. Enumerating all image entries in namespace I
  3. Querying Wikimedia Commons API for license info (batched, rate-limited)
  4. Writing image_licenses.json to the repo root

Run locally:
  ZIM_FILE=path/to/klexikon.zim python scripts/generate_license_json.py

Run in GitHub Actions:
  See .github/workflows/update_image_licenses.yml
"""

import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
    from libzim.reader import Archive
except ImportError:
    print("Missing dependencies. Run: pip install libzim requests")
    sys.exit(1)

ZIM_FILE    = os.environ.get("ZIM_FILE", "klexikon.zim")
ZIM_VERSION = os.environ.get("ZIM_VERSION", "klexikon_de_all_maxi_2025-10")
OUTPUT_FILE = Path("image_licenses.json")

COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
ALLOWED_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BATCH_SIZE    = 50    # Wikimedia API limit per request
REQUEST_DELAY = 0.5   # seconds between API calls (be a good citizen)


def is_permitted(license_str: str) -> bool:
    if not license_str:
        return False
    l = license_str.strip().upper()
    if l == "CC0":
        return True
    if not l.startswith("CC BY"):
        return False
    if "-NC" in l or "-ND" in l:
        return False
    return l.startswith("CC BY ") or l.startswith("CC BY-SA ")


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def query_batch(filenames: list[str]) -> dict:
    titles = "|".join(f"File:{f}" for f in filenames)
    r = requests.get(
        COMMONS_API,
        params={
            "action": "query",
            "titles": titles,
            "prop": "imageinfo",
            "iiprop": "extmetadata",
            "format": "json",
        },
        timeout=30,
        headers={"User-Agent": "WissensfreundApp/1.0 (license-checker)"},
    )
    r.raise_for_status()
    return r.json().get("query", {}).get("pages", {})


def process_page(page: dict) -> dict:
    info_list = page.get("imageinfo") or []
    if not info_list:
        return {"allowed": False, "license": None, "author": None, "license_url": None}
    meta = info_list[0].get("extmetadata") or {}
    lic  = meta.get("LicenseShortName", {}).get("value", "")
    auth = strip_html(meta.get("Artist", {}).get("value", ""))
    url  = meta.get("LicenseUrl", {}).get("value", "")
    return {
        "allowed":     is_permitted(lic),
        "license":     lic  or None,
        "author":      auth or None,
        "license_url": url  or None,
    }


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM file not found: {zim_path}")
        sys.exit(1)

    print(f"Opening {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    archive = Archive(str(zim_path))

    filenames: list[str] = []
    for entry in archive:
        path = entry.path
        if path.startswith("I/") or path.startswith("-/"):
            name = path.split("/", 1)[1]
            if Path(name).suffix.lower() in ALLOWED_EXTS:
                filenames.append(name)

    print(f"Found {len(filenames)} images to check")

    results: dict[str, dict] = {}
    batches = [filenames[i:i + BATCH_SIZE] for i in range(0, len(filenames), BATCH_SIZE)]

    for i, batch in enumerate(batches, 1):
        print(f"  Batch {i}/{len(batches)} ({len(batch)} images)...", end=" ", flush=True)
        try:
            pages = query_batch(batch)
            for page in pages.values():
                fname = page.get("title", "").removeprefix("File:")
                results[fname] = process_page(page)
            print("ok")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(REQUEST_DELAY)

    output = {
        "generated":   date.today().isoformat(),
        "zim_version": ZIM_VERSION,
        "images":      results,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    allowed = sum(1 for v in results.values() if v["allowed"])
    print(f"\nDone: {len(results)} images, {allowed} allowed → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
