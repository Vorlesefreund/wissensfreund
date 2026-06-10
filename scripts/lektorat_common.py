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
import unicodedata

log = logging.getLogger(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────

COMPANION_CHAR_CAP   = 30_000          # positional slice je Companion-Text
LEKTORAT_MODEL       = "claude-sonnet-4-6"
PROBLEMATIC_VERDICTS = {"NICHT_BELEGT", "ÜBERZOGEN", "WIDERSPRUCH"}
TIER_VALUES          = {"AUTO", "VORSCHLAG", "ESKALATION"}

LEKTORAT_SYSTEM = (
    "Du bist Faktenprüfer und Korrektor für Kinderlexikon-Artikel. "
    "Prüfe alle faktischen Aussagen AUSSCHLIESSLICH gegen die beigefügten "
    "Quell-Volltexte — niemals aus Vorwissen.\n\n"

    "FAERBUNGS-REGEL — diese Formulierungen NICHT flaggen (= BELEGT):\n"
    "  · Illustrative Vergleiche belegter Zahlen/Größen: «56 m ≈ 18-stöckiges Hochhaus», "
    "«so groß wie ein Haus», «so hoch wie Bäume» (bei aus Baumstämmen geschnitzten Pfählen)\n"
    "  · Mildes sprachliches/emotionales Kolorit («stolz», «wunderschön»), "
    "das den Sachverhalt nicht ändert\n"
    "  · Register-gerechte Vereinfachungen, die im Kern stimmen "
    "(z.B. «runde Zelte» für Tipis in Stufe 1)\n"
    "NUR flaggen bei: (a) neuer, nicht belegter Sachaussage (Detail/Pflanze/Ereignis), "
    "ODER (b) Zahl/Superlativ/Größenordnung, die Quelle nicht stützt oder widerspricht "
    "(«der höchste der Welt» wo Quelle «einer der höchsten» sagt). "
    "Idealisierung/NPOV-Verstoß: ESKALATION.\n"
    "BELEGT-BEDINGUNG: Der genaue Sachverhalt muss DIREKT in der Quelle stehen — "
    "nicht nur das Thema. «Ist impliziert» oder «lässt sich schließen» reicht NICHT aus.\n"
    "VERBUND-REGEL: Enthält ein Satz zwei Sachverhalte (A UND B), müssen BEIDE einzeln "
    "direkt in den Quellen stehen. Ist B nicht direkt belegt, ist der Gesamtsatz NICHT_BELEGT.\n\n"

    "FÜR JEDE AUSSAGE diese Felder liefern:\n"
    "  claim: EXAKTER vollständiger Satz aus dem Artikel (wird per Textersatz eingebaut)\n"
    "  verdikt: BELEGT | NICHT_BELEGT | ÜBERZOGEN | WIDERSPRUCH\n"
    "  tier (nur bei Nicht-BELEGT):\n"
    "    AUTO      — eindeutiger, register-sicherer Ersatz-Satz bildbar; "
    "beleg_fuer_korrektur WÖRTLICH in Quelle auffindbar\n"
    "    VORSCHLAG — Ersatz möglich aber Umformulierung nötig / mehrere Optionen / "
    "Beleg-Zitat nicht exakt wörtlich\n"
    "    ESKALATION— kein gegroundeter Ersatz möglich / Idealisierung/NPOV / "
    "Quelle mehrdeutig / struktureller Umbau\n"
    "  beleg_oder_begruendung: wörtliches Quellzitat bei BELEGT; kurze Begründung sonst\n"
    "  korrektur_neu: bei AUTO/VORSCHLAG der vollständig korrigierte Satz "
    "(gleiches Register, quellenbasiert; NIE vage abschwächen, z.B. NICHT "
    "«so hoch wie Bäume» durch «sehr groß» ersetzen); bei BELEGT/ESKALATION leer lassen\n"
    "  beleg_fuer_korrektur: bei AUTO/VORSCHLAG WÖRTLICHES Quellzitat als Beleg für "
    "korrektur_neu; bei BELEGT/ESKALATION leer lassen\n\n"

    "KORREKTIONS-PRINZIP:\n"
    "  · Gleichwertiger Ersatz: Zahl→Quell-Zahl, Superlativ→Quell-Form, "
    "unbelegtes Detail→belegtes Pendant aus der Quelle\n"
    "  · KEINE Abschwächung ins Vage, KEINE ersatzlose Streichung\n"
    "  · Register wahren (Stufe 1: kindgerecht; Stufe 3: sachlich)\n\n"

    "Antworte NUR mit JSON-Array:\n"
    '[{"claim":"exakter Satz aus Artikel","verdikt":"BELEGT|NICHT_BELEGT|ÜBERZOGEN|WIDERSPRUCH",'
    '"tier":"AUTO|VORSCHLAG|ESKALATION|","beleg_oder_begruendung":"...",'
    '"korrektur_neu":"...","beleg_fuer_korrektur":"..."}]\n\n'
    "JSON-Sicherheit: Innerhalb von Feldwerten keine geraden Anführungszeichen. "
    "Zitierte Textstellen in «\xa0» oder Apostrophe einschliessen."
)

# Reihenfolge der Felder im JSON (für robust extractor)
_ALL_FIELD_ORDER = [
    "claim", "verdikt", "tier", "beleg_oder_begruendung",
    "korrektur_neu", "beleg_fuer_korrektur",
]


# ── Quellblock (symmetrisch zur Generierung) ──────────────────────────────────

def build_grounded_sources_block(
    primary_title: str,
    primary_text: str,
    companion_titles: list[str],
    companion_texts: dict[str, str],
) -> str:
    """Primär ungekürzt · Companions[:COMPANION_CHAR_CAP]."""
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
        "Liefere für jede Aussage alle sechs Felder im JSON-Array."
    )


