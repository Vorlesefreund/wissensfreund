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

ZIM_FILE     = os.environ.get("ZIM_FILE", "klexikon.zim")
ARTICLES     = [a.strip() for a in os.environ.get("ARTICLES", "Elefanten,Fußball,Berlin").split(",") if a.strip()]
DELAY        = float(os.environ.get("DELAY", "1.0"))
OUTPUT       = Path(os.environ.get("OUTPUT", "scrape_image_results.json"))
SKIP_COMMONS = os.environ.get("SKIP_COMMONS", "0") == "1"
ALL_ARTICLES = os.environ.get("ALL_ARTICLES", "0") == "1"
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "0"))  # 0 = kein Limit

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

def scrape_article_filenames(article: str) -> list[dict] | None:
    """
    Gibt Liste von {filename, caption} zurück, oder None bei HTTP-Fehler (404 etc.).
    Jeder Dateiname wird dedupliziert (Thumb- + Magnify-Link = selbe Datei).
    Caption wird aus thumbcaption/figcaption/gallerytext extrahiert.
    """
    url = f"{KLEXIKON}/wiki/{quote(article.replace(' ', '_'))}"
    try:
        html = _get(url)
    except Exception as e:
        print(f"  WARN Seite nicht abrufbar ({type(e).__name__}): {url} — {e}", file=sys.stderr)
        return None
    time.sleep(DELAY)

    seen:   set[str]   = set()
    result: list[dict] = []
    for m in re.finditer(r'href="/wiki/Datei:([^"#]+)"', html, re.IGNORECASE):
        fn  = unquote(m.group(1)).replace("_", " ")
        key = fn.lower()
        if key in seen:
            continue
        seen.add(key)
        if _should_filter(fn):
            continue
        caption = _extract_caption(html[m.end():])
        result.append({"filename": fn, "caption": caption or None})
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

_STRIP_TAGS = re.compile(r'<[^>]+>')

