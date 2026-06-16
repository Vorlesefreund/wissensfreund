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
import concurrent.futures
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
sys.path.insert(0, str(Path(__file__).parent.parent))
import cost_tracker                      # noqa: E402
from generate_articles import (          # noqa: E402
    fetch_wikipedia_text,
    resolve_lemma,
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
from lektorat_common import (            # noqa: E402
    COMPANION_CHAR_CAP,
    PROBLEMATIC_VERDICTS,
    build_grounded_sources_block,
    build_lektorat_parts,
    annotate_article_lektorat,
    run_lektorat_batch,
    run_lektorat_sync,
)

GEMINI_MODEL       = "gemini-3.5-flash"
OUT_DIR            = ROOT / "articles" / "test_grounded"
CATALOG_PATH       = ROOT / "catalog_full.json"

_RUN_ID: str = ""   # wird in main() gesetzt (--run-id)
SYSTEM_PROMPT_PATH = ROOT / "wissensfreund_generator_prompt_v3.23_production.md"

APPEAL_TARGET     = {"high": 15, "medium": 10, "low": 6}
MAX_VISION_CHECKS = 40
MAX_IMG_PRIMARY   = 20
MAX_IMG_COMPANION = 6

# Companion-Cap gestaffelt nach Appeal (kein Auffüllen)
COMPANION_CAP = {"low": 4, "medium": 5, "high": 6}

# Ergiebigkeits-Bänder je Stufe: (Wlo, Whi). Wortziel = Kurve über Ergiebigkeits-Score.
ERG_BANDS: dict[int, tuple[int, int]] = {1: (50, 250), 2: (80, 400), 3: (100, 650)}
RETRY_FLOOR_FRAC   = 0.70   # Retry-Untergrenze als Bruchteil des Ziels (nur klares Untertreiben nachfordern)
ERG_FALLBACK_SCORE = 6      # medium, wenn Thema (noch) nicht gerated — sichtbar geloggt
APPEAL_TIER_HIGH   = 7.0    # Erg-Mittel ≥ → high   (steuert Companion-/Bildmenge)
APPEAL_TIER_MED    = 4.0    # Erg-Mittel ≥ → medium, sonst low
CAP_GRACE_FRAC     = 0.05   # Toleranz über wmax, bevor getrimmt wird (0.0 = strikt ≤ Cap)
TRIM_MAX_ATTEMPTS  = 2      # max. Trim-Pässe, danach review_flag

AGE_RANGES = {1: "4-6 Jahre", 2: "7-9 Jahre", 3: "10-12 Jahre"}


def _load_ergiebigkeit() -> dict[str, dict]:
    """Lädt ergiebigkeit_scores.json → key (thema.lower) → {S1,S2,S3}."""
    path = ROOT / "ergiebigkeit_scores.json"
    if not path.exists():
        log.warning("ergiebigkeit_scores.json fehlt (%s) — Wortziel/Appeal nutzen Fallback", path)
        return {}
    data = json.load(path.open(encoding="utf-8"))
    return data.get("scores", data)  # toleriert {_meta,scores}- oder flaches Format

_ERGIEBIGKEIT: dict[str, dict] = _load_ergiebigkeit()


def wortziel_for(thema: str, level: int) -> tuple[int, int, str]:
    """(wmin_retry_floor, wmax_target, source) aus Ergiebigkeit + Kurve.

    wmax = round(Wlo + clamp((Erg-2)/6, 0, 1) * (Whi-Wlo))   (Bänder = ERG_BANDS)
    wmin = round(wmax * RETRY_FLOOR_FRAC)
    Kein gerateter Score → ERG_FALLBACK_SCORE, sichtbar geloggt (nie still mis-sizen).
    """
    lo, hi = ERG_BANDS.get(level, (100, 250))
    rec = _ERGIEBIGKEIT.get(thema.strip().lower())
    if rec is None:
        erg, source = ERG_FALLBACK_SCORE, "fallback-medium"
        log.warning("  Ergiebigkeit fehlt für '%s' (Stufe %d) → Fallback-Score %d",
                    thema, level, erg)
    else:
        erg, source = int(rec.get(f"S{level}", ERG_FALLBACK_SCORE)), "ergiebigkeit"
    frac = max(0.0, min(1.0, (erg - 2) / 6))
    wmax = round(lo + frac * (hi - lo))
    wmin = round(wmax * RETRY_FLOOR_FRAC)
    return wmin, wmax, source


def appeal_for(thema: str, job_appeal: str | None = None) -> tuple[str, str]:
    """Appeal-Tier (high/medium/low) aus Ergiebigkeit (Mittel der 3 Stufen).

    Steuert NUR Companion-Anzahl + Bildmenge — NICHT das Wortbudget.
    Gerated → Tier aus Erg-Mittel; sonst Job-Wert; sonst 'medium' (sichtbar geloggt).
    """
    rec = _ERGIEBIGKEIT.get(thema.strip().lower())
    if rec is not None:
        s = [int(rec.get(f"S{i}", ERG_FALLBACK_SCORE)) for i in (1, 2, 3)]
        mean = sum(s) / 3
        tier = "high" if mean >= APPEAL_TIER_HIGH else ("medium" if mean >= APPEAL_TIER_MED else "low")
        return tier, "ergiebigkeit"
    if job_appeal in ("low", "medium", "high"):
        return job_appeal, "job"
    log.warning("  Appeal: kein Ergiebigkeits-Score für '%s' → Fallback 'medium'", thema)
    return "medium", "fallback-medium"


EIGNUNG_STRICT = False  # True VOR dem Bulk: Themen ohne Urteil werden blockiert statt zugelassen


def _load_eignung() -> dict[str, dict]:
    """Lädt eignung_verdicts.json → key (thema.lower) → {eignung,age_floor,framing_note}."""
    path = ROOT / "eignung_verdicts.json"
    if not path.exists():
        log.warning("eignung_verdicts.json fehlt (%s) — Themen laufen über Eignungs-Fallback", path)
        return {}
    raw = json.load(path.open(encoding="utf-8"))
    data = raw.get("verdicts", raw)
    # Keys auf lowercase normieren — eignung_for() sucht mit .lower()
    return {k.strip().lower(): v for k, v in data.items()}


_EIGNUNG: dict[str, dict] = _load_eignung()


def eignung_for(thema: str) -> dict:
    """Eignungs-Urteil: {eignung, age_floor, framing_note, source}. Kein Urteil → Fallback (sichtbar)."""
    rec = _EIGNUNG.get(thema.strip().lower())
    if rec is None:
        if EIGNUNG_STRICT:
            log.warning("  Eignung: kein Urteil für '%s' → STRICT: blockiert", thema)
            return {"eignung": "exclude", "age_floor": 1, "framing_note": "", "source": "fallback-strict"}
        log.warning("  Eignung: kein Urteil für '%s' → Default include/S1 (ungeprüft)", thema)
        return {"eignung": "include", "age_floor": 1, "framing_note": "", "source": "fallback-permissive"}
    # Neues Schema: exclude:true statt eignung:"exclude"; age_floor direkt als int
    eignung_val = "exclude" if rec.get("exclude") else rec.get("eignung", "include")
    return {
        "eignung":      eignung_val,
        "age_floor":    int(rec.get("age_floor", 1)),
        "framing_note": rec.get("framing_note", "") or "",
        "source":       "verdict",
    }


def count_article_words(article: dict) -> int:
    """Zählt Wörter in Fließtext + Boxen (ohne Quiz, ohne Überschriften)."""
    words = 0
    for sec in article.get("sections", []):
        for s in sec.get("sentences", []):
            words += len(s.get("text", "").split())
        for box in sec.get("boxes", []):
            words += len(box.get("text", "").split())
            words += len(box.get("reveal_text", "").split())
    return words


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
) -> tuple[list[str], dict]:
    """Kompass: Gemini schlägt Begleitartikel frei vor. Gibt (companions, usage_dict) zurück."""
    lead = primary_text[:1500]
    prompt = COMPANION_PROMPT_TMPL.format(thema=thema, lead=lead)
    thinking = _make_thinking_config(model, budget_for_2_5=1024)
    log.info("  Phase 1 Kompass-Auswahl (Modell=%s, structured_output=JSON)", model)

    companions_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "companions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            )
        },
        required=["companions"],
    )

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=COMPANION_SYSTEM_PROMPT,
                    temperature=0.3,
                    thinking_config=thinking,
                    response_mime_type="application/json",
                    response_schema=companions_schema,
                ),
            )
            um = getattr(response, "usage_metadata", None)
            usage: dict = {}
            if um:
                usage = {
                    "input_tok":    int(getattr(um, "prompt_token_count", 0) or 0),
                    "output_tok":   int(getattr(um, "candidates_token_count", 0) or 0),
                    "cached_tok":   int(getattr(um, "cached_content_token_count", 0) or 0),
                    "thoughts_tok": int(getattr(um, "thoughts_token_count", 0) or 0),
                }
            text = (response.text or "").strip()
            data = json.loads(text)
            return [str(c) for c in data.get("companions", [])][:10], usage
        except json.JSONDecodeError as e:
            log.warning("  Phase 1 JSON-Fehler (V%d): %s | raw=%r", attempt, e, (response.text or "")[:120])
            return [], {}
        except Exception as e:
            err = str(e)
            if attempt < max_attempts and ("503" in err or "unavailable" in err.lower()):
                wait = min(60 * (2 ** (attempt - 1)), 300)
                log.warning("  Phase 1 503 (V%d/%d) -- warte %ds ...", attempt, max_attempts, wait)
                time.sleep(wait)
            else:
                log.error("  Phase 1 Fehler: %s", e)
                return [], {}
    return [], {}


