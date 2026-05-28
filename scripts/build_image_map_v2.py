#!/usr/bin/env python3
"""
Phase-2-Test: prop=images + Caption-Matching für ZIM-Bild-Mapping.

Phase 1 (offline):
  Strategy 1 — alt-Attribut ist Dateiname  (schnell, offline)
  Strategy 2 — vorhergehender Datei:-Link   (schnell, offline)

Phase 2 (API — nur für verbleibende Bilder):
  prop=images   statt action=parse → liefert alle Dateinamen im Artikel
  Matching nach (in Reihenfolge):
    a) Positions-Match wenn Anzahl exakt übereinstimmt
    b) Caption-Match: figcaption/thumbcaption aus ZIM-HTML gegen normierten Dateinamen

Umgebungsvariablen:
  ZIM_FILE      Pfad zur .zim-Datei (default: klexikon.zim)
  OUTPUT_FILE   Ausgabedatei        (default: image_map.json)
  MAX_ARTICLES  Testmodus           (0 = alle, >0 = Limit)
  API_DELAY     Pause zw. API-Calls (default: 0.4 s)
  SAMPLE_ARTICLE  Zeige Details für einen Artikel (default: Elefant)

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
    _session.headers["User-Agent"] = "WissensfreundBot/1.0 (phase2-mapper; build_image_map_v2.py)"
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: pip install requests", file=sys.stderr)

ZIM_FILE      = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE   = Path(os.environ.get("OUTPUT_FILE", "image_map.json"))
MAX_ARTICLES  = int(os.environ.get("MAX_ARTICLES", "0"))
API_DELAY     = float(os.environ.get("API_DELAY", "0.4"))
SAMPLE_ARTICLE = os.environ.get("SAMPLE_ARTICLE", "Elefant")

KLEXIKON_API  = "https://klexikon.zum.de/api.php"
ZIM_MAGIC     = 0x044d495a
IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# ── Regex ────────────────────────────────────────────────────────────────────

FILE_LINK_RE = re.compile(
    r'href="[^"]*(?:File|Datei|Fichier|Archivo|Bestand|Datoteka|Soubor|'
    r'Файл|ملف|Tiedosto|F%C3%A1jl|Fil|Vaizdas|Att%C4%93ls|Dosya):([^"#?&<>\s]+)"',
    re.IGNORECASE,
)
_FULL_IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
_SRC_HASH_RE = re.compile(r'\bsrc="[^"]*_assets_/([^"?#\s<>]+)"', re.IGNORECASE)
_ALT_FILE_RE = re.compile(
    r'\balt="([^"]{1,200}\.(?:jpg|jpeg|png|gif|svg|webp))"', re.IGNORECASE)
_ALT_ANY_RE  = re.compile(r'\balt="([^"]*)"', re.IGNORECASE)

# Caption-Elemente direkt nach einem <img>-Tag
_CAPTION_RE  = re.compile(
    r'<(?:figcaption|div[^>]*(?:thumbcaption|caption)[^>]*)>([^<]{3,200})</',
    re.IGNORECASE,
)


def _is_image_ext(name: str) -> bool:
    return Path(name.lower()).suffix in IMAGE_EXTS


# ── ZIM parsing ───────────────────────────────────────────────────────────────

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
    end   = cluster_ptrs[idx + 1] if idx + 1 < len(cluster_ptrs) else checksum_pos
    f.seek(start)
    info  = struct.unpack('B', f.read(1))[0]
    comp  = info & 0x0f
    ext   = bool(info & 0x10)
    raw   = f.read(end - start - 1)
    return _decompress(raw, comp) if raw else None, ext


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
    """Yield (title, html_str) for every HTML article."""
    with open(zim_path, 'rb') as f:
        header = f.read(80)
        magic, = struct.unpack_from('<I', header, 0)
        if magic != ZIM_MAGIC:
            print(f"ERROR: not a ZIM file", file=sys.stderr); return

        entry_count,     = struct.unpack_from('<I', header, 24)
        cluster_count,   = struct.unpack_from('<I', header, 28)
        url_ptr_pos,     = struct.unpack_from('<Q', header, 32)
        cluster_ptr_pos, = struct.unpack_from('<Q', header, 48)
        mime_list_pos,   = struct.unpack_from('<Q', header, 56)
        checksum_pos,    = struct.unpack_from('<Q', header, 72)

        mime_types = _read_mime_types(f, mime_list_pos)
        html_idxs  = {i for i, mt in enumerate(mime_types) if 'html' in mt.lower()}

        f.seek(cluster_ptr_pos)
        cluster_ptrs: list[int] = []
        for _ in range(cluster_count):
            raw = f.read(8)
            if len(raw) < 8: break
            cluster_ptrs.append(struct.unpack_from('<Q', raw)[0])

        entries = []
        for i in range(entry_count):
            f.seek(url_ptr_pos + i * 8)
            raw = f.read(8)
            if len(raw) < 8: break
            ptr, = struct.unpack_from('<Q', raw)
            f.seek(ptr)
            hdr = f.read(4)
            if len(hdr) < 4: continue
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
        cur_data = cur_extended = None

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


# ── HTML analysis ─────────────────────────────────────────────────────────────

def extract_zim_imgs(html: str) -> list[tuple[str, str]]:
    """Return [(hash_fn, alt)] for every _assets_ image in appearance order."""
    result = []
    for m in _FULL_IMG_RE.finditer(html):
        tag = m.group(0)
        src_m = _SRC_HASH_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        alt_m   = _ALT_ANY_RE.search(tag)
        alt     = unquote(alt_m.group(1)).strip() if alt_m else ""
        result.append((hash_fn, alt))
    return result


def extract_img_with_captions(html: str) -> list[tuple[str, str, str]]:
    """Return [(hash_fn, alt, caption)] for every _assets_ image."""
    result = []
    for m in _FULL_IMG_RE.finditer(html):
        tag     = m.group(0)
        src_m   = _SRC_HASH_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        alt_m   = _ALT_ANY_RE.search(tag)
        alt     = unquote(alt_m.group(1)).strip() if alt_m else ""

        # Look for caption in the 800 chars after the img tag
        after       = html[m.end(): m.end() + 800]
        caption_m   = _CAPTION_RE.search(after)
        caption     = caption_m.group(1).strip() if caption_m else ""
        result.append((hash_fn, alt, caption))
    return result


def try_offline_mapping(html: str, image_map: dict[str, str]) -> list[tuple[str, str, str]]:
    """
    Apply Strategy 1 (alt-as-filename) and Strategy 2 (Datei-link).
    Returns list of (hash_fn, alt, caption) for images that still need API lookup.
    """
    unmapped: list[tuple[str, str, str]] = []

    imgs_with_captions = extract_img_with_captions(html)

    for m in _FULL_IMG_RE.finditer(html):
        tag   = m.group(0)
        src_m = _SRC_HASH_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        key     = f"_assets_/{hash_fn}"
        if key in image_map:
            continue

        # Strategy 1: alt looks like a Commons filename
        alt_m = _ALT_FILE_RE.search(tag)
        if alt_m:
            alt = unquote(alt_m.group(1)).strip().replace(" ", "_")
            if alt:
                image_map[key] = alt
                continue

        # Strategy 2: preceding Datei: link
        img_pos = m.start()
        pre = html[max(0, img_pos - 1200): img_pos]
        link_matches = list(FILE_LINK_RE.finditer(pre))
        if link_matches:
            raw_name = unquote(link_matches[-1].group(1))
            original = raw_name.replace(' ', '_').rstrip('/')
            if original and _is_image_ext(original):
                image_map[key] = original
                continue

        # Find caption for this image
        after     = html[m.end(): m.end() + 800]
        cap_m     = _CAPTION_RE.search(after)
        caption   = cap_m.group(1).strip() if cap_m else ""
        alt_any   = _ALT_ANY_RE.search(tag)
        alt_text  = unquote(alt_any.group(1)).strip() if alt_any else ""
        unmapped.append((hash_fn, alt_text, caption))

    return unmapped


# ── Caption Matching ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, remove ext, replace _ with space."""
    text = re.sub(r'\.(jpg|jpeg|png|gif|webp|svg)$', '', text, flags=re.IGNORECASE)
    text = text.replace('_', ' ').replace('-', ' ')
    text = text.lower()
    text = re.sub(r'[^a-z0-9äöüß ]', ' ', text)
    return ' '.join(text.split())


