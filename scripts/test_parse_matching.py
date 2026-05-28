#!/usr/bin/env python3
"""
test_parse_matching.py — Vergleich ZIM-Bilder vs. action=parse für 5 Artikel.

Pro Artikel:
  1. ZIM-HTML → Bilder mit Index + figcaption/alt
  2. Klexikon action=parse → Bilder mit Index + Dateiname
  3. Positional-Match (Index) + Caption-Bestätigung (difflib)

Output: parse_matching_test.json + detailliertes stdout-Protokoll

Umgebungsvariablen:
  ZIM_FILE       (default: klexikon.zim)
  OUTPUT_FILE    (default: parse_matching_test.json)
  TEST_ARTICLES  kommagetrennt (default: Elefant,Beethoven,Berlin,Fußball,Dinosaurier)
  API_DELAY      (default: 0.5)
  CAPTION_THRESHOLD  difflib-Schwellwert für Bestätigung (default: 0.25)
"""

import difflib
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
    _session.headers["User-Agent"] = "WissensfreundBot/1.0 (parse-matching-test)"
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

ZIM_FILE    = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "parse_matching_test.json"))
API_DELAY   = float(os.environ.get("API_DELAY", "0.5"))
CAPTION_THRESHOLD = float(os.environ.get("CAPTION_THRESHOLD", "0.25"))
TEST_ARTICLES = [t.strip() for t in
    os.environ.get("TEST_ARTICLES", "Elefant,Beethoven,Berlin,Fußball,Dinosaurier").split(",")
    if t.strip()]

KLEXIKON_API = "https://klexikon.zum.de/api.php"
ZIM_MAGIC    = 0x044d495a

# ── ZIM binary helpers ────────────────────────────────────────────────────────

def _read_cstr(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        buf.extend(b)
    return buf.decode('utf-8', errors='replace')


def _read_mime_list(f, pos):
    f.seek(pos)
    types = []
    while True:
        mt = _read_cstr(f)
        if not mt:
            break
        types.append(mt)
    return types


def _decompress(data, comp):
    try:
        if comp in (0, 1): return data
        if comp == 4:       return lzma.decompress(data)
        if comp in (5, 8):
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=256 << 20) if HAS_ZSTD else None
        if comp == 6:       return lzma.decompress(data)
    except Exception:
        pass
    return None


def _read_cluster(f, ptrs, idx, eof):
    start = ptrs[idx]
    end   = ptrs[idx + 1] if idx + 1 < len(ptrs) else eof
    f.seek(start)
    b   = struct.unpack('B', f.read(1))[0]
    raw = f.read(end - start - 1)
    return _decompress(raw, b & 0x0f), bool(b & 0x10)


def _blob(data, num, ext):
    sz  = 8 if ext else 4
    fmt = '<Q' if ext else '<I'
    if len(data) < sz: return None
    base, = struct.unpack_from(fmt, data, 0)
    nb = base // sz - 1
    if num >= nb or (num + 2) * sz > len(data): return None
    a, = struct.unpack_from(fmt, data, num * sz)
    b, = struct.unpack_from(fmt, data, (num + 1) * sz)
    return data[a:b] if a <= b <= len(data) else None


