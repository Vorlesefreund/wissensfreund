#!/usr/bin/env python3
"""
Builds images_medium.zip by extracting images directly from the Klexikon ZIM.

The images in the ZIM use content-hashed filenames (e.g. "Assets /abc123.jpg")
that do not exist on Wikimedia Commons, so they must be read from the ZIM binary.

Steps:
  1. Read media_licenses.json for permitted image filenames
  2. Scan the ZIM entry table to locate each image (cluster_num, blob_num)
  3. Group images by cluster; decompress each cluster once (zstandard)
  4. Write extracted images directly to images_medium.zip
  5. Write images_medium_manifest.json

Output:
  images_medium.zip           — ZIP with entries images/{filename}
  images_medium_manifest.json — {filename: {size, extracted}} tracking dict

Run locally:
  ZIM_FILE=klexikon.zim LICENSES_FILE=media_licenses.json python scripts/download_images.py

GitHub Actions: see .github/workflows/update_image_licenses.yml (images job)
Requires: pip install zstandard
"""

import json
import os
import struct
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import unquote

_START_TIME = time.monotonic()

try:
    import zstandard
except ImportError:
    print("ERROR: pip install zstandard", file=sys.stderr)
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

LICENSES_FILE    = Path(os.environ.get("LICENSES_FILE", "media_licenses.json"))
ZIM_FILE         = Path(os.environ.get("ZIM_FILE", "klexikon.zim"))
MANIFEST_FILE    = Path("images_medium_manifest.json")
OUTPUT_ZIP       = Path("images_medium.zip")
ZIM_VERSION      = os.environ.get("ZIM_VERSION", "unknown")
MAX_IMAGES       = int(os.environ.get("MAX_IMAGES", "0"))
MAX_RUNTIME_SECS = int(os.environ.get("MAX_RUNTIME_SECONDS", "7200"))

MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB hard cap
MAX_IMG_BYTES = 5 * 1024 * 1024           # 5 MB per image

ZIM_MAGIC  = 0x044d495a
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ── ZIM binary reading ─────────────────────────────────────────────────────────

def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
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
    """
    Walk the ZIM URL-pointer table; return {filename: (cluster_num, blob_num)}
    for every entry whose decoded URL is in `wanted`.
    Exits early once all wanted images are found.
    """
    h = _read_header(zim_path)
    entry_count = h["entry_count"]
    url_ptr_pos = h["url_ptr_pos"]
    found: dict[str, tuple[int, int]] = {}
    remaining = set(wanted)

    with open(zim_path, "rb") as f:
        for i in range(entry_count):
            if not remaining:
                break
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from("<Q", raw)

            f.seek(ptr)
            hdr4 = f.read(4)
            if len(hdr4) < 4:
                continue
            mime_idx, param_len, _ns = struct.unpack_from("<HBc", hdr4)
            f.read(4)  # revision

            if mime_idx == 0xFFFF:
                f.read(4)       # redirect index
                _read_cstr(f)   # url
                _read_cstr(f)   # title
                if param_len:
                    f.read(param_len)
                continue

            cluster_num, blob_num = struct.unpack("<II", f.read(8))
            url = _read_cstr(f)
            _read_cstr(f)  # title
            if param_len:
                f.read(param_len)

            decoded = unquote(url)
            if decoded in remaining:
                found[decoded] = (cluster_num, blob_num)
                remaining.discard(decoded)

    return found


def _read_cluster_offsets(zim_path: Path, cluster_ptr_pos: int, cluster_count: int) -> list[int]:
    """Read all cluster start offsets from the cluster pointer table."""
    with open(zim_path, "rb") as f:
        f.seek(cluster_ptr_pos)
        data = f.read(cluster_count * 8)
    return [struct.unpack_from("<Q", data, i * 8)[0] for i in range(cluster_count)]


def decompress_cluster(
    zim_path: Path,
    cluster_offsets: list[int],
    cluster_num: int,
    zim_size: int,
) -> tuple[bytes, bool]:
    """
    Read and decompress one ZIM cluster.
    Returns (raw_data, extended) where extended=True means 8-byte blob offsets.
    """
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
        dctx = zstandard.ZstdDecompressor()
        raw = dctx.decompress(payload, max_output_size=256 * 1024 * 1024)
    else:
        raise ValueError(f"Unsupported cluster compression: {compression}")

    return raw, extended


