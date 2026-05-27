#!/usr/bin/env python3
"""
Scans Klexikon ZIM article HTML to build a mapping from content-hashed image
filenames to their original Wikimedia Commons filenames.

Modern Kiwix ZIM files store images as _assets_/<sha1hash>.<ext>.  This script
recovers the mapping using two strategies (tried in order for each image):

  1. alt-as-filename: if <img alt="Name.jpg"> looks like a filename, use it.
     Covers icons, logos, and un-captioned images (fast, offline).

  2. Datei-link: if a preceding <a href="…Datei:Name.jpg"> exists within 1200
     chars of the img tag, use the linked name.  Covers older ZIM formats where
     Kiwix preserved the file-description anchor.

  3. MediaWiki API (klexikon.zum.de): for articles where both offline strategies
     failed, fetch the rendered HTML via action=parse and extract Datei: links
     in appearance order.  Match by position with the ZIM HTML img tags.
     Skipped when MAX_ARTICLES is set (test mode) or when requests is absent.

Output: image_map.json
  {
    "_assets_/000535254c33a74347bae18d72f22d2e.jpg": "OriginalName.jpg",
    ...
  }

Usage:
  ZIM_FILE=klexikon.zim python scripts/build_image_map.py
  ZIM_FILE=klexikon.zim MAX_ARTICLES=50 python scripts/build_image_map.py

Requires: pip install zstandard requests
"""

import json
import lzma
import os
import re
import struct
import sys
import time
from pathlib import Path
from urllib.parse import unquote

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False
    print("WARNING: pip install zstandard", file=sys.stderr)

try:
    import requests as _requests
    _session = _requests.Session()
    _session.headers["User-Agent"] = "WissensfreundBot/1.0 (image-mapper; build_image_map.py)"
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: pip install requests (needed for MediaWiki API fallback)", file=sys.stderr)

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE  = Path(os.environ.get("OUTPUT_FILE", "image_map.json"))
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "0"))

KLEXIKON_API = "https://klexikon.zum.de/api.php"
API_DELAY    = 0.4   # seconds between MediaWiki API calls

ZIM_MAGIC  = 0x044d495a
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# <a href="...(Datei|File|etc.):OriginalName.ext" ...>  (Strategy 2 — older ZIMs)
FILE_LINK_RE = re.compile(
    r'href="[^"]*(?:File|Datei|Fichier|Archivo|Bestand|Datoteka|Soubor|'
    r'Файл|ملف|Tiedosto|F%C3%A1jl|Fil|Vaizdas|Att%C4%93ls|Dosya):([^"#?&<>\s]+)"',
    re.IGNORECASE,
)

# Full <img> tag (non-greedy body, stops at first >)
_FULL_IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)

# src="_assets_/hash.ext" within an img tag
_SRC_HASH_RE = re.compile(r'\bsrc="[^"]*_assets_/([^"?#\s<>]+)"', re.IGNORECASE)

# alt="Name.ext" where ext is an image extension  (Strategy 1)
_ALT_FILE_RE = re.compile(
    r'\balt="([^"]{1,200}\.(?:jpg|jpeg|png|gif|svg|webp))"',
    re.IGNORECASE,
)

