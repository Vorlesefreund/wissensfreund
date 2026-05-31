#!/usr/bin/env python3
"""
prepare_articles.py
Wissensfreund Artikel-Pipeline — Schritt 1

Liest die Kategorien-Whitelist, fragt die deutsche Wikipedia-API ab,
filtert und dedupliziert Artikel, und schreibt Job-Batches für die
Claude-API-Generierung (Schritt 2: generate_articles.py).

Verwendung:
    python prepare_articles.py \
        --whitelist wissensfreund_categories_whitelist.json \
        --out-dir   jobs/ \
        --age-levels 2 3 \
        --batch-size 50 \
        --dry-run

Ausgabe: jobs/batch_0001.json, batch_0002.json, …
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

WIKIPEDIA_API = "https://de.wikipedia.org/w/api.php"
USER_AGENT = "Wissensfreund-Pipeline/1.0 (educational children's app; https://github.com/Vorlesefreund/wissensfreund)"

PATTERN_FOR_CATEGORY = {
    "tiere":               "living_being",
    "pflanzen":            "living_being",
    "erde_natur":          "tech_science",
    "weltall":             "tech_science",
    "laender_staedte":     "place_geography",
    "geschichte":          "history_person",
    "personen":            "history_person",
    "technik_wissenschaft":"tech_science",
    "kultur_gesellschaft": "history_person",
    "sprache_kommunikation":"tech_science",
}


# ─────────────────────────────────────────────
# Wikipedia API helpers
# ─────────────────────────────────────────────

def wp_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_category_members(session: requests.Session, category: str, limit: int = 500) -> list[dict]:
    """Gibt alle Artikel einer Wikipedia-Kategorie zurück (paginiert)."""
    members = []
    params = {
        "action":      "query",
        "list":        "categorymembers",
        "cmtitle":     f"Kategorie:{category}",
        "cmtype":      "page",
        "cmlimit":     min(limit, 500),
        "cmprop":      "ids|title",
        "format":      "json",
        "apfilterredir": "nonredirects",
    }
    while True:
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("query", {}).get("categorymembers", [])
        members.extend(batch)
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont or len(members) >= limit:
            break
        params["cmcontinue"] = cont
        time.sleep(0.3)
    return members


def fetch_page_info(session: requests.Session, page_ids: list[int]) -> dict:
    """Ruft Textlänge und Revisions-ID für eine Liste von Page-IDs ab."""
    info = {}
    # Wikipedia-API erlaubt max. 50 IDs pro Request.
    # prop=revisions mit rvlimit schlägt fehl bei mehreren pageids → nur prop=info,
    # lastrevid aus info-Antwort nutzen.
    for chunk_start in range(0, len(page_ids), 50):
        chunk = page_ids[chunk_start:chunk_start + 50]
        params = {
            "action":  "query",
            "prop":    "info",
            "pageids": "|".join(str(p) for p in chunk),
            "inprop":  "url",
            "format":  "json",
        }
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for pid, pdata in pages.items():
            info[int(pid)] = {
                "length":    pdata.get("length", 0),
                "rev_id":    pdata.get("lastrevid", ""),
                "full_url":  pdata.get("fullurl", ""),
                "title":     pdata.get("title", ""),
            }
        time.sleep(0.2)
    return info


def fetch_wikimedia_images(session: requests.Session, title: str, max_images: int = 6) -> list[dict]:
    """Gibt verfügbare Bilder eines Artikels zurück (Wikimedia Commons, CC-Lizenz)."""
    params = {
        "action":   "query",
        "titles":   title,
        "prop":     "images",
        "imlimit":  20,
        "format":   "json",
    }
    resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    raw_images = []
    for page in pages.values():
        raw_images.extend(page.get("images", []))

    # Nur Commons-Bilder, keine Icons/Logos/Symbole
    skip_prefixes = ("File:Commons-logo", "File:Wikidata", "File:Question", "File:Symbol")
    filtered = [
        img["title"] for img in raw_images
        if not any(img["title"].startswith(p) for p in skip_prefixes)
    ]

    # Image-Infos (Lizenz, URL) für die ersten max_images holen
    if not filtered:
        return []

    image_info = []
    params2 = {
        "action":     "query",
        "titles":     "|".join(filtered[:max_images]),
        "prop":       "imageinfo",
        "iiprop":     "url|extmetadata",
        "iiurlwidth": 800,
        "format":     "json",
    }
    # Commons-API statt de.wikipedia für Bild-Metadaten
    resp2 = session.get(
        "https://commons.wikimedia.org/w/api.php",
        params=params2,
        timeout=30,
    )
    resp2.raise_for_status()
    cpages = resp2.json().get("query", {}).get("pages", {})
    for page in cpages.values():
        ii = page.get("imageinfo", [{}])[0]
        meta = ii.get("extmetadata", {})
        license_short = meta.get("LicenseShortName", {}).get("value", "unknown")
        # Nur freie Lizenzen
        if not _is_free_license(license_short):
            continue
        image_info.append({
            "wikimedia_id":  page.get("title", ""),
            "source_url":    ii.get("descriptionurl", ""),
            "thumb_url":     ii.get("thumburl", ""),
            "license":       _normalize_license(license_short),
            "license_author": meta.get("Artist", {}).get("value", ""),
            "alt":           meta.get("ImageDescription", {}).get("value", "")[:200],
        })
    return image_info


def _is_free_license(s: str) -> bool:
    s = s.upper()
    return any(k in s for k in ("CC0", "CC BY", "PUBLIC DOMAIN", "PD"))


def _normalize_license(s: str) -> str:
    mapping = {
        "CC0":        "CC0",
        "CC BY-SA 4": "CC BY-SA 4.0",
        "CC BY-SA":   "CC BY-SA",
        "CC BY 4":    "CC BY 4.0",
        "CC BY":      "CC BY",
        "PUBLIC":     "Public Domain",
        "PD":         "Public Domain",
    }
    for k, v in mapping.items():
        if k in s.upper():
            return v
    return s


# ─────────────────────────────────────────────
# Content-Tiefe + Interesse-Score
# ─────────────────────────────────────────────

def fetch_pageviews(session: requests.Session, title: str) -> int:
    """
    Fragt die Wikimedia Pageviews API ab.
    Gibt den Durchschnitt der letzten 3 Monate zurück.
    Bei Fehler: 0 (führt zu TOPIC_INTEREST='low' ohne Bonus).
    """
    import datetime
    end   = datetime.date.today().replace(day=1)
    start = (end - datetime.timedelta(days=90)).replace(day=1)
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"de.wikipedia/all-access/all-agents/"
        f"{title.replace(' ', '_')}/"
        f"monthly/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 404:
            return 0
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return 0
        return sum(i["views"] for i in items) // max(len(items), 1)
    except Exception:
        return 0


def compute_content_depth(text_length: int) -> int:
    """Leitet CONTENT_DEPTH aus der Wikipedia-Textlänge ab."""
    if text_length < 3000:
        return 1
    if text_length < 8000:
        return 2
    return 3


HIGH_INTEREST_CATEGORIES = {
    "tiere", "tiere_saeugetiere", "tiere_voegel",
    "tiere_reptilien", "tiere_insekten", "tiere_ausgestorben",
    "weltall", "weltall_raumfahrt", "weltall_planeten",
    "geschichte_antike", "geschichte_mittelalter",
    "kultur_sport", "kultur_essen",
    "pflanzen_pilze",
}


def compute_topic_interest(pageviews: int, category_id: str) -> str:
    """
    Bestimmt TOPIC_INTEREST aus Wikipedia-Pageviews und Kategorie.
    Kategorien die für Kinder besonders interessant sind bekommen
    einen Bonus-Faktor.
    """
    bonus = 1.5 if category_id in HIGH_INTEREST_CATEGORIES else 1.0
    adjusted = pageviews * bonus
    if adjusted > 50000:
        return "high"
    if adjusted > 10000:
        return "medium"
    return "low"


# ─────────────────────────────────────────────
# Whitelist + Dedup
# ─────────────────────────────────────────────

def load_whitelist(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_article_queue(
    whitelist: dict,
    session: requests.Session,
    age_levels: list[int],
    min_length: int,
    max_length: int,
) -> list[dict]:
    """
    Iteriert über alle Whitelist-Kategorien, fragt Wikipedia ab,
    filtert und gibt eine deduplizierte Liste von Job-Einträgen zurück.
    """
    seen_page_ids: set[int] = set()
    queue: list[dict] = []

    pipeline_rules = whitelist.get("pipeline_rules", {})
    effective_min = max(min_length, pipeline_rules.get("min_wikipedia_text_length", 500))
    effective_max = min(max_length, pipeline_rules.get("max_wikipedia_text_length", 50000))

    global_excl_patterns = whitelist.get("global_exclusions", {}).get("patterns", [])

    for top_cat in whitelist["categories"]:
        top_id          = top_cat["id"]
        theme_color     = top_cat["theme_color"]
        pattern         = PATTERN_FOR_CATEGORY.get(top_cat.get("category_ref", top_id), "tech_science")
        top_review_flag = top_cat.get("review_flag_default", False)
        top_review_reason = top_cat.get("review_reason", "")

        for sub in top_cat.get("subcategories", []):
            sub_id           = sub["id"]
            sub_review_flag  = sub.get("review_flag_default", top_review_flag)
            sub_review_reason = sub.get("review_reason", top_review_reason)
            sub_min_level    = sub.get("age_level_minimum", 1)

            wp_categories = sub.get("wikipedia_categories", [])
            if not wp_categories:
                log.warning("Sub %s hat keine wikipedia_categories — übersprungen", sub_id)
                continue

            log.info("  ↳ %s/%s — %d WP-Kategorien", top_id, sub_id, len(wp_categories))
            sub_members: list[dict] = []

            for wp_cat in wp_categories:
                # Globale Ausschlussmuster prüfen
                if any(excl.lower() in wp_cat.lower() for excl in global_excl_patterns):
                    log.debug("    Kategorie '%s' durch global_exclusions gefiltert", wp_cat)
                    continue
                try:
                    members = fetch_category_members(session, wp_cat)
                    log.debug("    %s → %d Mitglieder", wp_cat, len(members))
                    sub_members.extend(members)
                except Exception as e:
                    log.warning("    Fehler bei Kategorie '%s': %s", wp_cat, e)
                time.sleep(0.3)

            if not sub_members:
                continue

            # Deduplizieren innerhalb der Subkategorie
            unique_members = {m["pageid"]: m for m in sub_members if m["pageid"] not in seen_page_ids}
            if not unique_members:
                continue

            # Page-Infos (Länge, RevID) in Batches holen
            page_ids = list(unique_members.keys())
            try:
                page_infos = fetch_page_info(session, page_ids)
            except Exception as e:
                log.error("  fetch_page_info fehlgeschlagen: %s", e)
                continue

            for pid, member in unique_members.items():
                info = page_infos.get(pid, {})
                length = info.get("length", 0)

                # Längenfilter
                if not (effective_min <= length <= effective_max):
                    log.debug("    SKIP '%s' — Länge %d außerhalb [%d,%d]",
                              member["title"], length, effective_min, effective_max)
                    continue

                # Globale Ausschlussmuster im Titel
                if any(excl.lower() in member["title"].lower() for excl in global_excl_patterns):
                    log.debug("    SKIP '%s' — globale Ausschlussregel", member["title"])
                    continue

                seen_page_ids.add(pid)

                # Pageviews + abgeleitete Parameter
                pageviews      = fetch_pageviews(session, member["title"])
                time.sleep(0.1)
                content_depth  = compute_content_depth(info.get("length", 0))
                topic_interest = compute_topic_interest(pageviews, sub_id)

                # Job-Eintrag für alle angeforderten Altersgruppen ≥ sub_min_level
                for level in age_levels:
                    if level < sub_min_level:
                        continue
                    queue.append({
                        "article_id":       f"{_slugify(member['title'])}_l{level}",
                        "title":            member["title"],
                        "page_id":          pid,
                        "age_level":        level,
                        "pattern":          pattern,
                        "theme_color":      theme_color,
                        "category_top":     top_id,
                        "category_sub":     sub_id,
                        "source_url":       info.get("full_url", f"https://de.wikipedia.org/wiki/{member['title'].replace(' ','_')}"),
                        "source_rev":       str(info.get("rev_id", "")),
                        "review_flag":      sub_review_flag,
                        "review_reason":    sub_review_reason,
                        "queued_at":        datetime.now(timezone.utc).isoformat(),
                        "content_depth":    content_depth,
                        "topic_interest":   topic_interest,
                        "pageviews_month":  pageviews,
                    })

    log.info("Queue fertig: %d Jobs (%d eindeutige Artikel × Stufen)", len(queue), len(seen_page_ids))
    return queue


def _slugify(title: str) -> str:
    import re
    slug = title.lower().replace(" ", "_")
    slug = re.sub(r"[äöüß]", lambda m: {"ä":"ae","ö":"oe","ü":"ue","ß":"ss"}[m.group()], slug)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug[:60]


# ─────────────────────────────────────────────
# Batch-Schreiber
# ─────────────────────────────────────────────

def write_batches(queue: list[dict], out_dir: Path, batch_size: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i in range(0, len(queue), batch_size):
        batch = queue[i:i + batch_size]
        batch_num = i // batch_size + 1
        path = out_dir / f"batch_{batch_num:04d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "batch_number":    batch_num,
                "total_jobs":      len(batch),
                "created_at":      datetime.now(timezone.utc).isoformat(),
                "schema_version":  "1.0",
                "jobs":            batch,
            }, f, ensure_ascii=False, indent=2)
        written.append(path)
        log.info("  Batch %04d geschrieben: %d Jobs → %s", batch_num, len(batch), path)
    return written


# ─────────────────────────────────────────────
# Checkpoint / Resume
# ─────────────────────────────────────────────

def load_checkpoint(checkpoint_path: Path) -> set[str]:
    """Gibt bereits generierte article_ids zurück (für Resume)."""
    if not checkpoint_path.exists():
        return set()
    with open(checkpoint_path, encoding="utf-8") as f:
        return set(json.load(f))


def save_checkpoint(checkpoint_path: Path, done_ids: set[str]) -> None:
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(sorted(done_ids), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wissensfreund Artikel-Pipeline — Schritt 1: prepare_articles")
    p.add_argument("--whitelist",   required=True,  type=Path, help="Pfad zur wissensfreund_categories_whitelist.json")
    p.add_argument("--out-dir",     default="jobs", type=Path, help="Ausgabeverzeichnis für Batch-JSONs")
    p.add_argument("--age-levels",  nargs="+", type=int, default=[1, 2, 3], choices=[1, 2, 3])
    p.add_argument("--batch-size",  type=int, default=50, help="Jobs pro Batch-Datei")
    p.add_argument("--min-length",  type=int, default=500,   help="Min. Wikipedia-Textlänge (Zeichen)")
    p.add_argument("--max-length",  type=int, default=50000, help="Max. Wikipedia-Textlänge (Zeichen)")
    p.add_argument("--checkpoint",  type=Path, default=Path("checkpoint_done.json"), help="Checkpoint-Datei für Resume")
    p.add_argument("--dry-run",     action="store_true", help="Nur erste Kategorie, keine Dateien schreiben")
    p.add_argument("--top-category", type=str, default=None, help="Nur diese eine Top-Kategorie verarbeiten (z.B. 'tiere')")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    whitelist = load_whitelist(args.whitelist)
    log.info("Whitelist geladen: %d Top-Kategorien", len(whitelist["categories"]))

    if args.top_category:
        whitelist["categories"] = [
            c for c in whitelist["categories"]
            if c["id"] == args.top_category
        ]
        log.info("Filter aktiv: nur Kategorie '%s'", args.top_category)

    if args.dry_run:
        whitelist["categories"] = whitelist["categories"][:1]
        log.info("DRY-RUN: nur erste Kategorie (%s)", whitelist["categories"][0]["id"])

    session = wp_session()

    queue = build_article_queue(
        whitelist    = whitelist,
        session      = session,
        age_levels   = args.age_levels,
        min_length   = args.min_length,
        max_length   = args.max_length,
    )

    # Bereits fertige Artikel herausfiltern (Resume)
    done = load_checkpoint(args.checkpoint)
    if done:
        before = len(queue)
        queue = [j for j in queue if j["article_id"] not in done]
        log.info("Checkpoint: %d bereits erledigt, %d verbleibend (war %d)", len(done), len(queue), before)

    if args.dry_run:
        log.info("DRY-RUN abgeschlossen — %d Jobs gefunden, keine Dateien geschrieben", len(queue))
        for job in queue[:5]:
            print(json.dumps(job, ensure_ascii=False, indent=2))
        return

    batches = write_batches(queue, args.out_dir, args.batch_size)

    # Manifest schreiben
    manifest_path = args.out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "created_at":   datetime.now(timezone.utc).isoformat(),
            "total_jobs":   len(queue),
            "total_batches": len(batches),
            "age_levels":   args.age_levels,
            "batch_size":   args.batch_size,
            "batch_files":  [str(b.name) for b in batches],
        }, f, ensure_ascii=False, indent=2)

    log.info("Fertig. %d Jobs in %d Batches → %s", len(queue), len(batches), args.out_dir)
    log.info("Manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
