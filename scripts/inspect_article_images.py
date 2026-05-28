#!/usr/bin/env python3
"""
Listet alle im HTML eines ZIM-Artikels referenzierten Bilder auf:
  - Dateiname / Hash
  - width/height aus img-Attributen (falls vorhanden)
  - alt-Text
  - Lizenzstatus aus media_licenses.json

Verwendung:
  ZIM_FILE=klexikon.zim LICENSES_FILE=media_licenses.json ARTICLE=Elefant \
      python scripts/inspect_article_images.py
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

ZIM_FILE      = os.environ.get("ZIM_FILE", "klexikon.zim")
LICENSES_FILE = Path(os.environ.get("LICENSES_FILE", "media_licenses.json"))
ARTICLE       = os.environ.get("ARTICLE", "Elefant")

ZIM_MAGIC = 0x044D495A

IMG_RE = re.compile(r'<img\b([^>]*)>', re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'\b(\w+)=["\']([^"\']*)["\']', re.IGNORECASE)


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
        return None
    except Exception as e:
        print(f"  Decompression error (type {compression}): {e}", file=sys.stderr)
        return None


def find_article(zim_path: Path, keyword: str) -> tuple[str, str] | None:
    with open(zim_path, 'rb') as f:
        hdr = f.read(80)
        if len(hdr) < 80 or struct.unpack_from('<I', hdr, 0)[0] != ZIM_MAGIC:
            print("ERROR: Invalid ZIM file", file=sys.stderr)
            return None

        entry_count,   = struct.unpack_from('<I', hdr, 24)
        cluster_count, = struct.unpack_from('<I', hdr, 28)
        url_ptr_pos,   = struct.unpack_from('<Q', hdr, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', hdr, 48)
        mime_list_pos, = struct.unpack_from('<Q', hdr, 56)
        checksum_pos,  = struct.unpack_from('<Q', hdr, 72)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}

        f.seek(cluster_ptr_pos)
        cluster_ptrs: list[int] = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8:
                break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        kw_lower = keyword.lower()
        matches: list[tuple[str, str, int, int]] = []  # (url, title, cluster, blob)

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
            mime_idx, param_len, _ = struct.unpack_from('<HBc', hdr4)
            if mime_idx == 0xFFFF or mime_idx not in html_idxs:
                if mime_idx != 0xFFFF:
                    f.read(4)  # revision
                    f.read(8)  # cluster+blob
                    _read_cstr(f)
                    _read_cstr(f)
                continue
            f.read(4)  # revision
            cluster_num, blob_num = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f)
            decoded_url = unquote(url)
            if kw_lower in decoded_url.lower() or kw_lower in title.lower():
                matches.append((decoded_url, title, cluster_num, blob_num))

        if not matches:
            print(f"Kein Artikel gefunden für: {keyword!r}", file=sys.stderr)
            return None

        # Exact match bevorzugen
        exact = [m for m in matches if m[0].lower() == kw_lower or m[1].lower() == kw_lower]
        chosen = exact[0] if exact else matches[0]
        url, title, cluster_num, blob_num = chosen

        print(f"Artikel gefunden: url={url!r}  title={title!r}")
        if len(matches) > 1:
            print(f"  ({len(matches)} Treffer, nehme ersten exakten)")

        # Cluster lesen
        idx = cluster_num
        start = cluster_ptrs[idx]
        end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
        f.seek(start)
        info_byte = struct.unpack('B', f.read(1))[0]
        comp      = info_byte & 0x0F
        extended  = bool(info_byte & 0x10)
        raw_data  = f.read(end - start - 1)
        decompressed = _decompress(raw_data, comp)
        if decompressed is None:
            print(f"ERROR: Cluster {cluster_num} konnte nicht dekomprimiert werden", file=sys.stderr)
            return None

        ptr_size = 8 if extended else 4
        fmt = '<Q' if extended else '<I'
        first_off, = struct.unpack_from(fmt, decompressed, 0)
        n_blobs = first_off // ptr_size - 1
        if blob_num >= n_blobs:
            print(f"ERROR: blob_num={blob_num} >= n_blobs={n_blobs}", file=sys.stderr)
            return None
        off_a, = struct.unpack_from(fmt, decompressed, blob_num * ptr_size)
        off_b, = struct.unpack_from(fmt, decompressed, (blob_num + 1) * ptr_size)
        blob = decompressed[off_a:off_b]
        return title or url, blob.decode('utf-8', errors='replace')


def parse_img_tags(html: str) -> list[dict]:
    images = []
    for m in IMG_RE.finditer(html):
        attrs_str = m.group(1)
        attrs = {}
        for am in ATTR_RE.finditer(attrs_str):
            attrs[am.group(1).lower()] = am.group(2)
        src = attrs.get('src', '')
        if not src:
            continue
        # Normalize: entferne führendes ./
        src_clean = src.lstrip('./')
        images.append({
            'src_raw':  src,
            'src':      src_clean,
            'width':    attrs.get('width', ''),
            'height':   attrs.get('height', ''),
            'alt':      attrs.get('alt', ''),
            'class':    attrs.get('class', ''),
        })
    return images


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM nicht gefunden: {zim_path}", file=sys.stderr)
        sys.exit(1)

    # media_licenses.json laden
    licenses: dict = {}
    if LICENSES_FILE.exists():
        data = json.loads(LICENSES_FILE.read_text(encoding='utf-8'))
        licenses = data.get('images', {})
        print(f"Lizenzdaten: {len(licenses)} Einträge geladen aus {LICENSES_FILE}")
    else:
        print(f"WARN: {LICENSES_FILE} nicht gefunden — keine Lizenzprüfung möglich")

    print(f"\nSuche Artikel '{ARTICLE}' im ZIM...\n")
    result = find_article(zim_path, ARTICLE)
    if result is None:
        sys.exit(1)
    title, html = result

    images = parse_img_tags(html)
    print(f"\n{'='*70}")
    print(f"Artikel: {title}")
    print(f"HTML-Länge: {len(html)} Zeichen")
    print(f"Bilder im HTML: {len(images)}")
    print(f"{'='*70}\n")

    for i, img in enumerate(images, 1):
        src = img['src']
        # Lizenzinfo ermitteln — probiere mit und ohne _assets_/ Prefix
        lic_info = licenses.get(src) or licenses.get(f'_assets_/{Path(src).name}')

        if lic_info:
            allowed  = lic_info.get('allowed', '?')
            license_ = lic_info.get('license') or '(kein Eintrag)'
            author   = lic_info.get('author') or '—'
            commons  = lic_info.get('commons_file') or '—'
            lic_str  = f"{'✓ ERLAUBT' if allowed else '✗ GESPERRT'}  Lizenz: {license_}  Autor: {author}"
        else:
            lic_str  = '? NICHT IN LIZENZDATEI'
            commons  = '—'

        dim = ''
        if img['width'] and img['height']:
            dim = f"{img['width']}×{img['height']}px"
        elif img['width']:
            dim = f"w={img['width']}px"
        elif img['height']:
            dim = f"h={img['height']}px"
        else:
            dim = '(keine Dimensionen im HTML)'

        print(f"[{i:02d}] {Path(src).name}")
        print(f"      src:      {src}")
        print(f"      Größe:    {dim}")
        print(f"      alt:      {img['alt']!r}")
        print(f"      Lizenz:   {lic_str}")
        if commons != '—':
            print(f"      Commons:  {commons}")
        print()


if __name__ == '__main__':
    main()