def load_zim_articles(zim_path: Path, wanted: set[str]) -> dict[str, str]:
    """Return {title: html} for articles whose title is in `wanted`."""
    result = {}
    with open(zim_path, 'rb') as f:
        hdr = f.read(80)
        magic, = struct.unpack_from('<I', hdr, 0)
        if magic != ZIM_MAGIC:
            print("ERROR: not a ZIM file"); sys.exit(1)

        ec,  = struct.unpack_from('<I', hdr, 24)
        cc,  = struct.unpack_from('<I', hdr, 28)
        up,  = struct.unpack_from('<Q', hdr, 32)
        cpp, = struct.unpack_from('<Q', hdr, 48)
        mlp, = struct.unpack_from('<Q', hdr, 56)
        eof, = struct.unpack_from('<Q', hdr, 72)

        mimes = _read_mime_list(f, mlp)
        html_idx = {i for i, m in enumerate(mimes) if 'html' in m.lower()}

        f.seek(cpp)
        ptrs = []
        for _ in range(cc):
            r = f.read(8)
            if len(r) < 8: break
            ptrs.append(struct.unpack_from('<Q', r)[0])

        entries = []
        for i in range(ec):
            f.seek(up + i * 8)
            r = f.read(8)
            if len(r) < 8: break
            ptr, = struct.unpack_from('<Q', r)
            f.seek(ptr)
            h = f.read(4)
            if len(h) < 4: continue
            mi, _, _ = struct.unpack_from('<HBc', h)
            if mi == 0xffff or mi not in html_idx: continue
            f.read(4)
            cn, bn = struct.unpack('<II', f.read(8))
            url   = _read_cstr(f)
            title = _read_cstr(f) or unquote(url).rsplit('/', 1)[-1]
            if title in wanted:
                entries.append((cn, bn, title))

        entries.sort(key=lambda e: (e[0], e[1]))
        cur_ci, cur_data, cur_ext = -1, None, False

        for cn, bn, title in entries:
            if cn != cur_ci:
                cur_ci = cn
                cur_data, cur_ext = _read_cluster(f, ptrs, cn, eof)
            if cur_data is None: continue
            blob = _blob(cur_data, bn, cur_ext)
            if blob:
                try:
                    result[title] = blob.decode('utf-8', errors='replace')
                except Exception:
                    pass

    return result


# ── HTML → image list ─────────────────────────────────────────────────────────

_FULL_IMG_RE = re.compile(r'<img\b[^>]*>', re.I)
_SRC_HASH_RE = re.compile(r'\bsrc="[^"]*_assets_/([^"?#\s<>]+)"', re.I)
_ALT_RE      = re.compile(r'\balt="([^"]*)"', re.I)
_FIGURE_RE   = re.compile(r'<figure\b[^>]*>(.*?)</figure>', re.I | re.DOTALL)
_FIGCAP_RE   = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.I | re.DOTALL)
_THUMB_RE    = re.compile(
    r'class="[^"]*thumbinner[^"]*"[^>]*>(.*?)</div\s*>',
    re.I | re.DOTALL,
)
_THUMBCAP_RE = re.compile(r'class="[^"]*thumbcaption[^"]*"[^>]*>(.*?)</', re.I | re.DOTALL)
_TAG_RE      = re.compile(r'<[^>]+>')


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub('', html).strip()


def zim_images(html: str) -> list[dict]:
    """
    Return [{idx, hash_fn, caption}] in appearance order.
    caption = figcaption text, or thumbcaption, or alt attribute.
    """
    seen: set[str] = set()
    items: list[dict] = []

    def _add(hash_fn, caption, block_html=""):
        if hash_fn in seen:
            return
        seen.add(hash_fn)
        items.append({
            "idx":      len(items),
            "hash_fn":  hash_fn,
            "caption":  caption,
        })

    # 1. <figure> blocks
    for m in _FIGURE_RE.finditer(html):
        inner = m.group(1)
        src = _SRC_HASH_RE.search(inner)
        if not src:
            continue
        hash_fn = unquote(src.group(1))
        cap_m   = _FIGCAP_RE.search(inner)
        caption = _strip_tags(cap_m.group(1)) if cap_m else ""
        if not caption:
            alt_m = _ALT_RE.search(inner)
            caption = unquote(alt_m.group(1)).strip() if alt_m else ""
        _add(hash_fn, caption)

    # 2. .thumbinner divs (older format)
    for m in _THUMB_RE.finditer(html):
        inner = m.group(1)
        src = _SRC_HASH_RE.search(inner)
        if not src:
            continue
        hash_fn = unquote(src.group(1))
        cap_m   = _THUMBCAP_RE.search(inner)
        caption = _strip_tags(cap_m.group(1)) if cap_m else ""
        _add(hash_fn, caption)

    # 3. Remaining bare img tags
    for m in _FULL_IMG_RE.finditer(html):
        tag = m.group(0)
        src = _SRC_HASH_RE.search(tag)
        if not src:
            continue
        hash_fn = unquote(src.group(1))
        alt_m   = _ALT_RE.search(tag)
        alt     = unquote(alt_m.group(1)).strip() if alt_m else ""
        _add(hash_fn, alt)

    return items


