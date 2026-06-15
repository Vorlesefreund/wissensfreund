#!/usr/bin/env python3
"""
sound_compare.py  v2  (2026-06-15)
Vergleicht Freesound vs. Openverse auf ~100 kuratierten Themen.
Zapsplat: kein öffentlicher API-Endpunkt verfügbar → nicht eingebunden.

Phase 1 — Suche:    Freesound + Openverse parallel (ThreadPool)
Phase 2 — Clips:    Preview-Download → 4s-Clip extrahieren (pydub/ffmpeg)
Phase 3 — Report:   sound_compare.html mit eingebettetem <audio>-Player

Aufruf:
  python sound_compare.py                  # alle 100 Themen
  python sound_compare.py --limit 10       # erste 10 (Schnelltest)
  python sound_compare.py --no-freesound   # nur Openverse
  python sound_compare.py --no-clips       # ohne Download/Clip

Voraussetzungen:
  pip install requests
  winget install ffmpeg   (oder manuell in PATH)
"""

import os, sys, json, time, argparse, html, pathlib, threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Verzeichnis & Env ─────────────────────────────────────────────────────────
REPO_ROOT = pathlib.Path(__file__).parent
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

FS_KEY      = os.environ.get("FREESOUND_API_KEY", "")
OUT_HTML    = REPO_ROOT / "sound_compare.html"
OUT_JSON    = REPO_ROOT / "sound_compare_results.json"
CAND_DIR    = REPO_ROOT / "sound_compare_candidates"
N_RESULTS   = 5        # Ergebnisse pro Quelle
DUR_MIN_S   = 1.0      # Mindestlänge Sekunden
DUR_MAX_S   = 15.0     # Maximallänge Sekunden
FS_DELAY    = 0.35     # Pause zwischen Freesound-Calls (Rate-Limit-Schutz)
CLIP_MS     = 4000     # Clip-Länge in Millisekunden