def validate_and_resolve_companions(
    session: requests.Session,
    raw_companions: list[str],
    primary_title: str,
    cap: int = 5,
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

    return valid[:cap], rejected


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
        # Stopp sobald genug ab_stufe=1-Bilder für die restriktivste Stufe gesammelt
        if sum(1 for a in accepted if a.get("ab_stufe", 1) == 1) >= target:
            log.info("    Target %d S1-Bilder erreicht -- Vision-Check gestoppt", target)
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

        result, vision_usage = analyze_with_vision(client, img_bytes, mime, thema)
        if vision_usage:
            cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                                schritt="vision", modell="gemini-2.5-flash", **vision_usage)
        if result is None:
            rejected_vision.append({**img, "reason": "Vision-Fehler"})
            time.sleep(2.0)
            continue

        ab_stufe = result.get("ab_stufe", 0)
        beschreibung = result.get("beschreibung", "")
        if ab_stufe == 0:
            rejected_vision.append({**img, "reason": f"gesperrt: {beschreibung}"})
        elif result.get("relevanz", 0) < 4:
            rejected_vision.append({**img, "reason": f"relevanz={result['relevanz']} < 4"})
        else:
            accepted.append({
                **img,
                "ab_stufe":       ab_stufe,
                "relevanz":       result.get("relevanz", 5),
                "hero_candidate": result.get("hero_candidate", False),
                "beschreibung":   beschreibung,
            })

        time.sleep(10.0)

    accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))

    report = {
        "sources":          sources,
        "candidates_total": len(unique),
        "vision_checked":   len(accepted) + len(rejected_vision),
        "accepted":         len(accepted),
        "rejected":         len(rejected_vision),
        "target":           target,
        "hero":             next(
            (a["filename"] for a in accepted if a.get("hero_candidate", False)),
            accepted[0]["filename"] if accepted else None,
        ),
    }
    return accepted, report


def select_images_for_stufe(pool: list[dict], stufe: int, appeal: str) -> list[dict]:
    """Filtert Bildpool auf Altersfreigabe (ab_stufe <= stufe), cap nach APPEAL_TARGET."""
    filtered = [img for img in pool if img.get("ab_stufe", 1) <= stufe]
    filtered.sort(key=lambda x: (-x.get("relevanz", 0), -int(x.get("hero_candidate", False))))
    cap = APPEAL_TARGET.get(appeal, 10)
    return filtered[:cap]


