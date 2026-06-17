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
TIER_VALUES_V2       = {"SILENT", "KORRIGIERT", "PRÜFEN"}
# Aliase für Backward-Compat (generate_grounded.py, ältere Skripte)
PROBLEMATIC_VERDICTS = {"NICHT_BELEGT", "ÜBERZOGEN", "WIDERSPRUCH"}
TIER_VALUES          = {"AUTO", "VORSCHLAG", "ESKALATION"}

LEKTORAT_SYSTEM = (
    "Du bist Korrektor für Kinderlexikon-Artikel (Wissensfreund). "
    "Prüfe alle faktischen Aussagen AUSSCHLIESSLICH gegen die beigefügten "
    "Wikipedia-Volltexte — niemals aus eigenem Vorwissen.\n\n"

    "GROUNDING-REGEL:\n"
    "  · Der genaue Sachverhalt muss DIREKT in der Quelle stehen — nicht impliziert, nicht erschlossen.\n"
    "  · Verbund-Satz (A UND B): beide Teilaussagen müssen direkt belegt sein.\n"
    "  · NICHT flaggen: Illustrative Vergleiche belegter Größen («so groß wie ein Haus», "
    "«56 m ≈ 18-stöckiges Hochhaus»); mildes Sprachkolorit («stolz», «wunderschön»); "
    "register-gerechte Vereinfachungen die im Kern stimmen (z.B. «runde Zelte» für Tipis S1).\n"
    "  · NUR flaggen: (a) neue unbelegte Sachaussage, (b) Zahl/Superlativ den Quelle nicht stützt "
    "oder widerspricht («der höchste der Welt» wo Quelle «einer der höchsten» sagt).\n\n"

    "DREI KORREKTURSTUFEN:\n\n"

    "  SILENT — stillschweigend korrigieren:\n"
    "    Wann: Minimaler Eingriff, Beleg eindeutig. Zahl/Datum angepasst, Superlativ abgemildert, "
    "unbelegter Nebensatz gestrichen — ohne den Satzrhythmus zu brechen.\n"
    "    Aktion: Satz in korrektur_neu korrigieren.\n\n"

    "  KORRIGIERT — Häkchen-Kontrolle (Standard-Stufe bei Unsicherheit):\n"
    "    Wann: Substanziellerer Eingriff (Satz umformuliert, Behauptung anders gerahmt), "
    "Wikipedia-Evidenz aber klar. Im Zweifel KORRIGIERT statt PRÜFEN.\n"
    "    Aktion: Satz in korrektur_neu korrigieren + kurzes WP-Zitat als Beleg.\n\n"

    "  PRÜFEN — nur markieren, nicht ändern:\n"
    "    Wann: Echte Unsicherheit — Quelle widersprüchlich, Kontext fehlt, sensibler Sachverhalt, "
    "Idealisierung/NPOV-Verstoß, struktureller Umbau nötig.\n"
    "    Aktion: Artikel NICHT ändern. Problem und Begründung nennen.\n\n"

    "KORREKTIONS-PRINZIP:\n"
    "  · Gleichwertiger Ersatz: Zahl→Quell-Zahl, Superlativ→Quell-Form, "
    "unbelegtes Detail→belegtes Pendant aus der Quelle.\n"
    "  · KEINE Abschwächung ins Vage (NICHT «sehr groß» statt belegter Maßangabe).\n"
    "  · Register wahren (S1 kindgerecht, S3 sachlich). BELEGT-Aussagen: nicht auflisten.\n\n"

    "Antworte NUR mit diesem JSON-Objekt:\n"
    "{\n"
    '  "corrections": [\n'
    "    {\n"
    '      "claim_original": "Exakter Satz aus dem Artikel",\n'
    '      "korrektur_neu":  "Korrigierter Satz (quellenbasiert, gleiches Register)",\n'
    '      "stufe":          "SILENT|KORRIGIERT",\n'
    '      "beleg":          "Wörtliches WP-Zitat (≤25 Wörter) oder Positionsangabe"\n'
    "    }\n"
    "  ],\n"
    '  "pruefen": [\n'
    "    {\n"
    '      "claim_original": "Exakter Satz aus dem Artikel",\n'
    '      "problem":        "Kurze Problembeschreibung (1 Satz)",\n'
    '      "begruendung":    "Warum PRÜFEN statt KORRIGIERT (1 Satz)"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Wenn alles belegt: {\"corrections\": [], \"pruefen\": []}\n"
    "JSON-Sicherheit: Innerhalb von Feldwerten keine geraden Anführungszeichen. "
    "Zitierte Textstellen in «» einschließen."
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

def build_lektorat_parts(article: dict, sources_block: str) -> tuple[str, str]:
    """Teilt Lektorat-Prompt in (sources_prefix, article_task).

    sources_prefix: stabiler Quellblock, identisch für alle Stufen eines Themas
                    → Anthropic cache_control: ephemeral greift über die 3 Batch-Calls.
    article_task:   variabler Teil (Artikeltext je Stufe + Aufgabe).
    """
    article_text = article_to_lektorat_text(article)
    level = article.get("meta", {}).get("age_level", "?")
    title = article.get("meta", {}).get("title", "?")
    article_task = (
        f"PRÜF-ARTIKEL (Stufe {level}, Titel: {title}):\n{article_text}\n\n"
        "Prüfe alle faktischen Aussagen gegen die deklarierten Quellen. "
        "Liefere corrections (SILENT/KORRIGIERT) und pruefen-Flags im vorgegebenen JSON-Format."
    )
    return sources_block, article_task


def build_lektorat_prompt(article: dict, sources_block: str) -> str:
    """Backward-compat: ungecachte Volltext-Version (für Catch-Test / direkte Aufrufe)."""
    sources, task = build_lektorat_parts(article, sources_block)
    return f"{sources}\n\n{task}"


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
            score = _jaccard(claim_text, box.get("text", ""))
            if score > best_score:
                best_score = score
                best_loc = ("box_text", si, bi)
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
    elif best_loc[0] == "box_text":
        _, si, bi = best_loc
        article["sections"][si]["boxes"][bi]["text"] = korrektur_neu
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


# ── V2: Parser + Annotator (SILENT / KORRIGIERT / PRÜFEN) ────────────────────

def parse_lektorat_v2(raw: str) -> dict:
    """Parst das neue Lektorat-JSON-Format: {"corrections": [...], "pruefen": [...]}."""
    if not raw:
        raise ValueError("Leere Antwort")
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    for attempt in (cleaned, _fix_inner_quotes(cleaned)):
        start = attempt.find("{")
        if start == -1:
            continue
        try:
            inner = _extract_balanced(attempt[start:], "{", "}")
            obj = json.loads(inner)
            if isinstance(obj, dict):
                return {
                    "corrections": obj.get("corrections", []),
                    "pruefen":     obj.get("pruefen", []),
                }
        except (ValueError, json.JSONDecodeError):
            pass

    raise ValueError("Kein gültiges JSON-Objekt gefunden")


def annotate_article_lektorat_v2(
    article: dict,
    lektorat_result: dict,
    thema:  str = "",
    stufe:  str = "",
) -> None:
    """Wendet SILENT+KORRIGIERT-Korrekturen an; schreibt pruefbericht ins Artikel-JSON.

    review_flag = True nur bei PRÜFEN-Flags oder nicht einbaubaren Korrekturen.
    """
    corrections = lektorat_result.get("corrections", [])
    pruefen_in  = lektorat_result.get("pruefen", [])

    silent_lines:     list[str] = []
    korrigiert_lines: list[str] = []
    pruefen_lines:    list[str] = []

    for c in corrections:
        claim  = c.get("claim_original", "").strip()
        neu    = c.get("korrektur_neu", "").strip()
        tier   = c.get("stufe", "KORRIGIERT")
        beleg  = c.get("beleg", "").strip()

        if not claim or not neu or claim == neu:
            continue

        applied = _apply_auto_correction(article, claim, neu)

        if not applied:
            pruefen_lines.append(
                f"«{claim[:80]}» — Einbau fehlgeschlagen (Satz nicht gefunden)"
            )
            continue

        claim_s = claim[:70] + ("…" if len(claim) > 70 else "")
        neu_s   = neu[:70]   + ("…" if len(neu)   > 70 else "")
        if tier == "SILENT":
            beleg_s = f" (WP: {beleg[:40]})" if beleg else ""
            silent_lines.append(f"«{claim_s}» → «{neu_s}»{beleg_s}")
        else:
            beleg_s = f" — WP: «{beleg[:60]}»" if beleg else ""
            korrigiert_lines.append(f"«{claim_s}» → «{neu_s}»{beleg_s}")

    for p in pruefen_in:
        claim  = p.get("claim_original", "").strip()
        prob   = p.get("problem", "").strip()
        beg    = p.get("begruendung", "").strip()
        entry  = f"«{claim[:70]}» — {prob}"
        if beg:
            entry += f" ({beg})"
        pruefen_lines.append(entry)

    # Pruefbericht aufbauen
    header = f"## {thema} {stufe} — Lektorat" if thema else "## Lektorat"
    parts  = [header]
    if silent_lines:
        parts.append(f"### SILENT ({len(silent_lines)} Korrekturen)")
        parts.extend(f"- {l}" for l in silent_lines)
    if korrigiert_lines:
        parts.append(f"### KORRIGIERT ({len(korrigiert_lines)} Korrekturen)")
        parts.extend(f"- {l}" for l in korrigiert_lines)
    if pruefen_lines:
        parts.append(f"### PRÜFEN ({len(pruefen_lines)} Flags)")
        parts.extend(f"- {l}" for l in pruefen_lines)
    n_pr = len(pruefen_lines)
    parts.append(
        f"Zusammenfassung: {len(silent_lines)} silent, "
        f"{len(korrigiert_lines)} korrigiert, {n_pr} zu prüfen."
    )

    article["pruefbericht"] = {
        "text":         "\n".join(parts),
        "n_silent":     len(silent_lines),
        "n_korrigiert": len(korrigiert_lines),
        "n_pruefen":    n_pr,
    }

    if n_pr > 0:
        article.setdefault("meta", {})["review_flag"] = True
        existing = article["meta"].get("review_reason", "")
        reason   = f"lektorat: {n_pr} zu prüfen"
        article["meta"]["review_reason"] = (existing + "; " + reason).lstrip("; ")


# ── Anthropic Sync-API (Default für Test-/Kleinläufe) ────────────────────────

def run_lektorat_sync(
    parts_by_id: dict[str, tuple[str, str]],
    api_key: str,
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Führt Lektorat-Calls SEQUENZIELL aus (schnell für ≤5 Artikel).

    Gibt (results, usage_by_id) zurück.
    usage_by_id keys: input_tok, output_tok, cache_create_tok, cache_read_tok.

    Gleiche Prompt-Struktur wie run_lektorat_batch (cache_control: ephemeral).
    Sequenziell statt parallel: Call 1 schreibt den Anthropic-KV-Cache
    (cache_creation_input_tokens), Calls 2-3 lesen ihn (cache_read_input_tokens).
    """
    import anthropic

    client    = anthropic.Anthropic(api_key=api_key)
    results:    dict[str, list[dict]] = {}
    usage_by_id: dict[str, dict]     = {}

    for aid, (sources_prefix, article_task) in parts_by_id.items():
        log.info("  Lektorat-Sync [%s] …", aid)
        try:
            msg = client.messages.create(
                model=LEKTORAT_MODEL,
                max_tokens=16000,
                system=[
                    {"type": "text", "text": LEKTORAT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}},
                ],
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": sources_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": article_task},
                ]}],
            )
            raw = msg.content[0].text
            u   = msg.usage
            log.info(
                "  [%s] tokens in=%d create=%d read=%d out=%d",
                aid, u.input_tokens,
                getattr(u, "cache_creation_input_tokens", 0),
                getattr(u, "cache_read_input_tokens", 0),
                u.output_tokens,
            )
            usage_by_id[aid] = {
                "input_tok":       u.input_tokens,
                "output_tok":      u.output_tokens,
                "cache_create_tok": getattr(u, "cache_creation_input_tokens", 0),
                "cache_read_tok":   getattr(u, "cache_read_input_tokens", 0),
            }
            try:
                results[aid] = parse_lektorat_json(raw)
            except Exception as exc:
                log.warning("  Lektorat JSON-Parse [%s]: %s", aid, exc)
                results[aid] = []
        except Exception as exc:
            log.warning("  Lektorat-Sync [%s] fehlgeschlagen: %s", aid, exc)
            results[aid] = []
            usage_by_id[aid] = {}

    return results, usage_by_id


# ── Anthropic Batch-API ───────────────────────────────────────────────────────

def run_lektorat_batch(
    parts_by_id: dict[str, tuple[str, str]],
    api_key: str,
) -> dict[str, list[dict]]:
    """Reicht alle Lektorat-Anfragen als Anthropic Message Batch ein.

    parts_by_id: {article_id: (sources_prefix, article_task)}
      sources_prefix = stabiler Quellblock (cache_control: ephemeral)
      article_task   = variabler Artikeltext + Aufgabe

    Prompt-Caching: System-Prompt + sources_prefix sind über alle 3 Batch-Anfragen
    identisch → Anthropic KV-Cache-Hit ab 2. Anfrage (~50 % Token-Einsparung).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    batch_requests = []
    for aid, (sources_prefix, article_task) in parts_by_id.items():
        batch_requests.append({
            "custom_id": aid,
            "params": {
                "model":      LEKTORAT_MODEL,
                "max_tokens": 16000,
                "system": [
                    {"type": "text", "text": LEKTORAT_SYSTEM,
                     "cache_control": {"type": "ephemeral"}},
                ],
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": sources_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": article_task},
                ]}],
            },
        })

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
            msg = result.result.message
            raw = msg.content[0].text
            u   = msg.usage
            log.info(
                "  [%s] tokens in=%d create=%d read=%d out=%d",
                rid, u.input_tokens,
                getattr(u, "cache_creation_input_tokens", 0),
                getattr(u, "cache_read_input_tokens", 0),
                u.output_tokens,
            )
            try:
                results[rid] = parse_lektorat_json(raw)
            except Exception as exc:
                log.warning("  Lektorat JSON-Parse [%s]: %s", rid, exc)
                results[rid] = []
        else:
            log.warning("  Lektorat-Batch [%s]: %s", rid, result.result.type)
            results[rid] = []

    return results
