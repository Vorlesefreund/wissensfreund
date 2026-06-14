#!/usr/bin/env python3
"""
sound_sourcing.py  v1  (2026-06-14)
Wissensfreund — Sound-Bibliothek aufbauen via Freesound API

Nutzung:
  python sound_sourcing.py --phase search   --type ambient
  python sound_sourcing.py --phase search   --type spot
  python sound_sourcing.py --phase finalize --approvals sound_approvals.json

Voraussetzung:
  pip install requests
  FREESOUND_API_KEY=<dein-key>  (in .env oder Umgebungsvariable)
"""

import os, sys, json, re, time, shutil, argparse, pathlib
import requests
import anthropic
from string import Template

API_BASE     = "https://freesound.org/apiv2"
CAND_DIR     = pathlib.Path("sound_candidates")
LIB_DIR      = pathlib.Path("sound_library")
REVIEW_HTML  = pathlib.Path("sound_review.html")
LIB_JSON     = pathlib.Path("sound_library.json")

CATALOG_JSON  = pathlib.Path("catalog_full.json")
SCAN_CACHE    = pathlib.Path("sound_scan_cache.json")
SCAN_CAND_DIR = CAND_DIR / "catalog_scan"

SCAN_THEMENGEBIETE = {
    "Tiere",
    "Pflanzen & Pilze",
    "Menschlicher Körper & Gesundheit",
    "Erde, Wetter & Naturphänomene",
    "Naturräume & Landschaften",
    "Weltall & Astronomie",
    "Naturwissenschaft & Biologie-Konzepte",
    "Technik, Maschinen & Fahrzeuge",
    "Kunst, Musik & Literatur",
    "Sport & Spiele",
    "Essen & Alltag",
    "Religion, Feste & Bräuche",
    "Märchen, Mythologie & Fabelwesen",
    "Grundbegriffe (Zahlen, Formen, Farben, Zeit, Sprache)",
}

# ── Kategorien: Ambient ──────────────────────────────────────────────────────

