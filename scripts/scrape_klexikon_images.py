#!/usr/bin/env python3
"""
scrape_klexikon_images.py — Mappt ZIM-Bild-Referenzen → Commons-Dateinamen.

SCHRITT 1  Live-Klexikon-Seite scrapen → Datei:-Links in Reihenfolge
SCHRITT 2  Pro Datei-Seite: vollständige Commons-URL extrahieren
SCHRITT 3  ZIM-HTML → <img src> in Reihenfolge (hash oder named)
SCHRITT 4  Positions-Mapping: zim_ref[i] = filename[i]

Env-Variablen:
  ZIM_FILE   Pfad zum .zim (default: klexikon.zim; leer = nur Schritt 1+2)
  ARTICLES   Komma-getrennte Artikel-Titel
  DELAY      Sekunden zwischen Requests (default: 1.0)
  OUTPUT     Ausgabedatei (default: scrape_image_results.json)
"""

import json, lzma, os, re, struct, sys, time
from pathlib import Path
from urllib.parse import unquote, quote
from urllib.request import urlopen, Request

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import zstandard as _zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

ZIM_FILE = os.environ.get("ZIM_FILE", "klexikon.zim")
ARTICLES = [a.strip() for a in os.environ.get("ARTICLES", "Elefanten,Fußball,Berlin").split(",")]
DELAY    = float(os.environ.get("DELAY", "1.0"))
OUTPUT   = Path(os.environ.get("OUTPUT", "scrape_image_results.json"))

KLEXIKON  = "https://klexikon.zum.de"
ZIM_MAGIC = 0x044D495A

# Bilder herausfiltern: Logos, Icons, Karten-SVGs, Klexikon-Branding
FILTER_PREFIXES = (
    "commons-logo", "wikimedia", "cc-", "pd-", "gfdl",
    "question_book", "ambox", "portal-", "wikidata-",
    "symbol_", "icon_", "semiprotect", "edit-clear",
    "nuvola", "gnome-", "crystal_", "tango-",
    "flag_", "flag-", "minikl", "klexikon_k",
    "edit-", "portal_", "red_pog", "green_pog", "blue_pog",
)
# Animierte GIF-Frames: Muybridge_horse_animated_frame_0001.gif
_FRAME_RE = re.compile(r"_frame_\d+\.", re.IGNORECASE)
FILTER_AUDIO_EXTS = {".ogg", ".oga", ".wav", ".mp3", ".opus", ".flac"}


def _should_filter(filename: str) -> bool:
    # Normalisiere: Leerzeichen → Unterstrich, damit Filter-Prefixe greifen
    name = filename.lower().replace(" ", "_").rsplit("/", 1)[-1]
    ext  = Path(name).suffix
    if ext == ".svg":
        return True
    if ext in FILTER_AUDIO_EXTS:
        return True
    if _FRAME_RE.search(name):
        return True
    for p in FILTER_PREFIXES:
        if name.startswith(p):
            return True
    return False


# ── HTTP ─────────────────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "WissensfreundBot/1.0 (scrape-klexikon-images)"}

def _get(url: str) -> str:
    req = Request(url, headers=_HEADERS)
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


# ── SCHRITT 1: Live-Seite → Datei-Namen ─────────────────────────────────────────

def scrape_article_filenames(article: str) -> list[str]:
    """
    Gibt Datei-Namen in Reihenfolge des ersten Auftretens zurück.
    Jeder Dateiname wird dedupliziert (Thumb- + Magnify-Link = selbe Datei).
    """
    url  = f"{KLEXIKON}/wiki/{quote(article.replace(' ', '_'))}"
    html = _get(url)
    time.sleep(DELAY)

    seen:   set[str]  = set()
    result: list[str] = []
    for m in re.finditer(r'href="/wiki/Datei:([^"#]+)"', html, re.IGNORECASE):
        fn = unquote(m.group(1)).replace("_", " ")   # kanonisch mit Leerzeichen
        key = fn.lower()
        if key in seen:
            continue
        seen.add(key)
        if _should_filter(fn):
            continue
        result.append(fn)
    return result


