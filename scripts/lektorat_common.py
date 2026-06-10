#!/usr/bin/env python3
"""
lektorat_common.py
Gemeinsame Konstanten, Prompt-Bausteine und Batch-Ausführung für
generate_grounded.py (Post-Phase-2-Lektorat) und run_lektorat_catchtest.py.
Eine Quelle, kein Drift.
"""
import json
import logging
import re
import time

log = logging.getLogger(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────

COMPANION_CHAR_CAP   = 30_000          # positional slice je Companion-Text
LEKTORAT_MODEL       = "claude-sonnet-4-6"
PROBLEMATIC_VERDICTS = {"NICHT_BELEGT", "ÜBERZOGEN", "WIDERSPRUCH"}
TIER_VALUES          = {"AUTO", "VORSCHLAG", "ESKALATION"}

LEKTORAT_SYSTEM = (
    "Du bist Faktenprüfer. Prüfe alle Aussagen im vorgelegten Artikel AUSSCHLIESSLICH gegen die "
    "beigefügten Quell-Volltexte — niemals aus Vorwissen.\n\n"
    "Für jede faktische Aussage:\n"
    "  Verdikt: BELEGT | NICHT_BELEGT | ÜBERZOGEN | WIDERSPRUCH\n"
    "  Tier (nur bei Nicht-BELEGT):\n"
    "    AUTO      — ÜBERZOGEN, das durch eine lokale Abschwächung behebbar ist "
    "(z.B. »alle« → »viele«); eindeutiger lokaler Wert-Tausch.\n"
    "    VORSCHLAG — NICHT_BELEGT; WIDERSPRUCH mit nötiger Umschreibung; "
    "invasives ÜBERZOGEN; mittlere Konfidenz.\n"
    "    ESKALATION— Idealisierung/NPOV-Verstoß; Quelle mehrdeutig; "
    "geringe Konfidenz; struktureller Umbau nötig.\n"
    "  Bei BELEGT: tier leer lassen.\n\n"
    "Wörtliches Beleg-Zitat aus der Quelle bei BELEGT; sonst kurze Begründung. "
    "Vivide Sprache ist erlaubt, solange sie keine Fakten über die Quelle hinaus hinzufügt.\n\n"
    "Antworte NUR mit JSON-Array:\n"
    '[{"claim":"...","verdikt":"BELEGT|NICHT_BELEGT|ÜBERZOGEN|WIDERSPRUCH",'
    '"tier":"AUTO|VORSCHLAG|ESKALATION|","beleg_oder_begruendung":"..."}]\n\n'
    "WICHTIG JSON-Sicherheit: Innerhalb von Feldwerten keine geraden Anführungszeichen. "
    "Zitierte Textstellen in «\xa0» oder einfache Apostrophe einschliessen — nie \"Wort\" schreiben."
)


# ── Quellblock (symmetrisch zur Generierung) ──────────────────────────────────

def build_grounded_sources_block(
    primary_title: str,
    primary_text: str,
    companion_titles: list[str],
    companion_texts: dict[str, str],
) -> str:
    """
    Primär ungekürzt · Companions[:COMPANION_CHAR_CAP].
    Identisch zur Phase-2-Generierung in generate_grounded.py.
    """
    parts = [f"### Quelle: {primary_title}\n{primary_text}"]
    for title in companion_titles:
        text = companion_texts.get(title, "")
        if text:
            parts.append(f"### Quelle: {title}\n{text[:COMPANION_CHAR_CAP]}")
    return "DEKLARIERTE QUELLEN:\n" + "\n\n".join(parts)


# ── Artikel → lesbarer Fließtext ─────────────────────────────────────────────

def article_to_lektorat_text(article: dict) -> str:
    """Wandelt Artikel-JSON in lesbaren Text für den Lektorat-Prompt."""
    lines = []
    for sec in article.get("sections", []):
        heading = sec.get("heading", sec.get("title", "")).strip()
        if heading:
            lines.append(f"\n[{heading}]")
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


# ── Prompt-Builder ────────────────────────────────────────────────────────────

def build_lektorat_prompt(article: dict, sources_block: str) -> str:
    article_text = article_to_lektorat_text(article)
    level = article.get("meta", {}).get("age_level", "?")
    title = article.get("meta", {}).get("title", "?")
    return (
        f"PRÜF-ARTIKEL (Stufe {level}, Titel: {title}):\n{article_text}\n\n"
        f"{sources_block}\n\n"
        "Prüfe ALLE faktischen Aussagen im Artikel gegen die deklarierten Quellen. "
        "Gib für jede Aussage ein separates Verdikt mit Tier im JSON-Array."
    )


# ── JSON-Parser ───────────────────────────────────────────────────────────────

def _fix_inner_quotes(text: str) -> str:
    """Fix German inner quotes that break JSON: U+201E...U+0022 patterns.

    Claude uses „word" (U+201E open, U+0022 close) inside JSON string values.
    The U+0022 terminates the JSON string early. Two cases:
    - „word"" → inner " immediately before structural " → drop the inner "
    - „word" … → inner " followed by more text → replace inner " with '
    """
    text = text.replace('„', '«')  # „ → « (safe in JSON strings)
    # Case 1: inner " immediately followed by structural " → remove inner "
    text = re.sub(r'(?<=[^\s{[\n,"])"(?=")', '', text)
    # Case 2: inner " followed by non-structural continuation → replace with '
    text = re.sub(r'(?<=[^\s{[\n,"])"(?!\s*[:{}\],""])', "'", text)
    return text


def parse_lektorat_json(raw: str) -> list[dict]:
    if not raw:
        raise ValueError("Leere Antwort")
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    has_array = "[" in cleaned

    # Try standard JSON parse — first as-is, then with inner-quote fix
    for attempt in (cleaned, _fix_inner_quotes(cleaned)):
        start = attempt.find("[")
        if start != -1:
            try:
                inner = _extract_balanced(attempt[start:], "[", "]")
                result = json.loads(inner)
                if isinstance(result, list):
                    return result
            except (ValueError, json.JSONDecodeError):
                pass

    # Single-object fallback only when response has no array wrapper
    if not has_array:
        for attempt in (cleaned, _fix_inner_quotes(cleaned)):
            start = attempt.find("{")
            if start != -1:
                try:
                    inner = _extract_balanced(attempt[start:], "{", "}")
                    return [json.loads(inner)]
                except (ValueError, json.JSONDecodeError):
                    pass

    # Robust structural extraction — works even with unescaped " inside values
    result = _extract_lektorat_objects_robust(cleaned)
    if result:
        return result
    raise ValueError("Kein JSON-Array oder Objekt gefunden")


def _extract_lektorat_objects_robust(text: str) -> list[dict]:
    """Structural extraction: split on { } depth, extract fields by key position.

    Used when JSON parsing fails. Does NOT track string state, so it works even
    when string values contain unescaped " characters.
    """
    # Split into top-level { ... } blocks
    blocks = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                blocks.append(text[start : i + 1])

    results = []
    for block in blocks:
        # verdikt and tier have short, predictable values — safe regex
        vm = re.search(r'"verdikt"\s*:\s*"([^"]{1,30})"', block)
        tm = re.search(r'"tier"\s*:\s*"([^"]{0,20})"', block)
        claim = _field_value_between_keys(block, "claim", ["verdikt", "tier", "beleg_oder_begruendung"])
        beleg = _field_value_before_close(block, "beleg_oder_begruendung")
        results.append({
            "claim": claim,
            "verdikt": vm.group(1) if vm else "UNBEKANNT",
            "tier": tm.group(1) if tm else "",
            "beleg_oder_begruendung": beleg,
        })
    return results


def _field_value_between_keys(block: str, field: str, next_keys: list[str]) -> str:
    """Extract value of field by finding the value start and the next key as end marker."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', block)
    if not m:
        return ""
    rest = block[m.end():]
    next_pat = "|".join(re.escape(k) for k in next_keys)
    end = re.search(r'",\s*\n\s*"(?:' + next_pat + r'")', rest)
    if end:
        return rest[: end.start()]
    return rest.split('",')[0]


def _field_value_before_close(block: str, field: str) -> str:
    """Extract value of the last field (before the closing })."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', block)
    if not m:
        return ""
    rest = block[m.end():]
    # Last " before \n  }
    end = re.search(r'"\s*\n?\s*}', rest)
    if end:
        return rest[: end.start()]
    idx = rest.rfind('"')
    return rest[:idx] if idx >= 0 else rest


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str:
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[:i + 1]
    raise ValueError(f"Unvollständiges JSON (kein balanciertes '{close_ch}')")