AMBIENT = {
    # Natur
    "savanne":        ("Savanne / Afrika",            ["african savannah ambient loop", "savanna wildlife africa loop", "african plains birds wind ambient"]),
    "regenwald":      ("Regenwald / Tropisch",         ["tropical rainforest ambience loop", "jungle rain forest birds loop", "tropical forest ambient loop"]),
    "ozean_ruhig":    ("Ozean – ruhig",               ["calm ocean waves loop", "gentle sea waves ambient loop", "peaceful ocean waves loop"]),
    "ozean_sturm":    ("Ozean – Sturm",               ["stormy ocean waves ambient", "rough sea waves wind loop", "ocean storm ambient loop"]),
    "wald_tag":       ("Wald – Tag (Vögel)",           ["forest birds daytime ambient loop", "woodland birds chirping morning", "european forest birds ambient"]),
    "wald_nacht":     ("Wald – Nacht (Eulen/Grillen)", ["forest night crickets ambient loop", "night woodland crickets owls loop", "summer night forest ambient"]),
    "arktis":         ("Arktis / Polarwind",           ["arctic wind ambient loop", "polar blizzard wind loop", "icy wind cold ambient"]),
    "gebirge":        ("Gebirge / Alpen",              ["mountain wind alpine ambient loop", "alpine meadow wind birds loop", "mountain top wind ambient"]),
    "wueste":         ("Wüste / Hitze",                ["desert wind ambient loop", "hot desert sand wind loop", "arid desert wind ambient"]),
    "tiefsee":        ("Tiefsee / Unterwasser",        ["underwater ambient loop", "deep ocean underwater sound loop", "submarine ocean ambient loop"]),
    "fluss":          ("Fluss / Bach",                 ["river stream ambient loop", "babbling brook loop", "mountain stream water ambient"]),
    "sumpf":          ("Sumpf / Moor",                 ["swamp marsh frogs ambient loop", "wetland frogs crickets loop", "bog swamp ambient loop"]),
    "mittelmeer":     ("Mittelmeer / Küste",            ["mediterranean coast cicadas summer", "sea breeze cicadas ambient loop", "coastal summer ambient loop"]),
    "steppe":         ("Steppe / Prärie",              ["prairie wind grassland ambient", "open grassland wind birds loop", "steppe wind ambient loop"]),
    # Gesellschaft
    "markt":          ("Markt / Stadtgemurmel",        ["market crowd ambience loop", "busy marketplace crowd murmur", "street market ambient loop"]),
    "mittelalter":    ("Mittelalterlicher Markt",      ["medieval market ambience loop", "medieval fair crowd ambient", "renaissance fair market loop"]),
    "kirche":         ("Kirche / Glocken",             ["church bells ambient loop", "cathedral interior ambience", "church organ bells ambient"]),
    "schule":         ("Schule / Kinderstimmen",       ["children playground ambient loop", "school kids playing outside loop", "children voices playground"]),
    "sportplatz":     ("Sportplatz / Jubel",           ["stadium crowd cheering ambient", "sports crowd ambient loop", "crowd cheering stadium loop"]),
    "festumzug":      ("Festumzug / Feier",            ["carnival festival crowd ambient", "celebration crowd ambient loop", "festive parade crowd loop"]),
    "taverne":        ("Taverne / Gasthof",            ["tavern inn ambience loop", "medieval tavern crowd ambient loop", "inn background noise loop"]),
    "hafen":          ("Hafen / Meer",                 ["harbor port seagulls ambient loop", "port seagulls boat ambient loop", "harbor seaport ambient"]),
    # Geschichte
    "schlachtfeld":   ("Schlachtfeld – dezent",        ["distant battle drums ambient loop", "medieval battle distant drums loop", "war drums battle far ambient"]),
    "wikingerschiff": ("Wikingerschiff / Wellen",      ["sailing ship sea waves loop", "wooden ship creaking ocean loop", "ship sailing ambient loop"]),
    "antikes_rom":    ("Antikes Rom / Marktplatz",     ["ancient rome crowd ambient loop", "roman marketplace ambience loop", "ancient market crowd ambient"]),
    "aegypten":       ("Ägypten / Wüstenwind",         ["egypt desert wind ambient loop", "ancient egypt ambient wind loop", "sahara desert wind ambient"]),
    "urzeit":         ("Urzeit / Natur wild",          ["prehistoric nature ambient loop", "primeval wild nature loop", "jurassic nature ambient loop"]),
    # Technik
    "fabrik":         ("Fabrik / Maschinen",           ["factory machine ambient loop", "industrial machinery hum loop", "factory floor industrial ambient"]),
    "motor":          ("Motor / Fahrzeug",             ["car engine idle ambient loop", "vehicle motor running ambient", "engine hum idle loop"]),
    "lokomotive":     ("Dampflokomotive / Zug",        ["steam train locomotive ambient", "steam engine train loop", "old steam locomotive ambient"]),
    "labor":          ("Labor / Elektronik",           ["laboratory equipment ambient loop", "science lab hum loop", "computer server room hum ambient"]),
    "schmiede":       ("Schmiede / Feuer",             ["blacksmith forge fire ambient loop", "smithy hammer fire loop", "forge fire crackling ambient"]),
    "raumkapsel":     ("Raumkapsel / Cockpit",         ["spaceship interior ambient loop", "spacecraft cockpit hum loop", "space station ambient hum"]),
    "weltraum":       ("Weltraum / Stille",            ["outer space ambient loop", "space drone deep ambient", "cosmos deep space ambient loop"]),
    # Besonderes
    "hoehle":         ("Höhle / Echo / Tropfen",      ["cave dripping water ambient loop", "cavern echo drip loop", "underground cave ambient loop"]),
    "kamin":          ("Feuer / Kamin",                ["fireplace crackling fire loop", "cozy fireplace ambient loop", "campfire crackling ambient"]),
    "winter":         ("Winter / Schnee",              ["winter wind snow ambient loop", "cold winter wind ambient", "blizzard snow wind loop"]),
    "kueche":         ("Küche / Kochen",               ["kitchen cooking ambient loop", "home kitchen background ambient", "cooking sounds kitchen loop"]),
    "bergwerk":       ("Bergwerk / Unterirdisch",       ["mine shaft underground ambient loop", "coal mine ambient loop", "underground mining ambient"]),
}

# ── Kategorien: Spot Sounds (kurz, 1–8 Sek.) ────────────────────────────────