# ── Klexikon action=parse ─────────────────────────────────────────────────────

_MW_FILE_RE = re.compile(
    r'href="[^"]*(?:File|Datei):([^"#?&<>\s]+)"',
    re.I,
)
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
# Ignoriere Logos / Lizenzsymbole
_FILTER_PREFIXES = (
    'commons-logo', 'wikimedia', 'cc-', 'pd-', 'gfdl',
    'question', 'ambox', 'portal-', 'miniKlexikon',
    'wikiquote', 'wikibooks', 'wikispecies', 'wikinews',
    'wikivoyage', 'wikidata', 'wikipedia-logo',
)


def _is_content_image(name: str) -> bool:
    if Path(name.lower()).suffix not in _IMAGE_EXTS:
        return False
    nl = name.lower()
    return not any(nl.startswith(p) for p in _FILTER_PREFIXES)


def parse_images(title: str) -> list[dict]:
    """
    Fetch action=parse for title and return [{idx, filename}] in appearance order.
    Filenames are normalized Commons names (no 'Datei:' prefix, spaces→underscore).
    """
    try:
        r = _session.get(KLEXIKON_API, params={
            "action": "parse",
            "page":   title,
            "prop":   "text",
            "format": "json",
        }, timeout=30)
        r.raise_for_status()
        html = r.json().get("parse", {}).get("text", {}).get("*", "")
    except Exception as e:
        print(f"  action=parse error ({title}): {e}", file=sys.stderr)
        return []

    seen: set[str] = set()
    items: list[dict] = []
    for m in _MW_FILE_RE.finditer(html):
        fn = unquote(m.group(1)).replace(' ', '_').rstrip('/')
        if fn in seen or not _is_content_image(fn):
            continue
        seen.add(fn)
        items.append({"idx": len(items), "filename": fn})

    return items


# ── Matching ──────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    text = re.sub(r'\.(jpg|jpeg|png|gif|webp|svg)$', '', text, flags=re.I)
    text = text.replace('_', ' ').replace('-', ' ').lower()
    text = re.sub(r'[^a-z0-9äöüß ]', ' ', text)
    return ' '.join(text.split())