# ── TOPICS ────────────────────────────────────────────────────────────────────
# Format: (slug, englische Suchanfrage, deutsches Label)
# Liste vom User begonnen; nach Abbruch bei "schimpanse" sinngemäß vervollständigt.
TOPICS = [
    # Natur – Wetter & Phänomene (15)
    ("regen_leicht",   "light rain soft",             "Regen (leicht)"),
    ("regen_stark",    "heavy rain thunderstorm",      "Regen (stark)"),
    ("gewitter",       "thunder lightning storm",      "Gewitter"),
    ("wind_sturm",     "storm wind gust strong",       "Sturm"),
    ("wind_leicht",    "gentle breeze wind",           "Wind (leicht)"),
    ("wellen_meer",    "ocean waves sea shore",        "Meeresrauschen"),
    ("wasserfall",     "waterfall splashing",          "Wasserfall"),
    ("bach",           "stream brook babbling",        "Bach/Fluss"),
    ("feuer",          "fire crackling wood",          "Feuer"),
    ("vulkan",         "volcano eruption lava",        "Vulkan"),
    ("donner",         "thunder clap crack loud",      "Donner"),
    ("blitz",          "lightning bolt strike",        "Blitz"),
    ("erdbeben",       "earthquake rumble ground",     "Erdbeben"),
    ("schneesturm",    "blizzard snow wind cold",      "Schneesturm"),
    ("nebel",          "foghorn fog horn coast",       "Nebelhorn"),
    # Tiere – Säugetiere (22)
    ("elefant",        "elephant trumpet call",        "Elefant"),
    ("loewe",          "lion roar growl",              "Löwe"),
    ("tiger",          "tiger roar jungle",            "Tiger"),
    ("wolf",           "wolf howl wild",               "Wolf"),
    ("baer",           "bear growl roar",              "Bär"),
    ("gorilla",        "gorilla chest beat",           "Gorilla"),
    ("schimpanse",     "chimpanzee call jungle",       "Schimpanse"),
    ("affe",           "monkey chatter howler",        "Affe"),
    ("pferd",          "horse neigh whinny",           "Pferd"),
    ("kuh",            "cow moo cattle",               "Kuh"),
    ("schwein",        "pig oink grunt",               "Schwein"),
    ("huhn",           "chicken cluck hen",            "Huhn"),
    ("frosch",         "frog croak pond",              "Frosch"),
    ("fuchs",          "fox bark call wild",           "Fuchs"),
    ("hirsch",         "deer stag bugling rut",        "Hirsch"),
    ("katze",          "cat meow purring",             "Katze"),
    ("hund",           "dog barking",                  "Hund"),
    ("delfin",         "dolphin click whistle",        "Delfin"),
    ("wal",            "whale song humpback",          "Wal"),
    ("hai",            "underwater bubbles deep sea",  "Hai"),
    ("pinguin",        "penguin colony call",          "Pinguin"),
    ("zebra",          "zebra bray call",              "Zebra"),
    # Tiere – Vögel (7)
    ("adler",          "eagle cry screech",            "Adler"),
    ("eule",           "owl hoot night",               "Eule"),
    ("ente",           "duck quack water",             "Ente"),
    ("moewe",          "seagull cry coast",            "Möwe"),
    ("kraehe",         "crow caw",                     "Krähe"),
    ("papagei",        "parrot squawk tropical",       "Papagei"),
    ("vogelchor",      "birdsong morning chorus dawn", "Vogelchor"),
    # Tiere – Insekten & Reptilien (5)
    ("biene",          "bee buzz hive",                "Biene"),
    ("grillen",        "cricket chirp night",          "Grillen"),
    ("muecke",         "mosquito buzz flying insect",  "Mücke"),
    ("schlange",       "snake hiss rattle",            "Schlange"),
    ("krokodil",       "crocodile hiss snap",          "Krokodil"),
    # Lebensräume & Umgebungen (8)
    ("wald",           "forest birds ambience",        "Wald"),
    ("dschungel",      "tropical jungle rain forest",  "Dschungel"),
    ("savanne",        "savanna africa ambient",       "Savanne"),
    ("wueste",         "desert hot dry wind",          "Wüste"),
    ("ozean_tief",     "underwater ocean deep sea",    "Ozean"),
    ("gebirge",        "mountain alpine wind",         "Gebirge"),
    ("hoehle",         "cave dripping echo",           "Höhle"),
    ("sumpf",          "swamp frogs marsh night",      "Sumpf"),
    # Verkehr (8)
    ("auto",           "car engine passing drive",     "Auto"),
    ("zug",            "steam train locomotive",       "Zug"),
    ("flugzeug",       "airplane jet engine takeoff",  "Flugzeug"),
    ("schiff",         "ship foghorn port",            "Schiff"),
    ("motorrad",       "motorcycle engine revving",    "Motorrad"),
    ("hubschrauber",   "helicopter rotor blades",      "Hubschrauber"),
    ("fahrrad",        "bicycle bell ring",            "Fahrrad"),
    ("traktor",        "tractor farm engine",          "Traktor"),
    # Alltag & Stadt (9)
    ("glocke",         "church bell ringing toll",     "Glocke"),
    ("markt",          "outdoor market crowd busy",    "Markt"),
    ("spielplatz",     "children playground laugh",    "Spielplatz"),
    ("bauernhof",      "farm animals barn yard",       "Bauernhof"),
    ("hammer",         "hammer nail construction",     "Hammer"),
    ("tuer",           "door knock wooden",            "Tür"),
    ("applaus",        "audience applause clapping",   "Applaus"),
    ("kueche",         "kitchen frying sizzle",        "Küche"),
    ("alarm",          "emergency siren alarm loud",   "Sirene"),
    # Musik & Instrumente (10)
    ("trommel",        "drum beat rhythm hit",         "Trommel"),
    ("gitarre",        "acoustic guitar strumming",    "Gitarre"),
    ("klavier",        "piano melody notes",           "Klavier"),
    ("floete",         "flute melody breath",          "Flöte"),
    ("geige",          "violin string bowing",         "Geige"),
    ("trompete",       "trumpet fanfare brass",        "Trompete"),
    ("glockenspiel",   "glockenspiel xylophone notes", "Glockenspiel"),
    ("akkordeon",      "accordion folk music",         "Akkordeon"),
    ("orgel",          "pipe organ church",            "Orgel"),
    ("harfe",          "harp glissando pluck",         "Harfe"),
    # Technik & Weltall (9)
    ("rakete",         "rocket launch space thrust",   "Rakete"),
    ("explosion",      "explosion blast boom",         "Explosion"),
    ("maschine",       "factory machine industrial",   "Fabrik/Maschine"),
    ("computer",       "keyboard typing office",       "Tastatur"),
    ("roboter",        "robot electronic beep",        "Roboter"),
    ("kamera",         "camera shutter click photo",   "Kamera"),
    ("morgengrauen",   "dawn birds morning ambience",  "Morgendämmerung"),
    ("brunnen",        "water fountain splashing",     "Brunnen"),
    ("lachen_kinder",  "children laughing playing",    "Kinderlachen"),
    # Natur – Wasser & Jahreszeiten (7)
    ("hagel",          "hail storm hailstones roof",   "Hagel"),
    ("schnee_schritte","snow footsteps crunching",     "Schnee (Schritte)"),
    ("eis",            "ice cracking freezing cold",   "Eis/Gletscher"),
    ("quelle",         "spring water source bubbling", "Quelle"),
    ("see_ufer",       "lake shore gentle waves",      "Seeufer"),
    ("gebirgsbach",    "mountain stream water rocks",  "Gebirgsbach"),
    ("regen_dach",     "rain on roof patter drops",    "Regen auf Dach"),
]

