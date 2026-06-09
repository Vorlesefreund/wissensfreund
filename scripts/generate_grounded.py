#!/usr/bin/env python3
"""
generate_grounded.py
Zwei-Phasen-Artikel-Generierung mit validiertem Companion-Grounding + Vision-Bildpool.

FIX 1: thema (Anzeigetitel) vs. primaer_wikipedia (Quelle) getrennt.
       meta.title kommt IMMER aus thema, nie aus dem Wikipedia-Quellnamen.
FIX 2: Zwei-Phasen-Grounding (bereits vorhanden, erhalten).
FIX 3: Bild-Deckelung: Primär max. 20, je Companion max. 6, Gesamt-Pool max. 40.
       Batch-Download (parallel, Cache-first) vor Vision-Check.

Phase 1: Flash wählt Begleitartikel aus Wikipedia-Link-Liste des Primärartikels.
         Pipeline validiert: Link vorhanden + Artikel existiert auf Wikipedia.
Phase 2: Pipeline holt Companion-Volltexte + Vision-geprüften Bildpool.
         Flash generiert Artikel aus Primär + Companions + Pool.

Usage:
    python scripts/generate_grounded.py
    python scripts/generate_grounded.py --articles indianer_l1 indianer_l2 indianer_l3
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Imports aus bestehenden Modulen (nach logging-Setup)
sys.path.insert(0, str(Path(__file__).parent))
from generate_articles import (          # noqa: E402
    fetch_wikipedia_text,
    parse_article_json,
    validate_article,
    WIKIPEDIA_API,
    USER_AGENT,
    MIN_SENTENCES_PER_ARTICLE,
    MAX_SENTENCES_PER_ARTICLE,
)
import gemini_client                     # noqa: E402
from image_vision_filter import (        # noqa: E402
    fetch_image_candidates,
    download_image,
    analyze_with_vision,
)

GEMINI_MODEL       = "gemini-2.5-flash"
OUT_DIR            = ROOT / "articles" / "test_grounded"
SYSTEM_PROMPT_PATH = ROOT / "wissensfreund_generator_prompt_v3.20_production.md"

# Ziel-Bildanzahl nach Appeal (Cap — nie auffüllen)
APPEAL_TARGET     = {"high": 15, "medium": 10, "low": 6}
MAX_VISION_CHECKS = 40   # Gesamt-Obergrenze Kandidaten vor Vision
MAX_IMG_PRIMARY   = 20   # Max. Bilder aus Primärartikel (FIX 3)
MAX_IMG_COMPANION = 6    # Max. Bilder je Begleitartikel (FIX 3)
MAX_COMPANIONS    = 4    # Max. Begleitartikel die Flash wählen darf
MAX_LINK_LIST     = 300  # Max. Links im Companion-Prompt

AGE_RANGES = {1: "4-6 Jahre", 2: "7-9 Jahre", 3: "10-12 Jahre"}

# ── Test-Jobs (FIX 1: thema + primaer_wikipedia getrennt) ────────────────────
#
# thema            = kindgerechter Anzeigetitel → meta.title, ARTICLE_TITLE, Rahmung
# primaer_wikipedia = exakter Wikipedia-Artikeltitel für Fakten-Fetch
# title            = thema (Backward-Compat mit validate_article)

TEST_JOBS: dict[str, dict] = {
    "indianer_l1": {
        "article_id":        "indianer_l1",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         1,
        "topic_interest":    "high",
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "indianer_l2": {
        "article_id":        "indianer_l2",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         2,
        "topic_interest":    "high",
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "indianer_l3": {
        "article_id":        "indianer_l3",
        "thema":             "Indianer",
        "primaer_wikipedia": "Indianer",
        "title":             "Indianer",
        "age_level":         3,
        "topic_interest":    "high",
        "pattern":           "history_person",
        "category_top":      "laender_und_kulturen",
        "category_sub":      "voelker_und_kulturen",
    },
    "biene_l3": {
        "article_id":        "biene_l3",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         3,
        "topic_interest":    "high",
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
    },
    "demokratie_l1": {
        "article_id":        "demokratie_l1",
        "thema":             "Demokratie",
        "primaer_wikipedia": "Demokratie",
        "title":             "Demokratie",
        "age_level":         1,
        "topic_interest":    "medium",
        "pattern":           "tech_science",
        "category_top":      "gesellschaft",
        "category_sub":      "staat_und_recht",
    },
}

# ── Phase-1-Prompt ───────────────────────────────────────────────────────────

COMPANION_SYSTEM_PROMPT = (
    "Du wählst Wikipedia-Begleitartikel für einen Kinderwissens-Artikel aus.\n"
    "Antworte ausschliesslich mit gueltigem JSON ohne Markdown.\n"
    'Format: {"companions": ["Titel1", "Titel2"]}'
)

COMPANION_PROMPT_TMPL = """\
THEMA: {thema} (Stufe {age_level}, {ages})
APPEAL: {appeal}