# ── SCHRITT 2: Datei-Seite → Commons-URL ─────────────────────────────────────────

_FULL_IMG_RE  = re.compile(
    r'<div[^>]+id="file"[^>]*>.*?<a\s+href="(https://upload\.wikimedia\.org/wikipedia/commons/(?!thumb/)[^"]+)"',
    re.DOTALL | re.IGNORECASE,
)
_UPLOAD_RE    = re.compile(
    r'href="(https://upload\.wikimedia\.org/wikipedia/commons/(?!thumb/)[^"]+)"',
    re.IGNORECASE,
)
_COMMONS_PAGE_RE = re.compile(
    r'href="(https://commons\.wikimedia\.org/wiki/File:[^"]+)"',
    re.IGNORECASE,
)


def scrape_commons_url(filename: str) -> str | None:
    """
    Ruft https://klexikon.zum.de/wiki/Datei:{filename} auf
    und extrahiert die volle Commons-URL (ohne /thumb/).
    """
    url = f"{KLEXIKON}/wiki/Datei:{quote(filename.replace(' ', '_'))}"
    try:
        html = _get(url)
        time.sleep(DELAY)
    except Exception as e:
        print(f"    WARN Datei-Seite nicht erreichbar: {filename}: {e}", file=sys.stderr)
        return None

    # Bevorzuge fullImageLink-Block (erste direkte URL ohne /thumb/)
    m = _FULL_IMG_RE.search(html)
    if m:
        return m.group(1)

    # Fallback: irgendein upload-Link ohne /thumb/
    m = _UPLOAD_RE.search(html)
    if m:
        return m.group(1)

    # Letzter Ausweg: Commons-Seiten-URL
    m = _COMMONS_PAGE_RE.search(html)
    if m:
        return m.group(1)

    return None


# ── ZIM-Helpers ──────────────────────────────────────────────────────────────────

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
        if comp in (0, 1):  return data
        if comp == 4:       return lzma.decompress(data)
        if comp in (5, 8):
            return _zstd.ZstdDecompressor().decompress(data, max_output_size=32 << 20) if HAS_ZSTD else None
        if comp == 6:       return lzma.decompress(data)
    except Exception:
        pass
    return None


def build_zim_index(zim_path: Path) -> tuple[dict, list, int]:
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

        f.seek(mlp)
        mimes: list[str] = []
        while True:
            mt = _read_cstr(f)
            if not mt: break
            mimes.append(mt)
        html_idx = {i for i, m in enumerate(mimes) if "html" in m.lower()}

        f.seek(cpp)
        cluster_ptrs: list[int] = []
        for _ in range(cc):
            r = f.read(8)
            if len(r) < 8: break
            cluster_ptrs.append(struct.unpack_from("<Q", r)[0])

        for i in range(ec):
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
            url   = _read_cstr(f)
            title = _read_cstr(f)
            if not title:
                title = unquote(url).rsplit("/", 1)[-1]
            norm = " ".join(title.strip().replace("_", " ").lower().split())
            if norm:
                title_index[norm] = (title, cn, bn)
    return title_index, cluster_ptrs, eof


def read_blob(f, cluster_ptrs: list, eof: int, cn: int, bn: int) -> bytes | None:
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


# ── SCHRITT 3: ZIM-HTML → Bild-Referenzen ────────────────────────────────────────

# Muster 1: <img src="../../_assets_/abc123.jpg">
_ASSETS_RE = re.compile(r'_assets_/([^"\'>\s]+)', re.IGNORECASE)
# Muster 2: <img src="../../I/langde-220px-Filename.jpg">
_NAMED_RE  = re.compile(r'["\'](?:\.\./)*I/([^"\'>\s]+)["\']', re.IGNORECASE)
# Alle img src-Werte
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

