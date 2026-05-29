#!/usr/bin/env python3
"""
dry_run_image_count.py — Vergleicht ZIM-Bildanzahl vs. API-Bildanzahl.
KEIN Commons-Download.

Input:  title_map.json (aus build_title_map.py)
Output: dry_run_report.json

  count_match:          ZIM-count == API-count (gefiltert)
  count_mismatch_zim_more: ZIM > API (Bilder entfernt seit ZIM-Build)
  count_mismatch_api_more: ZIM < API (Bilder hinzugekommen seit ZIM-Build)
  api_no_images:        API liefert 0 Bilder (nach Filter)

ZIM-Zählung:  <figure>-Elemente mit <img>; Fallback: .thumbinner-Divs
API-Zählung:  prop=images, gefiltert (kein SVG, keine Logos/Icons)
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

try:
    import requests as _requests
    _session = _requests.Session()
    _session.headers["User-Agent"] = "WissensfreundBot/1.0 (dry-run-image-count)"
    HAS_REQUESTS = True
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

ZIM_FILE       = os.environ.get("ZIM_FILE", "klexikon.zim")
TITLE_MAP_FILE = os.environ.get("TITLE_MAP_FILE", "title_map.json")
OUTPUT_FILE    = Path(os.environ.get("OUTPUT_FILE", "dry_run_report.json"))
API_DELAY      = float(os.environ.get("API_DELAY", "0.3"))
MAX_ARTICLES   = int(os.environ.get("MAX_ARTICLES", "0"))   # 0 = alle

KLEXIKON_API = "https://klexikon.zum.de/api.php"
ZIM_MAGIC    = 0x044D495A

FILTER_PREFIXES = (
    "commons-logo", "wikimedia", "cc-", "pd-", "gfdl",
    "question_book", "ambox", "portal-", "wikidata-",
    "symbol_", "icon_", "semiprotect", "edit-clear",
    "nuvola", "gnome-", "crystal_", "tango-",
)


def _should_filter(raw_title: str) -> bool:
    """True wenn das Bild herausgefiltert werden soll."""
    name = raw_title.lower().split(":")[-1].strip()  # "Datei:Foo.jpg" → "foo.jpg"
    if name.endswith(".svg"):
        return True
    for prefix in FILTER_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


# ── ZIM binary helpers ────────────────────────────────────────────────────────

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
        if comp in (0, 1):
            return data
        if comp == 4:
            return lzma.decompress(data)
        if comp in (5, 8):
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=32 << 20) if HAS_ZSTD else None
        if comp == 6:
            return lzma.decompress(data)
    except Exception:
        pass
    return None


def build_zim_index(zim_path: Path) -> tuple[dict, list, int]:
    """
    Scannt alle HTML-Artikel und gibt zurück:
      title_index: {norm_title → (orig_title, cluster_num, blob_num)}
      cluster_ptrs: list[int]
      eof: int
    """
    title_index: dict[str, tuple] = {}
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

        # MIME-Typen
        f.seek(mlp)
        mimes: list[str] = []
        while True:
            mt = _read_cstr(f)
            if not mt:
                break
            mimes.append(mt)
        html_idx = {i for i, m in enumerate(mimes) if "html" in m.lower()}

        # Cluster-Pointer
        f.seek(cpp)
        cluster_ptrs: list[int] = []
        for _ in range(cc):
            r = f.read(8)
            if len(r) < 8:
                break
            cluster_ptrs.append(struct.unpack_from("<Q", r)[0])

        # Einträge scannen
        for i in range(ec):
            f.seek(up + i * 8)
            r = f.read(8)
            if len(r) < 8:
                break
            ptr, = struct.unpack_from("<Q", r)
            f.seek(ptr)
            h = f.read(4)
            if len(h) < 4:
                continue
            mi, _, ns_b = struct.unpack_from("<HBc", h)
            if mi == 0xFFFF or mi not in html_idx:
                continue
            f.read(4)   # revision
            cn, bn = struct.unpack("<II", f.read(8))
            url    = _read_cstr(f)
            title  = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit("/", 1)[-1]
            norm = " ".join(title.strip().replace("_", " ").lower().split())
            if norm:
                title_index[norm] = (title, cn, bn)

    return title_index, cluster_ptrs, eof


def read_blob(f, cluster_ptrs: list, eof: int, cn: int, bn: int) -> bytes | None:
    if cn >= len(cluster_ptrs):
        return None
    start = cluster_ptrs[cn]
    end   = cluster_ptrs[cn + 1] if cn + 1 < len(cluster_ptrs) else eof
    f.seek(start)
    b   = struct.unpack("B", f.read(1))[0]
    raw = f.read(end - start - 1)
    data = _decompress(raw, b & 0x0F)
    if not data:
        return None
    ext = bool(b & 0x10)
    sz  = 8 if ext else 4
    fmt = "<Q" if ext else "<I"
    if len(data) < sz:
        return None
    base, = struct.unpack_from(fmt, data, 0)
    nb = base // sz - 1
    if bn >= nb or (bn + 2) * sz > len(data):
        return None
    a,  = struct.unpack_from(fmt, data, bn * sz)
    b2, = struct.unpack_from(fmt, data, (bn + 1) * sz)
    return data[a:b2] if a <= b2 <= len(data) else None


# ── Image-Zähler ─────────────────────────────────────────────────────────────

def count_zim_images(html: str) -> int:
    """
    Zählt Artikel-Bilder im ZIM-HTML über alle drei Klexikon-Container:
      1. <figure> … </figure>          (modernes MediaWiki)
      2. <div class="thumbinner">       (schwimmende Einzelbilder)
      3. <li class="gallerybox"> … </li>(MediaWiki-Galerie)
    Alle drei werden ADDIERT (kein Fallback-Muster mehr).
    """
    n = 0

    # 1. <figure> (modernes MediaWiki)
    for m in re.finditer(r"<figure[^>]*>.*?</figure>", html, re.DOTALL | re.IGNORECASE):
        if "<img" in m.group(0).lower():
            n += 1

    # 2. <div class="thumbinner"> — Wortgrenze, damit "notthumbinner" nicht matcht
    for m in re.finditer(
        r'<div[^>]+class=["\'][^"\']*\bthumbinner\b[^"\']*["\'][^>]*>.*?</div>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        if "<img" in m.group(0).lower():
            n += 1

    # 3. <li class="gallerybox"> — eine <li> = ein Galerie-Bild
    for m in re.finditer(
        r'<li[^>]+class=["\'][^"\']*\bgallerybox\b[^"\']*["\'][^>]*>.*?</li>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        if "<img" in m.group(0).lower():
            n += 1

    return n


def count_parse_images(api_title: str) -> int | None:
    """
    Zählt gerenderte Bilder via action=parse&prop=images.
    Gibt Bilder in Erscheinungsreihenfolge zurück (nicht alphabetisch wie prop=images),
    vergleichbar mit der ZIM-Renderung.
    Boilerplate-Icons/Logos werden herausgefiltert.
    """
    try:
        r = _session.get(KLEXIKON_API, params={
            "action": "parse",
            "page":   api_title,
            "prop":   "images",
            "format": "json",
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        images = data.get("parse", {}).get("images", [])
        # images sind reine Dateinamen ohne Namespace-Präfix
        filtered = [fn for fn in images if not _should_filter("Datei:" + fn)]
        return len(filtered)
    except Exception as e:
        print(f"  parse-API-Fehler '{api_title}': {e}", file=sys.stderr)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    title_map = json.loads(Path(TITLE_MAP_FILE).read_text(encoding="utf-8"))
    lookup: dict[str, str] = title_map["lookup"]   # {zim_title → api_title}

    items = list(lookup.items())
    if MAX_ARTICLES > 0:
        items = items[:MAX_ARTICLES]
    total = len(items)
    print(f"Zu verarbeitende Artikel: {total}")

    # ZIM-Index aufbauen
    zim_path = Path(ZIM_FILE)
    print(f"Baue ZIM-Index aus {zim_path} …")
    title_index, cluster_ptrs, eof = build_zim_index(zim_path)
    print(f"  ZIM-Index: {len(title_index)} Einträge")
    print()

    count_match:           list[dict] = []
    mismatch_zim_more:     list[dict] = []
    mismatch_api_more:     list[dict] = []
    api_no_images:         list[dict] = []
    zim_not_found:         list[str]  = []
    api_errors:            list[str]  = []

    with open(zim_path, "rb") as f:
        for idx, (zim_title, api_title) in enumerate(items):
            if idx % 200 == 0:
                print(f"  [{idx:4d}/{total}] {zim_title!r}")

            # ZIM-Bild zählen
            norm  = " ".join(zim_title.strip().replace("_", " ").lower().split())
            entry = title_index.get(norm)
            if not entry:
                zim_not_found.append(zim_title)
                continue
            _, cn, bn = entry
            blob = read_blob(f, cluster_ptrs, eof, cn, bn)
            if not blob:
                zim_not_found.append(zim_title)
                continue
            html      = blob.decode("utf-8", errors="replace")
            zim_count = count_zim_images(html)

            # API-Bild zählen (action=parse — gerenderte Bilder in Erscheinungsreihenfolge)
            time.sleep(API_DELAY)
            api_count = count_parse_images(api_title)
            if api_count is None:
                api_errors.append(api_title)
                continue

            rec = {"zim": zim_title, "api": api_title,
                   "zim_count": zim_count, "api_count": api_count}

            if api_count == 0:
                api_no_images.append(rec)
            elif zim_count == api_count:
                count_match.append(rec)
            elif zim_count > api_count:
                mismatch_zim_more.append({**rec, "delta": zim_count - api_count})
            else:
                mismatch_api_more.append({**rec, "delta": api_count - zim_count})

    # ── Report ────────────────────────────────────────────────────────────────
    summary = {
        "total_processed":    total,
        "count_match":        len(count_match),
        "count_mismatch":     len(mismatch_zim_more) + len(mismatch_api_more),
        "mismatch_zim_more":  len(mismatch_zim_more),
        "mismatch_api_more":  len(mismatch_api_more),
        "api_no_images":      len(api_no_images),
        "zim_not_found":      len(zim_not_found),
        "api_errors":         len(api_errors),
    }

    # Plausibilitätscheck
    warnings: list[str] = []
    min_match = total // 2   # ≥50% der verarbeiteten Artikel müssen übereinstimmen
    if summary["count_match"] < min_match:
        warnings.append(
            f"⚠️ NICHT VERIFIZIERT: count_match={summary['count_match']}"
            f" < 50% ({min_match}) von {total} verarbeiteten Artikeln"
        )
    if summary["api_no_images"] >= 200:
        warnings.append(f"⚠️ NICHT VERIFIZIERT: api_no_images={summary['api_no_images']} ≥ 200")

    report = {
        "summary":              summary,
        "plausibility_warnings": warnings,
        # Samples (volle Listen wären zu groß)
        "count_match_sample":         count_match[:30],
        "mismatch_zim_more":          mismatch_zim_more,   # vollständig
        "mismatch_api_more":          mismatch_api_more,   # vollständig
        "api_no_images":              api_no_images,       # vollständig
        "zim_not_found":              zim_not_found,
        "api_errors":                 api_errors,
    }
    OUTPUT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nGespeichert → {OUTPUT_FILE}")

    # Konsolen-Summary
    print(f"\n{'='*60}")
    print(f"Verarbeitet:         {total}")
    print(f"count_match:         {summary['count_match']}")
    print(f"count_mismatch:      {summary['count_mismatch']}")
    print(f"  ZIM > API:         {summary['mismatch_zim_more']}  ← Bilder entfernt")
    print(f"  ZIM < API:         {summary['mismatch_api_more']}  ← Bilder hinzugekommen")
    print(f"api_no_images:       {summary['api_no_images']}")
    print(f"zim_not_found:       {summary['zim_not_found']}")
    print(f"api_errors:          {summary['api_errors']}")
    if warnings:
        print()
        for w in warnings:
            print(w)
        sys.exit(1)   # Workflow schlägt fehl → manuell prüfen


if __name__ == "__main__":
    main()