def _variable_suffix(job: dict, wmax: int) -> str:
    """Variabler Suffix je Stufe: AGE_LEVEL + Bild-Stufen-Filter + WORTZIEL.
    Muss identisch in build_grounded_user_message und _split_grounded_user_message sein."""
    stufe = job.get("age_level", 2)
    return (
        f"AGE_LEVEL: {stufe}\n"
        f"BILD-STUFEN-FILTER: Fuer AGE_LEVEL={stufe} ausschliesslich Bilder mit "
        f"ab_stufe<={stufe} verwenden. Bilder mit ab_stufe>{stufe} ignorieren.\n"
        f"WORTZIEL: Strebe {wmax} Woerter an und schoepfe den Wikipedia-Stoff so weit aus, "
        f"dass du nah an {wmax} herankommst. "
        f"{wmax} ist zugleich die harte Obergrenze — schreibe nicht darueber hinaus. "
        f"Wenn nach Erreichen von {wmax} noch Stoff uebrig ist, waehle die kindgerechtesten Aspekte aus, "
        f"statt alles aufzunehmen. "
        f"Kuerzer als {wmax} nur, wenn der Wikipedia-Stoff die Laenge nicht hergibt — niemals aufblaehen."
    )


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
            parts += [f"WIKIPEDIA_TEXT_{i} (Begleitartikel: {comp}):", text[:COMPANION_CHAR_CAP], ""]

    # Stabile Metadaten
    parts.append(f"ARTICLE_TITLE: {thema}")
    if job.get("topic_interest"):
        parts.append(f"TOPIC_INTEREST: {job['topic_interest']}")
    if companion_order:
        parts.append(f"VERWENDETE_BEGLEITTEXTE: {', '.join(companion_order)}")
    dd = job.get("doppelbedeutung_directive", "")
    if dd:
        parts.append(f"DOPPELBEDEUTUNG: {dd}")
    fr = job.get("framing_note", "")
    if fr:
        parts.append(f"FRAMING: {fr}")

    # Bildpool (stabil — gleiche Images für alle Stufen)
    if images:
        parts += [
            "",
            "AVAILABLE_IMAGES (kindgerecht geprueft, mit Beschreibung):",
        ]
        for idx, img in enumerate(images):
            author = img.get("license_author", "")[:40]
            desc = img.get("beschreibung", "")
            hero_flag = " [HERO-KANDIDAT]" if img.get("hero_candidate") else ""
            line = (
                f"[{idx}] {img['filename']} | ab_stufe={img.get('ab_stufe', 1)} | {img['thumb_url']} | "
                f"{img['license']} | {author}"
            )
            if desc:
                line += f"\n    Beschreibung: {desc}{hero_flag} Relevanz: {img['relevanz']}/10"
            parts.append(line)
        _appeal_band = {"high": "10–15", "medium": "5–10", "low": "3–6"}.get(
            job.get("resolved_appeal", "medium"), "5–10"
        )
        parts += [
            "",
            "Bildauswahl-Regeln:",
            "- images[0] = Hero-Bild: das repraesentativste Foto des Themas",
            "- thumb_url in images[] = URL aus AVAILABLE_IMAGES (exakt uebernehmen)",
            "- img_index in sentences = 0-basierter Index in DEINEM images[]-Array",
            "- Kein Bild doppelt verwenden",
            f"- {_appeal_band} Bilder gesamt (nur wenn gute vorhanden; nie erzwingen)",
            "- Fuer jedes Bild: filename, alt, caption, license, license_author, source_url, thumb_url befuellen",
        ]

    # ── Variabler Suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL je Stufe ─
    level   = job.get("age_level", 2)
    wmin, wmax, _wz_src = wortziel_for(thema, level)
    parts.append(_variable_suffix(job, wmax))

    return "\n".join(parts)


def _split_grounded_user_message(
    job: dict,
    primary_text: str,
    companion_texts: dict[str, str],
    companion_order: list[str],
    images: list[dict],
) -> tuple[str, str]:
    """Teilt die User-Message in (stabiler_prefix, variabler_suffix).

    stabiler_prefix: Wikipedia-Texte + Metadaten + Bilder (gleich für alle Stufen)
    variabler_suffix: AGE_LEVEL + BILD-STUFEN-FILTER + WORTZIEL (je Stufe verschieden)
    """
    full = build_grounded_user_message(
        job, primary_text, companion_texts, companion_order, images
    )
    level  = job.get("age_level", 2)
    thema  = job.get("thema", job.get("title", ""))
    wmin, wmax, _wz_src = wortziel_for(thema, level)
    variable = _variable_suffix(job, wmax)
    stable = full[: len(full) - len(variable)].rstrip("\n")
    return stable, variable


# ── Gemini Context Cache ─────────────────────────────────────────────────────

