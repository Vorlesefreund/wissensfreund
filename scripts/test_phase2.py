#!/usr/bin/env python3
"""
test_phase2.py — Phase-2-Test: prop=images + difflib + Commons-API

Für jeden Artikel:
  1. Klexikon prop=images → gefilterte Dateiliste
  2. ZIM-HTML → <figure>-Blöcke (md5hash + figcaption) + img/alt-Fallback
  3. difflib.SequenceMatcher Caption-Matching (threshold 0.4)
  4. Commons imageinfo → url_600 + source_url + author + license

Output: image_map.json
  {
    "md5hash.jpg": {
      "filename":       "African_elephant.jpg",
      "url_600":        "https://...",
      "artist":         "...",
      "license":        "CC-BY-SA-4.0",
      "low_confidence": false
    }
  }

Umgebungsvariablen:
  ZIM_FILE         Pfad zur .zim-Datei (default: klexikon.zim)
  OUTPUT_FILE      (default: image_map.json)
  MAX_ARTICLES     0 = alle, >0 = Limit  (default: 5 für Test)
  API_DELAY        Pause zwischen Klexikon-API-Calls (default: 0.4)
  COMMONS_DELAY    Pause zwischen Commons-API-Calls  (default: 0.5)
  TEST_ARTICLES    Kommagetrennte Artikelnamen für gezielten Test
                   z.B. "Elefant,Beethoven,Dinosaurier"
  CONFIDENCE_THRESHOLD  difflib-Schwellwert (default: 0.4)

Requires: pip install zstandard requests
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
from urllib.parse import unquote, quote

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False
    print("WARNING: pip install zstandard", file=sys.stderr)

try:
    import requests as _requests
    _klexikon = _requests.Session()
    _klexikon.headers["User-Agent"] = "WissensfreundBot/1.0 (test-phase2; contact: wissensfreund@example.com)"
    _commons = _requests.Session()
    _commons.headers["User-Agent"] = "WissensfreundBot/1.0 (test-phase2; contact: wissensfreund@example.com)"
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: pip install requests", file=sys.stderr)

ZIM_FILE   = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "image_map.json"))
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "5"))
API_DELAY    = float(os.environ.get("API_DELAY", "0.4"))
COMMONS_DELAY = float(os.environ.get("COMMONS_DELAY", "0.5"))
TEST_ARTICLES = [t.strip() for t in os.environ.get("TEST_ARTICLES", "").split(",") if t.strip()]
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.4"))

KLEXIKON_API = "https://klexikon.zum.de/api.php"
COMMONS_API  = "https://commons.wikimedia.org/w/api.php"
ZIM_MAGIC    = 0x044d495a
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif"}  # no SVG in target set

# Präfixe die herausgefiltert werden (Logos, Lizenzsymbole, Commons-Icons)
FILTER_PREFIXES = (
    "commons-logo",
    "wikimedia",
    "cc-",
    "pd-",
    "gfdl",
    "question",
    "wikiquote",
    "wikibooks",
    "wiktionary",
    "wikispecies",
    "wikinews",
    "wikivoyage",
    "wikidata",
    "wikipedia-logo",
    "ambox",
    "portal-",
)


# ── ZIM parsing ────────────────────────────────────────────────────────────────

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


def _read_cluster(f, cluster_ptrs, idx, checksum_pos):
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


def _extract_blob(data, blob_num, extended):
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
        cluster_ptrs = []
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


# ── HTML → figure blocks ───────────────────────────────────────────────────────

_FIGURE_RE   = re.compile(r'<figure\b[^>]*>(.*?)</figure>', re.IGNORECASE | re.DOTALL)
_THUMB_RE    = re.compile(
    r'<div\b[^>]*class="[^"]*thumb[^"]*"[^>]*>(.*?)</div\s*>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
_IMG_SRC_RE  = re.compile(r'\bsrc="[^"]*_assets_/([^"?#\s<>]+)"', re.IGNORECASE)
_CAPTION_RE  = re.compile(r'<figcaption[^>]*>([^<]{2,300})</figcaption>', re.IGNORECASE)
_THUMBCAP_RE = re.compile(r'class="[^"]*thumbcaption[^"]*"[^>]*>([^<]{2,300})<', re.IGNORECASE)
_ALT_RE      = re.compile(r'\balt="([^"]{1,200})"', re.IGNORECASE)
_FULL_IMG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)


def extract_figures(html: str) -> list[tuple[str, str]]:
    """
    Return [(hash_filename, caption_text)] in appearance order.
    Tries <figure> blocks first, then .thumb divs, then bare img tags with alt.
    hash_filename: e.g. "abc123.jpg"
    caption_text:  figcaption or alt attribute
    """
    results = []
    seen_hashes: set[str] = set()

    def _try_figure_block(block: str) -> tuple[str, str] | None:
        src_m = _IMG_SRC_RE.search(block)
        if not src_m:
            return None
        hash_fn = unquote(src_m.group(1))
        cap_m   = _CAPTION_RE.search(block) or _THUMBCAP_RE.search(block)
        caption = cap_m.group(1).strip() if cap_m else ""
        if not caption:
            alt_m   = _ALT_RE.search(block)
            caption = unquote(alt_m.group(1)).strip() if alt_m else ""
        return hash_fn, caption

    # 1. <figure> blocks
    for m in _FIGURE_RE.finditer(html):
        r = _try_figure_block(m.group(0))
        if r and r[0] not in seen_hashes:
            seen_hashes.add(r[0])
            results.append(r)

    # 2. .thumb divs (older MediaWiki format)
    for m in _THUMB_RE.finditer(html):
        r = _try_figure_block(m.group(0))
        if r and r[0] not in seen_hashes:
            seen_hashes.add(r[0])
            results.append(r)

    # 3. Bare img tags (fallback — any remaining _assets_ images)
    for m in _FULL_IMG_RE.finditer(html):
        tag   = m.group(0)
        src_m = _IMG_SRC_RE.search(tag)
        if not src_m:
            continue
        hash_fn = unquote(src_m.group(1))
        if hash_fn in seen_hashes:
            continue
        alt_m   = _ALT_RE.search(tag)
        caption = unquote(alt_m.group(1)).strip() if alt_m else ""
        seen_hashes.add(hash_fn)
        results.append((hash_fn, caption))

    return results


# ── Klexikon prop=images ───────────────────────────────────────────────────────

def _should_filter(filename: str) -> bool:
    """Return True if this file should be excluded (logo, icon, SVG, etc.)."""
    name_lower = filename.lower()
    # SVG-Dateien immer ausschließen
    if name_lower.endswith('.svg'):
        return True
    # Bekannte Präfixe für Nicht-Inhaltsbilder
    for prefix in FILTER_PREFIXES:
        if name_lower.startswith(prefix):
            return True
    return False


def fetch_klexikon_images(title: str) -> list[str]:
    """
    Fetch filtered list of image filenames from Klexikon via prop=images.
    Returns Commons filenames (without 'Datei:' prefix), SVGs and logos removed.
    """
    if not HAS_REQUESTS:
        return []
    try:
        r = _klexikon.get(KLEXIKON_API, params={
            "action":  "query",
            "titles":  title,
            "prop":    "images",
            "imlimit": "50",
            "format":  "json",
        }, timeout=30)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            raw = [
                unquote(img["title"]).split(":", 1)[-1].replace(" ", "_")
                for img in page.get("images", [])
                if img.get("ns") == 6
            ]
            return [fn for fn in raw if not _should_filter(fn)]
    except Exception as e:
        print(f"  Klexikon API error ({title}): {e}", file=sys.stderr)
    return []


# ── Caption matching ───────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalize for difflib comparison."""
    text = re.sub(r'\.(jpg|jpeg|png|gif|webp)$', '', text, flags=re.IGNORECASE)
    text = text.replace('_', ' ').replace('-', ' ')
    text = text.lower()
    text = re.sub(r'[^a-z0-9äöüß ]', ' ', text)
    return ' '.join(text.split())