# ── Prüfbericht erstellen + Artikel annotieren ───────────────────────────────

def build_pruefbericht(verdicts: list[dict]) -> dict:
    """Strukturiert rohe Verdikt-Liste in pruefbericht {findings, summary}."""
    findings = [
        {
            "claim":                  v.get("claim", ""),
            "verdikt":                v.get("verdikt", "UNBEKANNT"),
            "tier":                   v.get("tier", ""),
            "beleg_oder_begruendung": v.get("beleg_oder_begruendung", ""),
        }
        for v in verdicts
    ]
    summary = {
        "BELEGT":       sum(1 for f in findings if f["verdikt"] == "BELEGT"),
        "NICHT_BELEGT": sum(1 for f in findings if f["verdikt"] == "NICHT_BELEGT"),
        "ÜBERZOGEN":    sum(1 for f in findings if f["verdikt"] == "ÜBERZOGEN"),
        "WIDERSPRUCH":  sum(1 for f in findings if f["verdikt"] == "WIDERSPRUCH"),
        "AUTO":         sum(1 for f in findings if f["tier"] == "AUTO"),
        "VORSCHLAG":    sum(1 for f in findings if f["tier"] == "VORSCHLAG"),
        "ESKALATION":   sum(1 for f in findings if f["tier"] == "ESKALATION"),
    }
    return {"findings": findings, "summary": summary}


