#!/usr/bin/env python3
"""
ZIM diagnostic: counts ALL entries by extension, reports URL patterns,
samples article HTML to count <img> tags, and checks cluster compression types.

Run in CI:
  ZIM_FILE=klexikon.zim python scripts/diagnose_zim.py

Run locally:
  ZIM_FILE=path/to/klexikon.zim python scripts/diagnose_zim.py
"""

import lzma
import os
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "20"))  # HTML articles to sample
ZIM_MAGIC    = 0x044D495A

IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
AUDIO_EXTS   = {".ogg", ".oga", ".mp3", ".opus", ".wav", ".flac"}

IMG_SRC_RE   = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.IGNORECASE)


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


def _read_cluster_raw(f, cluster_ptrs: list[int], idx: int, checksum_pos: int):
    if idx >= len(cluster_ptrs):
        return None, False, -1
    start = cluster_ptrs[idx]
    end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
    f.seek(start)
    info_byte = struct.unpack('B', f.read(1))[0]
    comp      = info_byte & 0x0F
    extended  = bool(info_byte & 0x10)
    raw_size  = end - start - 1
    if raw_size <= 0:
        return None, extended, comp
    raw = f.read(raw_size)
    return _decompress(raw, comp), extended, comp


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


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    zim_size = zim_path.stat().st_size
    print(f"ZIM: {zim_path} ({zim_size // 1_048_576} MB)")

    with open(zim_path, 'rb') as f:
        header = f.read(80)
        if len(header) < 80:
            print("ERROR: ZIM too small", file=sys.stderr)
            sys.exit(1)

        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: Not a ZIM file (magic={hex(magic)})", file=sys.stderr)
            sys.exit(1)

        major_ver,   = struct.unpack_from('<H', header, 4)
        minor_ver,   = struct.unpack_from('<H', header, 6)
        entry_count, = struct.unpack_from('<I', header, 24)
        cluster_count, = struct.unpack_from('<I', header, 28)
        url_ptr_pos,   = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', header, 48)
        mime_list_pos,   = struct.unpack_from('<Q', header, 56)
        checksum_pos,    = struct.unpack_from('<Q', header, 72)

        print(f"Version: {major_ver}.{minor_ver}")
        print(f"Entries: {entry_count}, Clusters: {cluster_count}")
        print(f"url_ptr_pos: 0x{url_ptr_pos:x}, cluster_ptr_pos: 0x{cluster_ptr_pos:x}")
        print()

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}
        print(f"MIME types ({len(mime_types)} total):")
        for i, mt in enumerate(mime_types):
            print(f"  [{i}] {mt}")
        print()

        # Read cluster pointer list
        f.seek(cluster_ptr_pos)
        cluster_ptrs: list[int] = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8:
                break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        # ── Pass 1: scan ALL directory entries ─────────────────────────────────
        print("Scanning ALL directory entries...")
        ext_counter   = Counter()
        ns_counter    = Counter()
        mime_counter  = Counter()
        assets_count  = 0
        redirect_count = 0
        no_ext_urls   = []
        sample_urls: dict[str, list[str]] = defaultdict(list)
        html_entries  = []

        for i in range(entry_count):
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8:
                break
            ptr, = struct.unpack_from('<Q', raw)

            f.seek(ptr)
            hdr4 = f.read(4)
            if len(hdr4) < 4:
                continue
            mime_idx, param_len, ns_bytes = struct.unpack_from('<HBc', hdr4)
            ns = ns_bytes.decode('latin-1', errors='replace')
            ns_counter[ns] += 1
            mime_counter[mime_idx] += 1

            f.read(4)  # revision

            if mime_idx == 0xFFFF:
                redirect_count += 1
                f.read(4)  # redirect target
            else:
                cluster_num, blob_num = struct.unpack('<II', f.read(8))
                if mime_idx in html_idxs:
                    url   = _read_cstr(f)
                    title = _read_cstr(f)
                    html_entries.append((cluster_num, blob_num, url, title))
                    ext_counter['(html)'] += 1
                    if param_len:
                        f.read(param_len)
                    continue

            url     = _read_cstr(f)
            decoded = unquote(url)
            ext     = Path(decoded).suffix.lower()

            if '_assets_/' in decoded or decoded.startswith('_assets_'):
                assets_count += 1

            if ext:
                ext_counter[ext] += 1
                if len(sample_urls[ext]) < 5:
                    sample_urls[ext].append(decoded)
            else:
                ext_counter['(no ext)'] += 1
                if len(no_ext_urls) < 10:
                    no_ext_urls.append(decoded)

            if param_len:
                f.read(param_len)

        print(f"\n{'='*60}")
        print(f"DIRECTORY SCAN RESULTS ({entry_count} total entries)")
        print(f"{'='*60}")
        print(f"  Redirects:   {redirect_count}")
        print(f"  HTML articles: {len(html_entries)}")
        print(f"  _assets_/ URLs: {assets_count}")
        print()

        print("Extension distribution (top 30):")
        image_total = 0
        audio_total = 0
        for ext, count in sorted(ext_counter.items(), key=lambda x: -x[1])[:30]:
            tag = ""
            if ext in IMAGE_EXTS:
                tag = " ← IMAGE"
                image_total += count
            elif ext in AUDIO_EXTS:
                tag = " ← AUDIO"
                audio_total += count
            print(f"  {ext:20s} {count:6d}{tag}")

        print()
        print(f"  TOTAL image extensions: {image_total}")
        print(f"  TOTAL audio extensions: {audio_total}")

        print()
        print("Namespace distribution:")
        for ns, count in sorted(ns_counter.items(), key=lambda x: -x[1]):
            print(f"  '{ns}'  {count}")

        if no_ext_urls:
            print()
            print(f"Sample URLs with NO extension ({len(no_ext_urls)} shown):")
            for u in no_ext_urls:
                print(f"  {u!r}")

        print()
        print("Sample URLs per image extension:")
        for ext in IMAGE_EXTS:
            samples = sample_urls.get(ext, [])
            if samples:
                print(f"  {ext}:")
                for s in samples:
                    print(f"    {s!r}")

        # ── Pass 2: sample HTML articles, count <img> tags ─────────────────────
        print()
        print(f"{'='*60}")
        print(f"HTML ARTICLE SAMPLING (first {MAX_ARTICLES} articles)")
        print(f"{'='*60}")

        html_entries.sort(key=lambda e: (e[0], e[1]))

        img_counts = []
        img_src_patterns = Counter()
        cur_cluster_idx = -1
        cur_data = None
        cur_extended = False
        cur_comp = -1

        sampled = 0
        for cluster_num, blob_num, url, title in html_entries:
            if sampled >= MAX_ARTICLES:
                break

            if cluster_num != cur_cluster_idx:
                cur_cluster_idx = cluster_num
                cur_data, cur_extended, cur_comp = _read_cluster_raw(
                    f, cluster_ptrs, cluster_num, checksum_pos
                )

            if cur_data is None:
                continue

            blob = _extract_blob(cur_data, blob_num, cur_extended)
            if not blob:
                continue

            try:
                html = blob.decode('utf-8', errors='replace')
            except Exception:
                continue

            imgs = IMG_SRC_RE.findall(html)
            img_counts.append(len(imgs))

            # Categorize src patterns
            for src in imgs:
                if '_assets_/' in src:
                    img_src_patterns['_assets_/'] += 1
                elif src.startswith('data:'):
                    img_src_patterns['data:'] += 1
                elif src.startswith('http'):
                    img_src_patterns['http'] += 1
                else:
                    img_src_patterns[f'other:{src[:30]}'] += 1

            if sampled < 5:
                print(f"  [{sampled+1}] {title!r}: {len(imgs)} images")
                for src in imgs[:3]:
                    print(f"       src={src[:80]!r}")

            sampled += 1

        if img_counts:
            avg = sum(img_counts) / len(img_counts)
            total_if_all = avg * len(html_entries)
            print(f"\n  Articles sampled: {sampled}")
            print(f"  Images per article: min={min(img_counts)} max={max(img_counts)} avg={avg:.1f}")
            print(f"  Projected total images (avg × {len(html_entries)} articles): {total_if_all:.0f}")
            print()
            print("  img src patterns:")
            for pat, count in sorted(img_src_patterns.items(), key=lambda x: -x[1]):
                print(f"    {pat}: {count}")

        # ── Pass 3: cluster compression type distribution ──────────────────────
        print()
        print(f"{'='*60}")
        print("CLUSTER COMPRESSION TYPE DISTRIBUTION")
        print(f"{'='*60}")
        comp_counter = Counter()
        sample_size = min(cluster_count, 200)
        step = max(1, cluster_count // sample_size)
        for idx in range(0, cluster_count, step):
            start = cluster_ptrs[idx]
            end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
            if end <= start:
                continue
            with open(zim_path, 'rb') as fz:
                fz.seek(start)
                info_byte = struct.unpack('B', fz.read(1))[0]
            comp = info_byte & 0x0F
            comp_counter[comp] += 1

        comp_names = {0: 'none', 1: 'none(v1)', 4: 'lzma', 5: 'zstandard', 6: 'lzma(6)', 8: 'zstd(8)'}
        for comp, count in sorted(comp_counter.items()):
            name = comp_names.get(comp, f'unknown({comp})')
            print(f"  compression {comp} ({name}): {count} clusters sampled")

        print()
        print("SUMMARY")
        print(f"  Image entries in ZIM directory (with known ext): {image_total}")
        print(f"  Audio entries in ZIM directory: {audio_total}")
        print(f"  HTML articles: {len(html_entries)}")
        if img_counts:
            print(f"  Avg images per article (sampled): {sum(img_counts)/len(img_counts):.1f}")
            print(f"  Projected images if fully extracted: {sum(img_counts)/len(img_counts) * len(html_entries):.0f}")


if __name__ == "__main__":
    main()