assert len(TOPICS) == 100, f"TOPICS-Anzahl stimmt nicht: {len(TOPICS)}"


# ── Freesound ─────────────────────────────────────────────────────────────────
_fs_lock = threading.Lock()
_fs_last_call = [0.0]

def _fs_wait():
    with _fs_lock:
        gap = FS_DELAY - (time.time() - _fs_last_call[0])
        if gap > 0:
            time.sleep(gap)
        _fs_last_call[0] = time.time()

def freesound_search(query: str, n: int = N_RESULTS) -> dict:
    if not FS_KEY:
        return {"results": [], "total": 0, "error": "no_key"}
    _fs_wait()
    flt = (
        f"duration:[{DUR_MIN_S} TO {DUR_MAX_S}] "
        'license:("Creative Commons 0" OR "Attribution")'
    )
    params = {
        "query": query,
        "filter": flt,
        "fields": "id,name,username,duration,license,previews",
        "sort": "score",
        "page_size": n,
        "token": FS_KEY,
    }
    try:
        r = requests.get("https://freesound.org/apiv2/search/text/", params=params, timeout=12)
    except Exception as exc:
        return {"results": [], "total": 0, "error": str(exc)}
    if r.status_code == 429:
        return {"results": [], "total": 0, "error": "rate_limited"}
    if not r.ok:
        return {"results": [], "total": 0, "error": f"HTTP {r.status_code}"}
    data = r.json()
    return {
        "results": [
            {
                "id": str(s.get("id", "")),
                "title": s.get("name", ""),
                "author": s.get("username", ""),
                "duration": round(float(s.get("duration", 0)), 1),
                "license": s.get("license", ""),
                "preview_url": s.get("previews", {}).get("preview-hq-mp3", ""),
            }
            for s in data.get("results", [])
        ],
        "total": data.get("count", 0),
        "error": None,
    }


# ── Openverse ─────────────────────────────────────────────────────────────────
def openverse_search(query: str, n: int = N_RESULTS) -> dict:
    params = {
        "q": query,
        "license": "cc0,by",
        "page_size": min(n * 4, 20),
    }
    try:
        r = requests.get("https://api.openverse.org/v1/audio/", params=params, timeout=12)
    except Exception as exc:
        return {"results": [], "total": 0, "error": str(exc)}
    if not r.ok:
        return {"results": [], "total": 0, "error": f"HTTP {r.status_code}"}
    data = r.json()
    dur_min_ms = int(DUR_MIN_S * 1000)
    dur_max_ms = int(DUR_MAX_S * 1000)
    filtered = [
        {
            "id": s.get("id", ""),
            "title": s.get("title", ""),
            "author": s.get("creator", ""),
            "duration": round((s.get("duration") or 0) / 1000, 1),
            "license": s.get("license", ""),
            "preview_url": s.get("url", "") or s.get("audio_url", ""),
            "source": s.get("source", ""),
        }
        for s in data.get("results", [])
        if dur_min_ms <= (s.get("duration") or 0) <= dur_max_ms
    ]
    return {"results": filtered[:n], "total": data.get("result_count", 0), "error": None}


# ── Phase 1: Parallel-Suche ───────────────────────────────────────────────────
def _search_topic(topic: tuple, use_freesound: bool) -> dict:
    slug, query_en, label_de = topic
    fs = freesound_search(query_en) if use_freesound else {"results": [], "total": 0, "error": "disabled"}
    ov = openverse_search(query_en)
    return {"slug": slug, "query_en": query_en, "label_de": label_de,
            "freesound": fs, "openverse": ov}

