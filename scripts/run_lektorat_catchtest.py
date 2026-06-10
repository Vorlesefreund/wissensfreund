#!/usr/bin/env python3
"""
run_lektorat_catchtest.py
Catch-Test für Lektorats-Modellwahl.
Misst CATCH-RATE (gefangene Slips) und FALSCH-POSITIV-RATE je Verifizierer.
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
DOTENV_PATH = ROOT / ".env"
GOLDSET_PATH = ROOT / "tests" / "lektorat_goldset.json"
ARTICLES_DIR = ROOT / "articles" / "test_modelcompare2"
RESULT_PATH = ROOT / "tests" / "lektorat_catchtest_result.md"
WIKIPEDIA_API = "https://de.wikipedia.org/w/api.php"

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))
from lektorat_common import (            # noqa: E402
    COMPANION_CHAR_CAP,
    LEKTORAT_SYSTEM,
    build_grounded_sources_block,
    parse_lektorat_json,
)

PROBLEMATIC = {"NICHT_BELEGT", "ÜBERZOGEN", "WIDERSPRUCH"}

VERIFIER_DEFAULT = [
    {"id": "claude-sonnet-4-6", "family": "claude", "label": "Claude Sonnet 4.6"},
]

VERIFIER_COMPARE = [
    {"id": "claude-sonnet-4-6",         "family": "claude", "label": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5-20251001",  "family": "claude", "label": "Claude Haiku 4.5"},
    {"id": "gemini-3.1-pro",             "family": "gemini", "label": "Gemini 3.1 Pro",
     "fallbacks": ["gemini-2.5-pro", "gemini-2.5-pro-preview"]},
]


# ── Wikipedia fetch with retry + pre-cache ────────────────────────────────────

_WIKI_CACHE: dict[str, str] = {}   # title → full text (uncapped)


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_wiki_full(session: requests.Session, title: str) -> str:
    """Holt den vollständigen Wikipedia-Text (gecacht, mit 429-Retry)."""
    key = title.lower()
    if key in _WIKI_CACHE:
        return _WIKI_CACHE[key]
    params = {
        "action": "query", "titles": title, "redirects": "1",
        "prop": "extracts", "explaintext": True, "exsectionformat": "plain",
        "exlimit": "max", "format": "json",
    }
    for attempt in range(1, 5):
        try:
            resp = session.get(WIKIPEDIA_API, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 15 * attempt
                log.warning("    Wikipedia 429 (V%d) — warte %ds ...", attempt, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = _clean(page.get("extract", ""))
                _WIKI_CACHE[key] = text
                return text
            _WIKI_CACHE[key] = ""
            return ""
        except requests.HTTPError:
            raise
        except Exception as e:
            if attempt < 4:
                time.sleep(5 * attempt)
            else:
                raise
    return ""


# ── Pre-cache all sources from goldset ───────────────────────────────────────

def prefetch_all_sources(goldset: list[dict], session: requests.Session) -> None:
    """Fetcht alle benötigten Wikipedia-Texte einmalig und befüllt _WIKI_CACHE."""
    all_titles: set[str] = set()
    for item in goldset:
        all_titles.update(item.get("deklarierte_quellen", []))
        if item.get("primaer_artikel"):
            all_titles.add(item["primaer_artikel"])
    log.info("Pre-fetching %d Wikipedia-Quellen ...", len(all_titles))
    for title in sorted(all_titles):
        log.info("  → %s", title)
        fetch_wiki_full(session, title)
        time.sleep(0.8)  # Wikipedia-Rate-Limit respektieren


# ── Article JSON → readable text ──────────────────────────────────────────────

def article_to_text(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for sec in data.get("sections", []):
        title = sec.get("title", "").strip()
        if title:
            lines.append(f"\n[{title}]")
        for s in sec.get("sentences", []):
            t = s.get("text", "").strip()
            if t:
                lines.append(t)
        for box in sec.get("boxes", []):
            t = box.get("text", "").strip()
            if t:
                lines.append(f"  BOX: {t}")
            for s in box.get("sentences", []):
                t = s.get("text", "").strip()
                if t:
                    lines.append(f"  BOX: {t}")
    return "\n".join(lines)


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_article_prompt(item: dict) -> str:
    """L1/L2: Ganzen Artikel + alle deklarierten Quellen. Quelltexte aus Cache."""
    art_id = item["herkunft"]
    art_path = ARTICLES_DIR / f"{art_id}.json"
    article_text = article_to_text(art_path) if art_path.exists() else "[Artikel nicht verfügbar]"

    sources_block = _build_sources_block(item["deklarierte_quellen"],
                                          item.get("primaer_artikel"),
                                          is_single_claim=False)
    return (
        f"PRÜF-ARTIKEL (Herkunft: {art_id}):\n{article_text}\n\n"
        f"{sources_block}\n\n"
        "Prüfe ALLE faktischen Aussagen im Artikel gegen die deklarierten Quellen. "
        "Gib für jede Aussage ein separates Verdikt im JSON-Array."
    )


def build_claim_prompt(item: dict) -> str:
    """L3/L4/K1-K6: Einzelne Aussage + deklarierte Quellen."""
    claim = item["claim"]
    sources_block = _build_sources_block(item["deklarierte_quellen"],
                                          item.get("primaer_artikel"),
                                          is_single_claim=True)
    return f"AUSSAGE: {claim}\n\n{sources_block}\n\nPrüfe die Aussage gegen die deklarierten Quellen."


def _build_sources_block(sources: list[str], primaer: str | None,
                          is_single_claim: bool) -> str:
    """
    - Artikel-Checks (is_single_claim=False): build_grounded_sources_block aus lektorat_common
      → Primär ungekürzt, Companions[:COMPANION_CHAR_CAP] — identisch zur Generierung.
    - Einzelaussagen (is_single_claim=True): alle Quellen ungekürzt (keine Companion-Logik).
    """
    if not is_single_claim:
        primaer_text = _WIKI_CACHE.get((primaer or "").lower(), "") if primaer else ""
        companion_titles = [s for s in sources if s.lower() != (primaer or "").lower()]
        companion_texts  = {t: _WIKI_CACHE.get(t.lower(), "") for t in companion_titles}
        return build_grounded_sources_block(
            primaer or "", primaer_text, companion_titles, companion_texts
        )
    # Einzelaussage: alle Quellen voll
    all_sources = list(sources)
    if primaer and primaer not in all_sources:
        all_sources.append(primaer)
    parts = [
        f"### Quelle: {title}\n{_WIKI_CACHE.get(title.lower(), '[nicht gecacht]')}"
        for title in all_sources
    ]
    return "DEKLARIERTE QUELLEN:\n" + "\n\n".join(parts)


def find_verdict(verdicts: list[dict], match_begriffe: list[str]) -> tuple[str, str]:
    begriffe_lower = [b.lower() for b in match_begriffe]
    for v in verdicts:
        claim_text = v.get("claim", "").lower()
        if any(b in claim_text for b in begriffe_lower):
            return v.get("verdikt", "UNBEKANNT"), v.get("beleg_oder_begruendung", "")
    if len(verdicts) == 1:
        v = verdicts[0]
        return v.get("verdikt", "UNBEKANNT"), v.get("beleg_oder_begruendung", "")
    return "NICHT_GEFUNDEN", "(kein match_begriff im Verifier-Output)"


# ── Regex-Fallback für Verdikt ────────────────────────────────────────────────

_VERDIKT_RE = re.compile(
    r'"verdikt"\s*:\s*"(BELEGT|NICHT_BELEGT|ÜBERZOGEN|WIDERSPRUCH)"',
    re.IGNORECASE
)


def extract_verdikt_fallback(raw: str, match_begriffe: list[str]) -> tuple[str, str] | None:
    """Sucht per Regex nach Verdikt-Feldern, die nahe einem match_begriff stehen."""
    begriffe_lower = [b.lower() for b in match_begriffe]
    raw_lower = raw.lower()
    for b in begriffe_lower:
        idx = raw_lower.find(b)
        if idx == -1:
            continue
        window = raw[max(0, idx - 500): idx + 500]
        m = _VERDIKT_RE.search(window)
        if m:
            return m.group(1).upper(), "(regex-fallback)"
    # Nimm erstes Verdikt im ganzen Text
    m = _VERDIKT_RE.search(raw)
    if m:
        return m.group(1).upper(), "(regex-fallback, kein match_begriff)"
    return None


# ── API callers ───────────────────────────────────────────────────────────────

def call_claude(model_id: str, user_msg: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model_id,
        max_tokens=8000,
        system=LEKTORAT_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text


def call_gemini(model_id: str, user_msg: str) -> str:
    from google import genai
    from google.genai import types as gtypes
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for attempt in range(1, GEMINI_RETRY + 1):
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=user_msg,
                config=gtypes.GenerateContentConfig(
                    system_instruction=LEKTORAT_SYSTEM,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            return resp.text or ""
        except Exception as e:
            err = str(e)
            if attempt < GEMINI_RETRY and ("503" in err or "unavailable" in err.lower()):
                wait = min(30 * (2 ** (attempt - 1)), 120)
                log.warning("    Gemini 503 (V%d/%d) — warte %ds ...", attempt, GEMINI_RETRY, wait)
                time.sleep(wait)
            else:
                raise


def probe_gemini_model(model_id: str) -> bool:
    try:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        client.models.generate_content(
            model=model_id,
            contents="Antworte nur: OK",
            config=gtypes.GenerateContentConfig(max_output_tokens=5),
        )
        return True
    except Exception:
        return False


def call_verifier(model_cfg: dict, user_msg: str) -> str:
    if model_cfg["family"] == "claude":
        return call_claude(model_cfg["resolved_id"], user_msg)
    return call_gemini(model_cfg["resolved_id"], user_msg)


# ── Model discovery ───────────────────────────────────────────────────────────

def resolve_verifiers(compare: bool = False) -> list[dict]:
    candidates = VERIFIER_COMPARE if compare else VERIFIER_DEFAULT
    available = []
    for cfg in candidates:
        cfg = dict(cfg)
        if cfg["family"] == "claude":
            if os.environ.get("ANTHROPIC_API_KEY"):
                cfg["resolved_id"] = cfg["id"]
                cfg["available"] = True
                available.append(cfg)
            else:
                log.warning("ANTHROPIC_API_KEY fehlt — %s übersprungen", cfg["label"])
                cfg["available"] = False
                cfg["skip_reason"] = "ANTHROPIC_API_KEY nicht gesetzt"
                available.append(cfg)
        elif cfg["family"] == "gemini":
            candidates = [cfg["id"]] + cfg.get("fallbacks", [])
            resolved = None
            for mid in candidates:
                log.info("  Prüfe Gemini-Modell: %s ...", mid)
                if probe_gemini_model(mid):
                    resolved = mid
                    break
            if resolved:
                cfg["resolved_id"] = resolved
                cfg["available"] = True
                if resolved != cfg["id"]:
                    log.info("  %s → Fallback auf %s", cfg["label"], resolved)
                available.append(cfg)
            else:
                log.warning("Kein verfügbares Modell für %s", cfg["label"])
                cfg["available"] = False
                cfg["resolved_id"] = None
                cfg["skip_reason"] = f"Keines verfügbar aus {candidates}"
                available.append(cfg)
    return available


# ── Run single item ───────────────────────────────────────────────────────────

def run_item(item: dict, v: dict) -> dict:
    iid = item["id"]
    is_article = item["typ"] == "artikel_slip"
    prompt = build_article_prompt(item) if is_article else build_claim_prompt(item)

    raw = call_verifier(v, prompt)
    verdicts = None
    verdikt = beleg = ""

    try:
        verdicts = parse_lektorat_json(raw)
        verdikt, beleg = find_verdict(verdicts, item["match_begriffe"])
    except Exception as parse_err:
        # Regex-Fallback
        fb = extract_verdikt_fallback(raw, item["match_begriffe"])
        if fb:
            verdikt, beleg = fb
            log.info("    Regex-Fallback: %s", verdikt)
        else:
            raise parse_err

    return {"id": iid, "claim": item["claim"][:80], "gold": item["gold_verdikt"],
            "got": verdikt, "beleg": (beleg or "")[:120]}


# ── Main test runner ──────────────────────────────────────────────────────────

def run_catchtest(compare: bool = False):
    load_dotenv(DOTENV_PATH)
    goldset = json.loads(GOLDSET_PATH.read_text(encoding="utf-8"))
    slips      = [i for i in goldset if i["typ"] in ("artikel_slip", "claim")]
    kontrollen = [i for i in goldset if i["typ"] == "kontrolle"]

    log.info("Goldset: %d Slips, %d Kontrollen", len(slips), len(kontrollen))
    if not compare:
        log.info("Modus: Sonnet-only (--compare für Mehrmodell-Vergleich)")

    session = requests.Session()
    session.headers.update({"User-Agent": "Wissensfreund-Lektorat-Test/1.0"})

    # Einmaliges Pre-Fetching aller Quellen
    prefetch_all_sources(goldset, session)

    log.info("Verifizierer-Auflösung ...")
    verifiers = resolve_verifiers(compare=compare)

    results: dict[str, dict] = {}

    for v in verifiers:
        label = v["label"]
        results[label] = {"caught": [], "missed": [], "fp": [], "ok": [], "errors": []}

        if not v.get("available"):
            results[label]["skip_reason"] = v.get("skip_reason", "nicht verfügbar")
            log.warning("  [%s] ÜBERSPRUNGEN: %s", label, v.get("skip_reason", ""))
            continue

        log.info("=== Verifizierer: %s (→ %s) ===", label, v["resolved_id"])

        for item in slips:
            log.info("  [%s] Slip %s ...", label, item["id"])
            try:
                entry = run_item(item, v)
                if entry["got"] in PROBLEMATIC:
                    results[label]["caught"].append(entry)
                    log.info("    ✓ GEFANGEN: %s", entry["got"])
                else:
                    results[label]["missed"].append(entry)
                    log.info("    ✗ VERPASST: %s", entry["got"])
            except Exception as e:
                log.error("    FEHLER: %s", e)
                results[label]["errors"].append({"id": item["id"], "error": str(e)[:120]})
            time.sleep(0.5)

        for item in kontrollen:
            log.info("  [%s] Kontrolle %s ...", label, item["id"])
            try:
                entry = run_item(item, v)
                if entry["got"] in PROBLEMATIC:
                    results[label]["fp"].append(entry)
                    log.warning("    ✗ FALSCH-POSITIV: %s", entry["got"])
                else:
                    results[label]["ok"].append(entry)
                    log.info("    ✓ KORREKT: %s", entry["got"])
            except Exception as e:
                log.error("    FEHLER: %s", e)
                results[label]["errors"].append({"id": item["id"], "error": str(e)[:120]})
            time.sleep(0.5)

    return verifiers, results, slips, kontrollen


# ── Markdown report ───────────────────────────────────────────────────────────

def write_report(verifiers, results, slips, kontrollen):
    lines = [
        "# Lektorat Catch-Test Ergebnisse",
        "",
        f"Goldset: {len(slips)} Slips (L1–L{len(slips)}) × {len(kontrollen)} Kontrollen (K1–K{len(kontrollen)})",
        "",
        "## Übersicht",
        "",
        "| Verifizierer | Catch-Rate | FP-Rate | Verpasste Slips | Falsch-Positive |",
        "|---|---|---|---|---|",
    ]
    for v in verifiers:
        label = v["label"]
        r = results[label]
        if not v.get("available"):
            lines.append(f"| {label} | — | — | — | {r.get('skip_reason', 'n/v')} |")
            continue
        n_c = len(r["caught"]); n_m = len(r["missed"])
        n_fp = len(r["fp"]);    n_ok = len(r["ok"])
        n_s = n_c + n_m;        n_ctrl = n_fp + n_ok
        missed_ids = ", ".join(x["id"] for x in r["missed"]) or "—"
        fp_ids     = ", ".join(x["id"] for x in r["fp"])    or "—"
        errs = len(r["errors"])
        err_note = f" (+{errs} Fehler)" if errs else ""
        lines.append(
            f"| {label} | {n_c}/{n_s}{err_note} | {n_fp}/{n_ctrl}{err_note} "
            f"| {missed_ids} | {fp_ids} |"
        )

    lines += ["", "---", ""]

    for v in verifiers:
        label = v["label"]
        r = results[label]
        lines += [f"## {label}", ""]
        if not v.get("available"):
            lines += [f"**Übersprungen:** {r.get('skip_reason', 'n/v')}", ""]
            continue
        lines += [f"Modell-ID: `{v.get('resolved_id', v['id'])}`", ""]
        lines += ["### Slips", ""]
        for e in r["caught"]:
            lines.append(f"- ✓ **{e['id']} GEFANGEN** ({e['got']}) gold={e['gold']}")
            lines.append(f"  > {e['claim']}")
        for e in r["missed"]:
            lines.append(f"- ✗ **{e['id']} VERPASST** ({e['got']}) gold={e['gold']}")
            lines.append(f"  > {e['claim']}")
        for e in r["errors"]:
            if e["id"].startswith("L"):
                lines.append(f"- ⚠ {e['id']} FEHLER: {e['error']}")
        lines += ["", "### Kontrollen", ""]
        for e in r["ok"]:
            lines.append(f"- ✓ {e['id']} korrekt ({e['got']})")
        for e in r["fp"]:
            lines.append(f"- ✗ **{e['id']} FALSCH-POSITIV** ({e['got']}) gold=BELEGT")
            lines.append(f"  > {e['claim']}")
            lines.append(f"  > Begründung: {e['beleg'][:100]}")
        for e in r["errors"]:
            if e["id"].startswith("K"):
                lines.append(f"- ⚠ {e['id']} FEHLER: {e['error']}")
        lines.append("")

    RESULT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info("Ergebnisdatei: %s", RESULT_PATH)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Lektorat Catch-Test")
    parser.add_argument("--compare", action="store_true",
                        help="Mehrmodell-Vergleich (Sonnet + Haiku + Gemini)")
    ap = parser.parse_args()
    verifiers, results, slips, kontrollen = run_catchtest(compare=ap.compare)
    write_report(verifiers, results, slips, kontrollen)
    print(f"\nErgebnis: {RESULT_PATH}")