def annotate_article_lektorat(article: dict, verdicts: list[dict]) -> None:
    """
    Schreibt pruefbericht-Feld ins Artikel-JSON.
    review_flag = True nur bei VORSCHLAG oder ESKALATION (AUTO-only = kein Flag).
    """
    pb = build_pruefbericht(verdicts)
    article["pruefbericht"] = pb
    n_v = pb["summary"]["VORSCHLAG"]
    n_e = pb["summary"]["ESKALATION"]
    if n_v > 0 or n_e > 0:
        article.setdefault("meta", {})["review_flag"] = True
        existing = article["meta"].get("review_reason", "")
        reason = f"lektorat: {n_v} VORSCHLAG, {n_e} ESKALATION"
        article["meta"]["review_reason"] = (existing + "; " + reason).lstrip("; ")


# ── Anthropic Batch-API ───────────────────────────────────────────────────────

def run_lektorat_batch(
    prompts_by_id: dict[str, str],
    api_key: str,
) -> dict[str, list[dict]]:
    """
    Reicht alle Lektorat-Anfragen als Anthropic Message Batch ein (50 % günstiger),
    pollt bis abgeschlossen, gibt article_id → rohe Verdikt-Liste zurück.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    batch_requests = [
        {
            "custom_id": aid,
            "params": {
                "model": LEKTORAT_MODEL,
                "max_tokens": 16000,
                "system": LEKTORAT_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
        }
        for aid, prompt in prompts_by_id.items()
    ]

    batch = client.messages.batches.create(requests=batch_requests)
    log.info("  Lektorat-Batch gestartet: %s (%d Anfragen)", batch.id, len(batch_requests))

    poll_interval = 10
    while batch.processing_status == "in_progress":
        time.sleep(poll_interval)
        batch = client.messages.batches.retrieve(batch.id)
        c = batch.request_counts
        log.info(
            "  Batch %s … %s (✓%d ✗%d ⌛%d)",
            batch.id[:20], batch.processing_status,
            c.succeeded, c.errored, c.processing,
        )

    results: dict[str, list[dict]] = {}
    for result in client.messages.batches.results(batch.id):
        rid = result.custom_id
        if result.result.type == "succeeded":
            raw = result.result.message.content[0].text
            try:
                results[rid] = parse_lektorat_json(raw)
            except Exception as exc:
                log.warning("  Lektorat JSON-Parse [%s]: %s", rid, exc)
                results[rid] = []
        else:
            log.warning("  Lektorat-Batch [%s]: %s", rid, result.result.type)
            results[rid] = []

    return results