def _extract_caption(html_from_here: str) -> str:
    """
    Extrahiert den deutschen Bildtext aus den drei Klexikon-Container-Formaten.
    Sucht im Fenster von 3000 Zeichen nach dem Datei:-Link.
    """
    chunk = html_from_here[:3000]

    # Format 1: <div class="thumbcaption"> — enthält zuerst ein Magnify-Div,
    # dann den eigentlichen Text. Das erste </div> schließt das Magnify-Div,
    # danach folgt der Caption-Text bis zum schließenden </div>.
    m = re.search(
        r'class="thumbcaption"[^>]*>.*?</div>\s*(.*?)\s*</div>',
        chunk, re.DOTALL | re.IGNORECASE
    )
    if m:
        t = re.sub(r'\s+', ' ', _STRIP_TAGS.sub('', m.group(1))).strip()
        if t:
            return t

    # Format 2: <figcaption> (modernes MediaWiki / figure-Elemente)
    m = re.search(r'<figcaption[^>]*>(.*?)</figcaption>', chunk, re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r'\s+', ' ', _STRIP_TAGS.sub('', m.group(1))).strip()
        if t:
            return t

    # Format 3: <div class="gallerytext"> (MediaWiki-Galerien)
    m = re.search(r'class="gallerytext"[^>]*>(.*?)</div>', chunk, re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r'\s+', ' ', _STRIP_TAGS.sub('', m.group(1))).strip()
        if t:
            return t

    return ''


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
    if live_files is None:
        return {"article": article, "status": "WARN_404",
                "has_gallery": False, "live_count": 0, "zim_count": 0,
                "mapped": 0, "no_commons": 0, "data": []}
    n_live = len(live_files)
    print(f"  Datei-Links (dedupliziert, gefiltert): {n_live}")

    plausibility_ok = True
    if not (3 <= n_live <= 20):
        print(f"  WARN: {n_live} Bilder ausserhalb 3-20")
        plausibility_ok = False

    # ── Schritt 2 ────────────────────────────────────────────────
    commons_entries: list[dict] = []
    no_commons = 0
    if SKIP_COMMONS:
        print("Schritt 2 — übersprungen (SKIP_COMMONS=1)")
        for item in live_files:
            commons_entries.append({
                "filename":    item["filename"],
                "caption":     item["caption"],
                "commons_url": None,
            })
    else:
        print("Schritt 2 — Datei-Seiten → Commons-URLs …")
        for item in live_files:
            fn = item["filename"]
            cu = scrape_commons_url(fn)
            if cu is None:
                no_commons += 1
                print(f"  WARN keine Commons-URL: {fn}")
            commons_entries.append({
                "filename":    fn,
                "caption":     item["caption"],
                "commons_url": cu,
            })

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
            "position":    i,
            "filename":    ce["filename"],
            "caption":     ce["caption"],
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
                           "caption": ce["caption"], "commons_url": ce["commons_url"]})

    # ── Konsolen-Ausgabe ─────────────────────────────────────────
    print()
    for r in mapped:
        pos  = r["position"]
        fn   = r["filename"]
        cu   = r.get("commons_url", "")
        cap  = r.get("caption") or ""
        extra = ""
        if "hash" in r:
            extra = f"  hash={r['hash']}"
        elif "zim_named" in r:
            extra = f"  zim_named={r['zim_named'][:40]}"
        cu_short = (cu[:70] + "…") if cu and len(cu) > 70 else (cu or "(kein Commons-Link)")
        print(f"  [{pos}] {fn}")
        if cap:
            print(f"       Bildtext: {cap[:100]}{'…' if len(cap)>100 else ''}")
        print(f"       {cu_short}{extra}")

    # Gallery-Erkennung: live >> zim deutet auf MediaWiki-<gallery>-Block hin,
    # den Kiwix nicht als _assets_/-img rendert.
    zim_n      = len(zim_refs)
    has_gallery = zim_index is not None and n_live > zim_n + 3
    if has_gallery:
        print(f"\n  INFO: has_gallery=true  live={n_live} zim={zim_n} → Gallery-Lücke {n_live - zim_n} Bilder")
    elif zim_refs and zim_n != n_live:
        print(f"\n  INFO: live={n_live} zim={zim_n} → nur {n_map} Paare gemappt")

    status = "OK" if plausibility_ok else "WARN_count"
    return {
        "article":     article,
        "status":      status,
        "has_gallery": has_gallery,
        "live_count":  n_live,
        "zim_count":   zim_n,
        "mapped":      n_map,
        "no_commons":  no_commons,
        "data":        mapped,
    }


# ── Main ─────────────────────────────────────────────────────────────────────────

