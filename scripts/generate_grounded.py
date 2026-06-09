#!/usr/bin/env python3
"""
generate_grounded.py
Zwei-Phasen-Artikel-Generierung mit Kompass-Companion-Grounding + Vision-Bildpool.

Phase 1 (KOMPASS, einmal pro Thema):
  Gemini schlägt Begleitartikel frei aus Wissen vor (kein Link-Pool).
  Validierung: Wikipedia-Existenz prüfen + Weiterleitungen auflösen.
  Shared über alle Stufen desselben Themas.

Phase 2 (je Stufe):
  Primärtext + Companion-Volltexte als stabiler Prefix → Prompt-Caching.
  Stufenspezifische AGE_LEVEL-Anweisung am Ende.

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
from collections import defaultdict
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
SYSTEM_PROMPT_PATH = ROOT / "wissensfreund_generator_prompt_v3.21_production.md"

APPEAL_TARGET     = {"high": 15, "medium": 10, "low": 6}
MAX_VISION_CHECKS = 40
MAX_IMG_PRIMARY   = 20
MAX_IMG_COMPANION = 6
MAX_COMPANIONS    = 5

AGE_RANGES = {1: "4-6 Jahre", 2: "7-9 Jahre", 3: "10-12 Jahre"}


def _make_thinking_config(model: str, budget_for_2_5: int) -> types.ThinkingConfig:
    """Gibt das modellspezifische ThinkingConfig zurück (medium)."""
    if "2.5" in model:
        cfg = types.ThinkingConfig(thinking_budget=budget_for_2_5)
        log.info("  ThinkingConfig: thinking_budget=%d (Modell=%s)", budget_for_2_5, model)
        return cfg
    cfg = types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)
    log.info("  ThinkingConfig: thinking_level=MEDIUM (Modell=%s)", model)
    return cfg


# ── Test-Jobs ─────────────────────────────────────────────────────────────────

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
    "biene_l1": {
        "article_id":        "biene_l1",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         1,
        "topic_interest":    "high",
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
    },
    "biene_l2": {
        "article_id":        "biene_l2",
        "thema":             "Biene",
        "primaer_wikipedia": "Biene",
        "title":             "Biene",
        "age_level":         2,
        "topic_interest":    "high",
        "pattern":           "living_being",
        "category_top":      "tiere",
        "category_sub":      "insekten",
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


# ── Phase-1-Prompt (Kompass) ─────────────────────────────────────────────────

COMPANION_SYSTEM_PROMPT = (
    "Du waehlst Wikipedia-Begleitartikel fuer einen Kinderwissens-Artikel aus.\n"
    "Antworte ausschliesslich mit gueltigem JSON ohne Markdown.\n"
    'Format: {"companions": ["Lemma1","Lemma2",...]}'
)

COMPANION_PROMPT_TMPL = """\
THEMA: {thema}

PRIMAERARTIKEL-EINLEITUNG:
{lead}