def try_create_gemini_cache(
    client: genai.Client,
    model: str,
    system_prompt: str,
    stable_prefix: str,
) -> str | None:
    """Versucht, einen Gemini Context Cache für den stabilen Quellblock zu erstellen.

    Gibt den Cache-Namen zurück (z.B. 'cachedContents/abc123') oder None bei Fehler.
    Mindestens ~4 000 Tokens Inhalt nötig (je Modell); bei nicht unterstütztem Modell
    oder Fehler: graceful fallback (None → volle Message senden).
    """
    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                contents=[{"role": "user", "parts": [{"text": stable_prefix}]}],
                ttl="900s",
            ),
        )
        log.info("  Gemini-Cache erstellt: %s (~%d Zeichen stable_prefix)",
                 cache.name, len(stable_prefix))
        return cache.name
    except Exception as e:
        log.info("  Gemini Context Cache nicht verfügbar (%s) — sende vollen Kontext", e)
        return None


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
    raw_companions, kompass_usage = select_companions_raw(client, thema, primary_text, model)
    if kompass_usage:
        cost_tracker.track(run_id=_RUN_ID, thema=thema, stufe="S0",
                            schritt="kompass", modell=model, **kompass_usage)
    log.info("  Kompass-Vorschlag: %s", raw_companions)

    # Validierung + Weiterleitungsauflösung (cap gestaffelt nach Appeal)
    companion_cap = COMPANION_CAP.get(appeal, 5)
    valid_companions, rejected = validate_and_resolve_companions(
        session, raw_companions, primary_wikipedia, cap=companion_cap
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


TRIM_SYSTEM_PROMPT = (
    "Du bist Lektor für ein deutsches Kinderlexikon. Du erhältst einen fertigen Artikel als JSON "
    "und eine Wort-Obergrenze. Kürze den Artikel auf höchstens diese Wortzahl: straffe Sätze, "
    "entferne den am wenigsten kindrelevanten Abschnitt oder eine entbehrliche Box. Bewahre Struktur "
    "(sections mit sentences/boxes, quiz), Faktentreue, Tonfall, Stil und die Sprachstufe. Erfinde "
    "nichts hinzu. Gib AUSSCHLIESSLICH das gekürzte JSON nach demselben Schema zurück — kein Vortext."
)


def _trim_article_to_cap(article: dict, wmax: int, model: str, thinking_config) -> tuple[dict, int]:
    """Kürzt einen zu langen Artikel per Modell-Lektorat auf ≤ wmax. Rückgabe: (article, word_count)."""
    import json as _json
    trim_msg = (
        f"WORT-OBERGRENZE: {wmax}\n"
        f"Der folgende Artikel hat zu viele Wörter. Kürze ihn auf höchstens {wmax} Wörter.\n\n"
        f"ARTIKEL_JSON:\n{_json.dumps(article, ensure_ascii=False)}"
    )
    raw = gemini_client.call_gemini(
        TRIM_SYSTEM_PROMPT, trim_msg, model=model, thinking_config=thinking_config,
        response_mime_type="application/json",
    )
    trimmed = parse_article_json(raw)
    trimmed.setdefault("meta", {}).update(article.get("meta", {}))
    return trimmed, count_article_words(trimmed)


BOX_REPAIR_SYSTEM_PROMPT = (
    "Du bist Lektor für ein deutsches Kinderlexikon. Du erhältst einen fertigen Artikel als JSON, "
    "dessen Callout-Boxen schlecht verteilt sind. Ordne JEDE vorhandene Box dem inhaltlich passenden "
    "Abschnitt zu, sodass keine zwei Boxen am Stück am Ende stehen und bei zwei oder mehr Boxen "
    "mindestens eine im mittleren Drittel sitzt. Du änderst AUSSCHLIESSLICH die Box-Platzierung. "
    "Box-Inhalt (type/text/reveal_text), Abschnittsreihenfolge, Überschriften und ALLE Sätze bleiben "
    "wortgleich. Nichts hinzufügen, nichts löschen, nichts umformulieren. Gib NUR das JSON nach "
    "demselben Schema zurück — kein Vortext."
)


def _box_lint(article: dict) -> str | None:
    """Prüft Box-Verteilung deterministisch. Rückgabe: Verstoßgrund oder None (ok)."""
    secs = article.get("sections", [])
    counts = [len(s.get("boxes", []) or []) for s in secs]
    total, n = sum(counts), len(secs)
    if total < 2 or n < 2:
        return None
    if counts[-1] >= 2:
        return "Box-Clusterung: >=2 Boxen im letzten Abschnitt"
    if n >= 3:
        lo, hi = n // 3, (2 * n + 2) // 3
        if not any(counts[i] > 0 for i in range(lo, hi)):
            return "Box-Verteilung: keine Box im mittleren Drittel"
    return None


def _box_signature(article: dict):
    """Inhalts-Fingerabdruck (positionsunabhängig): Box-Multiset + Abschnittssätze."""
    boxes = sorted(
        (b.get("type", ""), (b.get("text", "") or "").strip(), (b.get("reveal_text", "") or "").strip())
        for s in article.get("sections", []) for b in (s.get("boxes", []) or [])
    )
    sentences = [
        (s.get("heading", ""),
         tuple((x.get("text", "") or "").strip() for x in (s.get("sentences", []) or [])))
        for s in article.get("sections", [])
    ]
    return boxes, sentences


def _box_repair_pass(article: dict, model: str, thinking_config) -> dict:
    """Modell ordnet vorhandene Boxen den passenden Abschnitten zu (Inhalt unverändert)."""
    import json as _json
    msg = (
        "Die Callout-Boxen sind schlecht verteilt. Ordne sie den passenden Abschnitten zu — "
        "nur Platzierung, Inhalt/Sätze/Reihenfolge wortgleich.\n\n"
        f"ARTIKEL_JSON:\n{_json.dumps(article, ensure_ascii=False)}"
    )
    raw = gemini_client.call_gemini(
        BOX_REPAIR_SYSTEM_PROMPT, msg, model=model, thinking_config=thinking_config,
        response_mime_type="application/json",
    )
    repaired = parse_article_json(raw)
    repaired.setdefault("meta", {}).update(article.get("meta", {}))
    return repaired


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
    gemini_cache: str | None = None,
) -> tuple[dict | None, dict]:
    """Phase 2: Artikel für eine Stufe generieren (shared sources).

    gemini_cache: Cache-Name aus try_create_gemini_cache (optional).
    Wenn gesetzt: nur variabler Suffix (AGE_LEVEL + WORTZIEL) gesendet,
    stabiler Prefix aus Cache gelesen → ~75 % Token-Einsparung auf cached Tokens.
    """
    article_id       = job["article_id"]
    thema            = job.get("thema", job["title"])
    prompt_version   = SYSTEM_PROMPT_PATH.stem.split("_v")[-1].split("_")[0]
    generation_method = f"{model}/medium/v{prompt_version}"

    # Stufengerechte Bildauswahl: nur Bilder mit ab_stufe <= age_level
    _appeal = job.get("resolved_appeal", "medium")
    images = select_images_for_stufe(images, job["age_level"], _appeal)
    log.info("  Bildpool fuer S%d: %d Bilder (ab_stufe<=%d, appeal=%s)",
             job["age_level"], len(images), job["age_level"], _appeal)

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

    phase2_thinking = _make_thinking_config(model, budget_for_2_5=8192)
    _GEN_MAX_ATTEMPTS = 4
    _GEN_RETRY_WAITS  = [30, 60, 120, 240]

    article     = None
    user_msg: str | None = None  # lazy für Wortzahl-Retry

    for gen_attempt in range(1, _GEN_MAX_ATTEMPTS + 1):
        try:
            if gemini_cache:
                _, variable_suffix = _split_grounded_user_message(
                    job, primary_text, companion_texts, valid_companions, images
                )
                report["phase2"]["user_msg_len"] = len(variable_suffix)
                if gen_attempt == 1:
                    log.info("  Phase 2: Cache-Hit — sende nur variable Suffix (%d Zeichen)",
                             len(variable_suffix))
                raw_response = gemini_client.call_gemini(
                    system_prompt, variable_suffix, model=model, thinking_config=phase2_thinking,
                    response_mime_type="application/json", cached_content=gemini_cache,
                )
            else:
                if user_msg is None:
                    user_msg = build_grounded_user_message(
                        job, primary_text, companion_texts, valid_companions, images
                    )
                    report["phase2"]["user_msg_len"] = len(user_msg)
                raw_response = gemini_client.call_gemini(
                    system_prompt, user_msg, model=model, thinking_config=phase2_thinking,
                    response_mime_type="application/json",
                )

            # JSON-Parse
            try:
                article = parse_article_json(raw_response)
            except (json.JSONDecodeError, ValueError) as parse_err:
                errors_dir = out_dir / "_errors"
                errors_dir.mkdir(parents=True, exist_ok=True)
                (errors_dir / f"{article_id}_raw.txt").write_text(raw_response or "", encoding="utf-8")
                raise RuntimeError(f"JSON-Parse: {parse_err}") from parse_err

            # Plausibilitätsprüfung: Pflichtfelder, nicht 1-Token-Fragment
            n_secs  = len(article.get("sections", []))
            n_sents = sum(len(s.get("sentences", [])) for s in article.get("sections", []))
            if n_secs == 0 or n_sents < 3:
                raise RuntimeError(
                    f"Artikel nicht plausibel: {n_secs} Sections, {n_sents} Sätze"
                )

            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=f"S{job['age_level']}", schritt="article_gen",
                                    modell=model, **_u)
            break  # Erfolg

        except Exception as e:
            err_str = str(e)
            # Cache abgelaufen (TTL überschritten durch 503-Sturm) → Full-Context, kein Warten
            if gemini_cache and "CachedContent not found" in err_str:
                log.warning(
                    "  Phase 2 [%s]: Gemini-Cache abgelaufen/ungueltig — wechsle auf Full-Context",
                    article_id,
                )
                gemini_cache = None
                article = None
                continue
            if gen_attempt < _GEN_MAX_ATTEMPTS:
                wait = _GEN_RETRY_WAITS[gen_attempt - 1]
                log.warning(
                    "  Phase 2 [%s] Versuch %d/%d: %s — warte %ds",
                    article_id, gen_attempt, _GEN_MAX_ATTEMPTS, e, wait,
                )
                time.sleep(wait)
                article = None
            else:
                log.error(
                    "  Phase 2 [%s]: alle %d Versuche fehlgeschlagen: %s",
                    article_id, _GEN_MAX_ATTEMPTS, e,
                )
                report["errors"].append(
                    f"Phase 2 alle {_GEN_MAX_ATTEMPTS} Versuche fehlgeschlagen: {e}"
                )
                return None, report

    article.setdefault("meta", {})["id"]           = article_id
    article["meta"]["title"]                        = thema
    article["meta"]["generated_at"]                 = datetime.now(timezone.utc).isoformat()
    article["meta"]["grounding_companions"]          = valid_companions
    article["meta"]["generation_method"]             = generation_method
    _lemma_flags = job.get("lemma_flags", [])
    _review = [f for f in _lemma_flags if f.startswith(("BITTE PRUEFEN", "LEMMA_GEWECHSELT"))]
    if _review:
        article["meta"]["review_flag"]   = True
        article["meta"]["review_reason"] = "; ".join(_review)

    # ── Wortzahl-Check + ggf. Retry ──────────────────────────────────────────
    wmin, wmax, _wz_src = wortziel_for(thema, job["age_level"])
    word_count = count_article_words(article)
    report["phase2"]["word_count"]  = word_count
    report["phase2"]["word_target"] = f"{wmin}–{wmax}"

    if word_count < wmin:
        log.warning("  Wortzahl zu kurz: %d Wörter (Ziel %d–%d) — Retry", word_count, wmin, wmax)
        if user_msg is None:
            user_msg = build_grounded_user_message(
                job, primary_text, companion_texts, valid_companions, images
            )
        retry_hint = (
            f"\n\nRETRY_FEEDBACK: Vorentwurf hatte {word_count} Wörter, Ziel {wmin}–{wmax}. "
            f"Entwickle die deklarierten Quellen voller — konkrete Fakten, Beispiele, "
            f"Mechanismen ausarbeiten. Harte Obergrenze {wmax} Wörter nicht überschreiten. "
            f"Kein Auffüllen ohne Quellbasis."
        )
        retry_msg = user_msg + retry_hint
        try:
            raw_retry = gemini_client.call_gemini(
                system_prompt, retry_msg, model=model, thinking_config=phase2_thinking,
                response_mime_type="application/json",
            )
            article_retry = parse_article_json(raw_retry)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=f"S{job['age_level']}", schritt="article_gen",
                                    modell=model, **_u)
            wc_retry = count_article_words(article_retry)
            report["phase2"]["retry_needed"]     = True
            report["phase2"]["retry_word_count"] = wc_retry
            log.info("  Retry Wortzahl: %d Wörter", wc_retry)
            # Metadaten auf Retry-Artikel übertragen
            article_retry.setdefault("meta", {})["id"]               = article_id
            article_retry["meta"]["title"]                            = thema
            article_retry["meta"]["generated_at"]                     = article["meta"]["generated_at"]
            article_retry["meta"]["grounding_companions"]             = valid_companions
            article_retry["meta"]["generation_method"]                = generation_method
            article = article_retry
            word_count = wc_retry
            if word_count < wmin:
                log.warning("  Nach Retry immer noch zu kurz: %d Wörter → review_flag", word_count)
                article["meta"]["review_flag"]   = True
                article["meta"]["review_reason"] = f"Wortzahl nach Retry {word_count} < {wmin}"
        except Exception as e:
            log.error("  Retry fehlgeschlagen: %s", e)
            report["errors"].append(f"Retry fehlgeschlagen: {e}")
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = f"Retry fehlgeschlagen: {e}"
    else:
        report["phase2"]["retry_needed"] = False

    # ── Wortzahl-Guard: zu lang → Trim-Pass (harte Obergrenze) ───────────────
    cap = round(wmax * (1 + CAP_GRACE_FRAC))
    trims = 0
    while word_count > cap and trims < TRIM_MAX_ATTEMPTS:
        trims += 1
        log.warning("  Wortzahl zu lang: %d > Cap %d (Ziel %d) — Trim-Pass %d/%d",
                    word_count, cap, wmax, trims, TRIM_MAX_ATTEMPTS)
        try:
            article, word_count = _trim_article_to_cap(article, wmax, model, phase2_thinking)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=f"S{job['age_level']}", schritt="trim",
                                    modell=model, **_u)
            log.info("  Trim-Pass %d Ergebnis: %d Wörter", trims, word_count)
        except Exception as e:
            log.error("  Trim-Pass fehlgeschlagen: %s", e)
            report["errors"].append(f"Trim-Pass fehlgeschlagen: {e}")
            break
    if trims:
        report["phase2"]["trim_passes"] = trims
        if word_count > cap:
            log.warning("  Nach %d Trim-Pass(es) weiter zu lang: %d > %d → review_flag",
                        trims, word_count, cap)
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = f"Wortzahl {word_count} > Cap {cap} nach Trim"

    report["phase2"]["word_count"] = word_count
    article["meta"]["word_count"] = word_count

    # ── Box-Verteilungs-Guard: Clusterung → Auto-Reparatur, sonst review_flag ──
    box_issue = _box_lint(article)
    if box_issue:
        log.warning("  %s — Box-Reparatur-Pass", box_issue)
        try:
            repaired = _box_repair_pass(article, model, phase2_thinking)
            _u = gemini_client._last_usage.copy()
            if _u:
                cost_tracker.track(run_id=_RUN_ID, thema=thema,
                                    stufe=f"S{job['age_level']}", schritt="box_repair",
                                    modell=model, **_u)
            same_content = _box_signature(repaired) == _box_signature(article)
            if same_content and _box_lint(repaired) is None:
                article = repaired
                report["phase2"]["box_repaired"] = True
                log.info("  Box-Reparatur erfolgreich (Inhalt unverändert).")
            else:
                why = "Inhalt verändert" if not same_content else "Verteilung weiter verletzt"
                log.warning("  Box-Reparatur verworfen (%s) → review_flag", why)
                report["phase2"]["box_repaired"] = False
                article["meta"]["review_flag"]   = True
                article["meta"]["review_reason"] = (
                    article["meta"].get("review_reason", "") + f"; {box_issue}").lstrip("; ")
        except Exception as e:
            log.error("  Box-Reparatur fehlgeschlagen: %s", e)
            report["errors"].append(f"Box-Reparatur fehlgeschlagen: {e}")
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + f"; {box_issue}").lstrip("; ")

    val_errors = validate_article(article, job)
    if val_errors:
        for e in val_errors:
            log.warning("  Validierungsfehler: %s", e)
        article["meta"].setdefault("review_flag", True)
        existing_reason = article["meta"].get("review_reason", "")
        extra = "; ".join(val_errors[:3])
        article["meta"]["review_reason"] = (existing_reason + "; " + extra).lstrip("; ")

    report["phase2"]["validation_errors"]  = val_errors
    report["phase2"]["companions_fetched"] = list(companion_texts.keys())

    return article, report