SPOT = {
    "elefant":     ("Elefant",            2, 8,  ["elephant trumpet call sound", "elephant trumpeting short"]),
    "loewe":       ("Löwe",               2, 8,  ["lion roar sound effect", "lion growling roar short"]),
    "wolf":        ("Wolf",               2, 8,  ["wolf howl sound effect", "wolf howling short"]),
    "delfin":      ("Delfin",             1, 6,  ["dolphin sound effect short", "dolphin whistle click"]),
    "wal":         ("Wal",                3, 10, ["whale song effect short", "humpback whale call"]),
    "hund":        ("Hund",               1, 5,  ["dog bark sound effect", "dog barking short"]),
    "katze":       ("Katze",              1, 5,  ["cat meow sound effect", "cat meowing short"]),
    "pferd":       ("Pferd",              1, 6,  ["horse neigh sound effect", "horse whinny short"]),
    "kuh":         ("Kuh",                1, 5,  ["cow moo sound effect", "cow mooing short"]),
    "adler":       ("Adler",              1, 5,  ["eagle cry screech effect", "eagle screech short"]),
    "eule":        ("Eule",               1, 5,  ["owl hoot sound effect", "owl hooting short"]),
    "hahn":        ("Hahn",               1, 6,  ["rooster crow sound effect", "cock crowing morning"]),
    "frosch":      ("Frosch",             1, 5,  ["frog croaking ribbit effect", "frog sound short"]),
    "biene":       ("Biene",              2, 6,  ["bee buzzing sound effect", "bumblebee buzz short"]),
    "affe":        ("Affe",               1, 6,  ["monkey call sound effect", "chimpanzee call short"]),
    "baer":        ("Bär",                1, 6,  ["bear growl roar effect", "grizzly bear growl short"]),
    "dinosaurier": ("Dinosaurier",        2, 8,  ["dinosaur roar effect short", "t-rex roar sound"]),
    "pinguin":     ("Pinguin",            1, 5,  ["penguin call sound effect", "penguin noise short"]),
    "krokodil":    ("Krokodil",           1, 6,  ["crocodile hiss snap effect", "alligator hiss short"]),
    "schlange":    ("Schlange",           1, 5,  ["snake hiss sound effect", "rattlesnake hiss short"]),
    "hupe":        ("Hupe / Auto",        1, 4,  ["car horn honk effect", "car horn beep short"]),
    "zug_pfiff":   ("Zug-Pfiff",         1, 5,  ["train whistle sound effect", "steam train whistle short"]),
    "schiff":      ("Schiff-Sirene",      2, 6,  ["ship foghorn sound effect", "boat horn short"]),
    "glocke":      ("Glocke",             1, 5,  ["bell ring sound effect", "hand bell ring short"]),
    "fanfare":     ("Fanfare / Trompete", 2, 8,  ["fanfare trumpet sound effect", "royal fanfare short"]),
    "gong":        ("Gong",               1, 5,  ["gong strike sound effect", "gong sound short"]),
    "feuerwerk":   ("Feuerwerk",          1, 5,  ["fireworks explosion sound", "firework bang short"]),
    "schwert":     ("Schwert / Clash",    1, 4,  ["sword clash metal effect", "sword fight clang short"]),
    "kanone":      ("Kanone",             1, 5,  ["cannon fire sound effect", "cannon shot explosion"]),
    "rakete":      ("Raketenstart",       3, 10, ["rocket launch sound effect", "rocket ignition blast"]),
}

# ── API ──────────────────────────────────────────────────────────────────────

def get_api_key():
    key = os.environ.get("FREESOUND_API_KEY", "")
    if not key:
        env = pathlib.Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("FREESOUND_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        sys.exit("FEHLER: FREESOUND_API_KEY nicht gesetzt. Siehe freesound.org/apiv2/apply/")
    return key

def freesound_search(query, api_key, dur_min, dur_max, n=5):
    params = {
        "query":     query,
        "token":     api_key,
        "filter":    f'license:"Creative Commons 0" duration:[{dur_min} TO {dur_max}]',
        "fields":    "id,name,description,duration,previews,username,avg_rating,num_downloads",
        "page_size": n,
        "sort":      "rating_desc",
    }
    try:
        r = requests.get(f"{API_BASE}/search/text/", params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"    Suche fehlgeschlagen ({query}): {e}")
        return []

def download_preview(sound, out_path):
    url = sound["previews"].get("preview-hq-mp3") or sound["previews"].get("preview-lq-mp3")
    if not url or out_path.exists():
        return bool(out_path.exists())
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"    Download fehlgeschlagen: {e}")
        return False

# ── Catalog-Scan ─────────────────────────────────────────────────────────────

