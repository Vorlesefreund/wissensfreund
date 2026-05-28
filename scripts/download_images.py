#!/usr/bin/env python3
"""
Downloads Klexikon article images at three quality tiers.

Strategy: download the full-resolution original from Wikimedia Commons once
per image (Special:FilePath without ?width=, follows redirect to CDN origin),
then resize locally with Pillow. This guarantees genuine size differences
across tiers — unlike server-side width scaling, which returns the original
when the image is already smaller than the requested width.

  thumb    (max 300×300 px, JPEG quality 70)  — gallery strip / thumbnail
  standard (max 800×800 px, JPEG quality 80)  — fullscreen standard users
  pro      (max 1600×1600 px, JPEG quality 85) — fullscreen pro / premium

Fallback: ZIM binary extraction for Klexikon-specific images without a Commons
equivalent. These are also resized with Pillow; raw bytes used only when Pillow
cannot decode the format (e.g. SVG).

Output:
  images_thumb.zip          images_thumb_manifest.json
  images_standard.zip       images_standard_manifest.json
  images_pro.zip            images_pro_manifest.json

Run locally:
  ZIM_FILE=klexikon.zim LICENSES_FILE=media_licenses.json python scripts/download_images.py

GitHub Actions: see .github/workflows/update_image_licenses.yml (images job)
Requires: pip install requests zstandard Pillow
"""

import io
import json
import lzma
import os
import struct
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import unquote, quote

import requests
from PIL import Image

try:
    import zstandard
except ImportError:
    print("ERROR: pip install zstandard", file=sys.stderr)
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

LICENSES_FILE = Path(os.environ.get("LICENSES_FILE", "media_licenses.json"))
ZIM_FILE      = Path(os.environ.get("ZIM_FILE", "klexikon.zim"))
ZIM_VERSION   = os.environ.get("ZIM_VERSION", "unknown")
MAX_IMAGES    = int(os.environ.get("MAX_IMAGES", "0"))
COMMONS_DELAY = float(os.environ.get("COMMONS_DELAY", "0.15"))
SHARD_INDEX   = int(os.environ.get("SHARD_INDEX", "0"))
SHARD_COUNT   = int(os.environ.get("SHARD_COUNT", "1"))

# Quality tiers: (name, max_px, jpeg_quality)
SIZES = [
    ("thumb",    300, 70),
    ("standard", 800, 80),
    ("pro",     1600, 85),
]

MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB hard cap per ZIP
MAX_IMG_BYTES = 25 * 1024 * 1024        # 25 MB per original download

# No ?width= — we want the full-resolution original; redirect followed automatically
COMMONS_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{fn}"
IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ZIM_MAGIC   = 0x044D495A

_session = requests.Session()
_session.headers["User-Agent"] = "WissensfreundApp/1.0 (az@expansionssupport.de)"
_start = time.monotonic()


# ── Image resizing with Pillow ─────────────────────────────────────────────────

def resize_for_tier(data: bytes, max_px: int, quality: int) -> bytes | None:
    """Resize image to fit within max_px×max_px; return JPEG bytes. Never upscales."""
    try:
        img = Image.open(io.BytesIO(data))
        # Convert to RGB for JPEG output (handles RGBA, P, L, etc.)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img.convert("RGB"), mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # thumbnail() shrinks to fit, never upscales
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


# ── Wikimedia Commons download ─────────────────────────────────────────────────

def download_commons_original(commons_fn: str) -> bytes | None:
    """Download the full-resolution original from Wikimedia Commons."""
    url = COMMONS_URL.format(fn=quote(commons_fn, safe=""))
    try:
        r = _session.get(url, timeout=60, allow_redirects=True)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.content
        if len(data) == 0 or len(data) > MAX_IMG_BYTES:
            return None
        return data
    except Exception as e:
        print(f"    WARN {commons_fn}: {e}")
        return None


# ── ZIM binary reading (fallback for images without commons_file) ──────────────

def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b"\x00":
            break
        buf.extend(b)
    return buf.decode("utf-8", errors="replace")


def _read_header(zim_path: Path) -> dict:
    with open(zim_path, "rb") as f:
        hdr = f.read(80)
    if len(hdr) < 80:
        raise ValueError("ZIM file too small")
    magic, = struct.unpack_from("<I", hdr, 0)
    if magic != ZIM_MAGIC:
        raise ValueError(f"Not a ZIM file (magic={hex(magic)})")
    return {
        "entry_count":     struct.unpack_from("<I", hdr, 24)[0],
        "cluster_count":   struct.unpack_from("<I", hdr, 28)[0],
        "url_ptr_pos":     struct.unpack_from("<Q", hdr, 32)[0],
        "cluster_ptr_pos": struct.unpack_from("<Q", hdr, 48)[0],
    }


