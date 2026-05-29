#!/usr/bin/env python3
"""
read_zim_metadata.py — Liest alle Metadaten aus einer ZIM-Datei.

Gibt aus:
  - Dateiname + Größe + MD5/SHA256
  - ZIM-Version (major.minor)
  - Alle M-Namespace-Einträge: Date, Title, Language, Creator, Publisher, …
  - Anzahl HTML-Artikel (tatsächliche Inhaltsartikel)
  - MIME-Typ-Liste

Usage: ZIM_FILE=klexikon.zim python scripts/read_zim_metadata.py
"""

import hashlib
import lzma
import os
import struct
import sys
from pathlib import Path

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

ZIM_FILE  = os.environ.get("ZIM_FILE", "klexikon.zim")
ZIM_MAGIC = 0x044D495A


def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        buf.extend(b)
    return buf.decode('utf-8', errors='replace')


def _decompress(data: bytes, comp: int) -> bytes | None:
    try:
        if comp in (0, 1): return data
        if comp == 4:      return lzma.decompress(data)
        if comp in (5, 8):
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=4 << 20) if HAS_ZSTD else None
        if comp == 6:      return lzma.decompress(data)
    except Exception:
        pass
    return None


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: not found: {zim_path}"); sys.exit(1)

    size = zim_path.stat().st_size
    print(f"File:    {zim_path.resolve()}")
    print(f"Size:    {size:,} bytes  ({size / 1_048_576:.1f} MB)")

    # Checksums
    md5  = hashlib.md5()
    sha1 = hashlib.sha1()
    with open(zim_path, 'rb') as f:
        while chunk := f.read(1 << 20):
            md5.update(chunk); sha1.update(chunk)
    print(f"MD5:     {md5.hexdigest()}")
    print(f"SHA1:    {sha1.hexdigest()}")
    print()

    with open(zim_path, 'rb') as f:
        hdr = f.read(80)
        if len(hdr) < 80:
            print("ERROR: file too small"); sys.exit(1)

        magic, = struct.unpack_from('<I', hdr, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: not a ZIM file (magic={hex(magic)})"); sys.exit(1)

        major, minor = struct.unpack_from('<HH', hdr, 4)
        ec, cc       = struct.unpack_from('<II', hdr, 24)
        up,          = struct.unpack_from('<Q',  hdr, 32)
        cpp,         = struct.unpack_from('<Q',  hdr, 48)
        mlp,         = struct.unpack_from('<Q',  hdr, 56)
        eof,         = struct.unpack_from('<Q',  hdr, 72)

        print(f"ZIM version:   {major}.{minor}")
        print(f"Total entries: {ec}")
        print(f"Clusters:      {cc}")
        print()

        # MIME types
        f.seek(mlp)
        mimes: list[str] = []
        while True:
            mt = _read_cstr(f)
            if not mt: break
            mimes.append(mt)
        html_idxs = {i for i, m in enumerate(mimes) if 'html' in m.lower()}

        print("MIME types:")
        for i, m in enumerate(mimes):
            print(f"  [{i}] {m}")
        print()

        # Cluster pointers
        f.seek(cpp)
        ptrs: list[int] = []
        for _ in range(cc):
            r = f.read(8)
            if len(r) < 8: break
            ptrs.append(struct.unpack_from('<Q', r)[0])

        def read_blob(cn: int, bn: int) -> bytes | None:
            if cn >= len(ptrs): return None
            start = ptrs[cn]
            end   = ptrs[cn + 1] if cn + 1 < len(ptrs) else eof
            f.seek(start)
            b   = struct.unpack('B', f.read(1))[0]
            raw = f.read(end - start - 1)
            data = _decompress(raw, b & 0x0f)
            if not data: return None
            ext = bool(b & 0x10)
            sz  = 8 if ext else 4
            fmt = '<Q' if ext else '<I'
            if len(data) < sz: return None
            base, = struct.unpack_from(fmt, data, 0)
            nb = base // sz - 1
            if bn >= nb or (bn + 2) * sz > len(data): return None
            a,  = struct.unpack_from(fmt, data, bn * sz)
            b2, = struct.unpack_from(fmt, data, (bn + 1) * sz)
            return data[a:b2] if a <= b2 <= len(data) else None

        # Scan all entries: collect M-namespace (metadata) + count HTML
        metadata:    dict[str, str] = {}
        html_count   = 0
        ns_counts:   dict[str, int] = {}

        for i in range(ec):
            f.seek(up + i * 8)
            r = f.read(8)
            if len(r) < 8: break
            ptr, = struct.unpack_from('<Q', r)
            f.seek(ptr)
            h = f.read(4)
            if len(h) < 4: continue
            mi, _, ns_b = struct.unpack_from('<HBc', h)
            ns = ns_b.decode('ascii', errors='?')
            ns_counts[ns] = ns_counts.get(ns, 0) + 1

            if mi != 0xffff and mi in html_idxs:
                html_count += 1

            if ns == 'M' and mi != 0xffff:
                f.read(4)  # reserved
                cn, bn = struct.unpack('<II', f.read(8))
                key    = _read_cstr(f)
                _read_cstr(f)  # title (usually empty)
                blob = read_blob(cn, bn)
                if blob:
                    try:
                        metadata[key] = blob.decode('utf-8', errors='replace').strip()
                    except Exception:
                        metadata[key] = repr(blob[:80])

        # Print metadata
        print("=== ZIM Metadata (M namespace) ===")
        priority = ['Date', 'Title', 'Language', 'Creator', 'Publisher',
                    'Description', 'LongDescription', 'Name', 'Tags',
                    'Scraper', 'Source', 'Counter']
        printed = set()
        for key in priority:
            if key in metadata:
                v = metadata[key]
                print(f"  {key}: {v!r}" if len(v) < 120 else f"  {key}: {v[:117]!r}…")
                printed.add(key)
        for key, val in sorted(metadata.items()):
            if key not in printed:
                v = val
                print(f"  {key}: {v!r}" if len(v) < 120 else f"  {key}: {v[:117]!r}…")

        if not metadata:
            print("  (no metadata found)")

        print()
        print("=== Entry namespace breakdown ===")
        for ns, cnt in sorted(ns_counts.items()):
            print(f"  '{ns}': {cnt}")

        print()
        print(f"=== Article count ===")
        print(f"  HTML articles (text/html MIME):  {html_count}")


if __name__ == '__main__':
    main()