PRIMAERTEXT (erste 2000 Zeichen):
{excerpt}

LINK_LISTE ({n_links} interne Wikipedia-Links aus dem Artikel):
{link_list}

Waehle 2-4 Begleitartikel die den Kinderartikel am meisten bereichern.
Nur Artikel aus der LINK_LISTE. Kriterien:
- Konkrete Inhalte fuer Kinder: Verhalten, Prozesse, Rekorde, Fakten
- Thematisch nah am Primaer-Thema (vertiefen, nicht abweichen)
Antworte NUR mit JSON: {{"companions": ["Titel1", "Titel2"]}}"""


# ── Wikipedia-Hilfsfunktionen ─────────────────────────────────────────────────

def fetch_wikipedia_links(session: requests.Session, title: str) -> list[str]:
    """Holt alle internen Links (Namespace 0) eines Wikipedia-Artikels."""
    all_links: list[str] = []
    params = {
        "action": "query", "format": "json",
        "titles": title, "redirects": "1",
        "prop": "links", "plnamespace": 0, "pllimit": 500,
    }
    while True:
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            for lnk in page.get("links", []):
                t = lnk.get("title", "")
                if t:
                    all_links.append(t)
        cont = data.get("continue", {})
        if "plcontinue" not in cont:
            break
        params["plcontinue"] = cont["plcontinue"]
        time.sleep(0.2)
    return all_links


def check_articles_exist(session: requests.Session, titles: list[str]) -> dict[str, bool]:
    """Prüft für eine Liste von Titeln ob die Wikipedia-Artikel existieren."""
    result: dict[str, bool] = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i+20]
        params = {
            "action": "query", "format": "json",
            "titles": "|".join(chunk), "redirects": "1",
            "prop": "info",
        }
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        normalizations = {
            n["from"].lower(): n["to"]
            for n in data.get("query", {}).get("normalized", [])
        }
        redirects = {
            r["from"].lower(): r["to"]
            for r in data.get("query", {}).get("redirects", [])
        }
        for t in chunk:
            result[t] = any(
                "missing" not in page
                for page in pages.values()
                if page.get("title", "").lower() in (
                    t.lower(),
                    normalizations.get(t.lower(), "").lower(),
                    redirects.get(t.lower(), "").lower(),
                )
            )
        time.sleep(0.1)
    return result


# ── Phase 1: Companion-Auswahl ────────────────────────────────────────────────

def select_companions_raw(
    client: genai.Client,
    thema: str,
    age_level: int,
    appeal: str,
    primary_text: str,
    link_list: list[str],
) -> list[str]:
    """Flash wählt Begleitartikel aus. Gibt Roh-Liste zurück (noch nicht validiert)."""
    link_sample = link_list[:MAX_LINK_LIST]
    prompt = COMPANION_PROMPT_TMPL.format(
        thema=thema,
        age_level=age_level,
        ages=AGE_RANGES.get(age_level, ""),
        appeal=appeal,
        excerpt=primary_text[:2000],
        n_links=len(link_sample),
        link_list=", ".join(link_sample),
    )

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COMPANION_SYSTEM_PROMPT,
                    temperature=0.3,
                    thinking_config=types.ThinkingConfig(thinking_budget=1024),
                ),
            )
            text = (response.text or "").strip()
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
            data = json.loads(text)
            return [str(c) for c in data.get("companions", [])][:MAX_COMPANIONS]
        except json.JSONDecodeError as e:
            log.warning("  Phase 1 JSON-Fehler (V%d): %s", attempt, e)
            return []
        except Exception as e:
            err = str(e)
            if attempt < 3 and ("503" in err or "unavailable" in err.lower()):
                log.warning("  Phase 1 503 (V%d) — warte 60s ...", attempt)
                time.sleep(60)
            else:
                log.error("  Phase 1 Fehler: %s", e)
                return []
    return []


def validate_companions(
    session: requests.Session,
    raw_companions: list[str],
    link_set: set[str],
) -> tuple[list[str], list[dict]]:
    """Validiert Companion-Liste. Gibt (valid, rejected_log) zurück."""
    valid: list[str] = []
    rejected: list[dict] = []

    link_set_lower = {t.lower() for t in link_set}

    for comp in raw_companions:
        if comp.lower() not in link_set_lower:
            rejected.append({"title": comp, "reason": "nicht in Link-Liste des Primärartikels"})
            continue
        valid.append(comp)

    if valid:
        existence = check_articles_exist(session, valid)
        confirmed: list[str] = []
        for comp in valid:
            if existence.get(comp, False):
                confirmed.append(comp)
            else:
                rejected.append({"title": comp, "reason": "Wikipedia-Artikel nicht gefunden"})
        valid = confirmed

    return valid, rejected


# ── Bildpool (FIX 3: Deckelung + Batch-Download) ──────────────────────────────

def build_image_pool(
    session: requests.Session,
    client: genai.Client,
    thema: str,
    primary_wikipedia: str,
    companion_titles: list[str],
    appeal: str,
) -> tuple[list[dict], dict]:
    """
    Sammelt Bilder aus Primär + Companions, cappt pro Quelle,
    dedupliziert, batch-downloaded (Cache-first), vision-filtert.
    Gibt (accepted_images, report_dict) zurück.
    """
    all_candidates: list[dict] = []
    sources: dict[str, int] = {}

    # Primär-Bilder: max. MAX_IMG_PRIMARY nach Dateiname-Vorfilter
    primary_imgs = fetch_image_candidates(
        session, primary_wikipedia, max_candidates=MAX_IMG_PRIMARY
    )
    sources[primary_wikipedia] = len(primary_imgs)
    for img in primary_imgs:
        img["_source"] = primary_wikipedia
    all_candidates.extend(primary_imgs)
    log.info("    Bilder aus '%s': %d (cap=%d)", primary_wikipedia, len(primary_imgs), MAX_IMG_PRIMARY)

    # Companion-Bilder: max. MAX_IMG_COMPANION pro Artikel
    for comp_title in companion_titles:
        time.sleep(0.5)
        comp_imgs = fetch_image_candidates(
            session, comp_title, max_candidates=MAX_IMG_COMPANION
        )
        sources[comp_title] = len(comp_imgs)
        for img in comp_imgs:
            img["_source"] = comp_title
        all_candidates.extend(comp_imgs)
        log.info("    Bilder aus '%s': %d (cap=%d)", comp_title, len(comp_imgs), MAX_IMG_COMPANION)

    # Deduplizieren nach filename (primary first)
    seen: set[str] = set()
    unique: list[dict] = []
    for img in all_candidates:
        fn = img["filename"]
        if fn not in seen:
            seen.add(fn)
            unique.append(img)

    # Gesamtdeckel
    to_check = unique[:MAX_VISION_CHECKS]
    log.info("    Kandidaten gesamt (dedupliziert): %d, Vision-Check: %d", len(unique), len(to_check))

    # Vision-Check: sequenziell, 10s Pause — kein paralleles Batch-Download
    # (parallele Downloads triggern Wikimedia Burst-Rate-Limit auf upload.wikimedia.org)
    accepted: list[dict] = []
    rejected_vision: list[dict] = []
    target = APPEAL_TARGET.get(appeal, 10)
    _consecutive_dl_failures = 0

    for img in to_check:
        if len(accepted) >= target:
            log.info("    Target %d erreicht — Vision-Check gestoppt", target)
            break

        img_bytes = download_image(session, img["thumb_url"])
        if img_bytes is None:
            rejected_vision.append({**img, "reason": "Download fehlgeschlagen"})
            _consecutive_dl_failures += 1
            if _consecutive_dl_failures >= 3:
                log.warning("    3 Downloads fehlgeschlagen — 300s Wikimedia-Cooldown ...")
                time.sleep(300)
                _consecutive_dl_failures = 0
            else:
                time.sleep(10.0)
            continue

        _consecutive_dl_failures = 0
        mime = "image/jpeg"
        url = img["thumb_url"].lower()
        if url.endswith(".png"):
            mime = "image/png"
        elif url.endswith(".webp"):
            mime = "image/webp"

        result = analyze_with_vision(client, img_bytes, mime, thema)
        if result is None:
            rejected_vision.append({**img, "reason": "Vision-Fehler"})
            time.sleep(2.0)
            continue

        if not result.get("kindgerecht", False):
            grund = result.get("ablehnungsgrund", "")
            rejected_vision.append({**img, "reason": f"kindgerecht=false: {grund}"})
        elif result.get("relevanz", 0) < 4:
            rejected_vision.append({**img, "reason": f"relevanz={result['relevanz']} < 4"})
        else:
            accepted.append({
                **img,
                "relevanz":      result.get("relevanz", 5),
                "hero_tauglich": result.get("hero_tauglich", False),
                "beschreibung":  result.get("beschreibung", ""),
            })

        time.sleep(10.0)  # 10s zwischen Downloads — bleibt unter Wikimedia-Rate-Limit

    accepted.sort(key=lambda x: (-x["relevanz"], -int(x["hero_tauglich"])))
    accepted = accepted[:target]

    report = {
        "sources":          sources,
        "candidates_total": len(unique),
        "vision_checked":   len(accepted) + len(rejected_vision),
        "accepted":         len(accepted),
        "rejected":         len(rejected_vision),
        "target":           target,
        "hero":             next(
            (a["filename"] for a in accepted if a["hero_tauglich"]),
            accepted[0]["filename"] if accepted else None,
        ),
    }
    return accepted, report


# ── Phase-2-User-Message ──────────────────────────────────────────────────────

def build_grounded_user_message(
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    companion_order: list[str],
    images: list[dict],
) -> str:
    """Baut die User-Message mit Primär- + Companion-Texten + Vision-Bildpool."""
    thema = job.get("thema", job["title"])
    primaer_src = job.get("primaer_wikipedia", job["title"])
    parts: list[str] = []

    # Wikipedia-Texte (Primär + Companions)
    parts += [f"WIKIPEDIA_TEXT_1 (Primaarartikel: {primaer_src}):", primary_text, ""]
    for i, comp in enumerate(companion_order, 2):
        text = companion_texts.get(comp, "")
        if text:
            parts += [f"WIKIPEDIA_TEXT_{i} (Begleitartikel: {comp}):", text[:6000], ""]

    # Pflichtfelder
    parts += [
        f"ARTICLE_TITLE: {thema}",
        f"AGE_LEVEL: {job['age_level']}",
    ]
    if job.get("topic_interest"):
        parts.append(f"TOPIC_INTEREST: {job['topic_interest']}")
    if companion_order:
        parts.append(f"VERWENDETE_BEGLEITTEXTE: {', '.join(companion_order)}")

    # Bildpool mit Vision-Beschreibungen
    if images:
        parts += [
            "",
            "AVAILABLE_IMAGES (kindgerecht geprueft, mit Beschreibung):",
        ]
        for idx, img in enumerate(images):
            author = img.get("license_author", "")[:40]
            desc = img.get("beschreibung", "")
            hero_flag = " [HERO-KANDIDAT]" if img.get("hero_tauglich") else ""
            line = (
                f"[{idx}] {img['filename']} | {img['thumb_url']} | "
                f"{img['license']} | {author}"
            )
            if desc:
                line += f"\n    Beschreibung: {desc}{hero_flag} Relevanz: {img['relevanz']}/10"
            parts.append(line)
        parts += [
            "",
            "Bildauswahl-Regeln:",
            "- images[0] = Hero-Bild: das repraesentativste Foto des Themas",
            "- thumb_url in images[] = URL aus AVAILABLE_IMAGES (exakt uebernehmen)",
            "- img_index in sentences = 0-basierter Index in DEINEM images[]-Array",
            "- Kein Bild doppelt verwenden",
            f"- {'8-12 Bilder gesamt' if job.get('topic_interest') == 'high' else '4-8 Bilder gesamt'}",
            "- Fuer jedes Bild: filename, alt, caption, license, license_author, source_url, thumb_url befuellen",
        ]

    return "\n".join(parts)


# ── Haupt-Orchestrierung ──────────────────────────────────────────────────────

def run_grounded_article(
    session: requests.Session,
    client: genai.Client,
    system_prompt: str,
    job: dict,
) -> tuple[dict | None, dict]:
    """
    Führt Zwei-Phasen-Generierung durch.
    Gibt (article_dict_or_None, phase_report) zurück.
    """
    article_id       = job["article_id"]
    thema            = job.get("thema", job["title"])
    primaer_wikipedia = job.get("primaer_wikipedia", job["title"])
    appeal           = job.get("topic_interest", "medium")

    report: dict = {
        "article_id": article_id,
        "thema":      thema,
        "primaer_wikipedia": primaer_wikipedia,
        "phase1":     {},
        "phase2":     {},
        "errors":     [],
    }

    # ── Primärtext ────────────────────────────────────────────────────────────
    log.info("  Hole Primaertext: '%s' (thema='%s')", primaer_wikipedia, thema)
    try:
        primary_text = fetch_wikipedia_text(session, primaer_wikipedia)
    except Exception as e:
        report["errors"].append(f"Wikipedia-Fetch: {e}")
        return None, report

    if len(primary_text) < 300:
        report["errors"].append(f"Primaertext zu kurz: {len(primary_text)} Zeichen")
        return None, report

    log.info("  Primaertext: %d Zeichen", len(primary_text))

    # ── Phase 1: Links holen + Flash-Companion-Auswahl ────────────────────────
    log.info("  Phase 1: Link-Liste holen (%s) ...", primaer_wikipedia)
    try:
        link_list = fetch_wikipedia_links(session, primaer_wikipedia)
    except Exception as e:
        report["errors"].append(f"Links-Fetch: {e}")
        link_list = []

    link_set = set(link_list)
    log.info("  %d interne Links gefunden", len(link_list))

    log.info("  Phase 1: Flash waehlt Companions (Thema: %s) ...", thema)
    raw_companions = select_companions_raw(
        client, thema, job["age_level"], appeal, primary_text, link_list
    )
    log.info("  Flash-Vorschlag: %s", raw_companions)

    valid_companions, rejected_companions = validate_companions(
        session, raw_companions, link_set
    )
    log.info("  Validiert: %s", valid_companions)
    for r in rejected_companions:
        log.warning("  Verworfen: %s (%s)", r["title"], r["reason"])

    report["phase1"] = {
        "link_count":       len(link_list),
        "raw_companions":   raw_companions,
        "valid_companions": valid_companions,
        "rejected":         rejected_companions,
    }

    # ── Phase 2: Companion-Texte holen ───────────────────────────────────────
    companion_texts: dict[str, str] = {}
    for comp in valid_companions:
        try:
            ct = fetch_wikipedia_text(session, comp)
            companion_texts[comp] = ct
            log.info("  Companion-Text '%s': %d Zeichen", comp, len(ct))
        except Exception as e:
            log.warning("  Companion-Text '%s' Fehler: %s", comp, e)

    # ── Bildpool (FIX 3: Deckelung + Batch-Download) ─────────────────────────
    log.info("  Baue Bildpool (Primaer + %d Companions) ...", len(valid_companions))
    images, img_report = build_image_pool(
        session, client, thema,
        primaer_wikipedia, valid_companions, appeal
    )
    log.info("  Bildpool: %d akzeptiert, Hero=%s", img_report["accepted"], img_report["hero"])
    report["phase2"]["images"] = img_report

    # ── Phase 2: Artikel generieren ───────────────────────────────────────────
    log.info("  Phase 2: Artikel generieren (Thema: %s, Stufe %d) ...", thema, job["age_level"])
    user_msg = build_grounded_user_message(
        job, primary_text, companion_texts, valid_companions, images
    )
    report["phase2"]["user_msg_len"] = len(user_msg)

    try:
        raw_response = gemini_client.call_gemini(system_prompt, user_msg)
    except Exception as e:
        report["errors"].append(f"Gemini-Fehler Phase 2: {e}")
        return None, report

    try:
        article = parse_article_json(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        report["errors"].append(f"JSON-Parse: {e}")
        errors_dir = OUT_DIR / "_errors"
        errors_dir.mkdir(parents=True, exist_ok=True)
        (errors_dir / f"{article_id}_raw.txt").write_text(raw_response or "", encoding="utf-8")
        return None, report

    # Meta fixieren (FIX 1: title immer aus thema, nie aus Quellnamen)
    article.setdefault("meta", {})["id"] = article_id
    article["meta"]["title"] = thema                          # FIX 1: override
    article["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    article["meta"]["grounding_companions"] = valid_companions

    # Validieren
    val_errors = validate_article(article, job)
    if val_errors:
        for e in val_errors:
            log.warning("  Validierungsfehler: %s", e)
        article["meta"]["review_flag"] = True
        article["meta"]["review_reason"] = "; ".join(val_errors[:3])

    report["phase2"]["validation_errors"] = val_errors
    report["phase2"]["companions_fetched"] = list(companion_texts.keys())

    return article, report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Zwei-Phasen-Grounding Artikel-Generator")
    parser.add_argument(
        "--articles", nargs="+",
        default=list(TEST_JOBS.keys()),
        help="Artikel-IDs zum Generieren (default: alle Test-Jobs)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))

    client = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "_errors").mkdir(exist_ok=True)

    for article_id in args.articles:
        job = TEST_JOBS.get(article_id)
        if not job:
            log.error("Unbekannte article_id: %s (verfuegbar: %s)",
                      article_id, list(TEST_JOBS.keys()))
            continue

        thema = job.get("thema", job["title"])
        print(f"\n{'='*60}")
        print(f"GENERIERE: {article_id} | Thema: {thema} | Stufe {job['age_level']}")
        print(f"  primaer_wikipedia: {job.get('primaer_wikipedia', thema)}")
        print(f"{'='*60}")

        article, report = run_grounded_article(session, client, system_prompt, job)

        # Report speichern (immer)
        report_path = OUT_DIR / f"{article_id}_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if article:
            out_path = OUT_DIR / f"{article_id}.json"
            out_path.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            meta_title = article.get("meta", {}).get("title", "?")
            n_imgs = len(article.get("images", []))
            n_sents = sum(
                len(s.get("sentences", []))
                for s in article.get("sections", [])
            )
            review = " [REVIEW]" if article["meta"].get("review_flag") else ""
            print(f"\n  Artikel gespeichert: {out_path.relative_to(ROOT)}")
            print(f"  meta.title = '{meta_title}' (erwartet: '{thema}')")
            print(f"  Bilder: {n_imgs} | Saetze: {n_sents}{review}")
        else:
            print(f"\n  FEHLER: {report.get('errors')}")

        # Kompakter Bericht
        p1 = report.get("phase1", {})
        p2 = report.get("phase2", {})
        print(f"\n  Phase 1:")
        print(f"    Links gefunden:    {p1.get('link_count', 0)}")
        print(f"    Flash-Vorschlag:   {p1.get('raw_companions', [])}")
        print(f"    Validiert:         {p1.get('valid_companions', [])}")
        for r in p1.get("rejected", []):
            print(f"    Verworfen:         {r['title']} ({r['reason']})")
        img = p2.get("images", {})
        if img:
            print(f"\n  Bildpool:")
            for src, cnt in img.get("sources", {}).items():
                print(f"    {src}: {cnt} Kandidaten")
            print(f"    Vision-gecheckt: {img.get('vision_checked')}")
            print(f"    Akzeptiert:      {img.get('accepted')} / Target {img.get('target')}")
            print(f"    Hero-Bild:       {img.get('hero')}")
        if report.get("errors"):
            print(f"\n  Fehler: {report['errors']}")

        print(f"\n  Report: {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