Schlage bis zu 5 deutschsprachige Wikipedia-Begleitartikel vor, die diesen Kinderartikel bereichern.
Kriterien:
- Vertiefen das Thema fuer ein Kind: konkret, anschaulich, lebendig
- Auch solche, mit denen sich laendlaeufige Vorstellungen aufgreifen und richtigstellen lassen
- Fokuserhaltend: Thema vertiefen, NICHT zu Eltern-/Nachbarthemen wechseln
- Lieber weniger als ungeeignete auffuellen (kein Mindestwert)
Ausgabe NUR JSON: {{"companions": ["Lemma1","Lemma2",...]}}"""


# ── Legacy-Funktionen (von batch_run.py importiert) ──────────────────────────

def fetch_wikipedia_links(session: requests.Session, title: str) -> list[str]:
    """Legacy: holt interne Links (Namespace 0). Noch von batch_run.py genutzt."""
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
    """Legacy: prüft Artikel-Existenz ohne Redirect-Auflösung. Noch von batch_run.py genutzt."""
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


def validate_companions(
    session: requests.Session,
    raw_companions: list[str],
    link_set: set[str],
) -> tuple[list[str], list[dict]]:
    """Legacy: validiert gegen Link-Set. Noch von batch_run.py genutzt."""
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


# ── Phase 1: Kompass-Auswahl ─────────────────────────────────────────────────

def select_companions_raw(
    client: genai.Client,
    thema: str,
    primary_text: str,
    model: str = GEMINI_MODEL,
) -> list[str]:
    """Kompass: Gemini schlägt Begleitartikel frei vor (kein Link-Pool)."""
    lead = primary_text[:1500]
    prompt = COMPANION_PROMPT_TMPL.format(thema=thema, lead=lead)
    thinking = _make_thinking_config(model, budget_for_2_5=1024)
    log.info("  Phase 1 Kompass-Auswahl (Modell=%s)", model)

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COMPANION_SYSTEM_PROMPT,
                    temperature=0.3,
                    thinking_config=thinking,
                ),
            )
            text = (response.text or "").strip()
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
            data = json.loads(text)
            return [str(c) for c in data.get("companions", [])][:10]
        except json.JSONDecodeError as e:
            log.warning("  Phase 1 JSON-Fehler (V%d): %s", attempt, e)
            return []
        except Exception as e:
            err = str(e)
            if attempt < 3 and ("503" in err or "unavailable" in err.lower()):
                log.warning("  Phase 1 503 (V%d) -- warte 60s ...", attempt)
                time.sleep(60)
            else:
                log.error("  Phase 1 Fehler: %s", e)
                return []
    return []


def validate_and_resolve_companions(
    session: requests.Session,
    raw_companions: list[str],
    primary_title: str,
) -> tuple[list[str], list[dict]]:
    """
    Prüft Wikipedia-Existenz, löst Weiterleitungen auf, dedupliziert.
    Gibt (valid_canonical, rejected_log) zurück.
    """
    if not raw_companions:
        return [], []

    params = {
        "action": "query", "format": "json",
        "titles": "|".join(raw_companions[:10]),
        "redirects": "1",
        "prop": "info",
    }
    try:
        resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        query = resp.json().get("query", {})
    except Exception as e:
        log.error("  Companion-Validierung API-Fehler: %s", e)
        return [], [{"title": c, "resolved": None, "reason": f"API-Fehler: {e}"}
                    for c in raw_companions]

    # Auflösungskette aufbauen: Normalisierung + Weiterleitungen
    resolve: dict[str, str] = {}
    for n in query.get("normalized", []):
        resolve[n["from"]] = n["to"]
    for r in query.get("redirects", []):
        resolve[r["from"]] = r["to"]

    def follow(title: str) -> str:
        seen_chain: set[str] = set()
        t = title
        while t in resolve and t not in seen_chain:
            seen_chain.add(t)
            t = resolve[t]
        return t

    existing: set[str] = {
        page["title"]
        for page in query.get("pages", {}).values()
        if "missing" not in page
    }

    valid: list[str] = []
    rejected: list[dict] = []
    seen_resolved: set[str] = set()
    primary_lower = primary_title.lower()

    for comp in raw_companions:
        resolved = follow(comp)
        resolved_lower = resolved.lower()
        changed = resolved != comp

        if resolved not in existing:
            rejected.append({"title": comp, "resolved": resolved, "reason": "nicht gefunden"})
            log.warning("  Verworfen: '%s'%s (nicht gefunden)", comp,
                        f" -> '{resolved}'" if changed else "")
            continue
        if resolved_lower == primary_lower:
            rejected.append({"title": comp, "resolved": resolved, "reason": "= Primaerartikel"})
            log.warning("  Verworfen: '%s' (= Primaerartikel)", comp)
            continue
        if resolved_lower in seen_resolved:
            rejected.append({"title": comp, "resolved": resolved, "reason": "Duplikat"})
            log.warning("  Verworfen: '%s' (Duplikat nach Aufloesung)", comp)
            continue

        seen_resolved.add(resolved_lower)
        if changed:
            log.info("  Companion aufgeloest: '%s' -> '%s'", comp, resolved)
        valid.append(resolved)

    return valid[:MAX_COMPANIONS], rejected


# ── Bildpool ──────────────────────────────────────────────────────────────────

def build_image_pool(
    session: requests.Session,
    client: genai.Client,
    thema: str,
    primary_wikipedia: str,
    companion_titles: list[str],
    appeal: str,
) -> tuple[list[dict], dict]:
    all_candidates: list[dict] = []
    sources: dict[str, int] = {}

    primary_imgs = fetch_image_candidates(
        session, primary_wikipedia, max_candidates=MAX_IMG_PRIMARY
    )
    sources[primary_wikipedia] = len(primary_imgs)
    for img in primary_imgs:
        img["_source"] = primary_wikipedia
    all_candidates.extend(primary_imgs)
    log.info("    Bilder aus '%s': %d (cap=%d)", primary_wikipedia, len(primary_imgs), MAX_IMG_PRIMARY)

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

    seen: set[str] = set()
    unique: list[dict] = []
    for img in all_candidates:
        fn = img["filename"]
        if fn not in seen:
            seen.add(fn)
            unique.append(img)

    to_check = unique[:MAX_VISION_CHECKS]
    log.info("    Kandidaten gesamt (dedupliziert): %d, Vision-Check: %d",
             len(unique), len(to_check))

    accepted: list[dict] = []
    rejected_vision: list[dict] = []
    target = APPEAL_TARGET.get(appeal, 10)
    _consecutive_dl_failures = 0

    for img in to_check:
        if len(accepted) >= target:
            log.info("    Target %d erreicht -- Vision-Check gestoppt", target)
            break

        img_bytes = download_image(session, img["thumb_url"])
        if img_bytes is None:
            rejected_vision.append({**img, "reason": "Download fehlgeschlagen"})
            _consecutive_dl_failures += 1
            if _consecutive_dl_failures >= 3:
                log.warning("    3 Downloads fehlgeschlagen -- 60s Wikimedia-Cooldown ...")
                time.sleep(60)
                _consecutive_dl_failures = 0
            else:
                time.sleep(10.0)
            continue

        _consecutive_dl_failures = 0
        mime = "image/jpeg"

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

        time.sleep(10.0)

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
    """
    Baut die User-Message mit stabilem Quell-Prefix und variablem AGE_LEVEL am Ende.
    Stabiler Prefix (gleich für alle Stufen eines Themas) → Prompt-Caching greift.
    """
    thema = job.get("thema", job["title"])
    primaer_src = job.get("primaer_wikipedia", job["title"])
    parts: list[str] = []

    # ── Stabiler Prefix: Wikipedia-Texte ─────────────────────────────────────
    parts += [f"WIKIPEDIA_TEXT_1 (Primaarartikel: {primaer_src}):", primary_text, ""]
    for i, comp in enumerate(companion_order, 2):
        text = companion_texts.get(comp, "")
        if text:
            parts += [f"WIKIPEDIA_TEXT_{i} (Begleitartikel: {comp}):", text[:6000], ""]

    # Stabile Metadaten
    parts.append(f"ARTICLE_TITLE: {thema}")
    if job.get("topic_interest"):
        parts.append(f"TOPIC_INTEREST: {job['topic_interest']}")
    if companion_order:
        parts.append(f"VERWENDETE_BEGLEITTEXTE: {', '.join(companion_order)}")

    # Bildpool (stabil — gleiche Images für alle Stufen)
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

    # ── Variabler Suffix: nur AGE_LEVEL wechselt je Stufe ───────────────────
    parts.append(f"AGE_LEVEL: {job['age_level']}")

    return "\n".join(parts)


# ── Phase-1-Orchestrierung: einmal pro Thema ─────────────────────────────────

def prepare_topic_sources(
    session: requests.Session,
    client: genai.Client,
    primary_wikipedia: str,
    thema: str,
    appeal: str,
    model: str,
    skip_images: bool,
) -> tuple[str, list[str], dict[str, str], list[dict], dict]:
    """
    Phase 1 + Quellen-Fetch, einmalig pro Thema.
    Gibt (primary_text, valid_companions, companion_texts, images, phase1_report) zurück.
    """
    # Primärtext
    log.info("  Hole Primaertext: '%s'", primary_wikipedia)
    time.sleep(2.0)
    primary_text = fetch_wikipedia_text(session, primary_wikipedia)
    log.info("  Primaertext: %d Zeichen", len(primary_text))

    if len(primary_text) < 300:
        raise ValueError(f"Primaertext zu kurz: {len(primary_text)} Zeichen")

    # Kompass-Auswahl
    raw_companions = select_companions_raw(client, thema, primary_text, model)
    log.info("  Kompass-Vorschlag: %s", raw_companions)

    # Validierung + Weiterleitungsauflösung
    valid_companions, rejected = validate_and_resolve_companions(
        session, raw_companions, primary_wikipedia
    )
    log.info("  Validiert (final): %s", valid_companions)

    phase1_report: dict = {
        "raw_companions":   raw_companions,
        "valid_companions": valid_companions,
        "rejected":         rejected,
    }

    # Companion-Volltexte holen
    companion_texts: dict[str, str] = {}
    for comp in valid_companions:
        try:
            time.sleep(0.5)
            ct = fetch_wikipedia_text(session, comp)
            companion_texts[comp] = ct
            log.info("  Companion-Text '%s': %d Zeichen", comp, len(ct))
        except Exception as e:
            log.warning("  Companion-Text '%s' Fehler: %s", comp, e)

    # Bildpool (optional)
    if skip_images:
        images: list[dict] = []
        log.info("  Bildpool: uebersprungen (--skip-images)")
    else:
        fetched_companions = [c for c in valid_companions if c in companion_texts]
        log.info("  Baue Bildpool (Primaer + %d Companions) ...", len(fetched_companions))
        images, img_report = build_image_pool(
            session, client, thema, primary_wikipedia, fetched_companions, appeal
        )
        log.info("  Bildpool: %d akzeptiert, Hero=%s",
                 img_report["accepted"], img_report["hero"])
        phase1_report["images"] = img_report

    return primary_text, valid_companions, companion_texts, images, phase1_report


# ── Phase-2-Generierung: je Stufe ────────────────────────────────────────────

def generate_one_level(
    client: genai.Client,
    system_prompt: str,
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    valid_companions: list[str],
    images: list[dict],
    phase1_report: dict,
    model: str,
    skip_images: bool,
    out_dir: Path,
) -> tuple[dict | None, dict]:
    """Phase 2: Artikel für eine Stufe generieren (shared sources)."""
    article_id       = job["article_id"]
    thema            = job.get("thema", job["title"])
    prompt_version   = SYSTEM_PROMPT_PATH.stem.split("_v")[-1].split("_")[0]
    generation_method = f"{model}/medium/v{prompt_version}"

    report: dict = {
        "article_id":        article_id,
        "thema":             thema,
        "primaer_wikipedia": job.get("primaer_wikipedia", thema),
        "phase1":            phase1_report,
        "phase2":            {"images": {"skipped": True} if skip_images else {}},
        "errors":            [],
    }

    log.info("  Phase 2: Artikel generieren (Thema: %s, Stufe %d, Modell: %s)",
             thema, job["age_level"], model)
    user_msg = build_grounded_user_message(
        job, primary_text, companion_texts, valid_companions, images
    )
    report["phase2"]["user_msg_len"] = len(user_msg)

    phase2_thinking = _make_thinking_config(model, budget_for_2_5=8192)
    try:
        raw_response = gemini_client.call_gemini(
            system_prompt, user_msg, model=model, thinking_config=phase2_thinking
        )
    except Exception as e:
        report["errors"].append(f"Gemini-Fehler Phase 2: {e}")
        return None, report

    try:
        article = parse_article_json(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        report["errors"].append(f"JSON-Parse: {e}")
        errors_dir = out_dir / "_errors"
        errors_dir.mkdir(parents=True, exist_ok=True)
        (errors_dir / f"{article_id}_raw.txt").write_text(raw_response or "", encoding="utf-8")
        return None, report

    article.setdefault("meta", {})["id"]           = article_id
    article["meta"]["title"]                        = thema
    article["meta"]["generated_at"]                 = datetime.now(timezone.utc).isoformat()
    article["meta"]["grounding_companions"]          = valid_companions
    article["meta"]["generation_method"]             = generation_method

    val_errors = validate_article(article, job)
    if val_errors:
        for e in val_errors:
            log.warning("  Validierungsfehler: %s", e)
        article["meta"]["review_flag"]   = True
        article["meta"]["review_reason"] = "; ".join(val_errors[:3])

    report["phase2"]["validation_errors"]  = val_errors
    report["phase2"]["companions_fetched"] = list(companion_texts.keys())

    return article, report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Kompass-Grounding Artikel-Generator")
    parser.add_argument(
        "--articles", nargs="+",
        default=list(TEST_JOBS.keys()),
        help="Artikel-IDs zum Generieren (default: alle Test-Jobs)",
    )
    parser.add_argument(
        "--gen-model", default=None,
        help="Gemini-Modell (z.B. gemini-2.5-flash, gemini-3.5-flash)",
    )
    parser.add_argument(
        "--skip-images", action="store_true",
        help="Bildpipeline komplett ueberspringen",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Ausgabeverzeichnis (default: articles/test_grounded)",
    )
    args = parser.parse_args()

    model      = args.gen_model or GEMINI_MODEL
    out_dir    = Path(args.output_dir).resolve() if args.output_dir else OUT_DIR
    model_slug = model.replace("gemini-", "").replace(".", "-")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))
    log.info("Modell: %s | skip_images: %s | out_dir: %s", model, args.skip_images, out_dir)

    client = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_errors").mkdir(exist_ok=True)

    # Jobs sammeln + Modell-Slug in article_id einbauen
    resolved_jobs: list[dict] = []
    for article_id in args.articles:
        job = TEST_JOBS.get(article_id)
        if not job:
            log.error("Unbekannte article_id: %s (verfuegbar: %s)",
                      article_id, list(TEST_JOBS.keys()))
            continue
        if args.gen_model:
            parts = article_id.rsplit("_", 1)
            effective_id = f"{parts[0]}_{model_slug}_{parts[1]}"
        else:
            effective_id = article_id
        resolved_jobs.append({**job, "article_id": effective_id})

    # Nach primaer_wikipedia gruppieren (Reihenfolge des ersten Auftretens bewahren)
    topic_groups: dict[str, list[dict]] = defaultdict(list)
    seen_topics: list[str] = []
    for job in resolved_jobs:
        primaer = job.get("primaer_wikipedia", job["title"])
        if primaer not in topic_groups:
            seen_topics.append(primaer)
        topic_groups[primaer].append(job)

    # ── Pro Thema: Phase 1 einmal, Phase 2 je Stufe ──────────────────────────
    for primary_wikipedia in seen_topics:
        topic_jobs = topic_groups[primary_wikipedia]
        thema  = topic_jobs[0].get("thema", topic_jobs[0]["title"])
        appeal = topic_jobs[0].get("topic_interest", "medium")
        levels = [j["age_level"] for j in topic_jobs]

        print(f"\n{'='*60}")
        print(f"THEMA: {thema} | Primaer: {primary_wikipedia} | Modell: {model}")
        print(f"Stufen: {levels} | Phase 1 laeuft EINMAL fuer alle Stufen")
        print(f"{'='*60}")

        try:
            primary_text, valid_companions, companion_texts, images, phase1_report = (
                prepare_topic_sources(
                    session, client, primary_wikipedia, thema, appeal,
                    model, args.skip_images
                )
            )
        except Exception as e:
            log.error("  Topic-Setup fehlgeschlagen: %s", e)
            continue

        # Befund Phase 1 ausgeben
        print(f"\n  [PHASE 1 — einmalig fuer '{thema}']")
        print(f"  Kompass-Vorschlag (roh): {phase1_report['raw_companions']}")
        for r in phase1_report["rejected"]:
            resolved_hint = f" (aufgeloest: '{r['resolved']}')" if r.get("resolved") else ""
            print(f"  Verworfen: '{r['title']}'{resolved_hint} — {r['reason']}")
        print(f"  Validiert + aufgeloest:  {valid_companions}")
        print(f"  [Quellblock wird fuer {len(topic_jobs)} Stufe(n) geteilt + gecacht]")

        # Phase 2: je Stufe
        for job in topic_jobs:
            article_id = job["article_id"]
            print(f"\n  --- Stufe {job['age_level']}: {article_id} ---")

            article, report = generate_one_level(
                client, system_prompt, job,
                primary_text, companion_texts, valid_companions, images,
                phase1_report, model, args.skip_images, out_dir,
            )

            report_path = out_dir / f"{article_id}_report.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if article:
                out_path = out_dir / f"{article_id}.json"
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
                gen_m  = article["meta"].get("generation_method", "?")
                print(f"  Gespeichert: {out_path.relative_to(ROOT)}")
                print(f"  meta.title='{meta_title}' | method='{gen_m}'")
                print(f"  Bilder: {n_imgs} | Saetze: {n_sents}{review}")
            else:
                print(f"  FEHLER: {report.get('errors')}")

            print(f"  Report: {report_path.relative_to(ROOT)}")

        print(f"\n  Companions (geteilt): {valid_companions}")


if __name__ == "__main__":
    main()