_BOILERPLATE = re.compile(
    r'^(blank|spacer|pixel|transparent|1x1|dot|clear)',
    re.IGNORECASE
)


def _classify_src(src: str) -> dict:
    """Klassifiziert einen ZIM img src-Wert."""
    base = src.rsplit("/", 1)[-1]

    # _assets_/{hash}.ext
    m = _ASSETS_RE.search(src)
    if m:
        return {"type": "hash", "ref": m.group(1)}

    # I/langde-Npx-Filename.ext  →  Filename.ext
    m = re.match(r'^[a-z]{2,8}-\d+px-(.+)', base, re.IGNORECASE)
    if m:
        name = m.group(1)
        if name.lower().endswith(".svg.png"):
            name = name[:-4]  # SVG wurde als PNG gerendert
        return {"type": "named", "ref": name}

    return {"type": "unknown", "ref": base}


def extract_zim_img_refs(html: str) -> list[dict]:
    """
    Gibt alle <img>-Referenzen aus ZIM-HTML in Reihenfolge zurück.
    Jede Referenz einmal (dedupliziert per src).
    """
    seen:   set[str]   = set()
    result: list[dict] = []
    for m in _IMG_SRC_RE.finditer(html):
        src  = m.group(1)
        base = src.rsplit("/", 1)[-1].lower()
        if base in seen:
            continue
        if _BOILERPLATE.match(base):
            continue
        seen.add(base)
        info = _classify_src(src)
        info["src"] = src
        result.append(info)
    return result


# ── SCHRITT 4: Mapping + Ausgabe ─────────────────────────────────────────────────