# ── JSON-Parser ───────────────────────────────────────────────────────────────

def _fix_inner_quotes(text: str) -> str:
    """Fix German inner quotes (U+201E + U+0022) that break JSON string parsing.

    Two cases:
    - inner" immediately before structural " → drop the inner "
    - inner" followed by more text → replace inner " with '
    """
    text = text.replace("„", "«")  # „ → «
    text = re.sub(r'(?<=[^\s{[\n,"])"(?=")', "", text)          # Case 1
    text = re.sub(r'(?<=[^\s{[\n,"])"(?!\s*[:{}\],""])', "'", text)  # Case 2
    return text


def parse_lektorat_json(raw: str) -> list[dict]:
    if not raw:
        raise ValueError("Leere Antwort")
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    has_array = "[" in cleaned

    # Try standard JSON parse — as-is, then with inner-quote fix
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

    Works even when string values contain unescaped " characters.
    """
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
        vm = re.search(r'"verdikt"\s*:\s*"([^"]{1,30})"', block)
        tm = re.search(r'"tier"\s*:\s*"([^"]{0,20})"', block)
        obj: dict = {
            "verdikt": vm.group(1) if vm else "UNBEKANNT",
            "tier":    tm.group(1) if tm else "",
        }
        for i, field in enumerate(_ALL_FIELD_ORDER):
            if field in ("verdikt", "tier"):
                continue
            next_fields = _ALL_FIELD_ORDER[i + 1:]
            if next_fields:
                obj[field] = _field_value_between_keys(block, field, next_fields)
            else:
                obj[field] = _field_value_before_close(block, field)
        results.append(obj)
    return results


def _field_value_between_keys(block: str, field: str, next_keys: list[str]) -> str:
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
    m = re.search(r'"' + re.escape(field) + r'"\s*:\s*"', block)
    if not m:
        return ""
    rest = block[m.end():]
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


# ── Hilfsfunktionen für Beleg-Check + Textersatz ─────────────────────────────

def _normalize_for_check(text: str) -> str:
    """NFKC-normalisiert + lowercase + whitespace-kollabiert für Substring-Check."""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.lower().split())


def _jaccard(a: str, b: str) -> float:
    """Jaccard-Ähnlichkeit auf Wort-Ebene für Satz-Matching."""
    wa = set(re.sub(r"[^\w\s]", "", a.lower()).split())
    wb = set(re.sub(r"[^\w\s]", "", b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _apply_auto_correction(article: dict, claim_text: str, korrektur_neu: str) -> bool:
    """Ersetzt den Satz in article, der claim_text am besten trifft, mit korrektur_neu.

    Gibt True zurück wenn Jaccard >= 0.4 und Ersatz vorgenommen wurde.
    """
    if not claim_text or not korrektur_neu or claim_text == korrektur_neu:
        return False

    best_score = 0.0
    best_loc: tuple | None = None  # ("sec", si, sj) or ("box", si, bi, sj)

    for si, sec in enumerate(article.get("sections", [])):
        for sj, sent in enumerate(sec.get("sentences", [])):
            score = _jaccard(claim_text, sent.get("text", ""))
            if score > best_score:
                best_score = score
                best_loc = ("sec", si, sj)
        for bi, box in enumerate(sec.get("boxes", [])):
            for sj, sent in enumerate(box.get("sentences", [])):
                score = _jaccard(claim_text, sent.get("text", ""))
                if score > best_score:
                    best_score = score
                    best_loc = ("box", si, bi, sj)

    if best_score < 0.4 or best_loc is None:
        return False

    if best_loc[0] == "sec":
        _, si, sj = best_loc
        article["sections"][si]["sentences"][sj]["text"] = korrektur_neu
    else:
        _, si, bi, sj = best_loc
        article["sections"][si]["boxes"][bi]["sentences"][sj]["text"] = korrektur_neu
    return True


# ── Prüfbericht erstellen + Artikel annotieren ───────────────────────────────

def build_pruefbericht(verdicts: list[dict], primary_text: str = "") -> dict:
    """Strukturiert Verdikt-Liste in pruefbericht mit Korrektur-Status (Stufe 2).

    Status je Finding:
      belegt         — Aussage korrekt, keine Aktion
      auto_angewandt — AUTO-Tier + beleg_fuer_korrektur wörtlich in primary_text
      vorschlag_offen— VORSCHLAG, oder AUTO dessen Beleg nicht wörtlich gefunden
      eskaliert      — ESKALATION (kein gegroundeter Ersatz)
    """
    n_primary = _normalize_for_check(primary_text)

    findings = []
    for v in verdicts:
        verdikt   = v.get("verdikt", "UNBEKANNT")
        tier      = v.get("tier", "")
        kor_neu   = v.get("korrektur_neu", "")
        beleg_k   = v.get("beleg_fuer_korrektur", "")

        if verdikt == "BELEGT":
            status = "belegt"
        elif tier == "ESKALATION":
            status = "eskaliert"
        elif tier == "AUTO":
            # Mechanischer Beleg-Check: wörtliches Zitat im Primärtext?
            if beleg_k and n_primary and _normalize_for_check(beleg_k) in n_primary:
                status = "auto_angewandt"
            else:
                tier   = "VORSCHLAG"   # Downgrade
                status = "vorschlag_offen"
        else:
            status = "vorschlag_offen"

        findings.append({
            "claim_original":         v.get("claim", ""),
            "verdikt":                verdikt,
            "tier":                   tier,
            "beleg_oder_begruendung": v.get("beleg_oder_begruendung", ""),
            "korrektur_neu":          kor_neu if status in ("auto_angewandt", "vorschlag_offen") else "",
            "beleg_fuer_korrektur":   beleg_k if status in ("auto_angewandt", "vorschlag_offen") else "",
            "status":                 status,
        })

    summary = {
        "auto_angewandt":  sum(1 for f in findings if f["status"] == "auto_angewandt"),
        "vorschlag_offen": sum(1 for f in findings if f["status"] == "vorschlag_offen"),
        "eskaliert":       sum(1 for f in findings if f["status"] == "eskaliert"),
    }
    return {"findings": findings, "summary": summary}


def annotate_article_lektorat(
    article: dict,
    verdicts: list[dict],
    primary_text: str = "",
) -> None:
    """Schreibt pruefbericht-Feld ins Artikel-JSON und wendet AUTO-Korrekturen an.

    review_flag = True nur bei vorschlag_offen oder eskaliert.
    AUTO-Korrekturen werden direkt in article["sections"] eingebaut.
    """
    pb = build_pruefbericht(verdicts, primary_text)

    # AUTO-Korrekturen einbauen
    for finding in pb["findings"]:
        if finding["status"] == "auto_angewandt" and finding["korrektur_neu"]:
            applied = _apply_auto_correction(
                article, finding["claim_original"], finding["korrektur_neu"]
            )
            if not applied:
                # Satz nicht im Artikel gefunden — auf VORSCHLAG herabstufen
                finding["status"] = "vorschlag_offen"
                finding["tier"]   = "VORSCHLAG"
                pb["summary"]["auto_angewandt"]  -= 1
                pb["summary"]["vorschlag_offen"] += 1

    article["pruefbericht"] = pb

    n_v = pb["summary"]["vorschlag_offen"]
    n_e = pb["summary"]["eskaliert"]
    if n_v > 0 or n_e > 0:
        article.setdefault("meta", {})["review_flag"] = True
        existing = article["meta"].get("review_reason", "")
        reason   = f"lektorat: {n_v} vorschlag, {n_e} eskaliert"
        article["meta"]["review_reason"] = (existing + "; " + reason).lstrip("; ")


# ── Anthropic Batch-API ───────────────────────────────────────────────────────

def run_lektorat_batch(
    prompts_by_id: dict[str, str],
    api_key: str,
) -> dict[str, list[dict]]:
    """Reicht alle Lektorat-Anfragen als Anthropic Message Batch ein (50 % günstiger),
    pollt bis abgeschlossen, gibt article_id → rohe Verdikt-Liste zurück.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    batch_requests = [
        {
            "custom_id": aid,
            "params": {
                "model":      LEKTORAT_MODEL,
                "max_tokens": 16000,
                "system":     LEKTORAT_SYSTEM,
                "messages":   [{"role": "user", "content": prompt}],
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