def caption_match(alt_text: str, caption: str, commons_fns: list[str]) -> tuple[str | None, str]:
    """
    Match alt_text or caption against list of Commons filenames.
    Returns (best_match_filename, match_type) or (None, 'no_match').
    """
    candidates = [t for t in [caption, alt_text] if t]
    if not candidates or not commons_fns:
        return None, 'no_match'

    norm_fns = [(_normalize(fn), fn) for fn in commons_fns]

    for source_text in candidates:
        norm_src = _normalize(source_text)
        if not norm_src:
            continue

        # Exact match
        for norm_fn, fn in norm_fns:
            if norm_src == norm_fn:
                return fn, 'exact'

        # Contains match (at least 5 chars overlap)
        for norm_fn, fn in norm_fns:
            if len(norm_src) >= 5 and len(norm_fn) >= 5:
                if norm_src in norm_fn or norm_fn in norm_src:
                    shorter = min(len(norm_src), len(norm_fn))
                    longer  = max(len(norm_src), len(norm_fn))
                    if shorter / longer >= 0.5:
                        return fn, 'contains'

        # Token overlap (≥50% of tokens match, min 2 tokens)
        src_tokens = set(norm_src.split())
        if len(src_tokens) >= 2:
            best_score = 0
            best_fn    = None
            for norm_fn, fn in norm_fns:
                fn_tokens = set(norm_fn.split())
                if not fn_tokens:
                    continue
                overlap = len(src_tokens & fn_tokens)
                score   = overlap / max(len(src_tokens), len(fn_tokens))
                if score > best_score:
                    best_score = score
                    best_fn    = fn
            if best_score >= 0.5:
                return best_fn, f'token({best_score:.2f})'

    return None, 'no_match'