def translate_themen_batch(themen: list[str]) -> dict[str, str]:
    """Übersetzt deutsche Themen-Namen ins Englische via Haiku (günstig)."""
    client = anthropic.Anthropic()
    result = {}
    batch_size = 80

    for i in range(0, len(themen), batch_size):
        batch = themen[i : i + batch_size]
        numbered = "\n".join(f"{j+1}. {t}" for j, t in enumerate(batch))
        prompt = (
            "Translate these German encyclopedia topic names to concise English "
            "search terms for Freesound.org (sound effects library). "
            "Return ONLY a JSON object mapping each German name to its English "
            "search term. No explanations, no markdown.\n\n" + numbered
        )
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
            result.update(json.loads(text))
        except Exception as e:
            print(f"  Übersetzungsfehler (Batch {i//batch_size+1}): {e} — nutze Deutsch")
            for t in batch:
                result[t] = t
        time.sleep(1)

    return result


def fetch_wikipedia_audio(thema: str, en_query: str) -> list[dict]:
    """
    Sucht Audiodateien via DE-Wikipedia-Artikel auf Wikimedia Commons.
    Fallback auf EN-Wikipedia wenn DE keinen Treffer liefert.
    """
    AUDIO_EXTS = {".ogg", ".wav", ".flac", ".mp3", ".oga"}
    filenames = []

    for lang, title in [("de", thema), ("en", en_query)]:
        try:
            r = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "titles": title, "prop": "images",
                        "imlimit": "50", "format": "json", "formatversion": "2"},
                timeout=10,
            )
            pages = r.json().get("query", {}).get("pages", [])
            for page in pages:
                for img in page.get("images", []):
                    t = img.get("title", "")
                    if pathlib.Path(t).suffix.lower() in AUDIO_EXTS:
                        filenames.append(t.replace("File:", "").replace("Datei:", ""))
        except Exception:
            pass
        if filenames:
            break

    if not filenames:
        return []

    audio_info = []
    for fname in filenames[:5]:
        try:
            r = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params={"action": "query", "titles": f"File:{fname}",
                        "prop": "imageinfo", "iiprop": "url|mime|size",
                        "format": "json", "formatversion": "2"},
                timeout=10,
            )
            pages = r.json().get("query", {}).get("pages", [])
            for page in pages:
                for info in page.get("imageinfo", []):
                    if info.get("mime", "").startswith("audio/") or \
                       pathlib.Path(fname).suffix.lower() in AUDIO_EXTS:
                        audio_info.append({
                            "filename": fname,
                            "url":      info.get("url", ""),
                            "mime":     info.get("mime", ""),
                        })
        except Exception:
            pass

    return audio_info