def scan_image_entries(zim_path: Path, wanted: set[str]) -> dict[str, tuple[int, int]]:
    h = _read_header(zim_path)
    found: dict[str, tuple[int, int]] = {}
    remaining = set(wanted)
    with open(zim_path, "rb") as f:
        for i in range(h["entry_count"]):
            if not remaining:
                break
            f.seek(h["url_ptr_pos"] + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from("<Q", raw)
            f.seek(ptr)
            hdr4 = f.read(4)
            if len(hdr4) < 4:
                continue
            mime_idx, param_len, _ns = struct.unpack_from("<HBc", hdr4)
            f.read(4)
            if mime_idx == 0xFFFF:
                f.read(4)
                _read_cstr(f)
                _read_cstr(f)
                if param_len:
                    f.read(param_len)
                continue
            cluster_num, blob_num = struct.unpack("<II", f.read(8))
            url = _read_cstr(f)
            _read_cstr(f)
            if param_len:
                f.read(param_len)
            decoded = unquote(url)
            if decoded in remaining:
                found[decoded] = (cluster_num, blob_num)
                remaining.discard(decoded)
    return found


def _read_cluster_offsets(zim_path: Path, cluster_ptr_pos: int, cluster_count: int) -> list[int]:
    with open(zim_path, "rb") as f:
        f.seek(cluster_ptr_pos)
        data = f.read(cluster_count * 8)
    return [struct.unpack_from("<Q", data, i * 8)[0] for i in range(cluster_count)]


def decompress_cluster(zim_path: Path, cluster_offsets: list[int],
                       cluster_num: int, zim_size: int) -> tuple[bytes, bool]:
    offset = cluster_offsets[cluster_num]
    end    = cluster_offsets[cluster_num + 1] if cluster_num + 1 < len(cluster_offsets) else zim_size
    with open(zim_path, "rb") as f:
        f.seek(offset)
        info_byte, = struct.unpack("<B", f.read(1))
        payload = f.read(end - offset - 1)
    compression = info_byte & 0x0F
    extended    = bool(info_byte & 0x10)
    if compression in (0, 1):
        raw = payload
    elif compression == 4:
        raw = lzma.decompress(payload)
    elif compression in (5, 8):
        raw = zstandard.ZstdDecompressor().decompress(payload, max_output_size=256 * 1024 * 1024)
    else:
        raise ValueError(f"Unsupported cluster compression: {compression}")
    return raw, extended


def extract_blob(raw: bytes, blob_num: int, extended: bool) -> bytes:
    offset_size = 8 if extended else 4
    fmt = "<Q" if extended else "<I"
    first_offset, = struct.unpack_from(fmt, raw, 0)
    blob_count = first_offset // offset_size - 1
    if blob_num > blob_count:
        raise IndexError(f"blob {blob_num} > cluster blob_count {blob_count}")
    start, = struct.unpack_from(fmt, raw, blob_num * offset_size)
    end,   = struct.unpack_from(fmt, raw, (blob_num + 1) * offset_size)
    return raw[start:end]


def extract_from_zim(filenames: list[str]) -> dict[str, bytes]:
    """Extract raw image bytes from ZIM for a list of filenames."""
    if not filenames or not ZIM_FILE.exists():
        return {}
    h = _read_header(ZIM_FILE)
    zim_size = ZIM_FILE.stat().st_size
    cluster_offsets = _read_cluster_offsets(ZIM_FILE, h["cluster_ptr_pos"], h["cluster_count"])
    entries = scan_image_entries(ZIM_FILE, set(filenames))

    by_cluster: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for fn, (cn, bn) in entries.items():
        by_cluster[cn].append((fn, bn))

    result: dict[str, bytes] = {}
    cluster_errors = 0
    blob_errors    = 0
    for cluster_num, items in by_cluster.items():
        try:
            raw, extended = decompress_cluster(ZIM_FILE, cluster_offsets, cluster_num, zim_size)
            for fn, blob_num in items:
                try:
                    data = extract_blob(raw, blob_num, extended)
                    if 0 < len(data) <= MAX_IMG_BYTES:
                        result[fn] = data
                    else:
                        blob_errors += 1
                except Exception as e:
                    blob_errors += 1
                    if blob_errors <= 3:
                        print(f"    WARN blob extract cluster={cluster_num} blob={blob_num}: {e}")
        except Exception as e:
            cluster_errors += 1
            if cluster_errors <= 5:
                print(f"    WARN cluster {cluster_num} decompress failed: {e}")
    if cluster_errors or blob_errors:
        print(f"  ZIM extract: {len(result)} ok, {cluster_errors} cluster errors, {blob_errors} blob errors")
    return result


# ── Manifest helper ────────────────────────────────────────────────────────────

def write_manifest(name: str, images: dict) -> None:
    manifest = {
        "generated":   date.today().isoformat(),
        "zim_version": ZIM_VERSION,
        "tier":        name,
        "images":      images,
    }
    path = Path(f"images_{name}_manifest.json")
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Manifest: {len(images)} images → {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not LICENSES_FILE.exists():
        print(f"ERROR: LICENSES_FILE={LICENSES_FILE} not found", file=sys.stderr)
        sys.exit(1)

    # 1. Load permitted image list ─────────────────────────────────────────────
    license_data = json.loads(LICENSES_FILE.read_text(encoding="utf-8"))
    all_images   = license_data.get("images", {})

    commons_list: list[tuple[str, str]] = []  # (zim_fn, commons_fn)
    zim_only:     list[str]             = []  # zim_fn (no Commons equivalent)

    for fn, info in all_images.items():
        if not info.get("allowed"):
            continue
        if Path(fn).suffix.lower() not in IMAGE_EXTS:
            continue
        cf = info.get("commons_file")
        if cf:
            commons_list.append((fn, cf))
        else:
            zim_only.append(fn)

    if MAX_IMAGES > 0:
        commons_list = commons_list[:MAX_IMAGES]
        zim_only     = zim_only[:max(0, MAX_IMAGES - len(commons_list))]
        print(f"[test mode] Limiting to {MAX_IMAGES} images")

    if SHARD_COUNT > 1:
        commons_list = [x for i, x in enumerate(commons_list) if i % SHARD_COUNT == SHARD_INDEX]
        zim_only     = [x for i, x in enumerate(zim_only)     if i % SHARD_COUNT == SHARD_INDEX]
        print(f"[shard {SHARD_INDEX}/{SHARD_COUNT}] {len(commons_list)} Commons + {len(zim_only)} ZIM-only")
    else:
        print(f"Commons images: {len(commons_list)}  |  ZIM-only: {len(zim_only)}")

    # 2. Open ZIP files ────────────────────────────────────────────────────────
    zips      = {name: zipfile.ZipFile(f"images_{name}.zip", "w", zipfile.ZIP_STORED)
                 for name, _, _ in SIZES}
    manifests = {name: {} for name, _, _ in SIZES}
    zip_bytes = {name: 0   for name, _, _ in SIZES}
    counts    = {name: 0   for name, _, _ in SIZES}

    # 3. Download originals from Wikimedia Commons, resize locally ─────────────
    print(f"\nDownloading {len(commons_list)} originals from Wikimedia Commons...")
    skip_count   = 0
    resize_fails = 0

    for i, (zim_fn, commons_fn) in enumerate(commons_list, 1):
        original = download_commons_original(commons_fn)
        if original is None:
            skip_count += 1
            time.sleep(COMMONS_DELAY)
            continue

        for tier_name, max_px, quality in SIZES:
            resized = resize_for_tier(original, max_px, quality)
            if resized is None:
                resize_fails += 1
                continue
            if zip_bytes[tier_name] + len(resized) > MAX_ZIP_BYTES:
                print(f"  {tier_name}: 2 GB cap reached — stopping")
                continue
            zips[tier_name].writestr(f"images/{zim_fn}", resized)
            manifests[tier_name][zim_fn] = {
                "size":       len(resized),
                "max_px":     max_px,
                "source":     "commons",
                "downloaded": date.today().isoformat(),
            }
            zip_bytes[tier_name] += len(resized)
            counts[tier_name]    += 1

        time.sleep(COMMONS_DELAY)

        if i % 100 == 0 or i == len(commons_list):
            elapsed = time.monotonic() - _start
            print(f"  {i}/{len(commons_list)} — "
                  f"thumb:{counts['thumb']} std:{counts['standard']} pro:{counts['pro']} "
                  f"— {elapsed:.0f}s elapsed")

    # 4. ZIM extraction fallback ───────────────────────────────────────────────
    if zim_only:
        print(f"\nExtracting {len(zim_only)} ZIM-only images (fallback)...")
        if not ZIM_FILE.exists():
            print(f"  WARN: ZIM_FILE={ZIM_FILE} not found — skipping ZIM fallback")
        else:
            extracted = extract_from_zim(zim_only)
            for fn, data in extracted.items():
                for tier_name, max_px, quality in SIZES:
                    resized = resize_for_tier(data, max_px, quality)
                    if resized is None:
                        resized = data  # keep raw bytes if Pillow can't decode (e.g. SVG)
                    if zip_bytes[tier_name] + len(resized) > MAX_ZIP_BYTES:
                        continue
                    zips[tier_name].writestr(f"images/{fn}", resized)
                    manifests[tier_name][fn] = {
                        "size":       len(resized),
                        "max_px":     max_px,
                        "source":     "zim",
                        "downloaded": date.today().isoformat(),
                    }
                    zip_bytes[tier_name] += len(resized)
                    counts[tier_name]    += 1
            print(f"  Extracted {len(extracted)} / {len(zim_only)} ZIM-only images")

    # 5. Close ZIPs + write manifests ─────────────────────────────────────────
    print()
    for name, _, _ in SIZES:
        zips[name].close()
        write_manifest(name, manifests[name])
        zip_mb = Path(f"images_{name}.zip").stat().st_size // 1_048_576
        print(f"  {name}: {counts[name]} images → {zip_mb} MB ZIP")

    elapsed = time.monotonic() - _start
    print(f"\nDone in {elapsed:.0f}s")
    if skip_count:
        print(f"  Skipped (Commons unavailable): {skip_count}")
    if resize_fails:
        print(f"  Resize failures (Pillow): {resize_fails}")


if __name__ == "__main__":
    main()