def _all_article_titles(zim_index: dict) -> list[str]:
    """Gibt alle Original-Titel aus dem ZIM-Index zurück (kein Redirect-Filter nötig,
    build_zim_index liefert bereits nur HTML-Einträge)."""
    seen_norm: set[str] = set()
    titles: list[str]   = []
    for norm, (title, _cn, _bn) in zim_index.items():
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        titles.append(title)
    titles.sort()
    return titles


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

    # Artikel-Liste bestimmen
    if ALL_ARTICLES:
        if not has_zim:
            print("ERROR: ALL_ARTICLES=1 erfordert ZIM_FILE"); sys.exit(1)
        articles = _all_article_titles(zim_index)
        print(f"ALL_ARTICLES: {len(articles)} Artikel aus ZIM-Index")
    else:
        articles = ARTICLES

    if MAX_ARTICLES and len(articles) > MAX_ARTICLES:
        print(f"MAX_ARTICLES={MAX_ARTICLES}: kürze auf {MAX_ARTICLES} Artikel")
        articles = articles[:MAX_ARTICLES]

    if SKIP_COMMONS:
        print("SKIP_COMMONS=1: Datei-Seiten werden nicht abgerufen")

    all_results = []
    if has_zim:
        with open(zim_path, "rb") as zim_f:
            for i, article in enumerate(articles, 1):
                if ALL_ARTICLES:
                    print(f"\n[{i}/{len(articles)}]", end="")
                r = process_article(article, zim_index, cluster_ptrs, eof, zim_f)
                all_results.append(r)
                # Periodisch speichern (alle 50 Artikel) damit Teilergebnisse verfügbar sind
                if ALL_ARTICLES and i % 50 == 0:
                    OUTPUT.write_text(json.dumps(all_results, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
                    print(f"  [Zwischenspeichern: {i} Artikel]")
    else:
        for article in articles:
            r = process_article(article, None, None, None, None)
            all_results.append(r)

    OUTPUT.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nGespeichert → {OUTPUT}")

    # ── Statistik berechnen ───────────────────────────────────────────────────
    total         = len(all_results)
    total_mapped  = sum(r.get("mapped", 0)     for r in all_results)
    total_live    = sum(r.get("live_count", 0) for r in all_results)
    stops         = [r["article"] for r in all_results if r["status"].startswith("STOP")]

    # perfect_match: live_count == mapped (inkl. Artikel ohne Bilder)
    perfect_match  = sum(1 for r in all_results if r.get("live_count", 0) == r.get("mapped", 0))
    small_mismatch = sum(1 for r in all_results
                         if 0 < r.get("live_count", 0) - r.get("mapped", 0) <= 3
                         and not r.get("has_gallery"))
    large_mismatch = sum(1 for r in all_results
                         if r.get("live_count", 0) - r.get("mapped", 0) > 3
                         and not r.get("has_gallery"))
    gallery_arts   = [r for r in all_results if r.get("has_gallery")]

    # ── gallery_articles.json ─────────────────────────────────────────────────
    gallery_path = OUTPUT.with_name("gallery_articles.json")
    gallery_out  = [
        {
            "article":    r["article"],
            "live_count": r.get("live_count", 0),
            "zim_count":  r.get("zim_count", 0),
            "mapped":     r.get("mapped", 0),
            "gap":        r.get("live_count", 0) - r.get("mapped", 0),
            "filenames":  [d["filename"] for d in r.get("data", [])
                           if "hash" not in d and "zim_named" not in d],
        }
        for r in gallery_arts
    ]
    gallery_path.write_text(json.dumps(gallery_out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Gallery-Artikel → {gallery_path}  ({len(gallery_out)} Einträge)")

    # ── run_summary.json ──────────────────────────────────────────────────────
    pct_perfect = perfect_match * 100 // max(total, 1)
    summary = {
        "total_articles":     total,
        "perfect_match":      perfect_match,
        "perfect_match_pct":  pct_perfect,
        "small_mismatch":     small_mismatch,
        "large_mismatch":     large_mismatch,
        "gallery_count":      len(gallery_arts),
        "total_images_live":  total_live,
        "total_images_mapped": total_mapped,
        "stops":              len(stops),
        "plausibility":       "OK" if pct_perfect >= 70 else "FAIL",
    }
    summary_path = OUTPUT.with_name("run_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("ZUSAMMENFASSUNG")
    print(f"{'='*65}")
    print(f"  Artikel gesamt:       {total}")
    print(f"  Perfect match:        {perfect_match}  ({pct_perfect}%)")
    print(f"  Small mismatch (1-3): {small_mismatch}")
    print(f"  Large mismatch (>3):  {large_mismatch}")
    print(f"  Gallery-Artikel:      {len(gallery_arts)}")
    print(f"  Live-Bilder gesamt:   {total_live}")
    print(f"  Gemappte Hash-Paare:  {total_mapped}")
    print(f"  STOP-Artikel:         {len(stops)}")
    print(f"  Plausibilität:        {summary['plausibility']}")

    if not ALL_ARTICLES:
        for r in all_results:
            gal = " [GALLERY]" if r.get("has_gallery") else ""
            print(f"  {r['article']:20s}  live={r.get('live_count',0):2d}  "
                  f"zim={r.get('zim_count','—'):>2}  mapped={r.get('mapped','—'):>2}  "
                  f"no_commons={r.get('no_commons',0)}  [{r['status']}]{gal}")

    # ── Plausibilitätsprüfung ─────────────────────────────────────────────────
    if pct_perfect < 70:
        print(f"\n⚠️  PLAUSIBILITÄT FEHLGESCHLAGEN: perfect_match={pct_perfect}% < 70%")
        print(f"   Erwartet: ~84% (~2.950 von ~3.500 Artikeln)")
        print(f"   → Vollrun-Ergebnis NICHT verwenden — Ursache prüfen!")
        sys.exit(1)

    if stops and not ALL_ARTICLES:
        print(f"\nSTOP-Artikel ({len(stops)}): {stops[:10]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
