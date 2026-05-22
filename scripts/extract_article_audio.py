#!/usr/bin/env python3
"""
Scans Klexikon ZIM article HTML for Wikimedia audio links
(href="...wpDestFile=FILENAME.ogg"), extracts captions,
writes article_audio_refs.json.

Uses binary ZIM parsing (no libzim required) — same proven approach as
generate_license_json.py. Handles zstd, xz, zlib and uncompressed clusters.

Run locally:
  ZIM_FILE=klexikon.zim python scripts/extract_article_audio.py
  ZIM_FILE=klexikon.zim MAX_ARTICLES=10 python scripts/extract_article_audio.py

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
    print("WARNING: pip install zstandard  (needed for zstd-compressed ZIM files)", file=sys.stderr)

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE  = Path("article_audio_refs.json")
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "0"))

ZIM_MAGIC = 0x044d495a

AUDIO_LINK_RE = re.compile(
    r'href="[^"]*[?&]wpDestFile=([^"&]+\.(?:ogg|oga|mp3|opus|wav|flac))',
    re.IGNORECASE,
)


def extract_caption(html: str, match_start: int) -> str | None:
    window = html[max(0, match_start - 500): match_start]
    text = re.sub(r"<[^>]+>", " ", window)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    for sep in (":", ".", "!", "?"):
        idx = text.rfind(sep)
        if idx >= 0:
            candidate = text[idx + 1:].strip()
            if 5 <= len(candidate) <= 200:
                return candidate
    tail = text[-150:].strip()
    return tail if len(tail) >= 5 else None


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


def _decompress(data: bytes, compression: int, cluster_idx: int = -1) -> bytes | None:
    # Compression types per current libzim/Kiwix:
    #   0/1 = none,  4 = lzma,  5 = zstd (NOT bzip2!),  6 = xz,  8 = zstd (old tools)
    try:
        if compression in (0, 1):
            return data
        if compression == 4:
            return lzma.decompress(data)
        if compression in (5, 8):  # zstd — type 5 in current libzim, type 8 in older tools
            if not HAS_ZSTD:
                print("ERROR: zstd cluster found but zstandard not installed; pip install zstandard",
                      file=sys.stderr)
                return None
            dctx = _zstd.ZstdDecompressor()
            return dctx.decompress(data, max_output_size=256 * 1024 * 1024)
        if compression == 6:
            return lzma.decompress(data)
        print(f"WARNING: unknown compression type {compression} in cluster {cluster_idx}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"WARNING: cluster {cluster_idx} decompression failed (type={compression}): {e} "
              f"[raw prefix: {data[:16].hex()}]", file=sys.stderr)
        return None


def _read_cluster(f, cluster_ptrs: list[int], idx: int, checksum_pos: int) -> tuple[bytes | None, bool]:
    """Read and decompress cluster idx. Returns (data, extended_offsets)."""
    if idx >= len(cluster_ptrs):
        return None, False
    start = cluster_ptrs[idx]
    end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos

    f.seek(start)
    info      = struct.unpack('B', f.read(1))[0]
    comp      = info & 0x0f
    extended  = bool(info & 0x10)
    raw_size  = end - start - 1
    if raw_size <= 0:
        return None, extended
    raw  = f.read(raw_size)
    data = _decompress(raw, comp, cluster_idx=idx)
    return data, extended


def _extract_blob(data: bytes, blob_num: int, extended: bool) -> bytes | None:
    """Extract blob blob_num from decompressed cluster data."""
    ptr_size = 8 if extended else 4
    fmt = '<Q' if extended else '<I'
    if len(data) < ptr_size:
        return None
    first_offset, = struct.unpack_from(fmt, data, 0)
    n_blobs = first_offset // ptr_size - 1   # N+1 offsets → N blobs
    if blob_num >= n_blobs:
        return None
    if (blob_num + 2) * ptr_size > len(data):
        return None
    off_a, = struct.unpack_from(fmt, data, blob_num       * ptr_size)
    off_b, = struct.unpack_from(fmt, data, (blob_num + 1) * ptr_size)
    if off_a > off_b or off_b > len(data):
        return None
    return data[off_a:off_b]


def iter_html_content(zim_path: Path):
    """Yield (title, html_bytes) for every HTML entry in the ZIM."""
    with open(zim_path, 'rb') as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM too small", file=sys.stderr)
            return

        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: not a ZIM file (magic={hex(magic)})", file=sys.stderr)
            return

        entry_count,   = struct.unpack_from('<I', header, 24)
        cluster_count, = struct.unpack_from('<I', header, 28)
        url_ptr_pos,   = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', header, 48)
        mime_list_pos, = struct.unpack_from('<Q', header, 56)
        checksum_pos,  = struct.unpack_from('<Q', header, 72)

        print(f"ZIM: {entry_count} entries, {cluster_count} clusters", flush=True)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}
        print(f"MIME types ({len(mime_types)}): {mime_types}", flush=True)
        print(f"HTML MIME indices: {html_idxs}", flush=True)
        if not html_idxs:
            print("ERROR: no text/html MIME type found in ZIM", file=sys.stderr)
            return

        # Read cluster pointer table
        f.seek(cluster_ptr_pos)
        cluster_ptrs: list[int] = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8:
                break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        # Pass 1: collect HTML entry metadata
        entries: list[tuple[int, int, str, str]] = []  # (cluster, blob, url, title)
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
                # Skip redirects and non-HTML entries without reading further
                continue

            f.read(4)  # revision
            cluster_num, blob_num = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit('/', 1)[-1]
            entries.append((cluster_num, blob_num, url, title))

        print(f"HTML entries found: {len(entries)}", flush=True)
        if not entries:
            print("ERROR: 0 HTML entries — check MIME type list above", file=sys.stderr)
            return

        # Pass 2: read blobs sorted by cluster for sequential I/O
        entries.sort(key=lambda e: (e[0], e[1]))

        cur_cluster_idx = -1
        cur_data:     bytes | None = None
        cur_extended: bool         = False

        for cluster_num, blob_num, url, title in entries:
            if cluster_num != cur_cluster_idx:
                cur_cluster_idx = cluster_num
                cur_data, cur_extended = _read_cluster(f, cluster_ptrs, cluster_num, checksum_pos)

            if cur_data is None:   # skip all entries from a failed cluster
                continue

            blob = _extract_blob(cur_data, blob_num, cur_extended)
            if blob:
                yield title, blob


def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Opening {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    if MAX_ARTICLES:
        print(f"Test mode: scanning at most {MAX_ARTICLES} HTML articles")

    results: dict[str, list] = {}
    html_count = 0

    for title, html_bytes in iter_html_content(zim_path):
        html_count += 1
        if MAX_ARTICLES and html_count > MAX_ARTICLES:
            break

        try:
            html = html_bytes.decode("utf-8", errors="replace")
        except Exception:
            continue

        refs = []
        for m in AUDIO_LINK_RE.finditer(html):
            refs.append({
                "filename": unquote(m.group(1)),
                "caption":  extract_caption(html, m.start()),
                "position": m.start(),
            })

        if refs:
            results[title] = refs
            print(f"  [{html_count}] {title}: {len(refs)} audio ref(s)")

        if html_count % 500 == 0:
            print(f"  {html_count} articles scanned, {len(results)} with audio...")

    OUTPUT_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    total_refs = sum(len(v) for v in results.values())
    print(
        f"\nDone: {html_count} articles scanned, "
        f"{total_refs} audio refs in {len(results)} articles -> {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