# ── MediaWiki API: prop=images ────────────────────────────────────────────────

def fetch_images_list(title: str) -> list[str]:
    """
    Fetch all image filenames embedded in an article via prop=images.
    Returns list of Commons filenames (without 'Datei:' prefix).
    Note: order is alphabetical, NOT appearance order.
    """
    if not HAS_REQUESTS:
        return []
    try:
        r = _session.get(KLEXIKON_API, params={
            "action":  "query",
            "titles":  title,
            "prop":    "images",
            "imlimit": "50",
            "format":  "json",
        }, timeout=30)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            return [
                unquote(img["title"]).split(":", 1)[-1].replace(" ", "_")
                for img in page.get("images", [])
                if img.get("ns") == 6 and _is_image_ext(img.get("title", ""))
            ]
    except Exception as e:
        print(f"  API error ({title}): {e}", file=sys.stderr)
    return []


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)...")
    if MAX_ARTICLES:
        print(f"Test mode: at most {MAX_ARTICLES} articles")

    image_map: dict[str, str]                                                       = {}
    needs_api: dict[str, tuple[list[tuple[str,str]], list[tuple[str,str,str]]]]    = {}
    articles_scanned = 0
    articles_with_imgs = 0

    for title, html in iter_html_content(zim_path):
        articles_scanned += 1
        if MAX_ARTICLES and articles_scanned > MAX_ARTICLES:
            break

        all_imgs = extract_zim_imgs(html)
        unmapped = try_offline_mapping(html, image_map)

        if all_imgs:
            articles_with_imgs += 1

        if unmapped:
            needs_api[title] = (all_imgs, unmapped)

        if articles_scanned % 500 == 0:
            print(f"  {articles_scanned} articles, {len(image_map)} offline mappings, "
                  f"{len(needs_api)} need API...")

        # Debug output for sample article
        if title == SAMPLE_ARTICLE and unmapped:
            print(f"\n── Sample: {title} ──")
            print(f"  Total images in ZIM HTML: {len(all_imgs)}")
            print(f"  Unmapped after Strategy 1+2: {len(unmapped)}")
            for i, (hf, alt, cap) in enumerate(unmapped[:5]):
                print(f"  [{i}] hash={hf[:16]}…  alt={alt!r}  caption={cap!r}")

    print(f"\nPhase 1+2 offline: {articles_scanned} articles scanned, "
          f"{articles_with_imgs} with images, "
          f"{len(image_map)} mappings, {len(needs_api)} articles need API")

    # ── Strategy 3: prop=images + Caption-Matching ────────────────────────────

    if not needs_api:
        print("All images mapped offline — no API needed!")
    elif not HAS_REQUESTS:
        print("WARNING: requests not installed — skipping API phase")
    elif MAX_ARTICLES:
        print("(Skipping API in test mode — set MAX_ARTICLES=0 for full run)")
    else:
        total_unmapped = sum(len(v[1]) for v in needs_api.values())
        print(f"\nPhase 2 — prop=images for {len(needs_api)} articles "
              f"({total_unmapped} unmapped images)...")

        api_hits       = 0
        positional_hits = 0
        caption_hits_exact    = 0
        caption_hits_contains = 0
        caption_hits_token    = 0
        no_match       = 0
        no_api_result  = 0

        for i, (title, (all_imgs, unmapped_imgs)) in enumerate(needs_api.items(), 1):
            commons_fns = fetch_images_list(title)
            time.sleep(API_DELAY)

            if not commons_fns:
                no_api_result += len(unmapped_imgs)
                continue

            # Positional match: API count == ZIM total count → safe positional match
            # (only use if 1 image to avoid alphabetical-order confusion)
            if len(commons_fns) == 1 and len(all_imgs) == 1:
                hash_fn, _ = all_imgs[0]
                key = f"_assets_/{hash_fn}"
                if key not in image_map and commons_fns[0]:
                    image_map[key] = commons_fns[0]
                    api_hits      += 1
                    positional_hits += 1
                continue

            # Caption match for all unmapped images in this article
            for hash_fn, alt, caption in unmapped_imgs:
                key = f"_assets_/{hash_fn}"
                if key in image_map:
                    continue
                matched_fn, match_type = caption_match(alt, caption, commons_fns)
                if matched_fn:
                    image_map[key] = matched_fn
                    api_hits += 1
                    if match_type == 'exact':
                        caption_hits_exact += 1
                    elif match_type == 'contains':
                        caption_hits_contains += 1
                    else:
                        caption_hits_token += 1
                else:
                    no_match += 1

            if i % 200 == 0:
                print(f"  {i}/{len(needs_api)} articles, {api_hits} new mappings so far...")

        print(f"\nPhase 2 results:")
        print(f"  Positional (1-image articles): {positional_hits}")
        print(f"  Caption exact match:           {caption_hits_exact}")
        print(f"  Caption contains match:        {caption_hits_contains}")
        print(f"  Caption token match:           {caption_hits_token}")
        print(f"  No match:                      {no_match}")
        print(f"  No API result:                 {no_api_result}")
        print(f"  Total new via API:             {api_hits}")

    # ── Save result ───────────────────────────────────────────────────────────

    OUTPUT_FILE.write_text(
        json.dumps(image_map, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\nDone: {articles_scanned} articles, {len(image_map)} mappings → {OUTPUT_FILE}")

    # Coverage estimate
    total_imgs_found = sum(len(v[0]) for v in needs_api.values()) + len(image_map) - sum(
        len([1 for hf, _ in v[0] if f"_assets_/{hf}" in image_map]) for v in needs_api.values()
    )
    print(f"Estimated coverage: ~{len(image_map)} of ~21100 ZIM images")


if __name__ == "__main__":
    main()