def extract_blob(raw: bytes, blob_num: int, extended: bool) -> bytes:
    """Extract one blob from decompressed cluster data."""
    offset_size = 8 if extended else 4
    fmt = "<Q" if extended else "<I"
    first_offset, = struct.unpack_from(fmt, raw, 0)
    blob_count = first_offset // offset_size - 1
    if blob_num > blob_count:
        raise IndexError(f"blob {blob_num} > cluster blob_count {blob_count}")
    start, = struct.unpack_from(fmt, raw, blob_num * offset_size)
    end,   = struct.unpack_from(fmt, raw, (blob_num + 1) * offset_size)
    return raw[start:end]


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    for path, label in [(LICENSES_FILE, "LICENSES_FILE"), (ZIM_FILE, "ZIM_FILE")]:
        if not path.exists():
            print(f"ERROR: {label}={path} not found", file=sys.stderr)
            sys.exit(1)

    # ── 1. Permitted image list ───────────────────────────────────────────────
    license_data = json.loads(LICENSES_FILE.read_text(encoding="utf-8"))
    permitted = [
        fn for fn, info in license_data.get("images", {}).items()
        if info.get("allowed") and Path(fn).suffix.lower() in IMAGE_EXTS
    ]
    if MAX_IMAGES > 0:
        permitted = permitted[:MAX_IMAGES]
        print(f"[test mode] Limiting to {MAX_IMAGES} images")
    print(f"Permitted images: {len(permitted)}")

    # ── 2. Locate images in ZIM entry table ───────────────────────────────────
    print(f"\nScanning ZIM ({ZIM_FILE.stat().st_size // 1_048_576} MB)...")
    zim_entries = scan_image_entries(ZIM_FILE, set(permitted))
    not_found   = len(permitted) - len(zim_entries)
    print(f"Located in ZIM: {len(zim_entries)} / {len(permitted)}"
          + (f"  ({not_found} not in ZIM — skipped)" if not_found else ""))

    if not zim_entries:
        print("Nothing to extract.")
        _write_manifest({})
        return

    # ── 3. Load cluster pointer table ─────────────────────────────────────────
    h = _read_header(ZIM_FILE)
    zim_size = ZIM_FILE.stat().st_size
    cluster_offsets = _read_cluster_offsets(ZIM_FILE, h["cluster_ptr_pos"], h["cluster_count"])

    # Group by cluster so each cluster is decompressed only once
    by_cluster: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for fn, (cn, bn) in zim_entries.items():
        by_cluster[cn].append((fn, bn))

    print(f"Clusters to decompress: {len(by_cluster)} (of {h['cluster_count']} total)")

    # ── 4. Extract images → ZIP ───────────────────────────────────────────────
    manifest:     dict[str, dict] = {}
    total_bytes   = 0
    entry_count   = 0
    skip_count    = 0
    cluster_done  = 0
    time_abort    = False

    print()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_STORED) as zf:
        for cluster_num in sorted(by_cluster.keys()):
            elapsed = time.monotonic() - _START_TIME
            if elapsed > MAX_RUNTIME_SECS:
                time_abort = True
                print(f"Time budget reached ({elapsed / 3600:.1f} h) — stopping early")
                break

            items = by_cluster[cluster_num]
            try:
                raw, extended = decompress_cluster(ZIM_FILE, cluster_offsets, cluster_num, zim_size)
                for fn, blob_num in items:
                    try:
                        data = extract_blob(raw, blob_num, extended)
                    except Exception as e:
                        print(f"  SKIP {fn}: {e}")
                        skip_count += 1
                        continue
                    if len(data) == 0 or len(data) > MAX_IMG_BYTES:
                        skip_count += 1
                        continue
                    if total_bytes + len(data) > MAX_ZIP_BYTES:
                        print("2 GB cap reached — stopping")
                        skip_count += len(items)
                        break
                    zf.writestr(f"images/{fn}", data)
                    manifest[fn] = {"size": len(data), "extracted": date.today().isoformat()}
                    total_bytes += len(data)
                    entry_count += 1
            except Exception as e:
                print(f"  SKIP cluster {cluster_num}: {e}")
                skip_count += len(items)

            cluster_done += 1
            if cluster_done % 100 == 0 or cluster_done == len(by_cluster):
                pct = cluster_done / len(by_cluster) * 100
                elapsed = time.monotonic() - _START_TIME
                print(f"  {cluster_done}/{len(by_cluster)} clusters ({pct:.0f}%)"
                      f" — {entry_count} images, {total_bytes // 1_048_576} MB"
                      f" — {elapsed:.0f}s elapsed")

    zip_mb = OUTPUT_ZIP.stat().st_size // 1_048_576
    print(f"\nResult: {entry_count} images → {zip_mb} MB ZIP")
    if skip_count:
        print(f"  Skipped: {skip_count}")
    if time_abort:
        deferred = len(zim_entries) - entry_count - skip_count
        print(f"  Deferred to next run: {deferred}")

    # ── 5. Manifest ───────────────────────────────────────────────────────────
    _write_manifest(manifest)


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