def best_match(caption: str, filenames: list[str]) -> tuple[str | None, float]:
    """
    Find the filename with highest SequenceMatcher ratio against caption.
    Returns (filename, ratio) or (None, 0.0).
    """
    if not caption or not filenames:
        return None, 0.0

    norm_cap = _normalize(caption)
    if not norm_cap:
        return None, 0.0

    best_fn    = None
    best_ratio = 0.0

    for fn in filenames:
        norm_fn = _normalize(fn)
        if not norm_fn:
            continue
        ratio = difflib.SequenceMatcher(None, norm_cap, norm_fn).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_fn    = fn

    return best_fn, best_ratio


# ── Commons imageinfo ──────────────────────────────────────────────────────────

def fetch_commons_info(filename: str) -> dict:
    """
    Fetch url_600, source_url, author, license from Wikimedia Commons.

    API-Call:
      prop=imageinfo&iiprop=url|descriptionurl|extmetadata
      &iiurlwidth=600&iiextmetadatafilter=Artist|LicenseShortName

    Gibt immer ein Dict zurück (leer bei Fehler/nicht gefunden).
    """
    if not HAS_REQUESTS:
        return {}
    try:
        r = _commons.get(COMMONS_API, params={
            "action":              "query",
            "prop":                "imageinfo",
            "iiprop":              "url|descriptionurl|extmetadata",
            "iiurlwidth":          "600",
            "iiextmetadatafilter": "Artist|LicenseShortName",
            "titles":              f"File:{filename}",
            "format":              "json",
        }, timeout=30)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                return {}
            info = info_list[0]
            meta = info.get("extmetadata", {})
            return {
                "url_600":    info.get("thumburl") or info.get("url", ""),
                "source_url": info.get("descriptionurl", ""),
                "author":     re.sub(r'<[^>]+>', '', meta.get("Artist",           {}).get("value", "")).strip(),
                "license":    meta.get("LicenseShortName", {}).get("value", ""),
            }
    except Exception as e:
        print(f"  Commons API error ({filename}): {e}", file=sys.stderr)
    return {}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}", file=sys.stderr)
        sys.exit(1)

    print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    if MAX_ARTICLES:
        print(f"Test mode: {MAX_ARTICLES} articles")
    if TEST_ARTICLES:
        print(f"Target articles: {TEST_ARTICLES}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print()

    image_map: dict[str, dict] = {}
    articles_processed = 0
    total_confident   = 0
    total_low_conf    = 0
    total_no_match    = 0
    total_commons_ok  = 0

    for title, html in iter_html_content(zim_path):

        # Filter: only process articles in TEST_ARTICLES list if specified
        if TEST_ARTICLES and title not in TEST_ARTICLES:
            continue

        figures = extract_figures(html)
        if not figures:
            if not TEST_ARTICLES:
                articles_processed += 1
                if MAX_ARTICLES and articles_processed >= MAX_ARTICLES:
                    break
            continue

        print(f"\n── {title} ({len(figures)} images) ──")

        # Step 1: Klexikon prop=images
        api_filenames = fetch_klexikon_images(title)
        time.sleep(API_DELAY)
        print(f"  Klexikon API: {len(api_filenames)} filtered filenames")
        if api_filenames:
            for fn in api_filenames[:5]:
                print(f"    • {fn}")
            if len(api_filenames) > 5:
                print(f"    … +{len(api_filenames)-5} more")

        # Steps 2+3: Match each ZIM image's caption to API filenames
        for hash_fn, caption in figures:
            print(f"\n  img: {hash_fn[:20]}…  caption: {caption!r:.60s}")

            matched_fn, ratio = best_match(caption, api_filenames)
            low_confidence    = ratio < CONFIDENCE_THRESHOLD if matched_fn else True

            status = "✓ confident" if matched_fn and not low_confidence else (
                     "~ low_conf" if matched_fn else "✗ no_match")
            print(f"  → {status}  ratio={ratio:.3f}  fn={matched_fn!r}")

            if not matched_fn:
                total_no_match += 1
                continue

            if low_confidence:
                total_low_conf += 1
            else:
                total_confident += 1

            entry: dict = {
                "filename":       matched_fn,
                "caption":        caption,
                "ratio":          round(ratio, 3),
                "low_confidence": low_confidence,
                "url_600":        "",
                "source_url":     "",
                "author":         "",
                "license":        "",
            }

            # Step 4: Commons imageinfo (only for confident matches to save quota)
            if not low_confidence:
                commons_info = fetch_commons_info(matched_fn)
                time.sleep(COMMONS_DELAY)
                if commons_info:
                    entry.update(commons_info)
                    total_commons_ok += 1
                    print(f"  Commons: {commons_info.get('license','?')}  {commons_info.get('source_url','')[:60]}")

            image_map[hash_fn] = entry

        articles_processed += 1
        if not TEST_ARTICLES and MAX_ARTICLES and articles_processed >= MAX_ARTICLES:
            break

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"Articles processed: {articles_processed}")
    print(f"Images in map:      {len(image_map)}")
    print(f"  Confident (≥{CONFIDENCE_THRESHOLD}): {total_confident}")
    print(f"  Low confidence:    {total_low_conf}")
    print(f"  No match:          {total_no_match}")
    print(f"  Commons info OK:   {total_commons_ok}")

    if image_map:
        confident_matches = [e for e in image_map.values() if not e["low_confidence"]]
        if confident_matches:
            print(f"\nConfident matches (sample):")
            for e in confident_matches[:5]:
                print(f"  {e['filename']} | ratio={e['ratio']} | {e['license']}")
        low_matches = [e for e in image_map.values() if e["low_confidence"]]
        if low_matches:
            print(f"\nLow-confidence matches (sample):")
            for e in low_matches[:5]:
                print(f"  {e['filename']} | ratio={e['ratio']} | caption={e['caption']!r:.50s}")

    OUTPUT_FILE.write_text(
        json.dumps(image_map, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\nSaved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
