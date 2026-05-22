#!/usr/bin/env python3
"""
Diagnostic: dumps the HTML around the first <img> tag for specified articles,
showing exactly what structure findNearbyCaption() sees.

Run:
  ZIM_FILE=klexikon.zim python scripts/dump_article_html.py
  ZIM_FILE=klexikon.zim ARTICLE=Beethoven python scripts/dump_article_html.py
  ZIM_FILE=klexikon.zim ARTICLE=Beethoven CONTEXT=2000 python scripts/dump_article_html.py

Requires: pip install zstandard
"""
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

ZIM_FILE   = os.environ.get("ZIM_FILE", "klexikon.zim")
ARTICLE    = os.environ.get("ARTICLE", "Beethoven")
CONTEXT    = int(os.environ.get("CONTEXT", "500"))   # chars to show after <img>

ZIM_MAGIC  = 0x044d495a
IMG_RE     = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*>', re.IGNORECASE)


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
                print("ERROR: pip install zstandard", file=sys.stderr)
                return None
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=256 * 1024 * 1024)
        if compression == 6:
            return lzma.decompress(data)
        return None
    except Exception as e:
        print(f"WARNING: decompression failed: {e}", file=sys.stderr)
        return None


def _read_cluster(f, cluster_ptrs: list[int], idx: int, checksum_pos: int):
    start = cluster_ptrs[idx]
    end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
    f.seek(start)
    info     = struct.unpack('B', f.read(1))[0]
    comp     = info & 0x0f
    extended = bool(info & 0x10)
    raw_size = end - start - 1
    if raw_size <= 0:
        return None, extended
    return _decompress(f.read(raw_size), comp), extended


def _extract_blob(data: bytes, blob_num: int, extended: bool) -> bytes | None:
    ptr_size = 8 if extended else 4
    fmt = '<Q' if extended else '<I'
    if len(data) < ptr_size:
        return None
    first_offset, = struct.unpack_from(fmt, data, 0)
    n_blobs = first_offset // ptr_size - 1
    if blob_num >= n_blobs or (blob_num + 2) * ptr_size > len(data):
        return None
    off_a, = struct.unpack_from(fmt, data, blob_num       * ptr_size)
    off_b, = struct.unpack_from(fmt, data, (blob_num + 1) * ptr_size)
    if off_a > off_b or off_b > len(data):
        return None
    return data[off_a:off_b]


def find_article_html(zim_path: Path, keyword: str) -> tuple[str, str] | None:
    with open(zim_path, 'rb') as f:
        header = f.read(80)
        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print("Not a ZIM file", file=sys.stderr)
            return None

        entry_count,    = struct.unpack_from('<I', header, 24)
        cluster_count,  = struct.unpack_from('<I', header, 28)
        url_ptr_pos,    = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos,= struct.unpack_from('<Q', header, 48)
        mime_list_pos,  = struct.unpack_from('<Q', header, 56)
        checksum_pos,   = struct.unpack_from('<Q', header, 72)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}

        f.seek(cluster_ptr_pos)
        cluster_ptrs = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8:
                break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        kw = keyword.lower()
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
            mime_idx, param_len, _ = struct.unpack_from('<HBc', hdr)
            if mime_idx == 0xffff or mime_idx not in html_idxs:
                continue
            f.read(4)  # revision
            cluster_num, blob_num = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f)

            if kw not in url.lower() and kw not in title.lower():
                continue

            print(f"Found: url={url!r} title={title!r}")
            data, extended = _read_cluster(f, cluster_ptrs, cluster_num, checksum_pos)
            if data is None:
                print("Cluster decompression failed", file=sys.stderr)
                return None
            blob = _extract_blob(data, blob_num, extended)
            if blob is None:
                print("Blob extraction failed", file=sys.stderr)
                return None
            return title, blob.decode('utf-8', errors='replace')

    return None


def extract_body(html: str) -> str:
    for marker in ('id="mw-content-text"', 'id="mw-parser-output"', 'id="bodyContent"', '<body'):
        idx = html.lower().find(marker.lower())
        if idx > 0:
            tag_end = html.find('>', idx)
            if tag_end > 0:
                return html[tag_end + 1:]
    return html


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    result = find_article_html(zim_path, ARTICLE)
    if result is None:
        print(f"Article not found for keyword: {ARTICLE!r}", file=sys.stderr)
        sys.exit(1)

    title, html = result
    body = extract_body(html)
    print(f"\n{'='*60}")
    print(f"Article: {title}")
    print(f"Body length: {len(body)} chars")
    print(f"{'='*60}\n")

    imgs = list(IMG_RE.finditer(body))
    print(f"Found {len(imgs)} <img> tag(s)\n")

    for i, m in enumerate(imgs[:5]):
        src = m.group(1)
        print(f"─── Image {i+1}: src={src!r}")
        print(f"    match.range: {m.start()}..{m.end()-1}  (img tag length={m.end()-m.start()})")

        # Show context BEFORE the img (to see thumbinner/figure opening)
        pre_start = max(0, m.start() - 300)
        print(f"\n  [BEFORE img -300 chars]:")
        print(repr(body[pre_start:m.start()]))

        # Show context AFTER img (the window findNearbyCaption searches)
        after_start = m.end() - 1   # last char of match (the '>')
        after_end   = min(after_start + CONTEXT, len(body))
        print(f"\n  [AFTER img +{CONTEXT} chars]:")
        snippet = body[after_start:after_end]
        print(repr(snippet))

        # Check what caption patterns appear
        for pat in ['thumbcaption', 'figcaption', 'gallerytext']:
            idx = snippet.lower().find(pat)
            print(f"  {pat}: {'found at offset ' + str(idx) if idx >= 0 else 'NOT FOUND'}")
        print()


if __name__ == "__main__":
    main()