def run_search(topics: list, use_freesound: bool, workers: int = 4) -> list:
    results = [None] * len(topics)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_search_topic, t, use_freesound): i for i, t in enumerate(topics)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:
                slug, query_en, label_de = topics[idx]
                results[idx] = {"slug": slug, "query_en": query_en, "label_de": label_de,
                                 "freesound": {"results": [], "total": 0, "error": str(exc)},
                                 "openverse": {"results": [], "total": 0, "error": str(exc)}}
            done += 1
            print(f"\r  Suche [{done:3d}/{len(topics)}]", end="", flush=True)
    print()
    return results


# ── Phase 2: Clip-Extraktion ──────────────────────────────────────────────────
def _safe_id(rid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(rid)[:24])

def _download(url: str, dst: pathlib.Path) -> bool:
    if dst.exists() and dst.stat().st_size > 100:
        return True
    try:
        r = requests.get(url, timeout=20, stream=True)
        if not r.ok:
            return False
        dst.write_bytes(r.content)
        return True
    except Exception:
        return False

def extract_clip(src: pathlib.Path, dst: pathlib.Path, duration_ms: int = CLIP_MS) -> bool:
    """4-Sek-Clip ab erstem Ton (Stille am Anfang überspringen) — via ffmpeg."""
    import subprocess, re
    dur_s = duration_ms / 1000

    # Stille am Anfang ermitteln
    start_s = 0.0
    try:
        probe = subprocess.run(
            ["ffmpeg", "-i", str(src),
             "-af", "silencedetect=n=-38dB:d=0.05",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=20,
        )
        ends = re.findall(r"silence_end:\s*([\d.]+)", probe.stderr)
        if ends:
            start_s = float(ends[0])
    except Exception:
        pass  # Fallback: Schnitt ab 0

    # Clip extrahieren
    fade_out_start = max(0.0, dur_s - 0.08)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(round(start_s, 3)),
        "-i", str(src),
        "-t", str(dur_s),
        "-af", f"afade=t=in:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.08",
        "-b:a", "128k", "-ar", "44100", "-ac", "1",
        str(dst),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        if r.returncode != 0 or not dst.exists():
            return False
        if dst.stat().st_size < 8_000:   # < ~0.5s bei 128kbps → verwerfen
            dst.unlink(missing_ok=True)
            return False
        return True
    except FileNotFoundError:
        print("\n    ffmpeg nicht gefunden — bitte installieren: winget install ffmpeg", flush=True)
        return False
    except Exception as e:
        print(f"\n    Clip-Fehler {src.name}: {e}", flush=True)
        return False

def _process_clip(slug: str, source_name: str, item: dict) -> None:
    """Download + Clip für ein einzelnes Ergebnis. Setzt item['clip_path']."""
    url = item.get("preview_url", "")
    if not url:
        return
    CAND_DIR.mkdir(exist_ok=True)
    rid = _safe_id(item.get("id", "x"))
    orig = CAND_DIR / f"{slug}_{source_name}_{rid}_orig.mp3"
    clip = CAND_DIR / f"{slug}_{source_name}_{rid}_clip.mp3"

    if not _download(url, orig):
        return
    if clip.exists() and clip.stat().st_size > 100:
        item["clip_path"] = f"sound_compare_candidates/{clip.name}"
        return
    if extract_clip(orig, clip):
        item["clip_path"] = f"sound_compare_candidates/{clip.name}"

def run_clips(results: list, workers: int = 4) -> None:
    tasks = []
    for r in results:
        for src_name, src_data in [("freesound", r["freesound"]), ("openverse", r["openverse"])]:
            for item in src_data.get("results", []):
                tasks.append((r["slug"], src_name, item))
    if not tasks:
        return
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_process_clip, slug, src, item) for slug, src, item in tasks]
        for fut in as_completed(futures):
            done += 1
            print(f"\r  Clips  [{done:3d}/{len(tasks)}]", end="", flush=True)
    print()


# ── Phase 3: HTML-Report ──────────────────────────────────────────────────────
LICENSE_SHORT = {
    "cc0":  "CC0",
    "by":   "CC BY",
    "by-nc":"CC BY-NC",
    "by-sa":"CC BY-SA",
    "http://creativecommons.org/publicdomain/zero/1.0/":    "CC0",
    "http://creativecommons.org/licenses/by/4.0/":          "CC BY 4.0",
    "http://creativecommons.org/licenses/by/3.0/":          "CC BY 3.0",
    "http://creativecommons.org/licenses/by-nc/3.0/":       "CC BY-NC 3.0",
    "http://creativecommons.org/licenses/by-nc/4.0/":       "CC BY-NC 4.0",
    "http://creativecommons.org/licenses/by-sa/4.0/":       "CC BY-SA 4.0",
}

