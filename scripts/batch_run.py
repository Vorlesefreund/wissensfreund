#!/usr/bin/env python3
"""
batch_run.py
POC (NICHT Produktionspfad): Gemini Batch API für Zwei-Phasen-Artikel-Generierung.

Produktionspfad: prepare_articles.py → generate_articles.py → upload_articles.py
                 (via .github/workflows/artikel_pipeline.yml)

Dieses Skript ist ein lokales Experiment zur Umgehung von 503-Überlastung via
Gemini Batch API. Phase-1-Logik (Link-Pool) entspricht NICHT mehr generate_grounded.py
(Kompass). Bei Bedarf auf Kompass-Logik angleichen.

Bilder: nur aus .cache/downloads/ (kein neuer Wikimedia-Download).
Schreibt progress.json kontinuierlich.
Startet HTTP-Server auf :8080 → http://localhost:8080/dashboard.html

Usage:
    python scripts/batch_run.py
"""

import hashlib
import json
import logging
import os
import re
import subprocess
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

sys.path.insert(0, str(Path(__file__).parent))
from generate_articles import (        # noqa: E402
    fetch_wikipedia_text,
    parse_article_json,
    validate_article,
    WIKIPEDIA_API,
    USER_AGENT,
)
from generate_grounded import (         # noqa: E402
    COMPANION_SYSTEM_PROMPT,
    COMPANION_PROMPT_TMPL,
    AGE_RANGES,
    MAX_COMPANIONS,
    MAX_IMG_PRIMARY,
    MAX_IMG_COMPANION,
    MAX_VISION_CHECKS,
    APPEAL_TARGET,
    SYSTEM_PROMPT_PATH,
    OUT_DIR,
    fetch_wikipedia_links,
    validate_companions,
    build_grounded_user_message,
    TEST_JOBS,
)
from image_vision_filter import (       # noqa: E402
    fetch_image_candidates,
    download_image,
    analyze_with_vision,
)

GEMINI_MODEL   = "gemini-2.5-flash"
MAX_LINK_LIST  = 300   # batch_run.py-intern: Link-Pool-Cap für Batch-Phase-1
PROGRESS_FILE  = ROOT / "progress.json"
DL_CACHE_DIR   = ROOT / ".cache" / "downloads"
POLL_SECONDS   = 30

DONE_STATES    = {
    "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
    "JOB_STATE_PARTIALLY_SUCCEEDED", "JOB_STATE_EXPIRED",
}
SUCCESS_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}


# ── Progress I/O ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_progress(state: dict) -> None:
    PROGRESS_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def init_progress(article_ids: list[str]) -> dict:
    state: dict = {}
    for aid in article_ids:
        state[aid] = {
            "phase1":     {"status": "pending", "batch_job": None, "submitted_at": None},
            "companions": {"status": "pending", "titles": [], "error": None},
            "phase2":     {"status": "pending", "batch_job": None, "submitted_at": None},
            "final":      {"status": "pending", "output_file": None, "error": None},
        }
    return state


# ── Batch-Hilfsfunktionen ────────────────────────────────────────────────────

def _extract_text(response: types.GenerateContentResponse | None) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", None)
    if text:
        return text
    for cand in getattr(response, "candidates", []):
        parts = []
        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
            if not getattr(part, "thought", False) and getattr(part, "text", None):
                parts.append(part.text)
        if parts:
            return "".join(parts)
    return ""