def caption_ratio(caption: str, filename: str) -> float:
    nc = _norm(caption)
    nf = _norm(filename)
    if not nc or not nf:
        return 0.0
    return difflib.SequenceMatcher(None, nc, nf).ratio()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}"); sys.exit(1)

    print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    print(f"Test articles: {TEST_ARTICLES}")
    print(f"Caption confirmation threshold: {CAPTION_THRESHOLD}")
    print()

    # Load ZIM HTML for all target articles
    print("Loading ZIM articles...")
    wanted = set(TEST_ARTICLES)
    zim_html = load_zim_articles(zim_path, wanted)
    found = set(zim_html.keys())
    missing = wanted - found
    if missing:
        print(f"  WARNING: not found in ZIM: {missing}")
        print(f"  (ZIM titles may differ — check with dump_article_html.py)")
    print(f"  Loaded: {sorted(found)}")
    print()

    all_results = {}
    global_total   = 0
    global_matched = 0
    global_confirmed = 0

    for article in TEST_ARTICLES:
        if article not in zim_html:
            print(f"── {article}: NOT IN ZIM ──\n")
            continue

        html = zim_html[article]
        zim_imgs = zim_images(html)

        print(f"── {article} ──")
        print(f"  ZIM images: {len(zim_imgs)}")

        # Fetch action=parse
        api_imgs = parse_images(article)
        time.sleep(API_DELAY)
        print(f"  API images (action=parse, filtered): {len(api_imgs)}")

        # Show mismatch
        if len(zim_imgs) != len(api_imgs):
            diff = len(api_imgs) - len(zim_imgs)
            sign = "+" if diff > 0 else ""
            print(f"  ⚠ Count mismatch: {sign}{diff} "
                  f"({'API has more' if diff>0 else 'ZIM has more'} — "
                  f"{'article updated since Oct 2025?' if diff>0 else 'filtered or deduped'})")

        print()
        print(f"  {'Idx':>3}  {'ZIM hash':20s}  {'API filename':45s}  {'Pos':3s}  {'Cap-ratio':9s}  Status")
        print(f"  {'---':>3}  {'--------':20s}  {'-'*45}  {'---':3s}  {'-'*9}  ------")

        article_matches = []
        matched = 0
        confirmed = 0

        for zi in zim_imgs:
            idx = zi["idx"]

            # Positional match: API image at same index
            if idx < len(api_imgs):
                api_fn = api_imgs[idx]["filename"]
                pos_match = True
            else:
                api_fn    = "(no API image at this index)"
                pos_match = False

            # Caption confirmation
            ratio = caption_ratio(zi["caption"], api_fn) if pos_match else 0.0
            caption_ok = ratio >= CAPTION_THRESHOLD

            # Confidence: positional match exists (caption is confirmation, not gate)
            confident = pos_match
            # Extra flag if caption also confirms
            caption_confirmed = pos_match and caption_ok

            status = ""
            if not pos_match:
                status = "✗ no_api_img"
            elif caption_confirmed:
                status = "✓ pos+caption"
                confirmed += 1
                matched   += 1
            else:
                status = "~ pos_only"
                matched += 1

            hash_short = zi["hash_fn"][:18] + "…"
            fn_short   = (api_fn[:43] + "…") if len(api_fn) > 44 else api_fn
            cap_short  = (zi["caption"][:35] + "…") if len(zi["caption"]) > 36 else zi["caption"]

            print(f"  {idx:>3}  {hash_short:20s}  {fn_short:45s}  {'✓' if pos_match else '✗':3s}  {ratio:9.3f}  {status}")
            if zi["caption"]:
                print(f"       caption: {cap_short!r}")

            article_matches.append({
                "idx":               idx,
                "zim_hash":          zi["hash_fn"],
                "caption":           zi["caption"],
                "api_filename":      api_fn if pos_match else None,
                "position_match":    pos_match,
                "caption_ratio":     round(ratio, 3),
                "caption_confirmed": caption_confirmed,
                "confident":         confident,
            })

        print()
        print(f"  → {matched}/{len(zim_imgs)} positional matches, "
              f"{confirmed}/{len(zim_imgs)} caption-confirmed")

        all_results[article] = {
            "zim_count":    len(zim_imgs),
            "api_count":    len(api_imgs),
            "count_delta":  len(api_imgs) - len(zim_imgs),
            "matched":      matched,
            "confirmed":    confirmed,
            "images":       article_matches,
        }

        global_total     += len(zim_imgs)
        global_matched   += matched
        global_confirmed += confirmed
        print()

    # ── Global summary ────────────────────────────────────────────────────────

    print("=" * 70)
    print(f"SUMMARY — {len(all_results)} articles")
    print(f"  Total ZIM images:          {global_total}")
    print(f"  Positional matches:        {global_matched} ({100*global_matched//max(global_total,1)}%)")
    print(f"  Caption-confirmed:         {global_confirmed} ({100*global_confirmed//max(global_total,1)}%)")
    print()
    print(f"  Per-article breakdown:")
    for art, res in all_results.items():
        delta = res['count_delta']
        sign  = f"+{delta}" if delta > 0 else str(delta)
        delta_note = f"  Δ={sign}" if delta != 0 else ""
        print(f"    {art:15s}: ZIM={res['zim_count']:3d}  API={res['api_count']:3d}{delta_note}"
              f"  matched={res['matched']:3d}  confirmed={res['confirmed']:3d}")

    OUTPUT_FILE.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