def _lic(s: str) -> str:
    return LICENSE_SHORT.get(s.lower().strip(), s[:14] if s else "—")

def _render_result_rows(items: list, src_label: str) -> str:
    if not items:
        return "<tr><td colspan='4'><em style='color:#aaa'>–</em></td></tr>"
    rows = []
    for r in items:
        title_full = html.escape(r.get("title", ""))
        title  = title_full[:55]
        author = html.escape(r.get("author", "")[:20])
        dur    = f"{r.get('duration', 0)}s"
        lic    = _lic(r.get("license", ""))
        clip   = r.get("clip_path", "")
        orig   = r.get("preview_url", "")
        src_b  = (f"<span class='src'>{html.escape(r.get('source',''))}</span>"
                  if src_label == "openverse" and r.get("source") else "")
        if clip:
            clip_esc = html.escape(clip)
            player = (f"<audio controls preload='none' "
                      f"style='height:22px;width:180px;vertical-align:middle' "
                      f"src='{clip_esc}'></audio>")
        elif orig:
            orig_esc = html.escape(orig)
            player = f"<a href='{orig_esc}' target='_blank'>▶ extern</a>"
        else:
            player = "—"
        rows.append(
            f"<tr>"
            f"<td class='tit' title='{title_full}'>{title}</td>"
            f"<td class='aut'>{author}{' ' + src_b if src_b else ''}</td>"
            f"<td class='dur'>{dur}</td>"
            f"<td class='lic'>{lic}</td>"
            f"<td>{player}</td>"
            f"</tr>"
        )
    return "".join(rows)

def _stat_val(n, color): return f"<div class='val' style='color:{color}'>{n}</div>"