def _strip_md(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    return re.sub(r"\n?```$", "", text).strip()


def _state_str(batch_job: types.BatchJob) -> str:
    s = batch_job.state
    return s.value if s else "unknown"


def poll_until_done(
    client: genai.Client,
    batch_name: str,
    progress: dict,
    phase_key: str,
    article_ids: list[str],
) -> types.BatchJob:
    log.info("Polling %s ...", batch_name)
    while True:
        job = client.batches.get(name=batch_name)
        state = _state_str(job)
        for aid in article_ids:
            progress[aid][phase_key]["status"] = state
            progress[aid][phase_key]["polled_at"] = _now()
        write_progress(progress)
        log.info("  Batch %s → %s", batch_name[-30:], state)
        if state in DONE_STATES:
            return job
        time.sleep(POLL_SECONDS)


# ── Image Pool (nur Cache) ───────────────────────────────────────────────────

def build_image_pool_cached(
    session: requests.Session,
    client: genai.Client,
    job: dict,
    companion_titles: list[str],
) -> list[dict]:
    """Bildpool ohne neue Downloads — nur .cache/downloads/*.jpg nutzen.

    Holt Metadaten per API, prüft Cache, lädt Vision nur für gecachte Bilder.
    """
    thema      = job.get("thema", job["title"])
    primary_wp = job.get("primaer_wikipedia", job["title"])
    appeal     = job.get("topic_interest", "medium")
    target     = APPEAL_TARGET.get(appeal, 10)

    all_candidates: list[dict] = []

    primary_imgs = fetch_image_candidates(session, primary_wp, max_candidates=MAX_IMG_PRIMARY)
    for img in primary_imgs:
        img["_source"] = primary_wp
    all_candidates.extend(primary_imgs)
    log.info("    Metadaten '%s': %d Bilder", primary_wp, len(primary_imgs))

    for comp in companion_titles:
        time.sleep(0.4)
        comp_imgs = fetch_image_candidates(session, comp, max_candidates=MAX_IMG_COMPANION)
        for img in comp_imgs:
            img["_source"] = comp
        all_candidates.extend(comp_imgs)
        log.info("    Metadaten '%s': %d Bilder", comp, len(comp_imgs))

    # Deduplizieren
    seen: set[str] = set()
    unique: list[dict] = []
    for img in all_candidates:
        if img["filename"] not in seen:
            seen.add(img["filename"])
            unique.append(img)

    to_check = unique[:MAX_VISION_CHECKS]
    log.info("    Kandidaten: %d (Vision-Check max %d)", len(unique), len(to_check))

    accepted: list[dict] = []

    for img in to_check:
        if len(accepted) >= target:
            break

        # Nur gecachte Bilder nutzen (kein Download)
        url = img.get("thumb_url", "")
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_800 = DL_CACHE_DIR / f"{cache_key}_800.jpg"

        if not cache_800.exists():
            # Nicht gecacht → ohne Vision in Pool aufnehmen (basis Metadaten)
            accepted.append({
                **img,
                "ab_stufe":       1,
                "relevanz":      5,
                "hero_candidate": False,
                "beschreibung":  "",
            })
            continue

        img_bytes = cache_800.read_bytes()
        result, _usage = analyze_with_vision(client, img_bytes, "image/jpeg", thema)
        if result is None:
            continue

        ab_stufe = result.get("ab_stufe", 0)
        if ab_stufe == 0:
            continue
        if result.get("relevanz", 0) < 4:
            continue

        accepted.append({
            **img,
            "ab_stufe":       ab_stufe,
            "relevanz":       result.get("relevanz", 5),
            "hero_candidate": result.get("hero_candidate", False),
            "beschreibung":   result.get("beschreibung", ""),
        })

    accepted.sort(key=lambda x: (-x["relevanz"], -int(x.get("hero_candidate", False))))
    log.info("    Bildpool akzeptiert: %d (target=%d)", len(accepted), target)
    return accepted[:target]


# ── Phase-1-Batch ────────────────────────────────────────────────────────────

def build_phase1_requests(
    article_ids: list[str],
    fetched: dict,
) -> list[types.InlinedRequest]:
    reqs: list[types.InlinedRequest] = []
    for aid in article_ids:
        job  = TEST_JOBS[aid]
        data = fetched[aid]
        link_sample = data["link_list"][:MAX_LINK_LIST]
        prompt = COMPANION_PROMPT_TMPL.format(
            thema     = job.get("thema", job["title"]),
            age_level = job["age_level"],
            ages      = AGE_RANGES.get(job["age_level"], ""),
            appeal    = job.get("topic_interest", "medium"),
            excerpt   = data["primary_text"][:2000],
            n_links   = len(link_sample),
            link_list = ", ".join(link_sample),
        )
        reqs.append(types.InlinedRequest(
            contents = prompt,
            config   = types.GenerateContentConfig(
                system_instruction = COMPANION_SYSTEM_PROMPT,
                temperature        = 0.3,
                thinking_config    = types.ThinkingConfig(thinking_budget=1024),
            ),
            metadata = {"article_id": aid, "phase": "1"},
        ))
    return reqs


# ── Phase-2-Batch ────────────────────────────────────────────────────────────

def build_phase2_requests(
    article_ids: list[str],
    fetched: dict,
    companions_map: dict,
    companion_texts_map: dict,
    image_pools: dict,
    system_prompt: str,
) -> list[types.InlinedRequest]:
    reqs: list[types.InlinedRequest] = []
    for aid in article_ids:
        job              = TEST_JOBS[aid]
        primary_text     = fetched[aid]["primary_text"]
        valid_companions = companions_map.get(aid, [])
        companion_texts  = companion_texts_map.get(aid, {})
        images           = image_pools.get(aid, [])

        user_msg = build_grounded_user_message(
            job, primary_text, companion_texts, valid_companions, images
        )
        reqs.append(types.InlinedRequest(
            contents = user_msg,
            config   = types.GenerateContentConfig(
                system_instruction = system_prompt,
                temperature        = 0.6,
                thinking_config    = types.ThinkingConfig(thinking_budget=8192),
            ),
            metadata = {"article_id": aid, "phase": "2"},
        ))
    return reqs


# ── Ergebnisse extrahieren ───────────────────────────────────────────────────

def extract_phase1_results(
    batch_job: types.BatchJob,
    fetched: dict,
    session: requests.Session,
    progress: dict,
) -> dict[str, list[str]]:
    companions_map: dict[str, list[str]] = {}

    inlined = getattr(getattr(batch_job, "dest", None), "inlined_responses", None) or []
    if not inlined:
        log.warning("Phase 1: Keine inlined_responses im BatchJob-Dest.")
        # Alle auf failed setzen
        for aid in progress:
            progress[aid]["companions"]["status"] = "failed"
            progress[aid]["companions"]["error"]  = "Keine Antworten vom Batch"
            companions_map[aid] = []
        return companions_map

    for resp in inlined:
        aid = (resp.metadata or {}).get("article_id", "")
        if not aid or aid not in progress:
            continue

        if resp.error:
            log.error("  %s Phase 1 Fehler: %s", aid, resp.error)
            progress[aid]["phase1"]["status"]     = "failed"
            progress[aid]["companions"]["status"] = "failed"
            progress[aid]["companions"]["error"]  = str(resp.error)
            companions_map[aid] = []
            continue

        text = _strip_md(_extract_text(resp.response))
        try:
            data = json.loads(text)
            raw  = [str(c) for c in data.get("companions", [])][:MAX_COMPANIONS]
        except json.JSONDecodeError as e:
            log.warning("  %s Phase 1 JSON-Fehler: %s", aid, e)
            raw = []

        link_set        = set(fetched[aid]["link_list"])
        valid, rejected = validate_companions(session, raw, link_set)

        progress[aid]["phase1"]["status"]     = "done"
        progress[aid]["companions"]["status"] = "done"
        progress[aid]["companions"]["titles"] = valid
        if rejected:
            progress[aid]["companions"]["rejected"] = [r["title"] for r in rejected]

        log.info("  %s Companions: %s", aid, valid)
        companions_map[aid] = valid

    return companions_map


def extract_phase2_results(
    batch_job: types.BatchJob,
    progress: dict,
    system_prompt: str,
) -> list[str]:
    """Gibt Liste erfolgreicher article_ids zurück."""
    succeeded: list[str] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    inlined = getattr(getattr(batch_job, "dest", None), "inlined_responses", None) or []
    if not inlined:
        log.warning("Phase 2: Keine inlined_responses im BatchJob-Dest.")
        for aid in progress:
            progress[aid]["phase2"]["status"] = "failed"
            progress[aid]["final"]["status"]  = "failed"
            progress[aid]["final"]["error"]   = "Keine Antworten vom Batch"
        return succeeded

    for resp in inlined:
        aid = (resp.metadata or {}).get("article_id", "")
        if not aid or aid not in progress:
            continue

        if resp.error:
            log.error("  %s Phase 2 Fehler: %s", aid, resp.error)
            progress[aid]["phase2"]["status"] = "failed"
            progress[aid]["final"]["status"]  = "failed"
            progress[aid]["final"]["error"]   = str(resp.error)
            continue

        raw = _extract_text(resp.response)
        try:
            article = parse_article_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            log.error("  %s JSON-Parse: %s", aid, e)
            (OUT_DIR / "_errors").mkdir(exist_ok=True)
            (OUT_DIR / "_errors" / f"{aid}_batch_raw.txt").write_text(raw or "", encoding="utf-8")
            progress[aid]["phase2"]["status"] = "failed"
            progress[aid]["final"]["status"]  = "failed"
            progress[aid]["final"]["error"]   = f"JSON-Parse: {e}"
            continue

        job = TEST_JOBS[aid]
        thema = job.get("thema", job["title"])
        article.setdefault("meta", {})["id"]           = aid
        article["meta"]["title"]                        = thema
        article["meta"]["generated_at"]                 = _now()
        article["meta"]["grounding_companions"]         = progress[aid]["companions"].get("titles", [])
        article["meta"]["generation_method"]            = "batch_api"

        val_errors = validate_article(article, job)
        if val_errors:
            for e in val_errors:
                log.warning("  %s Validierung: %s", aid, e)
            article["meta"]["review_flag"]   = True
            article["meta"]["review_reason"] = "; ".join(val_errors[:3])

        out_path = OUT_DIR / f"{aid}.json"
        out_path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("  %s → %s ✓", aid, out_path.name)

        progress[aid]["phase2"]["status"]   = "done"
        progress[aid]["final"]["status"]    = "done"
        progress[aid]["final"]["output_file"] = str(out_path)
        succeeded.append(aid)

    return succeeded


# ── HTTP-Dashboard-Server ────────────────────────────────────────────────────

def start_dashboard_server(port: int = 8080) -> subprocess.Popen | None:
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--directory", str(ROOT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        log.info("Dashboard-Server gestartet: http://localhost:%d/dashboard.html", port)
        return proc
    except Exception as e:
        log.warning("HTTP-Server konnte nicht gestartet werden: %s", e)
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY nicht gesetzt.")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    log.info("System-Prompt: %d Zeichen", len(system_prompt))

    client  = genai.Client(api_key=api_key)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    article_ids = list(TEST_JOBS.keys())
    progress    = init_progress(article_ids)
    write_progress(progress)

    # HTTP-Server für Dashboard
    server_proc = start_dashboard_server(8080)

    try:
        _run(client, session, system_prompt, article_ids, progress)
    finally:
        if server_proc:
            server_proc.terminate()
            log.info("Dashboard-Server gestoppt.")


def _run(
    client: genai.Client,
    session: requests.Session,
    system_prompt: str,
    article_ids: list[str],
    progress: dict,
) -> None:
    # ── Primärtexte + Links holen (sequentiell) ──────────────────────────────
    log.info("Hole Primärtexte + Link-Listen ...")
    fetched: dict = {}
    seen_wp: dict[str, tuple] = {}  # wp-title → (primary_text, link_list) — Dedup-Cache
    for aid in article_ids:
        job  = TEST_JOBS[aid]
        wp   = job.get("primaer_wikipedia", job["title"])
        if wp in seen_wp:
            fetched[aid] = {"primary_text": seen_wp[wp][0], "link_list": seen_wp[wp][1]}
            log.info("  %s: Primärtext wiederverwendet (%s)", aid, wp)
            progress[aid]["phase1"]["status"] = "fetching_done"
            write_progress(progress)
            continue
        try:
            time.sleep(1.0)  # Wikipedia-Rate-Limit-Schutz
            primary_text = fetch_wikipedia_text(session, wp)
            time.sleep(0.5)
            link_list    = fetch_wikipedia_links(session, wp)
        except Exception as e:
            log.error("  %s Wikipedia-Fetch: %s", aid, e)
            progress[aid]["phase1"]["status"] = "failed"
            progress[aid]["final"]["error"]   = f"Wikipedia-Fetch: {e}"
            fetched[aid] = {"primary_text": "", "link_list": []}
            write_progress(progress)
            continue

        seen_wp[wp] = (primary_text, link_list)
        fetched[aid] = {"primary_text": primary_text, "link_list": link_list}
        log.info("  %s: %d Zeichen, %d Links", aid, len(primary_text), len(link_list))
        progress[aid]["phase1"]["status"] = "fetching_done"
        write_progress(progress)

    # Nur Artikel mit gültigem Primärtext einreichen
    ready_ids = [aid for aid in article_ids if fetched.get(aid, {}).get("primary_text")]

    # ── Phase 1 Batch ────────────────────────────────────────────────────────
    log.info("\n=== PHASE 1 BATCH (%d Requests) ===", len(ready_ids))
    p1_requests = build_phase1_requests(ready_ids, fetched)

    try:
        batch1 = client.batches.create(model=GEMINI_MODEL, src=p1_requests)
        batch1_name = batch1.name
        log.info("Phase 1 Batch eingereicht: %s", batch1_name)
    except Exception as e:
        log.error("Phase 1 Batch-Einreichung fehlgeschlagen: %s", e)
        for aid in ready_ids:
            progress[aid]["phase1"]["status"] = "failed"
            progress[aid]["phase1"]["error"]  = str(e)
        write_progress(progress)
        return

    for aid in ready_ids:
        progress[aid]["phase1"]["status"]       = "submitted"
        progress[aid]["phase1"]["batch_job"]    = batch1_name
        progress[aid]["phase1"]["submitted_at"] = _now()
    write_progress(progress)

    # Batch 1 pollen
    batch1_done = poll_until_done(client, batch1_name, progress, "phase1", ready_ids)
    state1      = _state_str(batch1_done)
    log.info("Phase 1 abgeschlossen: %s", state1)

    if state1 not in SUCCESS_STATES:
        log.error("Phase 1 Batch fehlgeschlagen: %s", state1)
        for aid in ready_ids:
            progress[aid]["companions"]["status"] = "failed"
        write_progress(progress)
        return

    # Phase-1-Ergebnisse auslesen
    companions_map = extract_phase1_results(batch1_done, fetched, session, progress)
    write_progress(progress)

    # ── Companion-Texte holen ─────────────────────────────────────────────────
    log.info("\nHole Companion-Texte ...")
    companion_texts_map: dict[str, dict[str, str]] = {}
    for aid in ready_ids:
        companion_texts_map[aid] = {}
        for comp in companions_map.get(aid, []):
            try:
                ct = fetch_wikipedia_text(session, comp)
                companion_texts_map[aid][comp] = ct
                log.info("  %s: '%s' %d Zeichen", aid, comp, len(ct))
            except Exception as e:
                log.warning("  %s Companion '%s' Fehler: %s", aid, comp, e)

    # ── Bildpools (nur Cache) ────────────────────────────────────────────────
    log.info("\nBaue Bildpools (nur Cache) ...")
    image_pools: dict[str, list[dict]] = {}
    for aid in ready_ids:
        log.info("  Bildpool %s ...", aid)
        image_pools[aid] = build_image_pool_cached(
            session, genai.Client(api_key=os.environ["GEMINI_API_KEY"]),
            TEST_JOBS[aid], companions_map.get(aid, [])
        )
        progress[aid]["phase2"]["image_count"] = len(image_pools[aid])
        write_progress(progress)

    # ── Phase 2 Batch ────────────────────────────────────────────────────────
    log.info("\n=== PHASE 2 BATCH (%d Requests) ===", len(ready_ids))
    p2_requests = build_phase2_requests(
        ready_ids, fetched, companions_map, companion_texts_map, image_pools, system_prompt
    )

    try:
        batch2 = client.batches.create(model=GEMINI_MODEL, src=p2_requests)
        batch2_name = batch2.name
        log.info("Phase 2 Batch eingereicht: %s", batch2_name)
    except Exception as e:
        log.error("Phase 2 Batch-Einreichung fehlgeschlagen: %s", e)
        for aid in ready_ids:
            progress[aid]["phase2"]["status"] = "failed"
            progress[aid]["phase2"]["error"]  = str(e)
        write_progress(progress)
        return

    for aid in ready_ids:
        progress[aid]["phase2"]["status"]       = "submitted"
        progress[aid]["phase2"]["batch_job"]    = batch2_name
        progress[aid]["phase2"]["submitted_at"] = _now()
    write_progress(progress)

    # Batch 2 pollen
    batch2_done = poll_until_done(client, batch2_name, progress, "phase2", ready_ids)
    state2      = _state_str(batch2_done)
    log.info("Phase 2 abgeschlossen: %s", state2)

    if state2 not in SUCCESS_STATES:
        log.error("Phase 2 Batch fehlgeschlagen: %s", state2)
        for aid in ready_ids:
            progress[aid]["final"]["status"] = "failed"
        write_progress(progress)
        return

    # Phase-2-Ergebnisse + Retry-Runde
    succeeded = extract_phase2_results(batch2_done, progress, system_prompt)
    write_progress(progress)

    # Retry fehlgeschlagener Phase-2-Requests (max 1 Runde)
    failed_ids = [
        aid for aid in ready_ids
        if progress[aid]["final"]["status"] == "failed"
        and not progress[aid]["final"].get("retry_done")
    ]
    if failed_ids:
        log.info("\nRetry Phase 2 für %d fehlgeschlagene Artikel: %s", len(failed_ids), failed_ids)
        retry_reqs = build_phase2_requests(
            failed_ids, fetched, companions_map, companion_texts_map, image_pools, system_prompt
        )
        try:
            retry_batch = client.batches.create(model=GEMINI_MODEL, src=retry_reqs)
            log.info("Retry Batch eingereicht: %s", retry_batch.name)
            for aid in failed_ids:
                progress[aid]["phase2"]["status"]         = "retry_submitted"
                progress[aid]["phase2"]["retry_batch_job"] = retry_batch.name
                progress[aid]["final"]["retry_done"]      = True
            write_progress(progress)

            retry_done = poll_until_done(client, retry_batch.name, progress, "phase2", failed_ids)
            if _state_str(retry_done) in SUCCESS_STATES:
                retry_succeeded = extract_phase2_results(retry_done, progress, system_prompt)
                succeeded.extend(retry_succeeded)
        except Exception as e:
            log.error("Retry Batch fehlgeschlagen: %s", e)

    write_progress(progress)

    # ── Abschluss-Report ─────────────────────────────────────────────────────
    total   = len(ready_ids)
    n_done  = len(succeeded)
    n_fail  = total - n_done
    log.info("\n=== ABSCHLUSS ===")
    log.info("Fertig: %d/%d | Fehlgeschlagen: %d", n_done, total, n_fail)
    for aid in article_ids:
        status = progress[aid]["final"]["status"]
        companions = progress[aid]["companions"].get("titles", [])
        log.info("  %s → %s | Companions: %s", aid, status, companions)
    log.info("Dashboard: http://localhost:8080/dashboard.html")
    log.info("progress.json: %s", PROGRESS_FILE)


if __name__ == "__main__":
    main()
