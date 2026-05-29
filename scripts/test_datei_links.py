#!/usr/bin/env python3
"""
test_datei_links.py — Prüft ob ZIM-HTML <a href="/wiki/Datei:..."><img> enthält.

Wenn ja: MD5-Hash → Original-Commons-Dateiname direkt aus ZIM extrahierbar.
Kein API-Aufruf nötig!

Ausgabe pro Artikel:
  - Jedes Bild: src-Hash | href-Dateiname | gefunden/nicht gefunden
  - Zusammenfassung: mit_link / ohne_link
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

ZIM_FILE    = os.environ.get("ZIM_FILE", "klexikon.zim")
ZIM_MAGIC   = 0x044D495A

TEST_TITLES = ["Fußball", "Berlin", "Ameisen", "Dinosaurier", "Löwe"]


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


def load_zim_articles(zim_path: Path, wanted: set[str]) -> dict[str, str]:
    """Lädt HTML für alle Titel in `wanted`. Gibt {title: html} zurück."""
    norm_wanted = {" ".join(t.strip().replace("_", " ").lower().split()): t for t in wanted}
    results: dict[str, str] = {}

    with open(zim_path, "rb") as f:
        hdr = f.read(80)
        magic, = struct.unpack_from("<I", hdr, 0)
        if magic != ZIM_MAGIC:
            print("ERROR: kein ZIM-File"); sys.exit(1)

        ec,  = struct.unpack_from("<I", hdr, 24)
        cc,  = struct.unpack_from("<I", hdr, 28)
        up,  = struct.unpack_from("<Q", hdr, 32)
        cpp, = struct.unpack_from("<Q", hdr, 48)
        mlp, = struct.unpack_from("<Q", hdr, 56)
        eof, = struct.unpack_from("<Q", hdr, 72)

        # MIME
        f.seek(mlp)
        mimes = []
        while True:
            mt = _read_cstr(f)
            if not mt: break
            mimes.append(mt)
        html_idx = {i for i, m in enumerate(mimes) if "html" in m.lower()}

        # Cluster-Pointer
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
            if norm in norm_wanted and norm_wanted[norm] not in results:
                blob = read_blob(cn, bn)
                if blob:
                    results[norm_wanted[norm]] = blob.decode("utf-8", errors="replace")

    return results


def analyze_article(title: str, html: str) -> dict:
    """
    Sucht in HTML nach Mustern:
      A) <a href="...Datei:...|...File:..."><img src="...">  (Link vorhanden)
      B) <img src="..."> ohne umschließenden Datei:-Link      (kein Link)
    """
    # Alle <a href="...Datei:.../File:..."><img...> Paare
    # Regex: <a ...href="([^"]*(?:Datei|File):[^"]*)"...>...<img ..src="([^"]+)"
    linked = re.findall(
        r'<a[^>]+href="([^"]*(?:Datei|File):[^"]*)"[^>]*>\s*(?:<[^i/][^>]*>\s*)*<img[^>]+src="([^"]+)"',
        html, re.IGNORECASE
    )

    # Alle <img src="..."> im Dokument
    all_imgs = re.findall(r'<img[^>]+src="([^"]+)"', html, re.IGNORECASE)

    # Hashes der verlinkten Bilder
    linked_srcs = {src for _, src in linked}

    with_link    = []
    without_link = []

    for src in all_imgs:
        # Nur Bilder mit Hash-ähnlichem Pfad (kein UI-Icons)
        if not any(c.isalpha() for c in src.split("/")[-1].split(".")[0]):
            continue  # rein numerisch/kurz → Skip
        hash_part = src.split("/")[-1]  # z.B. "00977868...jpg" oder "m/00977868...jpg"
        if src in linked_srcs:
            # Finde zugehörigen href
            for href, s in linked:
                if s == src:
                    datei_name = href.split("Datei:")[-1].split("File:")[-1].strip("/")
                    with_link.append({"hash": hash_part, "datei": datei_name, "href": href})
                    break
        else:
            without_link.append({"hash": hash_part, "src": src})

    return {
        "title":        title,
        "with_link":    with_link,
        "without_link": without_link,
    }


def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: {zim_path} nicht gefunden"); sys.exit(1)

    print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    print(f"Test-Artikel: {TEST_TITLES}")
    print()

    articles = load_zim_articles(zim_path, set(TEST_TITLES))
    print(f"Geladen: {list(articles.keys())}")
    print()

    total_with    = 0
    total_without = 0

    for title in TEST_TITLES:
        if title not in articles:
            print(f"{'='*60}")
            print(f"⚠️  '{title}' NICHT IN ZIM GEFUNDEN")
            continue

        html   = articles[title]
        result = analyze_article(title, html)

        print(f"{'='*60}")
        print(f"Artikel: {title}")
        print(f"  mit Datei:-Link:    {len(result['with_link'])}")
        print(f"  ohne Datei:-Link:   {len(result['without_link'])}")

        if result["with_link"]:
            print(f"\n  ✓ Bilder MIT Link (alle):")
            for img in result["with_link"]:
                print(f"    hash: {img['hash']:40s}  →  {img['datei']}")
        else:
            print("  ✗ KEIN einziges Bild mit Datei:-Link gefunden!")

        if result["without_link"]:
            print(f"\n  ✗ Bilder OHNE Link ({len(result['without_link'])}):")
            for img in result["without_link"][:5]:
                print(f"    hash: {img['hash']}")
            if len(result["without_link"]) > 5:
                print(f"    … +{len(result['without_link'])-5} weitere")

        # Roher HTML-Schnipsel zum Debugging: erstes Bild
        first_img_ctx = ""
        m = re.search(r'.{0,200}<img[^>]+src="[^"]+"[^>]*/>.{0,200}', html, re.DOTALL)
        if m:
            snippet = m.group(0).replace("\n", " ")[:300]
            print(f"\n  HTML-Schnipsel (erstes img):")
            print(f"    {snippet}")

        total_with    += len(result["with_link"])
        total_without += len(result["without_link"])
        print()

    print(f"{'='*60}")
    print(f"GESAMT über {len(articles)} Artikel:")
    print(f"  MIT  Datei:-Link: {total_with}")
    print(f"  OHNE Datei:-Link: {total_without}")
    if total_with + total_without > 0:
        pct = 100 * total_with // (total_with + total_without)
        print(f"  Abdeckung:        {pct}%")
        if pct >= 80:
            print()
            print("✓ Datei:-Links vorhanden → Offline-Mapping möglich!")
            print("  Nächster Schritt: build_image_map_offline.py ohne API-Calls")
        elif pct > 0:
            print()
            print(f"⚠️  Nur {pct}% haben Links → Hybrid-Ansatz nötig")
        else:
            print()
            print("✗ Keine Links → API-Matching bleibt notwendig")


if __name__ == "__main__":
    main()