def phase_catalog_scan(candidates_per_thema: int = 3):
    """
    Scannt catalog_full.json: Wikimedia Commons (primär) → Freesound (Fallback).
    Jedes Thema aus SCAN_THEMENGEBIETE → Kandidaten cachen → HTML-Review.
    Bereits gecachte Themen werden übersprungen (Resume-fähig).
    """
    if not CATALOG_JSON.exists():
        sys.exit(f"FEHLER: {CATALOG_JSON} nicht gefunden.")

    api_key = get_api_key()
    SCAN_CAND_DIR.mkdir(parents=True, exist_ok=True)

    catalog = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    to_scan = [
        item for item in catalog
        if item.get("themengebiet") in SCAN_THEMENGEBIETE
        and item.get("eignung") != "exclude"
        and item.get("tier") == "primary"
    ]
    print(f"Themen im Scan-Scope: {len(to_scan)}")

    cache: dict = json.loads(SCAN_CACHE.read_text(encoding="utf-8")) \
        if SCAN_CACHE.exists() else {}
    already_done = sum(1 for t in to_scan if t["thema"] in cache)
    print(f"Bereits gecacht: {already_done} — neu zu suchen: {len(to_scan)-already_done}")

    need_trans = [t["thema"] for t in to_scan if t["thema"] not in cache]
    translations: dict[str, str] = {}
    if need_trans:
        print(f"Übersetze {len(need_trans)} Themen (Haiku-Batch) …")
        translations = translate_themen_batch(need_trans)
        print(f"  {len(translations)} Übersetzungen erhalten.")

    found_count = sum(1 for t in to_scan if cache.get(t["thema"]))
    for idx, item in enumerate(to_scan):
        thema = item["thema"]
        if thema in cache:
            continue

        en_query = translations.get(thema, thema)
        print(f"  [{idx+1}/{len(to_scan)}] {thema} → \"{en_query}\"", end=" ", flush=True)

        # ── Wikimedia Commons (primär) ────────────────────────────────
        wiki_audio = fetch_wikipedia_audio(thema, en_query)
        sounds = []
        slug = re.sub(r"[^a-z0-9]", "_", thema.lower())[:28]

        if wiki_audio:
            for audio in wiki_audio[:candidates_per_thema]:
                safe_fname = re.sub(r"[^a-z0-9_.]", "_", audio["filename"].lower())[:40]
                ext = pathlib.Path(audio["filename"]).suffix or ".ogg"
                fpath = SCAN_CAND_DIR / f"{slug}_wiki_{safe_fname}"
                try:
                    resp = requests.get(audio["url"], timeout=30)
                    resp.raise_for_status()
                    fpath.write_bytes(resp.content)
                    sounds.append({
                        "id":       f"wiki_{safe_fname}",
                        "name":     audio["filename"],
                        "author":   "Wikimedia Commons",
                        "duration": 0,
                        "rating":   5.0,
                        "license":  "CC-BY-SA",
                        "local":    str(fpath),
                        "source":   "wikimedia",
                        "en_query": en_query,
                    })
                except Exception as e:
                    print(f" [WP-DL: {e}]", end="")

        # ── Freesound (Fallback wenn Wikimedia leer) ──────────────────
        if not sounds:
            results = freesound_search(en_query, api_key, dur_min=0.5, dur_max=15, n=candidates_per_thema)
            if not results:
                results = freesound_search(thema, api_key, dur_min=0.5, dur_max=15, n=candidates_per_thema)
            good = [r for r in results if (r.get("avg_rating") or 0) >= 3.0]
            for r in good[:candidates_per_thema]:
                fpath = SCAN_CAND_DIR / f"{slug}_fs_{r['id']}.mp3"
                if download_preview(r, fpath):
                    sounds.append({
                        "id":       r["id"],
                        "name":     r["name"][:80],
                        "author":   r["username"],
                        "duration": round(r["duration"], 1),
                        "rating":   round(r.get("avg_rating") or 0, 1),
                        "license":  "CC0",
                        "local":    str(fpath),
                        "source":   "freesound",
                        "en_query": en_query,
                    })

        # ── Ergebnis speichern ────────────────────────────────────────
        src_tag = "[WP]" if (sounds and sounds[0].get("source") == "wikimedia") else "[FS]"
        if sounds:
            entry = {
                "thema":        thema,
                "themengebiet": item.get("themengebiet", ""),
                "en_query":     en_query,
                "sounds":       sounds,
            }
            cache[thema] = entry
            found_count += 1
            print(f"→ {len(sounds)} {src_tag}")
        else:
            cache[thema] = None
            print("→ kein Treffer")

        if idx % 25 == 0:
            SCAN_CACHE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        time.sleep(0.35)

    SCAN_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{found_count} Themen mit Freesound-Treffern (von {len(to_scan)} gescannt)")
    build_catalog_review_html(cache)


def build_catalog_review_html(cache: dict):
    """Generiert sound_review_catalog.html — gruppiert nach Themengebiet."""
    found = {k: v for k, v in cache.items() if v and v.get("sounds")}

    by_gebiet: dict[str, list] = {}
    for thema, data in sorted(found.items()):
        g = data.get("themengebiet", "Sonstiges")
        by_gebiet.setdefault(g, []).append((thema, data))

    cats_html = ""
    for gebiet, items in sorted(by_gebiet.items()):
        cards_html = ""
        for thema, data in items:
            player_html = ""
            for i, s in enumerate(data["sounds"]):
                rel   = pathlib.Path(s["local"]).as_posix()
                src   = s.get("source", "freesound")
                badge = "WP" if src == "wikimedia" else "FS"
                badge_color = "#1565C0" if src == "wikimedia" else "#2E7D32"
                jd    = json.dumps({"id": s["id"], "name": s["name"], "author": s["author"],
                                    "duration": s["duration"], "rating": s["rating"],
                                    "license": s.get("license", "CC0"), "local": s["local"],
                                    "source": src})
                player_html += (
                    f'<div class="sc" data-cat="{thema}" data-idx="{i}">'
                    f'<div class="meta">'
                    f'<span style="background:{badge_color};color:white;padding:1px 5px;'
                    f'border-radius:3px;font-size:.7em;font-weight:bold">{badge}</span>'
                    f' ★{s["rating"]} {s["duration"]}s · {s["author"]}</div>'
                    f'<div class="sname">{s["name"][:55]}</div>'
                    f'<audio controls src="{rel}" preload="none"></audio>'
                    f'<button class="sbtn" onclick=\'sel("{thema}",{i},{jd})\'>✓ Auswählen</button>'
                    f'</div>'
                )
            cards_html += (
                f'<div class="topic" data-cat="{thema}">'
                f'<div class="tname">{thema}</div>'
                f'<div class="players">{player_html}</div>'
                f'</div>'
            )
        cats_html += (
            f'<details open><summary class="ghead">{gebiet} ({len(items)})</summary>'
            f'<div class="grid">{cards_html}</div></details>'
        )

    html = f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>Wissensfreund — Catalog Sound Review</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;padding:16px;background:#f5f5f5}}
