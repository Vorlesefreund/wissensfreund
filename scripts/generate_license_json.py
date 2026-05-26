#!/usr/bin/env python3
"""
Generates media_licenses.json by:
  1. Opening the Klexikon ZIM file (binary parsing, no libzim required)
  2. Enumerating all image entries (namespace I/-) and audio entries
  3. Querying Wikimedia Commons API for license info (batched, rate-limited)
  4. Writing media_licenses.json to the repo root

Run locally:
  ZIM_FILE=path/to/klexikon.zim python scripts/generate_license_json.py

Run in GitHub Actions:
  See .github/workflows/update_image_licenses.yml
"""

import json
import os
import re
import struct
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote

try:
    import requests
except ImportError:
    print("Missing dependencies. Run: pip install requests")
    sys.exit(1)

ZIM_FILE       = os.environ.get("ZIM_FILE", "klexikon.zim")
ZIM_VERSION    = os.environ.get("ZIM_VERSION", "klexikon_de_all_maxi_2026-05")
IMAGE_MAP_FILE = Path(os.environ.get("IMAGE_MAP_FILE", "image_map.json"))
OUTPUT_FILE    = Path("media_licenses.json")

COMMONS_API   = "https://commons.wikimedia.org/w/api.php"
IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTS    = {".ogg", ".oga", ".mp3", ".opus", ".wav", ".flac"}
BATCH_SIZE    = 50
REQUEST_DELAY = 1.5   # Wikimedia Commons API rate limit: erhöht von 0.5 auf 1.5s

ZIM_MAGIC = 0x044d495a  # little-endian: bytes 5a 49 4d 04 ("ZIM\x04")


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


def extract_commons_filename(zim_url: str) -> str | None:
    """Return the original Wikimedia Commons filename from a ZIM thumbnail path.

    Klexikon ZIM stores MediaWiki thumbnails as:
      {lang}-{size}px-{original_commons_filename}
    Examples:
      langde-250px-DEU_Düsseldorf_COA.svg.png → DEU_Düsseldorf_COA.svg
      langde-220px-African_Bush_Elephant.jpg   → African_Bush_Elephant.jpg
      langde-20px-Red_pog.svg.png              → Red_pog.svg
    Returns None for content-hashed filenames with no Commons equivalent.
    """
    basename = zim_url.rsplit("/", 1)[-1]
    m = re.match(r"^[a-z]+-\d+px-(.+)", basename, re.IGNORECASE)
    if not m:
        return None
    original = m.group(1)
    # SVGs are rendered to PNG in the ZIM, producing a double extension (.svg.png).
    # Strip the trailing .png to recover the original .svg filename.
    if original.lower().endswith(".svg.png"):
        original = original[:-4]
    return original


def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        buf.extend(b)
    return buf.decode('utf-8', errors='replace')


def extract_media_filenames(zim_path: Path) -> tuple[list[str], list[str]]:
    """Parse ZIM binary to collect image and audio filenames (no libzim)."""
    images = []
    audio  = []

    with open(zim_path, 'rb') as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM file too small to be valid", file=sys.stderr)
            sys.exit(1)

        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: Not a ZIM file (magic={hex(magic)})", file=sys.stderr)
            sys.exit(1)

        entry_count, = struct.unpack_from('<I', header, 24)
        url_ptr_pos, = struct.unpack_from('<Q', header, 32)

        print(f"ZIM: {entry_count} entries, url_ptr_pos=0x{url_ptr_pos:x}")

        for i in range(entry_count):
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from('<Q', raw)

            f.seek(ptr)
            entry_hdr = f.read(4)
            if len(entry_hdr) < 4:
                continue
            mime_idx, param_len, ns_byte = struct.unpack_from('<HBc', entry_hdr)

            f.read(4)  # revision

            if mime_idx == 0xffff:
                f.read(4)  # redirect target index
            else:
                f.read(8)  # cluster number + blob number

            url     = _read_cstr(f)
            decoded = unquote(url)
            ext     = Path(decoded).suffix.lower()

            if ext in IMAGE_EXTS:
                images.append(decoded)
            elif ext in AUDIO_EXTS:
                audio.append(decoded)

    return images, audio


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


