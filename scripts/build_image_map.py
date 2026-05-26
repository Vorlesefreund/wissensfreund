#!/usr/bin/env python3
"""
Scans Klexikon ZIM article HTML to build a mapping from content-hashed image
filenames to their original Wikimedia Commons filenames.

Modern Kiwix ZIM files store images as _assets_/<sha1hash>.<ext> but wrap them
in <a href="...Datei:OriginalName.jpg"> links in the article HTML.  This script
recovers the mapping and writes image_map.json for use by generate_license_json.py.

Output: image_map.json
  {
    "_assets_/000535254c33a74347bae18d72f22d2e.jpg": "OriginalName.jpg",
    ...
  }

Usage:
  ZIM_FILE=klexikon.zim python scripts/build_image_map.py
  ZIM_FILE=klexikon.zim MAX_ARTICLES=50 python scripts/build_image_map.py

Requires: pip install zstandard
"""

import json
import lzma
import os
import re
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

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE  = Path(os.environ.get("OUTPUT_FILE", "image_map.json"))
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "0"))

ZIM_MAGIC  = 0x044d495a
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# <a href="...(Datei|File|etc.):OriginalName.ext" ...>
FILE_LINK_RE = re.compile(
    r'href="[^"]*(?:File|Datei|Fichier|Archivo|Bestand|Datoteka|Soubor|'
    r'Файл|ملف|Tiedosto|F%C3%A1jl|Fil|Vaizdas|Att%C4%93ls|Dosya):([^"#?&<>\s]+)"',
    re.IGNORECASE,
)

# <img src="../_assets_/hash.ext"> or <img src="_assets_/hash.ext">
ASSETS_IMG_RE = re.compile(
    r'<img\b[^>]*\bsrc="[^"]*_assets_/([^"?#\s<>]+)"',
    re.IGNORECASE,
)


def _is_image_ext(name: str) -> bool:
    return Path(name.lower()).suffix in IMAGE_EXTS


# ── ZIM binary reading ────────────────────────────────────────────────────────

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
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=256 * 1024 * 1024)
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


def _extract_blob(data: bytes, blob_num: int, extended: bool) -> bytes | None:
    ptr_size = 8 if extended else 4
    fmt = '<Q' if extended else '<I'
    if len(data) < ptr_size:
        return None
    first_offset, = struct.unpack_from(fmt, data, 0)
    n_blobs = first_offset // ptr_size - 1
    if blob_num >= n_blobs or (blob_num + 2) * ptr_size > len(data):
        return None
    off_a, = struct.unpack_from(fmt, data, blob_num * ptr_size)
    off_b, = struct.unpack_from(fmt, data, (blob_num + 1) * ptr_size)
    if off_a > off_b or off_b > len(data):
        return None
    return data[off_a:off_b]


def iter_html_content(zim_path: Path):
    """Yield (title, html_str) for every HTML entry in the ZIM."""
    with open(zim_path, 'rb') as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM too small", file=sys.stderr)
            return

        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: not a ZIM file (magic={hex(magic)})", file=sys.stderr)
            return

        entry_count,     = struct.unpack_from('<I', header, 24)
        cluster_count,   = struct.unpack_from('<I', header, 28)
        url_ptr_pos,     = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', header, 48)
        mime_list_pos,   = struct.unpack_from('<Q', header, 56)
        checksum_pos,    = struct.unpack_from('<Q', header, 72)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}

        if not html_idxs:
            print("ERROR: no text/html MIME type found in ZIM", file=sys.stderr)
            return

        f.seek(cluster_ptr_pos)
        cluster_ptrs: list[int] = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8:
                break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        entries = []
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
            mime_idx, _param_len, _ns = struct.unpack_from('<HBc', hdr)

            if mime_idx == 0xffff or mime_idx not in html_idxs:
                continue

            f.read(4)
            cluster_num, blob_num = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit('/', 1)[-1]
            entries.append((cluster_num, blob_num, url, title))

        print(f"ZIM: {entry_count} entries, {len(entries)} HTML articles")

        entries.sort(key=lambda e: (e[0], e[1]))

        cur_cluster_idx = -1
        cur_data = None
        cur_extended = False

        for cluster_num, blob_num, _url, title in entries:
            if cluster_num != cur_cluster_idx:
                cur_cluster_idx = cluster_num
                cur_data, cur_extended = _read_cluster(f, cluster_ptrs, cluster_num, checksum_pos)

            if cur_data is None:
                continue

            blob = _extract_blob(cur_data, blob_num, cur_extended)
            if blob:
                try:
                    yield title, blob.decode('utf-8', errors='replace')
                except Exception:
                    pass


# ── Mapping extraction ────────────────────────────────────────────────────────

def extract_mapping_from_html(html: str) -> dict[str, str]:
    """
    For each <img src="../_assets_/hash.ext"> find the nearest preceding
    <a href="...Datei:OriginalName.ext"> and return hash→original pairs.
    """
    mapping: dict[str, str] = {}

    for img_match in ASSETS_IMG_RE.finditer(html):
        hash_fn = unquote(img_match.group(1))
        key = f"_assets_/{hash_fn}"
        if key in mapping:
            continue

        img_pos = img_match.start()
        # Look back up to 1 200 chars for the enclosing <a href>
        pre = html[max(0, img_pos - 1200):img_pos]

        link_matches = list(FILE_LINK_RE.finditer(pre))
        if link_matches:
            raw_name = unquote(link_matches[-1].group(1))
            original = raw_name.replace(' ', '_').rstrip('/')
            if original and _is_image_ext(original):
                mapping[key] = original

    return mapping


def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    if MAX_ARTICLES:
        print(f"Test mode: at most {MAX_ARTICLES} articles")

    image_map: dict[str, str] = {}
    articles_scanned  = 0
    articles_with_img = 0

    for title, html in iter_html_content(zim_path):
        articles_scanned += 1
        if MAX_ARTICLES and articles_scanned > MAX_ARTICLES:
            break

        m = extract_mapping_from_html(html)
        if m:
            articles_with_img += 1
            before = len(image_map)
            image_map.update(m)
            # Diagnostic: show first few articles and their mappings in test mode
            if MAX_ARTICLES and articles_scanned <= 5:
                for k, v in m.items():
                    print(f"  {title}: {k} → {v}")

        if articles_scanned % 500 == 0:
            print(f"  {articles_scanned} articles, {len(image_map)} mappings so far...")

    OUTPUT_FILE.write_text(
        json.dumps(image_map, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    print(
        f"\nDone: {articles_scanned} articles scanned, "
        f"{articles_with_img} with images, "
        f"{len(image_map)} unique hash→original mappings → {OUTPUT_FILE}"
    )

    if not image_map:
        print(
            "\nWARNING: zero mappings found.\n"
            "The article HTML may use a different structure than expected.\n"
            "Re-run with MAX_ARTICLES=5 and check the output, or run\n"
            "dump_article_html.py to inspect the raw HTML."
        )


if __name__ == "__main__":
    main()