h1{{color:#1F4E79}}details{{background:white;border-radius:8px;margin-bottom:16px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
summary.ghead{{font-weight:bold;font-size:1.05em;color:#1F4E79;cursor:pointer;padding:4px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:10px}}
.topic{{border:1px solid #ddd;border-radius:6px;padding:8px;background:#fafafa}}
.tname{{font-weight:bold;font-size:.9em;margin-bottom:6px;color:#333}}
.players{{display:flex;flex-direction:column;gap:6px}}
.sc{{border:2px solid #eee;border-radius:4px;padding:6px;background:white}}
.sc.selected{{border-color:#2E7D32;background:#E8F5E9}}
.meta{{font-size:.72em;color:#888}}
.sname{{font-size:.78em;font-weight:bold;margin:2px 0}}
audio{{width:100%;height:28px}}
.sbtn{{width:100%;padding:4px;border:none;border-radius:3px;background:#1F4E79;color:white;
       font-size:.78em;cursor:pointer;margin-top:3px}}
.sbtn.selected{{background:#2E7D32}}
#expbtn{{padding:10px 24px;background:#1F4E79;color:white;border:none;border-radius:6px;
         font-size:1em;cursor:pointer;margin-top:20px}}
#expout{{width:100%;height:250px;font-family:monospace;font-size:.8em;margin-top:10px}}
.prog{{color:#666;font-size:.85em;margin:8px 0}}
</style></head><body>
<h1>Catalog Sound Review — {len(found)} Themen mit Freesound-Treffern</h1>
<p class="prog" id="prog">0 von {len(found)} ausgewählt</p>
{cats_html}
<button id="expbtn" onclick="exportSel()">Export JSON</button>
<textarea id="expout" placeholder="JSON erscheint nach Klick..."></textarea>
<script>
const sel_={{}}; const total={len(found)};
function sel(cat,idx,data){{
  document.querySelectorAll(`[data-cat="${{cat}}"] .sc`).forEach(e=>e.classList.remove('selected'));
  document.querySelectorAll(`[data-cat="${{cat}}"] .sbtn`).forEach(e=>{{e.classList.remove('selected');e.textContent='✓ Auswählen';}});
  const card=document.querySelector(`[data-cat="${{cat}}"] [data-idx="${{idx}}"]`);
  card.classList.add('selected');
  card.querySelector('.sbtn').classList.add('selected');
  card.querySelector('.sbtn').textContent='✓ Ausgewählt';
  sel_[cat]=data;
  document.getElementById('prog').textContent=Object.keys(sel_).length+' von '+total+' ausgewählt';
}}
function exportSel(){{document.getElementById('expout').value=JSON.stringify(sel_,null,2);}}
</script></body></html>"""

    out = pathlib.Path("sound_review_catalog.html")
    out.write_text(html, encoding="utf-8")
    print(f"Review-Seite: {out.resolve()}")
    print(f"→ Im Browser öffnen, pro Thema besten Sound wählen, Export klicken")
    print(f"→ JSON als sound_approvals_catalog.json speichern")
    print(f"→ Danach: python sound_sourcing.py --phase finalize --approvals sound_approvals_catalog.json --type spot")


# ── Phase 1: Search ──────────────────────────────────────────────────────────

def phase_search(sound_type):
    api_key = get_api_key()
    CAND_DIR.mkdir(exist_ok=True)
    cat_dir = CAND_DIR / sound_type
    cat_dir.mkdir(exist_ok=True)

    if sound_type == "ambient":
        categories = {k: (v[0], 20, 90, v[1]) for k, v in AMBIENT.items()}
    else:
        categories = {k: (v[0], v[1], v[2], v[3]) for k, v in SPOT.items()}

    all_candidates = {}

    for cat_key, (label, dur_min, dur_max, queries) in categories.items():
        print(f"\n  [{cat_key}] {label}")
        cat_path = cat_dir / cat_key
        cat_path.mkdir(exist_ok=True)

        seen_ids = set()
        candidates = []

        for query in queries:
            if len(candidates) >= 5:
                break
            results = freesound_search(query, api_key, dur_min, dur_max, n=5)
            for sound in results:
                if len(candidates) >= 5:
                    break
                if sound["id"] in seen_ids:
                    continue
                seen_ids.add(sound["id"])

                fname = f"{cat_key}_{len(candidates):02d}_{sound['id']}.mp3"
                fpath = cat_path / fname
                ok = download_preview(sound, fpath)
                if ok:
                    candidates.append({
                        "id":       sound["id"],
                        "name":     sound["name"][:80],
                        "author":   sound["username"],
                        "duration": round(sound["duration"], 1),
                        "rating":   round(sound.get("avg_rating") or 0, 1),
                        "license":  "CC0",
                        "local":    str(fpath),
                        "query":    query,
                    })
                    print(f"    v {sound['name'][:50]} ({round(sound['duration'],1)}s, *{round(sound.get('avg_rating') or 0,1)})")
                    time.sleep(0.3)

        all_candidates[cat_key] = {"label": label, "sounds": candidates}

    meta_file = CAND_DIR / f"{sound_type}_candidates.json"
    meta_file.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGespeichert: {meta_file}")

    build_review_html(sound_type, all_candidates)

# ── Review-HTML ───────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Wissensfreund Sound Review – {sound_type}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
  h1 {{ color: #1F4E79; }}
  .category {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  .cat-title {{ font-size: 1.1em; font-weight: bold; color: #1F4E79; margin-bottom: 12px; }}
  .sound-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
  .sound-card {{ border: 2px solid #ddd; border-radius: 6px; padding: 10px; background: #fafafa; cursor: pointer; transition: all .2s; }}
  .sound-card:hover {{ border-color: #1F4E79; }}
  .sound-card.selected {{ border-color: #2E7D32; background: #E8F5E9; }}
  .sound-card .meta {{ font-size: 0.78em; color: #666; margin: 4px 0; }}
  .sound-card audio {{ width: 100%; margin: 6px 0; }}
  .select-btn {{ width: 100%; padding: 6px; border: none; border-radius: 4px; cursor: pointer;
                 background: #1F4E79; color: white; font-size: 0.85em; }}
  .select-btn.selected {{ background: #2E7D32; }}
  #export-section {{ background: white; border-radius: 8px; padding: 20px; margin-top: 30px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  #export-btn {{ padding: 12px 30px; background: #1F4E79; color: white; border: none; border-radius: 6px;
                 font-size: 1em; cursor: pointer; }}
  #export-output {{ width: 100%; height: 300px; font-family: monospace; font-size: 0.85em; margin-top: 12px; }}
  .progress {{ color: #666; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>Wissensfreund Sound Review – {sound_type_label}</h1>
<p>Pro Kategorie einen Sound auswaehlen → am Ende "Export" klicken → JSON kopieren → in <code>sound_approvals_{sound_type}.json</code> speichern.</p>
<p class="progress" id="progress">0 von {total} Kategorien ausgewaehlt</p>
{categories_html}
<div id="export-section">
  <button id="export-btn" onclick="exportSelections()">Export – Ausgewaehlte Sounds als JSON</button>
  <textarea id="export-output" placeholder="Hier erscheint das JSON nach dem Klick..."></textarea>
</div>
<script>
const selections = {{}};
const total = {total};
function selectSound(catKey, idx, data) {{
  document.querySelectorAll(`[data-cat="${{catKey}}"] .sound-card`).forEach(c => c.classList.remove('selected'));
  document.querySelectorAll(`[data-cat="${{catKey}}"] .select-btn`).forEach(b => {{ b.classList.remove('selected'); b.textContent = 'Auswaehlen'; }});
  document.querySelector(`[data-cat="${{catKey}}"] [data-idx="${{idx}}"]`).classList.add('selected');
  const btn = document.querySelector(`[data-cat="${{catKey}}"] [data-idx="${{idx}}"] .select-btn`);
  btn.classList.add('selected'); btn.textContent = 'Ausgewaehlt';
  selections[catKey] = data;
  document.getElementById('progress').textContent = Object.keys(selections).length + ' von ' + total + ' Kategorien ausgewaehlt';
}}
function exportSelections() {{
  document.getElementById('export-output').value = JSON.stringify(selections, null, 2);
}}
</script>
</body>
</html>"""

CAT_TEMPLATE = """<div class="category" data-cat="{key}">
  <div class="cat-title">{label} <span style="color:#999;font-size:.85em">({n} Kandidaten)</span></div>
  <div class="sound-grid">{cards}</div>
</div>"""

CARD_TEMPLATE = """<div class="sound-card" data-cat="{key}" data-idx="{idx}">
  <div class="meta">* {rating} &nbsp;|&nbsp; {duration}s &nbsp;|&nbsp; {author}</div>
  <div style="font-size:.85em;margin:3px 0;font-weight:bold">{name}</div>
  <audio controls src="{audio_path}" preload="none"></audio>
  <button class="select-btn" onclick='selectSound("{key}", {idx}, {json_data})'>Auswaehlen</button>
</div>"""

def build_review_html(sound_type, all_candidates):
    cats_html = ""
    for key, cat in all_candidates.items():
        cards = ""
        for i, s in enumerate(cat["sounds"]):
            json_data = json.dumps({
                "id": s["id"], "name": s["name"], "author": s["author"],
                "duration": s["duration"], "rating": s["rating"],
                "license": s["license"], "local": s["local"],
            })
            rel_path = pathlib.Path(s["local"]).as_posix()
            cards += CARD_TEMPLATE.format(
                key=key, idx=i, rating=s["rating"], duration=s["duration"],
                author=s["author"], name=s["name"][:60],
                audio_path=rel_path, json_data=json_data,
            )
        cats_html += CAT_TEMPLATE.format(key=key, label=cat["label"], n=len(cat["sounds"]), cards=cards)

    label = "Ambient Loops" if sound_type == "ambient" else "Spot Sounds"
    html = HTML_TEMPLATE.format(
        sound_type=sound_type, sound_type_label=label,
        total=len(all_candidates), categories_html=cats_html,
    )
    out = pathlib.Path(f"sound_review_{sound_type}.html")
    out.write_text(html, encoding="utf-8")
    print(f"Review-Seite: {out.resolve()}")
    print(f"→ Im Browser oeffnen, Sounds anhoeren, auswaehlen, JSON exportieren")
    print(f"→ JSON speichern als: sound_approvals_{sound_type}.json")

# ── Phase 2: Finalize ─────────────────────────────────────────────────────────

def phase_finalize(approvals_file, sound_type):
    approvals = json.loads(pathlib.Path(approvals_file).read_text(encoding="utf-8"))
    sub = LIB_DIR / sound_type
    sub.mkdir(parents=True, exist_ok=True)

    lib = {}
    for cat_key, sound in approvals.items():
        src = pathlib.Path(sound["local"])
        if not src.exists():
            print(f"  FEHLER: Datei nicht gefunden: {src}")
            continue
        dst = sub / f"{cat_key}.mp3"
        shutil.copy2(src, dst)
        lib[cat_key] = {
            "file":     f"sound_library/{sound_type}/{cat_key}.mp3",
            "label":    sound.get("name", cat_key),
            "author":   sound.get("author", ""),
            "duration": sound.get("duration", 0),
            "license":  "CC0",
            "type":     sound_type,
        }
        print(f"  v {cat_key}: {dst.name}")

    existing = json.loads(LIB_JSON.read_text(encoding="utf-8")) if LIB_JSON.exists() else {}
    existing.update(lib)
    LIB_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(lib)} Sounds → sound_library/{sound_type}/")
    print(f"sound_library.json aktualisiert ({len(existing)} Eintraege gesamt)")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["search", "finalize", "catalog-scan"], required=True)
    ap.add_argument("--type",  choices=["ambient", "spot"], default="ambient")
    ap.add_argument("--approvals", help="JSON-Datei mit genehmigten Sounds (phase=finalize)")
    ap.add_argument("--candidates", type=int, default=3,
                    help="Max. Freesound-Kandidaten je Thema beim catalog-scan (default 3)")
    args = ap.parse_args()

    if args.phase == "search":
        print(f"Suche {args.type} Sounds auf Freesound ...")
        phase_search(args.type)
    elif args.phase == "finalize":
        if not args.approvals:
            sys.exit("--approvals erforderlich fuer phase=finalize")
        phase_finalize(args.approvals, args.type)
    elif args.phase == "catalog-scan":
        phase_catalog_scan(candidates_per_thema=args.candidates)

if __name__ == "__main__":
    main()