def process_article(
    article:      str,
    zim_index:    dict | None,
    cluster_ptrs: list | None,
    eof:          int | None,
    zim_f,
) -> dict:
    print(f"\n{'='*65}")
    print(f"ARTIKEL: {article}")
    print(f"{'='*65}")

    # ── Schritt 1 ────────────────────────────────────────────────
    print("Schritt 1 — Scrape live Klexikon-Seite …")
    live_files = scrape_article_filenames(article)
    n_live = len(live_files)
    print(f"  Datei-Links (dedupliziert, gefiltert): {n_live}")

    plausibility_ok = True
    if not (3 <= n_live <= 20):
        print(f"  WARN: {n_live} Bilder ausserhalb 3-20")
        plausibility_ok = False

    # ── Schritt 2 ────────────────────────────────────────────────
    print("Schritt 2 — Datei-Seiten → Commons-URLs …")
    commons_entries: list[dict] = []
    no_commons = 0
    for fn in live_files:
        cu = scrape_commons_url(fn)
        if cu is None:
            no_commons += 1
            print(f"  WARN keine Commons-URL: {fn}")
        commons_entries.append({"filename": fn, "commons_url": cu})

    if live_files and no_commons / n_live > 0.5:
        print(f"  STOP: {no_commons}/{n_live} ohne Commons-URL (>50%)")
        return {"article": article, "status": "STOP_no_commons",
                "live_count": n_live, "no_commons": no_commons, "data": []}

    # ── Schritt 3 (nur mit ZIM) ───────────────────────────────────
    zim_refs: list[dict] = []
    if zim_index is not None:
        print("Schritt 3 — ZIM-HTML laden …")
        norm  = " ".join(article.strip().replace("_", " ").lower().split())
        entry = zim_index.get(norm)
        if not entry:
            print(f"  WARN: '{article}' nicht im ZIM-Index")
        else:
            _, cn, bn = entry
            blob = read_blob(zim_f, cluster_ptrs, eof, cn, bn)
            if not blob:
                print(f"  WARN: ZIM-Blob nicht lesbar")
            else:
                html     = blob.decode("utf-8", errors="replace")
                zim_refs = extract_zim_img_refs(html)
                print(f"  ZIM <img>-Referenzen: {len(zim_refs)}")
                # Zeige Typen-Verteilung
                types = {}
                for r in zim_refs:
                    types[r["type"]] = types.get(r["type"], 0) + 1
                for t, c in types.items():
                    print(f"    {t}: {c}")

    # ── Schritt 4: Positional Mapping ────────────────────────────
    n_map = min(n_live, len(zim_refs)) if zim_refs else 0
    mapped: list[dict] = []
    for i in range(n_map):
        zr  = zim_refs[i]
        ce  = commons_entries[i]
        rec: dict = {
            "position":   i,
            "filename":   ce["filename"],
            "commons_url": ce["commons_url"],
        }
        if zr["type"] == "hash":
            rec["hash"] = zr["ref"]
        elif zr["type"] == "named":
            rec["zim_named"] = zr["ref"]
        else:
            rec["zim_unknown"] = zr["ref"]
        mapped.append(rec)

    # Artikel ohne ZIM: nur Live-Daten ausgeben
    if not zim_refs:
        for i, ce in enumerate(commons_entries):
            mapped.append({"position": i, "filename": ce["filename"],
                           "commons_url": ce["commons_url"]})

    # ── Konsolen-Ausgabe ─────────────────────────────────────────
    print()
    for r in mapped:
        pos  = r["position"]
        fn   = r["filename"]
        cu   = r.get("commons_url", "")
        extra = ""
        if "hash" in r:
            extra = f"  hash={r['hash']}"
        elif "zim_named" in r:
            extra = f"  zim_named={r['zim_named'][:40]}"
        cu_short = (cu[:70] + "…") if cu and len(cu) > 70 else (cu or "(kein Commons-Link)")
        print(f"  [{pos}] {fn}")
        print(f"       {cu_short}{extra}")

    if zim_refs and len(zim_refs) != n_live:
        print(f"\n  INFO: live={n_live} zim={len(zim_refs)} → nur {n_map} Paare gemappt")

    status = "OK" if plausibility_ok else "WARN_count"
    return {
        "article":     article,
        "status":      status,
        "live_count":  n_live,
        "zim_count":   len(zim_refs),
        "mapped":      n_map,
        "no_commons":  no_commons,
        "data":        mapped,
    }


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    zim_path = Path(ZIM_FILE)
    has_zim  = zim_path.exists()

    if has_zim:
        print(f"ZIM: {zim_path} ({zim_path.stat().st_size // 1_048_576} MB)")
        print("Baue ZIM-Index …")
        zim_index, cluster_ptrs, eof = build_zim_index(zim_path)
        print(f"  {len(zim_index)} Einträge")
    else:
        print(f"INFO: ZIM nicht gefunden ({ZIM_FILE}) — nur Schritt 1+2 aktiv")
        zim_index = cluster_ptrs = eof = None

    all_results = []
    if has_zim:
        with open(zim_path, "rb") as zim_f:
            for article in ARTICLES:
                r = process_article(article, zim_index, cluster_ptrs, eof, zim_f)
                all_results.append(r)
    else:
        for article in ARTICLES:
            r = process_article(article, None, None, None, None)
            all_results.append(r)

    OUTPUT.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nGespeichert → {OUTPUT}")

    # Zusammenfassung
    print(f"\n{'='*65}")
    print("ZUSAMMENFASSUNG")
    print(f"{'='*65}")
    total_mapped   = sum(r.get("mapped", 0)     for r in all_results)
    total_no_comm  = sum(r.get("no_commons", 0) for r in all_results)
    total_live     = sum(r.get("live_count", 0) for r in all_results)
    stops          = [r["article"] for r in all_results if r["status"].startswith("STOP")]
    for r in all_results:
        print(f"  {r['article']:20s}  live={r.get('live_count',0):2d}  "
              f"zim={r.get('zim_count','—'):>2}  mapped={r.get('mapped','—'):>2}  "
              f"no_commons={r.get('no_commons',0)}  [{r['status']}]")
    if stops:
        print(f"\nSTOP-Artikel: {stops}")
        sys.exit(1)


if __name__ == "__main__":
    main()