def build_html(results: list, ts: str, clips_enabled: bool) -> str:
    total = len(results)
    ov_hits = sum(1 for r in results if r["openverse"]["results"])
    fs_hits = sum(1 for r in results if r["freesound"]["results"])
    fs_rl   = sum(1 for r in results if r["freesound"].get("error") == "rate_limited")
    fs_dis  = any(r["freesound"].get("error") in ("disabled", "no_key") for r in results)
    fs_status = ("Rate-limited!" if fs_rl else "deaktiviert" if fs_dis else "aktiv")

    rows = []
    for r in results:
        fs, ov = r["freesound"], r["openverse"]
        fc, oc = len(fs["results"]), len(ov["results"])
        errs = ""
        if fs.get("error") and fs["error"] not in ("disabled", "no_key"):
            errs += f"<span class='err'>FS: {html.escape(fs['error'])}</span> "
        if ov.get("error"):
            errs += f"<span class='err'>OV: {html.escape(ov['error'])}</span>"
        rows.append(f"""
<tr class='tr'>
  <td class='lbl'>
    <strong>{html.escape(r['label_de'])}</strong><br>
    <small><em>{html.escape(r['query_en'])}</em></small>
    {f"<br>{errs}" if errs else ""}
  </td>
  <td class='cnt {"ok" if fc else "z"}'>{fc}<br><small>/{fs.get("total","?")}</small></td>
  <td class='sc'><table class='rt'>{_render_result_rows(fs["results"],"freesound")}</table></td>
  <td class='cnt {"ok" if oc else "z"}'>{oc}<br><small>/{ov.get("total","?")}</small></td>
  <td class='sc'><table class='rt'>{_render_result_rows(ov["results"],"openverse")}</table></td>
</tr>""")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Sound-Vergleich — Wissensfreund</title>
<style>
body{{font:13px/1.4 sans-serif;margin:14px;background:#f5f5f5;color:#222}}
h1{{font-size:1.3em;margin:0 0 3px}}
.meta{{color:#777;font-size:11px;margin-bottom:12px}}
.sum{{background:#fff;border:1px solid #ddd;padding:10px 16px;border-radius:6px;
      margin-bottom:12px;display:flex;gap:20px;flex-wrap:wrap;align-items:center}}
.st{{text-align:center}}
.val{{font-size:1.7em;font-weight:700}}
.lb{{font-size:10px;color:#666}}
table.main{{width:100%;border-collapse:collapse;background:#fff}}
table.main thead th{{background:#2b2b2b;color:#fff;padding:6px 7px;text-align:left;font-size:12px}}
tr.tr{{border-bottom:1px solid #e8e8e8;vertical-align:top}}
tr.tr:hover{{background:#fffde7}}
.lbl{{width:170px;padding:7px 6px;font-size:12px}}
.cnt{{width:48px;text-align:center;padding:6px 4px;font-size:1.1em;font-weight:700}}
.cnt.ok{{color:#2e7d32}}.cnt.z{{color:#c62828}}
.sc{{padding:4px 5px;min-width:340px}}
table.rt{{width:100%;font-size:11px;border-collapse:collapse}}
table.rt tr{{border-bottom:1px solid #f2f2f2}}
table.rt td{{padding:2px 3px;vertical-align:middle}}
.tit{{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.aut{{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#555}}
.dur{{color:#1565c0;font-weight:700;white-space:nowrap}}
.lic{{color:#6a1b9a;font-size:10px;white-space:nowrap}}
.src{{background:#e3f2fd;color:#0d47a1;font-size:9px;padding:1px 3px;border-radius:2px}}
.err{{color:#b71c1c;font-size:10px}}
a{{color:#0066cc}}
</style>
</head>
<body>
<h1>Sound-Vergleich: Freesound vs. Openverse</h1>
<div class="meta">{html.escape(ts)} · {DUR_MIN_S}–{DUR_MAX_S}s · Top {N_RESULTS}/Quelle ·
Clips: {"4s extrahiert (pydub)" if clips_enabled else "deaktiviert (--no-clips)"} ·
Zapsplat: kein API</div>

<div class="sum">
  <div class="st">{_stat_val(total,"#333")}<div class="lb">Themen</div></div>
  <div class="st">{_stat_val(ov_hits,"#1565c0")}<div class="lb">Openverse Treffer</div></div>
  <div class="st">{_stat_val(f"{ov_hits/total*100:.0f}%","#1565c0")}<div class="lb">OV Coverage</div></div>
  <div class="st">{_stat_val(fs_hits,"#e65100")}<div class="lb">Freesound Treffer</div></div>
  <div class="st">{_stat_val(f"{fs_hits/total*100:.0f}%","#e65100")}<div class="lb">FS Coverage<br><small>({fs_status})</small></div></div>
</div>

<table class="main">
<thead>
<tr>
  <th>Thema / Query</th>
  <th>FS #</th><th>Freesound ({DUR_MIN_S}–{DUR_MAX_S}s)</th>
  <th>OV #</th><th>Openverse ({DUR_MIN_S}–{DUR_MAX_S}s)</th>
</tr>
</thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit",        type=int, default=0)
    ap.add_argument("--no-freesound", action="store_true")
    ap.add_argument("--no-clips",     action="store_true")
    ap.add_argument("--workers",      type=int, default=4)
    args = ap.parse_args()

    topics     = TOPICS[:args.limit] if args.limit else TOPICS
    use_fs     = not args.no_freesound and bool(FS_KEY)
    use_clips  = not args.no_clips
    if not FS_KEY and not args.no_freesound:
        print("  ⚠  FREESOUND_API_KEY nicht gesetzt → Freesound übersprungen")

    import shutil
    if use_clips and not shutil.which("ffmpeg"):
        print("  ⚠  ffmpeg nicht in PATH → --no-clips wird erzwungen")
        print("       Installation:  winget install ffmpeg")
        use_clips = False

    print(f"  Themen: {len(topics)} | FS: {'aktiv' if use_fs else 'aus'} | "
          f"Clips: {'aktiv' if use_clips else 'aus'} | Workers: {args.workers}")
    t0 = time.time()

    # Phase 1 – Suche
    results = run_search(topics, use_fs, args.workers)

    # Phase 2 – Clips
    if use_clips:
        run_clips(results, args.workers)

    elapsed = time.time() - t0
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + f"  ({elapsed:.0f}s)"

    # Phase 3 – Report
    html_out = build_html(results, ts, use_clips)
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ov_hits = sum(1 for r in results if r["openverse"]["results"])
    fs_hits = sum(1 for r in results if r["freesound"]["results"])
    clips   = sum(
        1 for r in results
        for src in [r["freesound"], r["openverse"]]
        for item in src.get("results", [])
        if item.get("clip_path")
    )
    print(f"\n  ✓ Openverse: {ov_hits}/{len(results)} Themen mit Treffern")
    if use_fs:
        print(f"  ✓ Freesound: {fs_hits}/{len(results)} Themen mit Treffern")
    if use_clips:
        print(f"  ✓ Clips:     {clips} extrahiert → sound_compare_candidates/")
    print(f"  → {OUT_HTML}")

if __name__ == "__main__":
    main()
