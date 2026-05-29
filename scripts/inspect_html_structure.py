#!/usr/bin/env python3
"""
inspect_html_structure.py — Zeigt die exakte HTML-Struktur rund um <img>-Tags
für Artikel mit ZIM-count=0 (figure + thumbinner greifen nicht).

Ausgabe:
  - Alle <img>-Tags mit je 300 Zeichen Kontext (Eltern-Tags, CSS-Klassen)
  - Regex-Treffer aller bekannten Container
  - Fix-Empfehlung

Usage: ZIM_FILE=klexikon.zim TARGETS="Aachen,Afrika,Amsterdam" python inspect_html_structure.py
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

ZIM_FILE = os.environ.get("ZIM_FILE", "klexikon.zim")
TARGETS  = [t.strip() for t in os.environ.get("TARGETS", "Aachen,Afrika,Amsterdam").split(",")]
ZIM_MAGIC = 0x044D495A


def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b"\x00":
            break
        buf.extend(b)
    return buf.decode("utf-8", errors="replace")


def _decompress(data: bytes, comp: int) -> bytes | None:
    try:
        if comp in (0, 1): return data
        if comp == 4:      return lzma.decompress(data)
        if comp in (5, 8):
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=32 << 20) if HAS_ZSTD else None
        if comp == 6:      return lzma.decompress(data)
    except Exception:
        pass
    return None


def load_articles(zim_path: Path, wanted: set[str]) -> dict[str, str]:
    norm_map = {" ".join(t.strip().replace("_", " ").lower().split()): t for t in wanted}
    results: dict[str, str] = {}

    with open(zim_path, "rb") as f:
        hdr = f.read(80)
        magic, = struct.unpack_from("<I", hdr, 0)
        if magic != ZIM_MAGIC:
            print("ERROR: kein ZIM"); sys.exit(1)

        ec,  = struct.unpack_from("<I", hdr, 24)
        cc,  = struct.unpack_from("<I", hdr, 28)
        up,  = struct.unpack_from("<Q", hdr, 32)
        cpp, = struct.unpack_from("<Q", hdr, 48)
        mlp, = struct.unpack_from("<Q", hdr, 56)
        eof, = struct.unpack_from("<Q", hdr, 72)

        f.seek(mlp)
        mimes = []
        while True:
            mt = _read_cstr(f)
            if not mt: break
            mimes.append(mt)
        html_idx = {i for i, m in enumerate(mimes) if "html" in m.lower()}

        f.seek(cpp)
        cluster_ptrs = []
        for _ in range(cc):
            r = f.read(8)
            if len(r) < 8: break
            cluster_ptrs.append(struct.unpack_from("<Q", r)[0])

        def read_blob(cn, bn):
            if cn >= len(cluster_ptrs): return None
            start = cluster_ptrs[cn]
            end   = cluster_ptrs[cn + 1] if cn + 1 < len(cluster_ptrs) else eof
            f.seek(start)
            b   = struct.unpack("B", f.read(1))[0]
            raw = f.read(end - start - 1)
            data = _decompress(raw, b & 0x0F)
            if not data: return None
            ext = bool(b & 0x10)
            sz  = 8 if ext else 4
            fmt = "<Q" if ext else "<I"
            if len(data) < sz: return None
            base, = struct.unpack_from(fmt, data, 0)
            nb = base // sz - 1
            if bn >= nb or (bn + 2) * sz > len(data): return None
            a,  = struct.unpack_from(fmt, data, bn * sz)
            b2, = struct.unpack_from(fmt, data, (bn + 1) * sz)
            return data[a:b2] if a <= b2 <= len(data) else None

        for i in range(ec):
            if len(results) == len(wanted): break
            f.seek(up + i * 8)
            r = f.read(8)
            if len(r) < 8: break
            ptr, = struct.unpack_from("<Q", r)
            f.seek(ptr)
            h = f.read(4)
            if len(h) < 4: continue
            mi, _, ns_b = struct.unpack_from("<HBc", h)
            if mi == 0xFFFF or mi not in html_idx: continue
            f.read(4)
            cn, bn = struct.unpack("<II", f.read(8))
            url    = _read_cstr(f)
            title  = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit("/", 1)[-1]
            norm = " ".join(title.strip().replace("_", " ").lower().split())
            if norm in norm_map and norm_map[norm] not in results:
                blob = read_blob(cn, bn)
                if blob:
                    results[norm_map[norm]] = blob.decode("utf-8", errors="replace")
    return results


def analyze(title: str, html: str):
    print(f"\n{'='*70}")
    print(f"ARTIKEL: {title}  ({len(html):,} Zeichen)")
    print(f"{'='*70}")

    # Alle <img>-Tags finden
    img_positions = [(m.start(), m.group(0)) for m in re.finditer(r'<img[^>]+>', html, re.IGNORECASE)]
    print(f"\nGefundene <img>-Tags: {len(img_positions)}")

    if not img_positions:
        print("  KEIN <img>-Tag im Artikel!")
        return

    # Für jedes img: 400 Zeichen Kontext davor zeigen
    for idx, (pos, tag) in enumerate(img_positions[:8]):
        src_m = re.search(r'src="([^"]+)"', tag)
        src = src_m.group(1)[-50:] if src_m else "?"
        print(f"\n  --- img #{idx+1} (src=…{src}) ---")

        # Kontext: 400 Zeichen davor
        ctx_before = html[max(0, pos-400):pos]
        ctx_after  = html[pos:pos+200]

        # Zeige öffnende Tags mit class/id-Attributen im Kontext
        tags_in_ctx = re.findall(r'<(?!/)(\w+)[^>]*(?:class|id)="[^"]*"[^>]*>', ctx_before, re.IGNORECASE)
        if tags_in_ctx:
            print(f"  Eltern-Tags mit class/id (letzten 400Z):")
            for t in tags_in_ctx[-5:]:
                # Kürze auf 120 Zeichen
                print(f"    {t[:120]}")

        # Zeige rohen Kontext (letzten 300 Zeichen vor img, bereinigt)
        ctx_clean = re.sub(r'\s+', ' ', ctx_before[-300:])
        print(f"  Kontext vor img: …{ctx_clean[-200:]!r}")

    # Zähle Treffer der verschiedenen Selektoren
    print(f"\n  SELEKTOR-CHECK:")
    figures        = re.findall(r'<figure[^>]*>.*?</figure>',           html, re.DOTALL | re.IGNORECASE)
    thumbinner     = re.findall(r'class=["\'][^"\']*thumbinner[^"\']*["\']',  html, re.IGNORECASE)
    thumb_divs     = re.findall(r'<div[^>]+class=["\'][^"\']*thumb[^"\']*["\'][^>]*>', html, re.IGNORECASE)
    gallery_boxes  = re.findall(r'<li[^>]+class=["\'][^"\']*gallerybox[^"\']*["\']',   html, re.IGNORECASE)
    image_divs     = re.findall(r'<div[^>]+class=["\'][^"\']*image[^"\']*["\'][^>]*>', html, re.IGNORECASE)
    imgs_with_src  = re.findall(r'<img[^>]+src="[^"]+"[^>]*/?>',        html, re.IGNORECASE)

    print(f"    <figure>:               {len(figures)}")
    print(f"    class=*thumbinner*:     {len(thumbinner)}")
    print(f"    <div class=*thumb*>:    {len(thumb_divs)}")
    print(f"    <li class=*gallerybox*: {len(gallery_boxes)}")
    print(f"    <div class=*image*>:    {len(image_divs)}")
    print(f"    <img src=...> gesamt:   {len(imgs_with_src)}")

    # Zeige alle class-Werte rund um img-Tags
    all_classes = set()
    for pos, _ in img_positions:
        ctx = html[max(0, pos-500):pos]
        for cls in re.findall(r'class="([^"]+)"', ctx):
            all_classes.update(cls.split())
    print(f"\n  CSS-Klassen im Umfeld aller img-Tags:")
    for cls in sorted(all_classes):
        print(f"    .{cls}")


def count_with_selector(html: str, selector: str) -> int:
    """Testet verschiedene kombinierte Selektoren."""
    if selector == "figure":
        figs = re.findall(r'<figure[^>]*>.*?</figure>', html, re.DOTALL | re.IGNORECASE)
        return sum(1 for f in figs if '<img' in f.lower())
    if selector == "thumb":
        # Alle .thumb-Container mit img
        thumbs = re.findall(r'<div[^>]+class="[^"]*\bthumb\b[^"]*"[^>]*>.*?</div>\s*</div>', html, re.DOTALL | re.IGNORECASE)
        return sum(1 for t in thumbs if '<img' in t.lower())
    if selector == "gallery":
        boxes = re.findall(r'<li[^>]+class="[^"]*\bgallerybox\b[^"]*"[^>]*>.*?</li>', html, re.DOTALL | re.IGNORECASE)
        return sum(1 for b in boxes if '<img' in b.lower())
    if selector == "all_img":
        # Rohe img-Zählung (ohne Filter)
        return len(re.findall(r'<img[^>]+src="[^A-Za-z][^"]*"', html, re.IGNORECASE))
    return 0


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: {zim_path} nicht gefunden"); sys.exit(1)

    print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    print(f"Ziel-Artikel: {TARGETS}")

    articles = load_articles(zim_path, set(TARGETS))
    print(f"\nGeladen: {list(articles.keys())}")

    for title in TARGETS:
        if title not in articles:
            print(f"\n⚠️  '{title}' NICHT IN ZIM GEFUNDEN")
            continue
        analyze(title, articles[title])

    # Zusammenfassung: welcher Selektor deckt am meisten ab?
    print(f"\n{'='*70}")
    print("SELEKTOR-VERGLEICH über alle geladenen Artikel:")
    print(f"{'='*70}")
    for selector in ("figure", "thumb", "gallery", "all_img"):
        counts = [count_with_selector(html, selector) for html in articles.values()]
        zero = sum(1 for c in counts if c == 0)
        print(f"  {selector:12s}: Ø={sum(counts)/max(len(counts),1):.1f}  zero={zero}/{len(counts)}")


if __name__ == "__main__":
    main()