# ── Catalog-Connector ─────────────────────────────────────────────────────────

def _build_catalog_jobs(themen: list[str], stufen: list[int]) -> list[dict]:
    """Baut Job-Dicts aus catalog_full.json für die gegebenen Themen + Stufen."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog_full.json nicht gefunden: {CATALOG_PATH}")
    catalog: list[dict] = json.load(CATALOG_PATH.open(encoding="utf-8"))
    by_thema = {e["thema"].strip().lower(): e for e in catalog}

    jobs: list[dict] = []
    for thema in themen:
        entry = by_thema.get(thema.strip().lower())
        if entry is None:
            log.warning("  Catalog: Thema '%s' nicht gefunden — uebersprungen", thema)
            continue
        if entry.get("eignung") == "exclude":
            log.info("  Catalog: '%s' ist exclude — uebersprungen", thema)
            continue
        age_floor = int(entry.get("age_floor") or 1)
        canonical = entry["thema"]
        for level in stufen:
            if level < age_floor:
                log.info("  Catalog: '%s' S%d unter age_floor S%d — uebersprungen", canonical, level, age_floor)
                continue
            slug = canonical.lower().replace(" ", "_").replace("/", "_")
            jobs.append({
                "article_id":        f"{slug}_l{level}",
                "thema":             canonical,
                "primaer_wikipedia": canonical,
                "title":             canonical,
                "age_level":         level,
                "topic_interest":    "medium",
                "pattern":           entry.get("themengebiet", ""),
                "category_top":      "",
                "category_sub":      "",
                "_catalog_rank":     entry.get("production_rank", 9999),
            })
    return jobs


def _load_catalog_rank_jobs(top_n: int, stufen: list[int]) -> list[dict]:
    """Lädt Top-N Themen nach production_rank aus catalog_full.json."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog_full.json nicht gefunden: {CATALOG_PATH}")
    catalog: list[dict] = json.load(CATALOG_PATH.open(encoding="utf-8"))
    eligible = [
        e for e in catalog
        if e.get("eignung") != "exclude" and e.get("production_rank") is not None
    ]
    eligible.sort(key=lambda e: int(e.get("production_rank") or 9999))
    top_themen = [e["thema"] for e in eligible[:top_n]]
    return _build_catalog_jobs(top_themen, stufen)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Kompass-Grounding Artikel-Generator")
    parser.add_argument(
        "--articles", nargs="+",
        default=None,
        help="Artikel-IDs aus TEST_JOBS (default: alle Test-Jobs, wenn kein --catalog)",
    )
    parser.add_argument(
        "--catalog", nargs="+", metavar="THEMA",
        help="Themen aus catalog_full.json (z.B. --catalog Vulkan Biene)",
    )
    parser.add_argument(
        "--catalog-rank", type=int, default=None, metavar="N",
        help="Top-N Themen nach production_rank aus catalog_full.json",
    )
    parser.add_argument(
        "--stufen", nargs="+", type=int, choices=[1, 2, 3], default=[1, 2, 3],
        help="Zu generierende Stufen (default: 1 2 3)",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run-ID fuer cost_tracker (default: Zeitstempel)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Zeigt Jobs + Eignungs-Gate, generiert nichts",
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
    parser.add_argument(
        "--skip-lektorat", action="store_true",
        help="Lektorat-Schritt (Claude Sonnet) nach Generierung ueberspringen",
    )
    parser.add_argument(
        "--lektorat-batch", action="store_true",
        help="Lektorat ueber Anthropic Batch-API (async, Polling) statt synchron",
    )
    args = parser.parse_args()

    global _RUN_ID
    _RUN_ID = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    model         = args.gen_model or GEMINI_MODEL
    out_dir       = Path(args.output_dir).resolve() if args.output_dir else OUT_DIR
    model_slug    = model.replace("gemini-", "").replace(".", "-")
    skip_lektorat = args.skip_lektorat
    use_batch_lektorat = args.lektorat_batch

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not skip_lektorat and not anthropic_key:
        log.warning("ANTHROPIC_API_KEY fehlt — Lektorat wird uebersprungen (--skip-lektorat zum Unterdrücken)")
        skip_lektorat = True

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))
    log.info("Modell: %s | skip_images: %s | out_dir: %s | run_id: %s",
             model, args.skip_images, out_dir, _RUN_ID)

    client = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_errors").mkdir(exist_ok=True)

    # Jobs sammeln
    resolved_jobs: list[dict] = []
    if args.catalog_rank:
        try:
            resolved_jobs = _load_catalog_rank_jobs(args.catalog_rank, args.stufen)
            log.info("Catalog-Rank: Top-%d Themen, %d Jobs", args.catalog_rank, len(resolved_jobs))
        except Exception as e:
            log.error("Catalog-Rank Fehler: %s", e)
            sys.exit(1)
    elif args.catalog:
        try:
            resolved_jobs = _build_catalog_jobs(args.catalog, args.stufen)
            log.info("Catalog: %d Themen, %d Jobs", len(args.catalog), len(resolved_jobs))
        except Exception as e:
            log.error("Catalog Fehler: %s", e)
            sys.exit(1)
    else:
        article_ids = args.articles if args.articles else list(TEST_JOBS.keys())
        for article_id in article_ids:
            job = TEST_JOBS.get(article_id)
            if not job:
                log.error("Unbekannte article_id: %s (verfuegbar: %s)",
                          article_id, list(TEST_JOBS.keys()))
                continue
            resolved_jobs.append({**job, "article_id": article_id})

    if args.dry_run:
        print(f"\n=== DRY-RUN: {len(resolved_jobs)} Jobs ===")
        for job in resolved_jobs:
            ev = eignung_for(job.get("thema", job["title"]))
            gate = f"exclude={ev['eignung']=='exclude'} age_floor={ev['age_floor']}"
            print(f"  {job['article_id']:30s}  {gate}")
        print("Kein einziger API-Call — dry-run beendet.")
        return

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
        thema      = topic_jobs[0].get("thema", topic_jobs[0]["title"])
        levels     = [j["age_level"] for j in topic_jobs]

        # ── Eignungs-Gate: exclude / age_floor / framing ─────────────────────
        ev = eignung_for(thema)
        if ev["eignung"] == "exclude":
            log.warning("  Eignungs-Gate: '%s' ausgeschlossen (%s) — übersprungen", thema, ev["source"])
            continue
        floor = ev["age_floor"]
        skipped = [j["age_level"] for j in topic_jobs if j["age_level"] < floor]
        topic_jobs = [j for j in topic_jobs if j["age_level"] >= floor]
        if skipped:
            log.info("  Eignungs-Gate: '%s' age_floor=S%d → Stufen %s übersprungen", thema, floor, skipped)
        if not topic_jobs:
            log.warning("  Eignungs-Gate: '%s' — alle Stufen unter age_floor S%d, nichts zu tun", thema, floor)
            continue
        for job in topic_jobs:
            job["framing_note"] = ev["framing_note"]
        levels = [j["age_level"] for j in topic_jobs]

        # ── Lemma auflösen (Redirect / BKS / Listen / Doppelbedeutung) ───────
        try:
            lr = resolve_lemma(session, thema)
        except Exception as e:
            log.warning("  resolve_lemma('%s') Fehler: %s — nutze primaer_wikipedia direkt",
                        thema, e)
            lr = {"resolved_title": None, "flags": [], "doppelbedeutung_directive": None}
        resolved_title = lr.get("resolved_title")
        lemma_flags    = lr.get("flags", [])
        dd_directive   = lr.get("doppelbedeutung_directive")
        if resolved_title:
            if resolved_title != primary_wikipedia:
                log.info("  Lemma aufgelöst: '%s' → '%s'", primary_wikipedia, resolved_title)
            primary_wikipedia = resolved_title
        else:
            log.warning("  Lemma '%s' nicht auflösbar (%s) — nutze '%s' direkt",
                        thema, lemma_flags, primary_wikipedia)
        if lemma_flags:
            log.info("  Lemma-Flags: %s", lemma_flags)
        if dd_directive:
            log.info("  Doppelbedeutung (diagnostisch, nicht injiziert): %s",
                     dd_directive.get("directive", ""))
        for job in topic_jobs:
            job["primaer_wikipedia"]         = primary_wikipedia
            job["lemma_flags"]               = lemma_flags
            job["doppelbedeutung_directive"] = (dd_directive or {}).get("directive", "")

        # Appeal-Tier (Companion-/Bildmenge) aus Ergiebigkeit
        appeal, appeal_source = appeal_for(thema, topic_jobs[0].get("topic_interest"))
        for job in topic_jobs:
            job["resolved_appeal"] = appeal
            job["appeal_source"]   = appeal_source

        print(f"\n{'='*60}")
        print(f"THEMA: {thema} | Primaer: {primary_wikipedia} | Modell: {model}")
        print(f"Stufen: {levels} | Appeal: {appeal} (Herkunft: {appeal_source})")
        print(f"Phase 1 laeuft EINMAL fuer alle Stufen")
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

        # Robustheit: Phase-1-Fehlschlag → LAUT abbrechen, KEIN Primär-only-Fallback
        if not valid_companions:
            log.error(
                "  ABBRUCH: Phase 1 lieferte keine validierten Companions fuer '%s' "
                "(503-Sturm oder kein Ergebnis). Kein Primaer-only-Fallback. "
                "Alle %d Stufe(n) uebersprungen.",
                thema, len(topic_jobs),
            )
            print(f"\n  *** FEHLER: Keine Companions fuer '{thema}' — Artikel NICHT generiert ***")
            for job in topic_jobs:
                err_report = {
                    "article_id": job["article_id"],
                    "thema": thema,
                    "status": "FAILED_NO_COMPANIONS",
                    "reason": "Phase 1 lieferte keine validierten Companions. Kein Primaer-only-Fallback.",
                    "phase1": phase1_report,
                    "errors": ["Phase 1: keine Companions nach allen Versuchen"],
                }
                report_path = out_dir / f"{job['article_id']}_report.json"
                report_path.write_text(
                    json.dumps(err_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                err_path = out_dir / "_errors" / f"{job['article_id']}_FAILED.json"
                err_path.write_text(
                    json.dumps(err_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.error("  FAILED: %s", job["article_id"])
            continue

        # Befund Phase 1 ausgeben
        print(f"\n  [PHASE 1 — einmalig fuer '{thema}']")
        print(f"  Kompass-Vorschlag (roh): {phase1_report['raw_companions']}")
        for r in phase1_report["rejected"]:
            resolved_hint = f" (aufgeloest: '{r['resolved']}')" if r.get("resolved") else ""
            print(f"  Verworfen: '{r['title']}'{resolved_hint} — {r['reason']}")
        print(f"  Validiert + aufgeloest:  {valid_companions}")
        print(f"  [Quellblock wird fuer {len(topic_jobs)} Stufe(n) geteilt + gecacht]")

        # Quellblock einmal pro Thema bauen (geteilt über alle Stufen)
        sources_block = build_grounded_sources_block(
            primary_wikipedia, primary_text, valid_companions, companion_texts
        )
        log.info("  Quellblock: %d Zeichen (Primaer + %d Companions)",
                 len(sources_block), len(valid_companions))

        # Gemini Context Cache: stabilen Prefix (Quellblock) einmal je Thema cachen
        gemini_cache: str | None = None
        if topic_jobs:
            stable_prefix, _ = _split_grounded_user_message(
                topic_jobs[0], primary_text, companion_texts, valid_companions, images
            )
            gemini_cache = try_create_gemini_cache(client, model, system_prompt, stable_prefix)

        # Phase 2: Stufen SEQUENZIELL generieren (verhindert 503-Burst beim parallelen Feuern)
        topic_articles: list[tuple[dict, dict, dict]] = []  # (job, article, report)
        failed_levels: list[str] = []

        try:
            print(f"\n  Phase 2 startet {len(topic_jobs)} Stufe(n) sequenziell ...")
            for job in sorted(topic_jobs, key=lambda j: j["age_level"]):
                article_id = job["article_id"]
                print(f"\n  --- Stufe {job['age_level']}: {article_id} ---")

                article, report = generate_one_level(
                    client, system_prompt, job,
                    primary_text, companion_texts, valid_companions, images,
                    phase1_report, model, args.skip_images, out_dir,
                    gemini_cache=gemini_cache,
                )

                report_path = out_dir / f"{article_id}_report.json"
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"  Report: {report_path.relative_to(ROOT)}")
                if article:
                    topic_articles.append((job, article, report))
                else:
                    failed_levels.append(article_id)
                    print(f"  FEHLGESCHLAGEN: {report.get('errors')}")

            # Lektorat (alle Stufen, Quellblock geteilt; sync=default, batch=--lektorat-batch)
            if not skip_lektorat and topic_articles:
                parts = {}
                aid_to_meta: dict[str, tuple[str, int]] = {}
                for job, article, _ in topic_articles:
                    aid = job["article_id"]
                    parts[aid] = build_lektorat_parts(article, sources_block)
                    aid_to_meta[aid] = (job.get("thema", job["title"]), job["age_level"])
                if use_batch_lektorat:
                    log.info("  Starte Lektorat-Batch fuer %d Artikel (Modell: claude-sonnet-4-6) ...",
                             len(topic_articles))
                    try:
                        lektorat_results = run_lektorat_batch(parts, anthropic_key)
                        lektorat_usage: dict[str, dict] = {}
                    except Exception as exc:
                        log.error("  Lektorat-Batch fehlgeschlagen: %s — Artikel ohne Lektorat-Feld", exc)
                        lektorat_results = {}
                        lektorat_usage = {}
                else:
                    log.info("  Starte Lektorat-Sync fuer %d Artikel (Modell: claude-sonnet-4-6) ...",
                             len(topic_articles))
                    try:
                        lektorat_results, lektorat_usage = run_lektorat_sync(parts, anthropic_key)
                    except Exception as exc:
                        log.error("  Lektorat-Sync fehlgeschlagen: %s — Artikel ohne Lektorat-Feld", exc)
                        lektorat_results = {}
                        lektorat_usage = {}
                for aid, u in lektorat_usage.items():
                    if u:
                        _thema_l, _level_l = aid_to_meta.get(aid, (thema, 0))
                        cost_tracker.track(
                            run_id=_RUN_ID, thema=_thema_l,
                            stufe=f"S{_level_l}", schritt="lektorat",
                            modell="claude-sonnet-4-6",
                            input_tok=u.get("input_tok", 0),
                            output_tok=u.get("output_tok", 0),
                            cached_tok=u.get("cache_read_tok", 0),
                        )
                for job, article, _ in topic_articles:
                    aid = job["article_id"]
                    verdicts = lektorat_results.get(aid, [])
                    annotate_article_lektorat(article, verdicts, primary_text)
                    pb = article.get("pruefbericht", {})
                    sm = pb.get("summary", {})
                    log.info(
                        "  Lektorat [%s]: %d Aussagen — angewandt:%d vorschlag:%d eskaliert:%d",
                        aid, len(pb.get("findings", [])),
                        sm.get("auto_angewandt", 0),
                        sm.get("vorschlag_offen", 0),
                        sm.get("eskaliert", 0),
                    )

            # Artikel schreiben (mit ggf. annotiertem lektorat-Feld)
            for job, article, report in topic_articles:
                article_id = job["article_id"]
                out_path = out_dir / f"{article_id}.json"
                out_path.write_text(
                    json.dumps(article, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                meta_title = article.get("meta", {}).get("title", "?")
                n_imgs  = len(article.get("images", []))
                n_sents = sum(
                    len(s.get("sentences", []))
                    for s in article.get("sections", [])
                )
                wc      = report["phase2"].get("word_count", "?")
                wtarget = report["phase2"].get("word_target", "?")
                retry   = " [RETRY]" if report["phase2"].get("retry_needed") else ""
                review  = " [REVIEW]" if article["meta"].get("review_flag") else ""
                pb      = article.get("pruefbericht", {})
                sm      = pb.get("summary", {})
                n_f     = len(pb.get("findings", []))
                lekt_note = (
                    f" [LEKTORAT {n_f}:{sm.get('auto_angewandt',0)}A"
                    f"/{sm.get('vorschlag_offen',0)}V/{sm.get('eskaliert',0)}E]"
                    if n_f else ""
                )
                gen_m   = article["meta"].get("generation_method", "?")
                print(f"  Gespeichert: {out_path.relative_to(ROOT)}")
                print(f"  meta.title='{meta_title}' | method='{gen_m}'")
                print(f"  Bilder: {n_imgs} | Saetze: {n_sents} | Woerter: {wc} (Ziel {wtarget}){retry}{review}{lekt_note}")

            if failed_levels:
                log.warning(
                    "  FEHLGESCHLAGEN (%d/%d Stufen): %s",
                    len(failed_levels), len(topic_jobs), ", ".join(failed_levels),
                )

        finally:
            if gemini_cache:
                try:
                    client.caches.delete(name=gemini_cache)
                    log.info("  Gemini-Cache geloescht: %s", gemini_cache)
                except Exception as e:
                    log.warning("  Gemini-Cache loeschen fehlgeschlagen (%s): %s", gemini_cache, e)

        print(f"\n  Appeal: {appeal} ({appeal_source}) | Companions ({len(valid_companions)}): {valid_companions}")


if __name__ == "__main__":
    main()
