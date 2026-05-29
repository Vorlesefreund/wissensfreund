#!/usr/bin/env python3
"""
build_title_map.py — ZIM-Titel vs. Live-API-Titel Mapping.

1. Liest alle Artikel-Titel aus der ZIM-Datei (HTML-Namespace)
2. Lädt alle Live-Artikel von klexikon.zum.de via allpages-API (paginiert)
3. Matcht ZIM → API:
   a) Exakt-Match (normalisiert)
   b) Singular/Plural via difflib ratio > 0.85
4. Speichert Ergebnis als title_map.json

Umgebungsvariablen:
  ZIM_FILE    (default: klexikon.zim)
  OUTPUT_FILE (default: title_map.json)
  API_DELAY   (default: 0.3)
  RATIO_THRESHOLD  difflib threshold für Singular/Plural (default: 0.85)

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
from urllib.parse import unquote

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

try:
    import requests as _requests
    _session = _requests.Session()
    _session.headers["User-Agent"] = "WissensfreundBot/1.0 (title-mapper)"
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

ZIM_FILE         = os.environ.get("ZIM_FILE", "klexikon.zim")
OUTPUT_FILE      = Path(os.environ.get("OUTPUT_FILE", "title_map.json"))
API_DELAY        = float(os.environ.get("API_DELAY", "0.3"))
RATIO_THRESHOLD  = float(os.environ.get("RATIO_THRESHOLD", "0.85"))

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


def _read_mime_list(f, pos: int) -> list[str]:
    f.seek(pos)
    types = []
    while True:
        mt = _read_cstr(f)
        if not mt:
            break
        types.append(mt)
    return types


def load_zim_titles(zim_path: Path) -> list[str]:
    """Return all HTML article titles from the ZIM (in ZIM order)."""
    titles = []
    with open(zim_path, 'rb') as f:
        hdr = f.read(80)
        magic, = struct.unpack_from('<I', hdr, 0)
        if magic != ZIM_MAGIC:
            print("ERROR: not a ZIM file"); sys.exit(1)

        ec,  = struct.unpack_from('<I', hdr, 24)
        up,  = struct.unpack_from('<Q', hdr, 32)
        mlp, = struct.unpack_from('<Q', hdr, 56)

        mimes    = _read_mime_list(f, mlp)
        html_idx = {i for i, m in enumerate(mimes) if 'html' in m.lower()}

        for i in range(ec):
            f.seek(up + i * 8)
            r = f.read(8)
            if len(r) < 8:
                break
            ptr, = struct.unpack_from('<Q', r)
            f.seek(ptr)
            h = f.read(4)
            if len(h) < 4:
                continue
            mi, _, ns_b = struct.unpack_from('<HBc', h)
            if mi == 0xffff or mi not in html_idx:
                continue
            # Skip cluster/blob pointers
            f.read(12)
            url   = _read_cstr(f)
            title = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit('/', 1)[-1]
            # Skip empty, numeric-only, or system entries
            if title and not title.startswith('_') and not title.isdigit():
                titles.append(title)

    return titles


# ── Klexikon allpages API ─────────────────────────────────────────────────────

def load_api_titles() -> list[str]:
    """Fetch all article titles from klexikon.zum.de via allpages (paginiert)."""
    titles = []
    apcontinue = None
    page_num = 0

    while True:
        params = {
            "action":  "query",
            "list":    "allpages",
            "aplimit": "500",
            "apnamespace": "0",   # Hauptnamespace (Artikel)
            "format":  "json",
        }
        if apcontinue:
            params["apcontinue"] = apcontinue

        try:
            r = _session.get(KLEXIKON_API, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  allpages API error: {e}", file=sys.stderr)
            break

        batch = [p["title"] for p in data.get("query", {}).get("allpages", [])]
        titles.extend(batch)
        page_num += 1
        print(f"  allpages page {page_num}: {len(batch)} titles (total: {len(titles)})")

        cont = data.get("continue", {})
        apcontinue = cont.get("apcontinue")
        if not apcontinue:
            break

        time.sleep(API_DELAY)

    return titles


# ── Normalization & Matching ───────────────────────────────────────────────────

def _norm(title: str) -> str:
    """Normalize title for comparison: strip, lowercase, collapse spaces."""
    return ' '.join(title.strip().replace('_', ' ').lower().split())


def build_title_map(zim_titles: list[str], api_titles: list[str]) -> dict:
    """
    Match ZIM titles to API titles.
    Returns dict with keys:
      exact:        [{zim, api}]
      fuzzy:        [{zim, api, ratio}]  (Singular/Plural etc.)
      zim_only:     [title]  (in ZIM, not in API → deleted or renamed)
      api_only:     [title]  (in API, not in ZIM → added after Oct 2025)
    """
    norm_api = {_norm(t): t for t in api_titles}
    norm_zim = {_norm(t): t for t in zim_titles}

    exact:    list[dict] = []
    fuzzy:    list[dict] = []
    zim_only: list[str]  = []

    remaining_api_norms = set(norm_api.keys())

    for zim_norm, zim_orig in sorted(norm_zim.items()):
        if zim_norm in norm_api:
            # Exact match (case-insensitive, space-normalized)
            api_orig = norm_api[zim_norm]
            exact.append({"zim": zim_orig, "api": api_orig})
            remaining_api_norms.discard(zim_norm)
        else:
            # Fuzzy match: find best API title by difflib ratio
            best_ratio = 0.0
            best_api   = None
            for api_norm in remaining_api_norms:
                r = difflib.SequenceMatcher(None, zim_norm, api_norm).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_api   = api_norm

            if best_api and best_ratio >= RATIO_THRESHOLD:
                api_orig = norm_api[best_api]
                fuzzy.append({
                    "zim":   zim_orig,
                    "api":   api_orig,
                    "ratio": round(best_ratio, 3),
                })
                remaining_api_norms.discard(best_api)
            else:
                # No good match — ZIM-only (was removed or renamed in live API)
                zim_only.append(zim_orig)

    api_only = [norm_api[n] for n in sorted(remaining_api_norms)]

    return {
        "exact":    exact,
        "fuzzy":    fuzzy,
        "zim_only": zim_only,
        "api_only": api_only,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    zim_path = Path(ZIM_FILE)
    if not zim_path.exists():
        print(f"ERROR: ZIM not found: {zim_path}"); sys.exit(1)

    print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
    print(f"Ratio threshold: {RATIO_THRESHOLD}")
    print()

    # 1. ZIM titles
    print("Step 1: Loading ZIM article titles...")
    zim_titles = load_zim_titles(zim_path)
    # Deduplicate while preserving order
    seen: set[str] = set()
    zim_titles_unique = []
    for t in zim_titles:
        if t not in seen:
            seen.add(t)
            zim_titles_unique.append(t)
    print(f"  ZIM titles: {len(zim_titles_unique)} unique ({len(zim_titles)} total)")

    # 2. API titles
    print("\nStep 2: Loading live API titles (allpages)...")
    api_titles = load_api_titles()
    print(f"  API titles: {len(api_titles)}")

    # 3. Build mapping
    print("\nStep 3: Matching ZIM → API...")
    result = build_title_map(zim_titles_unique, api_titles)

    # ── Summary ───────────────────────────────────────────────────────────────

    n_exact   = len(result["exact"])
    n_fuzzy   = len(result["fuzzy"])
    n_zim     = len(result["zim_only"])
    n_api     = len(result["api_only"])
    n_zim_tot = len(zim_titles_unique)

    print(f"\n{'='*60}")
    print(f"ZIM titles:          {n_zim_tot}")
    print(f"API titles:          {len(api_titles)}")
    print(f"Exact matches:       {n_exact} ({100*n_exact//max(n_zim_tot,1)}%)")
    print(f"Fuzzy matches:       {n_fuzzy} ({100*n_fuzzy//max(n_zim_tot,1)}%)")
    print(f"ZIM-only (no match): {n_zim} → deleted/renamed in live API")
    print(f"API-only (new):      {n_api} → added after Oct 2025")

    if result["fuzzy"]:
        print(f"\nFuzzy matches (sample, ratio≥{RATIO_THRESHOLD}):")
        for m in result["fuzzy"][:20]:
            print(f"  {m['zim']!r:35s} → {m['api']!r:35s}  ({m['ratio']})")
        if len(result["fuzzy"]) > 20:
            print(f"  … +{len(result['fuzzy'])-20} more")

    if result["zim_only"]:
        print(f"\nZIM-only titles (not in live API — {len(result['zim_only'])} total, first 30):")
        for t in result["zim_only"][:30]:
            print(f"  {t!r}")
        if len(result["zim_only"]) > 30:
            print(f"  … +{len(result['zim_only'])-30} more")

    if result["api_only"]:
        print(f"\nAPI-only titles (added after Oct 2025 — {len(result['api_only'])} total, first 20):")
        for t in result["api_only"][:20]:
            print(f"  {t!r}")
        if len(result["api_only"]) > 20:
            print(f"  … +{len(result['api_only'])-20} more")

    # ── ZIM-Titel für Testfälle ───────────────────────────────────────────────
    test_cases = ["Elefant", "Beethoven", "Fußball", "Dinosaurier", "Berlin"]
    print(f"\nTest cases — how are they stored in ZIM?")
    norm_to_zim = {_norm(t): t for t in zim_titles_unique}
    for tc in test_cases:
        nc = _norm(tc)
        if tc in seen:
            print(f"  '{tc}' → exact ZIM title: '{tc}'")
        else:
            # Find best ZIM match
            best_r, best_z = 0.0, None
            for nz, tz in norm_to_zim.items():
                r = difflib.SequenceMatcher(None, nc, nz).ratio()
                if r > best_r:
                    best_r, best_z = r, tz
            print(f"  '{tc}' → best ZIM match: {best_z!r} (ratio={best_r:.3f})")

    # ── Save ──────────────────────────────────────────────────────────────────

    # Build a flat lookup dict: zim_title → api_title for easy use
    lookup: dict[str, str] = {}
    for m in result["exact"]:
        lookup[m["zim"]] = m["api"]
    for m in result["fuzzy"]:
        lookup[m["zim"]] = m["api"]

    output = {
        "stats": {
            "zim_total":   n_zim_tot,
            "api_total":   len(api_titles),
            "exact":       n_exact,
            "fuzzy":       n_fuzzy,
            "zim_only":    n_zim,
            "api_only":    n_api,
            "ratio_threshold": RATIO_THRESHOLD,
        },
        "lookup":   lookup,        # zim_title → api_title (for build_image_map.py)
        "exact":    result["exact"],
        "fuzzy":    result["fuzzy"],
        "zim_only": result["zim_only"],
        "api_only": result["api_only"],
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"\nSaved → {OUTPUT_FILE}")
    print(f"Use 'lookup' dict in build_image_map.py to translate ZIM titles → API titles.")


if __name__ == "__main__":
    main()
