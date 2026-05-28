#!/usr/bin/env python3
"""
Phase 1: Inspect image entries in Klexikon ZIM.

Iterates over ALL entries (every namespace) and collects those whose
MIME type is an image type.  For each image entry records:
  - namespace  (e.g. 'I', 'A', '-')
  - url        (the internal ZIM path, e.g. "I/Elephant.jpg" or "_assets_/abc123.jpg")
  - title      (might be the original Commons filename — that's what we're testing)
  - mime       (e.g. "image/jpeg")

Saves the first MAX_ENTRIES results to OUTPUT_FILE (default: zim_image_entries.json).
Prints a summary to stdout.

Usage:
  ZIM_FILE=klexikon.zim python scripts/inspect_zim_images.py
  ZIM_FILE=klexikon.zim MAX_ENTRIES=500 python scripts/inspect_zim_images.py

Requires only stdlib + zstandard.
"""

import json
import lzma
import os
import struct
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False
    print("WARNING: pip install zstandard", file=sys.stderr)

ZIM_FILE    = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "zim_image_entries.json"))
MAX_ENTRIES = int(os.environ.get("MAX_ENTRIES", "2000"))

ZIM_MAGIC  = 0x044d495a
IMAGE_MIME_PREFIXES = ("image/",)

# ── ZIM helpers (shared with build_image_map.py) ──────────────────────────────

def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        buf.extend(b)
    return buf.decode('utf-8', errors='replace')


def _read_mime_types(f, pos: int) -> list[str]:
    f.seek(pos)
    types: list[str] = []
    while True:
        mt = _read_cstr(f)
        if not mt:
            break
        types.append(mt)
    return types


def _decompress(data: bytes, compression: int) -> bytes | None:
    try:
        if compression in (0, 1):
            return data
        if compression == 4:
            return lzma.decompress(data)
        if compression in (5, 8):
            if not HAS_ZSTD:
                return None
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=64 * 1024 * 1024)
        if compression == 6:
            return lzma.decompress(data)
        return None
    except Exception:
        return None


def _read_cluster(f, cluster_ptrs: list[int], idx: int, checksum_pos: int):
    if idx >= len(cluster_ptrs):
        return None, False
    start = cluster_ptrs[idx]
    end = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
    f.seek(start)
    info = struct.unpack('B', f.read(1))[0]
    comp = info & 0x0f
    extended = bool(info & 0x10)
    raw_size = end - start - 1
    if raw_size <= 0:
        return None, extended
    raw = f.read(raw_size)
    return _decompress(raw, comp), extended


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    print(f"Collecting up to {MAX_ENTRIES} image entries → {OUTPUT_FILE}")

    with open(zim_path, 'rb') as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM too small", file=sys.stderr)
            sys.exit(1)

        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: not a ZIM file (magic={hex(magic)})", file=sys.stderr)
            sys.exit(1)

        entry_count,     = struct.unpack_from('<I', header, 24)
        cluster_count,   = struct.unpack_from('<I', header, 28)
        url_ptr_pos,     = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', header, 48)
        mime_list_pos,   = struct.unpack_from('<Q', header, 56)
        checksum_pos,    = struct.unpack_from('<Q', header, 72)

        mime_types = _read_mime_types(f, mime_list_pos)
        image_mime_idxs = {
            i: mt for i, mt in enumerate(mime_types)
            if any(mt.lower().startswith(p) for p in IMAGE_MIME_PREFIXES)
        }
        redirect_mime_idx = 0xffff

        print(f"MIME types in ZIM ({len(mime_types)} total):")
        for i, mt in enumerate(mime_types):
            print(f"  [{i}] {mt}")

        print(f"\nImage MIME indices: {list(image_mime_idxs.keys())}")
        print(f"Total entries: {entry_count}")

        # Read all url pointers
        all_entries = []
        for i in range(entry_count):
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from('<Q', raw)

            f.seek(ptr)
            hdr = f.read(4)
            if len(hdr) < 4:
                continue
            mime_idx, _param_len, ns_bytes = struct.unpack_from('<HBc', hdr)
            ns = ns_bytes.decode('ascii', errors='replace')

            if mime_idx == redirect_mime_idx:
                # redirect entry — skip
                continue

            if mime_idx not in image_mime_idxs:
                continue

            # Read cluster_num, blob_num, url, title for image entries
            f.read(4)  # skip reserved
            cluster_num, blob_num = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f)

            all_entries.append({
                "namespace": ns,
                "url":       url,
                "title":     title,
                "mime":      image_mime_idxs[mime_idx],
                "cluster":   cluster_num,
                "blob":      blob_num,
            })

        print(f"\nFound {len(all_entries)} image entries total.")

        # ── Analysis ──────────────────────────────────────────────────────────

        ns_counts: dict[str, int] = {}
        title_is_filename = 0
        title_is_hash     = 0
        title_empty       = 0
        title_other       = 0

        import re
        HASH_RE = re.compile(r'^[0-9a-f]{20,}$', re.IGNORECASE)
        EXT_RE  = re.compile(r'\.(jpg|jpeg|png|gif|webp|svg)$', re.IGNORECASE)

        for e in all_entries:
            ns_counts[e["namespace"]] = ns_counts.get(e["namespace"], 0) + 1
            t = e["title"]
            if not t:
                title_empty += 1
            elif EXT_RE.search(t):
                title_is_filename += 1
            elif HASH_RE.match(t.split('.')[0]):
                title_is_hash += 1
            else:
                title_other += 1

        print(f"\n── Namespace breakdown ──")
        for ns, cnt in sorted(ns_counts.items()):
            print(f"  '{ns}': {cnt}")

        print(f"\n── Title analysis ──")
        print(f"  Has image extension (e.g. 'Elefant.jpg'):  {title_is_filename}")
        print(f"  Looks like a hash:                          {title_is_hash}")
        print(f"  Empty title:                                {title_empty}")
        print(f"  Other:                                      {title_other}")

        # ── Sample output ─────────────────────────────────────────────────────

        print(f"\n── First 30 image entries ──")
        for e in all_entries[:30]:
            print(f"  ns={e['namespace']}  url={e['url']!r:60s}  title={e['title']!r}")

        print(f"\n── 30 entries with non-empty title ──")
        with_title = [e for e in all_entries if e["title"]][:30]
        for e in with_title:
            print(f"  ns={e['namespace']}  url={e['url']!r:60s}  title={e['title']!r}")

        # ── Save to JSON ──────────────────────────────────────────────────────

        subset = all_entries[:MAX_ENTRIES]
        OUTPUT_FILE.write_text(
            json.dumps({
                "total_image_entries": len(all_entries),
                "entries_in_file":     len(subset),
                "namespace_counts":    ns_counts,
                "title_stats": {
                    "has_image_extension": title_is_filename,
                    "looks_like_hash":     title_is_hash,
                    "empty":              title_empty,
                    "other":              title_other,
                },
                "entries": subset,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSaved {len(subset)} entries → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