# Datei:/File: links in rendered MediaWiki HTML  (Strategy 3 parsing)
_MW_FILE_LINK_RE = re.compile(
    r'href="[^"]*(?:File|Datei):([^"#?&<>\s]+)"',
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
    """Yield (title, html_str) for every HTML article in the ZIM."""
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

        for cluster_num, blob_num, url, title in entries:
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


# ── Per-image extraction from ZIM HTML ───────────────────────────────────────

def extract_zim_imgs(html: str) -> list[tuple[str, str]]:
    """Return [(hash_fn, alt)] for every _assets_ image in appearance order."""
    result = []
    for m in _FULL_IMG_RE.finditer(html):
        tag = m.group(0)
        src_m = _SRC_HASH_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        alt_m   = _ALT_FILE_RE.search(tag)
        alt     = unquote(alt_m.group(1)).strip() if alt_m else ""
        result.append((hash_fn, alt))
    return result


# ── Offline mapping strategies ────────────────────────────────────────────────

def try_offline_mapping(html: str, image_map: dict[str, str]) -> list[tuple[str, str]]:
    """
    Apply Strategy 1 (alt-as-filename) and Strategy 2 (Datei link) to the HTML.
    Returns a list of (hash_fn, alt) pairs for images that still need API lookup.
    """
    unmapped: list[tuple[str, str]] = []

    for m in _FULL_IMG_RE.finditer(html):
        tag = m.group(0)
        src_m = _SRC_HASH_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        key = f"_assets_/{hash_fn}"
        if key in image_map:
            continue

        # Strategy 1: alt attribute looks like a Commons filename
        alt_m = _ALT_FILE_RE.search(tag)
        if alt_m:
            alt = unquote(alt_m.group(1)).strip().replace(" ", "_")
            if alt:
                image_map[key] = alt
                continue

        # Strategy 2: preceding <a href="...Datei:Name.ext"> (older ZIM formats)
        img_pos = m.start()
        pre = html[max(0, img_pos - 1200):img_pos]
        link_matches = list(FILE_LINK_RE.finditer(pre))
        if link_matches:
            raw_name = unquote(link_matches[-1].group(1))
            original = raw_name.replace(' ', '_').rstrip('/')
            if original and _is_image_ext(original):
                image_map[key] = original
                continue

        # Could not map offline — collect alt for potential API match
        alt_any = re.search(r'\balt="([^"]*)"', tag, re.IGNORECASE)
        alt_text = unquote(alt_any.group(1)).strip() if alt_any else ""
        unmapped.append((hash_fn, alt_text))

    return unmapped


# ── MediaWiki API (Strategy 3) ────────────────────────────────────────────────

def fetch_parsed_html(title: str) -> str:
    """Fetch the rendered HTML of an article from klexikon.zum.de."""
    try:
        r = _session.get(KLEXIKON_API, params={
            "action": "parse",
            "page":   title,
            "prop":   "text",
            "format": "json",
        }, timeout=30)
        r.raise_for_status()
        return r.json().get("parse", {}).get("text", {}).get("*", "")
    except Exception as e:
        print(f"  API error ({title}): {e}", file=sys.stderr)
        return ""


def api_filenames_in_order(rendered_html: str) -> list[str]:
    """Extract Datei:/File: link targets in appearance order from MediaWiki HTML."""
    return [
        unquote(m.group(1)).replace(" ", "_").rstrip("/")
        for m in _MW_FILE_LINK_RE.finditer(rendered_html)
        if _is_image_ext(unquote(m.group(1)))
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    if MAX_ARTICLES:
        print(f"Test mode: at most {MAX_ARTICLES} articles")

    image_map: dict[str, str] = {}
    articles_scanned   = 0
    articles_with_imgs = 0

    # Articles that need Strategy 3 API lookup: {title: [unmapped (hash, alt) pairs]}
    needs_api: dict[str, list[tuple[str, str]]] = {}

    for title, html in iter_html_content(zim_path):
        articles_scanned += 1
        if MAX_ARTICLES and articles_scanned > MAX_ARTICLES:
            break

        unmapped = try_offline_mapping(html, image_map)
        has_any  = unmapped or any(
            f"_assets_/{h}" in image_map
            for h, _ in extract_zim_imgs(html)
        )
        if has_any:
            articles_with_imgs += 1

        if unmapped:
            needs_api[title] = unmapped

        if articles_scanned % 500 == 0:
            print(f"  {articles_scanned} articles, {len(image_map)} mappings, "
                  f"{len(needs_api)} need API...")

    print(f"  {articles_scanned} articles scanned, {articles_with_imgs} with images")
    print(f"  Strategy 1+2: {len(image_map)} mappings, {len(needs_api)} articles need API")

    # Strategy 3: MediaWiki API for remaining unmapped images
    # Skipped in test mode (MAX_ARTICLES set) and when requests is unavailable.
    if needs_api and HAS_REQUESTS and not MAX_ARTICLES:
        print(f"\nMediaWiki API lookup for {len(needs_api)} articles "
              f"({sum(len(v) for v in needs_api.values())} images)...")
        api_hits = 0
        for i, (title, unmapped_imgs) in enumerate(needs_api.items(), 1):
            rendered = fetch_parsed_html(title)
            if not rendered:
                time.sleep(API_DELAY)
                continue

            api_fns = api_filenames_in_order(rendered)

            # Position-match only when both sides have the same count
            if len(unmapped_imgs) == len(api_fns):
                for (hash_fn, _), commons_fn in zip(unmapped_imgs, api_fns):
                    key = f"_assets_/{hash_fn}"
                    if key not in image_map and commons_fn:
                        image_map[key] = commons_fn
                        api_hits += 1

            time.sleep(API_DELAY)

            if i % 200 == 0:
                print(f"  {i}/{len(needs_api)} API calls, {api_hits} new mappings...")

        print(f"  Strategy 3: {api_hits} additional mappings from MediaWiki API")
    elif needs_api and MAX_ARTICLES:
        print("  (Skipping MediaWiki API in test mode — run without MAX_ARTICLES for full lookup)")

    OUTPUT_FILE.write_text(
        json.dumps(image_map, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    print(
        f"\nDone: {articles_scanned} articles scanned, "
        f"{articles_with_imgs} with images, "
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