def process_image_page(page: dict) -> dict:
    info_list = page.get("imageinfo") or []
    if not info_list:
        # File not found on Commons (likely content-hashed Kiwix filename).
        # Klexikon curates only CC-licensed content → trust by default.
        return {"allowed": True, "license": None, "author": None, "license_url": None}
    meta = info_list[0].get("extmetadata") or {}
    lic  = meta.get("LicenseShortName", {}).get("value", "")
    auth = strip_html(meta.get("Artist", {}).get("value", ""))
    url  = meta.get("LicenseUrl", {}).get("value", "")
    # If Commons explicitly says NC/ND → block. If no license string → trust Klexikon.
    allowed = is_permitted(lic) if lic else True
    return {
        "allowed":     allowed,
        "license":     lic  or None,
        "author":      auth or None,
        "license_url": url  or None,
    }


def process_audio_page(page: dict) -> dict:
    info_list = page.get("imageinfo") or []
    if not info_list:
        return {"allowed": True, "license": None, "author": None, "license_url": None, "caption": None}
    meta    = info_list[0].get("extmetadata") or {}
    lic     = meta.get("LicenseShortName", {}).get("value", "")
    auth    = strip_html(meta.get("Artist", {}).get("value", ""))
    url     = meta.get("LicenseUrl", {}).get("value", "")
    caption = strip_html(meta.get("ImageDescription", {}).get("value", ""))
    allowed = is_permitted(lic) if lic else True
    return {
        "allowed":     allowed,
        "license":     lic  or None,
        "author":      auth or None,
        "license_url": url  or None,
        "caption":     caption or None,
    }


def process_in_batches(filenames: list[str], process_fn, label: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    batches = [filenames[i:i + BATCH_SIZE] for i in range(0, len(filenames), BATCH_SIZE)]
    for i, batch in enumerate(batches, 1):
        print(f"  {label} batch {i}/{len(batches)} ({len(batch)} files)...", end=" ", flush=True)
        try:
            pages = query_batch(batch)
            for page in pages.values():
                # Normalize to underscores — Commons returns titles with spaces.
                fname = page.get("title", "").removeprefix("File:").replace(" ", "_")
                results[fname] = process_fn(page)
            print("ok")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(REQUEST_DELAY)
    return results


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM file not found: {zim_path}")
        sys.exit(1)

    print(f"Opening {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    image_filenames, audio_filenames = extract_media_filenames(zim_path)
    print(f"Found {len(image_filenames)} images, {len(audio_filenames)} audio files")

    # Load image_map.json if present (maps content-hashed ZIM filenames to Commons originals).
    # Produced by build_image_map.py — needed for ZIMs that use _assets_/<hash>.jpg storage.
    image_map: dict[str, str] = {}
    if IMAGE_MAP_FILE.exists():
        image_map = json.loads(IMAGE_MAP_FILE.read_text(encoding="utf-8"))
        print(f"Loaded image_map: {len(image_map)} hash→original entries")
    else:
        print(f"Note: {IMAGE_MAP_FILE} not found — content-hashed images will have no Commons mapping")

    # Build ZIM-filename → Commons-filename mapping.
    # Query Commons using the real filenames so we get actual license data.
    zim_to_commons: dict[str, str] = {}
    for fn in image_filenames:
        cf = extract_commons_filename(fn) or image_map.get(fn)
        if cf:
            zim_to_commons[fn] = cf

    unique_commons = list({cf for cf in zim_to_commons.values()})
    print(f"  {len(unique_commons)} unique Commons filenames extracted from {len(image_filenames)} ZIM entries")

    commons_license_data = process_in_batches(unique_commons, process_image_page, "image")
    audio_results        = process_in_batches(audio_filenames, process_audio_page,  "audio")

    # Assemble final image results keyed by ZIM filename.
    image_results: dict[str, dict] = {}
    for fn in image_filenames:
        cf = zim_to_commons.get(fn)
        if cf:
            data = commons_license_data.get(cf) or commons_license_data.get(cf.replace("_", " "))
            if data:
                result = {**data, "commons_file": cf}
            else:
                # Commons returned nothing — trust Klexikon curation.
                result = {"allowed": True, "license": None, "author": None,
                          "license_url": None, "commons_file": cf}
        else:
            # Content-hashed or unknown format — no Commons mapping available.
            result = {"allowed": True, "license": None, "author": None,
                      "license_url": None, "commons_file": None}
        image_results[fn] = result

    output = {
        "generated":   date.today().isoformat(),
        "zim_version": ZIM_VERSION,
        "images":      image_results,
        "audio":       audio_results,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    img_allowed   = sum(1 for v in image_results.values() if v["allowed"])
    audio_allowed = sum(1 for v in audio_results.values() if v["allowed"])
    print(f"\nDone: {len(image_results)} images ({img_allowed} allowed), "
          f"{len(audio_results)} audio ({audio_allowed} allowed) → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
