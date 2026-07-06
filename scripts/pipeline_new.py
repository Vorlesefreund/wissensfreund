#!/usr/bin/env python3
"""pipeline_new.py — Neuarchitektur Generator (Phase 1, MVP).

Modulare Pass-Struktur, aktiv NUR bei run_batch --pipeline new. Der alte
monolithische Pfad bleibt unberührt (Fallback-Garantie).

Fundament (Phase 1): Pass 1 (Plan) -> Pass 2 (Prosa/Markdown, Wortziel-Schleife)
-> Pass 6 (deterministischer JSON-Zusammenbau mit Rejoin-Invariante + Beleg-Suche).
Boxen/Bilder/Quiz sind bewusst minimale Stubs (Pass 3/4/5 folgen in Phase 2/3).

Grounding-Regel (eisern): jeder generative Pass bekommt den Quelltext; Inhalt
nur aus geladenem Wikipedia-Text, nie aus Trainingswissen.

State-Monotonie: Pass 2 legt den Fließtext fest. Kein späterer Pass trimmt oder
schreibt Prosa um. Pass 6 zerlegt nur — und beweist per Rejoin-Invariante, dass
kein Zeichen verändert wurde.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import gemini_client
from generate_grounded import (
    wortziel_for,
    count_article_words,
    ergiebigkeit_for,
    _make_thinking_config,
)

try:
    import cost_tracker
except Exception:  # pragma: no cover — Kostentracking ist best-effort
    cost_tracker = None

log = logging.getLogger("pipeline_new")

# Modell-Baseline Phase 1 (Pass 1, 2, Beleg-Suche). Empirische Verfeinerung später.
BASELINE_MODEL = "gemini-3.5-flash"

# Wortziel-Schleife: harte Deckelung gegen Endlosschleifen (1 initial + 2 Retries).
WORDLOOP_MAX_ATTEMPTS = 3


# ══════════════════════════════════════════════════════════════════════════════
# Quelltext-Aufbereitung
# ══════════════════════════════════════════════════════════════════════════════

def _source_block(thema: str, primary_text: str,
                  companion_texts: dict[str, str]) -> str:
    """Baut den Quelltext-Block: Primärartikel + benannte Companions."""
    parts = [f"### QUELLE — HAUPTTHEMA: {thema}\n{primary_text.strip()}"]
    for name, txt in companion_texts.items():
        if txt and txt.strip():
            parts.append(f"### QUELLE — BEGLEITARTIKEL: {name}\n{txt.strip()}")
    return "\n\n".join(parts)


def _level_register(stufe: int) -> str:
    return {
        1: "Stufe 1 (ca. 6–7 Jahre): kurze, einfache Sätze. Alltagswörter. "
           "Ein Gedanke pro Satz.",
        2: "Stufe 2 (ca. 8–9 Jahre): erste Fachbegriffe, aber sofort erklärt. "
           "Etwas längere Sätze, klarer roter Faden.",
        3: "Stufe 3 (ca. 10–12 Jahre): flüssige, zusammenhängende Erzählung, "
           "kein Schulbuchton. Fachbegriffe erklären oder weglassen.",
    }.get(stufe, "Stufe 2: klar und kindgerecht.")


def create_source_cache(client, model: str, thema: str, primary_text: str,
                        companion_texts: dict[str, str], ttl: str = "1800s") -> str | None:
    """Gemini Context Cache für den QUELLTEXT eines Themas (Primär + Companions).

    Bewusst OHNE eingebackenen System-Prompt (im Gegensatz zum alten Pfad): der
    Cache hält nur die Quelle als cached user-content, sodass ihn ALLE Pässe (Plan,
    Prosa, Box, Beleg-Suche) und später ein Gemini-Lektorat teilen können — jeder
    Pass liefert seinen eigenen System-Prompt in der frischen User-Message.
    Gibt den Cache-Namen zurück oder None (graceful Fallback → voller Kontext).

    Der wiederverwendbare Kern ist der stabile `_source_block`: ein Anthropic-
    Lektorat kann denselben Block über sein eigenes Prompt-Caching (cache_control)
    nutzen; ein Gemini-Lektorat direkt diesen Cache.
    """
    from google.genai import types as _types
    source = _source_block(thema, primary_text, companion_texts)
    try:
        cache = client.caches.create(
            model=model,
            config=_types.CreateCachedContentConfig(
                contents=[{"role": "user", "parts": [{"text": source}]}],
                ttl=ttl,
            ),
        )
        log.info("  [new] Quelltext-Cache erstellt: %s (~%d Zeichen)", cache.name, len(source))
        return cache.name
    except Exception as e:
        log.info("  [new] Quelltext-Cache nicht verfügbar (%s) — voller Kontext je Pass", e)
        return None


def _call_pass(system_prompt: str, body: str, source: str, model: str, thinking,
               cache: str | None, *, call_name: str,
               response_mime_type: str | None = None, response_schema=None) -> str:
    """Ein Pass-Aufruf. Mit Cache: Quelle steckt im Cache, System-Prompt wird in die
    User-Message gefaltet (call_gemini setzt bei cached_content kein system_instruction).
    Ohne Cache: System-Prompt separat, Quelle an den Body angehängt (Alt-Verhalten)."""
    if cache:
        return gemini_client.call_gemini(
            system_prompt, system_prompt + "\n\n" + body, model=model,
            thinking_config=thinking, response_mime_type=response_mime_type,
            response_schema=response_schema, cached_content=cache, call_name=call_name)
    return gemini_client.call_gemini(
        system_prompt, body + "\n\n" + source, model=model, thinking_config=thinking,
        response_mime_type=response_mime_type, response_schema=response_schema,
        call_name=call_name)


def _track(run_id: str | None, thema: str, stufe: int, schritt: str, model: str) -> None:
    """Best-effort Kostentracking aus gemini_client._last_usage."""
    if not (cost_tracker and run_id):
        return
    try:
        u = getattr(gemini_client, "_last_usage", {}) or {}
        if u:
            cost_tracker.track(run_id=run_id, thema=thema, stufe=f"S{stufe}",
                               schritt=schritt, modell=model, **u)
    except Exception as e:  # pragma: no cover
        log.debug("Kostentracking übersprungen: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# PASS 1 — PLAN
# ══════════════════════════════════════════════════════════════════════════════

PASS1_SYSTEM = (
    "Du planst einen kindgerechten Lexikonartikel für eine deutsche Kinder-App. "
    "Du arbeitest AUSSCHLIESSLICH mit dem gelieferten Quelltext — kein Wissen von "
    "außerhalb, nichts erfinden. Der Artikel handelt vom HAUPTTHEMA; Begleitartikel "
    "sind Fenster, die es illustrieren, kein Ersatz. Wähle nur, was die Geschichte "
    "trägt und ins Wortbudget passt. Gib NUR den Plan als JSON aus."
)

PASS1_SCHEMA = {
    "type": "object",
    "required": ["angle", "kernfakten", "abschnitte", "subtitle", "emoji"],
    "properties": {
        "angle": {"type": "string"},
        "kernfakten": {"type": "array", "items": {"type": "string"}},
        "companion_rolle": {"type": "string"},
        "abschnitte": {"type": "array", "items": {"type": "object",
            "required": ["heading"], "properties": {
                "heading": {"type": "string"},
                "inhalt": {"type": "string"}}}},
        "subtitle": {"type": "string"},
        "emoji": {"type": "string"},
    },
}


def pass1_plan(thema: str, stufe: int, wmin: int, wmax: int,
               primary_text: str, companion_texts: dict[str, str],
               valid_companions: list[str], model: str,
               run_id: str | None = None, cache: str | None = None) -> dict:
    """Pass 1: Erzählbogen + Kernfakten aus der Quelle (Thema-Primat)."""
    source = _source_block(thema, primary_text, companion_texts)
    comp_str = ", ".join(valid_companions) if valid_companions else "(keine)"
    body = (
        f"THEMA (Hauptthema, Rückgrat): {thema}\n"
        f"LESESTUFE: {_level_register(stufe)}\n"
        f"WORTZIEL für den späteren Text: {wmin}–{wmax} Wörter.\n"
        f"VERFÜGBARE BEGLEITARTIKEL: {comp_str}\n\n"
        "AUFGABE: Plane den Artikel. Gib als JSON aus:\n"
        "- angle: der Erzählbogen ums Hauptthema (ein Satz).\n"
        "- kernfakten: 3–8 wichtigste Fakten AUS DEM QUELLTEXT (wörtlich gedeckt).\n"
        "- companion_rolle: welcher Begleitartikel illustriert WAS — oder \"weglassen\".\n"
        "- abschnitte: 3–5 Abschnitte, je {heading, inhalt(kurz)}.\n"
        "- subtitle: kurzer kindgerechter Untertitel.\n"
        "- emoji: ein passendes Emoji."
    )
    thinking = _make_thinking_config(model, 8192)
    raw = _call_pass(PASS1_SYSTEM, body, source, model, thinking, cache,
                     call_name="pass1_plan", response_mime_type="application/json",
                     response_schema=PASS1_SCHEMA)
    _track(run_id, thema, stufe, "pass1_plan", model)
    plan = json.loads(raw)
    if not isinstance(plan, dict):
        raise ValueError("Pass 1: Plan ist kein JSON-Objekt")
    return plan


# ══════════════════════════════════════════════════════════════════════════════
# PASS 2 — PROSA (Markdown) + Wortziel-Schleife
# ══════════════════════════════════════════════════════════════════════════════

PASS2_SYSTEM = (
    "Du schreibst einen kindgerechten Lexikonartikel für eine deutsche Kinder-App. "
    "Schreib EINE zusammenhängende, spannende Geschichte ums Hauptthema — erzähl, "
    "zähl nicht auf, keine dichten Zahlen-Ketten. Verwende AUSSCHLIESSLICH belegte "
    "Fakten aus dem Quelltext; erfinde keine Gefühle, Motive oder Verstärker. Bei "
    "ernsten Themen nüchtern bleiben, keine beschönigenden Wörter für Leid oder "
    "Gewalt.\n\n"
    "FORMAT (streng): NUR Markdown mit `## Überschrift`-Zeilen und normalen "
    "Absätzen. KEIN JSON, keine Aufzählungszeichen, keine Boxen, keine Bilder, "
    "keine IDs. Beginne mit einer `## Überschrift`."
)


def _strip_md_fences(text: str) -> str:
    """Entfernt umschließende ```-Codefences, falls das Modell welche setzt."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return t.strip()


def _count_prose_words(markdown: str) -> int:
    """Zählt Wörter im Fließtext (ohne `##`-Überschriften) — konsistent mit
    count_article_words auf dem fertigen Artikel (Boxen im MVP leer)."""
    words = 0
    for line in markdown.splitlines():
        if line.strip().startswith("#"):
            continue
        words += len(line.split())
    return words


def pass2_prosa(plan: dict, thema: str, stufe: int, wmin: int, wmax: int,
                primary_text: str, companion_texts: dict[str, str],
                model: str, run_id: str | None = None,
                cache: str | None = None) -> tuple[str, dict]:
    """Pass 2: Plan -> Markdown-Prosa mit code-gesteuerter Wortziel-Schleife.

    Gibt (markdown, info) zurück. info: attempts, word_count, in_band, band.
    Deckelung: WORDLOOP_MAX_ATTEMPTS. Nach dem letzten Versuch die bandnächste
    Fassung nehmen (kein harter Abbruch). Kein späterer Pass trimmt (State-Monotonie).
    """
    source = _source_block(thema, primary_text, companion_texts)
    plan_json = json.dumps(plan, ensure_ascii=False, indent=2)
    base_body = (
        f"THEMA (Hauptthema): {thema}\n"
        f"LESESTUFE: {_level_register(stufe)}\n"
        f"WORTZIEL: {wmin}–{wmax} Wörter (Fließtext ohne Überschriften).\n\n"
        f"PLAN (Rückgrat des Artikels):\n{plan_json}\n\n"
        "Schreibe jetzt den Artikel als reines Markdown (## Überschriften + Absätze), "
        "streng nach Plan und Quelle."
    )
    thinking = _make_thinking_config(model, 8192)

    best_md: str | None = None
    best_dist = None
    best_wc = 0
    attempts = 0
    feedback = ""

    for attempt in range(1, WORDLOOP_MAX_ATTEMPTS + 1):
        attempts = attempt
        body = base_body + (f"\n\nRETRY_FEEDBACK: {feedback}" if feedback else "")
        raw = _call_pass(PASS2_SYSTEM, body, source, model, thinking, cache,
                         call_name=f"pass2_prosa#{attempt}",
                         response_mime_type="text/plain")
        _track(run_id, thema, stufe, "pass2_prosa", model)
        md = _strip_md_fences(raw)
        wc = _count_prose_words(md)

        if wc > wmax:
            dist = wc - wmax
        elif wc < wmin:
            dist = wmin - wc
        else:
            dist = 0

        if best_dist is None or dist < best_dist:
            best_md, best_dist, best_wc = md, dist, wc

        log.info("  Pass 2 Versuch %d/%d: %d Wörter (Ziel %d–%d, Abstand %d)",
                 attempt, WORDLOOP_MAX_ATTEMPTS, wc, wmin, wmax, dist)

        if dist == 0:
            break
        if wc > wmax:
            feedback = (f"Der Text hatte {wc} Wörter, das Ziel ist höchstens {wmax}. "
                        f"Straffe auf {wmin}–{wmax} Wörter: kürze Nebenstränge, "
                        f"keine neuen Themen, erhalte den roten Faden.")
        else:
            feedback = (f"Der Text hatte {wc} Wörter, das Ziel ist {wmin}–{wmax}. "
                        f"Vertiefe den Kernstrang mit konkreten, belegten Details aus "
                        f"der Quelle — keine neuen Themen, nichts erfinden.")

    info = {
        "attempts": attempts,
        "word_count": best_wc,
        "in_band": best_dist == 0,
        "band": f"{wmin}–{wmax}",
    }
    if best_dist != 0:
        log.warning("  Pass 2: Wortziel nach %d Versuchen verfehlt (%d Wörter, Ziel "
                    "%d–%d) — bandnächste Fassung + review_flag", attempts, best_wc,
                    wmin, wmax)
    return best_md or "", info


# ══════════════════════════════════════════════════════════════════════════════
# Deutscher Satz-Splitter (deterministisch, offset-basiert)
# ══════════════════════════════════════════════════════════════════════════════

# Abkürzungen (ohne Schluss-Punkt, lowercase). Nach diesen wird NICHT getrennt.
_ABBREV = {
    "z", "b", "d", "h", "u", "a", "s", "o", "vgl", "bzw", "ca", "etc", "usw",
    "usf", "evtl", "ggf", "inkl", "exkl", "max", "min", "mind", "sog", "geb",
    "gest", "verh", "jr", "sr", "nr", "abs", "art", "kap", "str", "tel", "dr",
    "prof", "dipl", "ing", "mio", "mrd", "tsd", "hrsg", "aufl", "jh", "jhd",
    "v", "n", "chr", "röm", "griech", "lat", "engl", "dt", "frz", "bspw", "ph",
}

_MONTHS = {
    "januar", "februar", "märz", "maerz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
}

_TERMINATORS = ".!?…"
_QUOTE_START = set("„«‚‹\"'“‘([")


def _prev_alnum_token(text: str, i: int) -> str:
    """Alnum-Lauf unmittelbar vor Position i (dem Terminator)."""
    m = i
    while m > 0 and text[m - 1].isalnum():
        m -= 1
    return text[m:i]


def _leading_alpha(text: str, k: int) -> str:
    m = k
    while m < len(text) and text[m].isalpha():
        m += 1
    return text[k:m]


def _is_boundary(text: str, i: int, j: int, k: int, n: int) -> bool:
    """Ist zwischen j (nach Terminator-Lauf) und k (nach Whitespace) eine
    echte Satzgrenze? i = Index des ersten Terminators."""
    # Absatzende ist immer Satzende.
    if k >= n:
        return True
    single_dot = (j - i == 1) and text[i] == "."
    if single_dot:
        token = _prev_alnum_token(text, i)
        low = token.lower()
        if low in _ABBREV:
            return False
        if len(token) == 1 and token.isupper():   # Initiale wie "z. B."
            return False
        if token.isdigit():                        # Ordinalzahl wie "8. Mai"
            nxt = _leading_alpha(text, k).lower()
            if nxt in _MONTHS or text[k].islower():
                return False
    # Startsignal des nächsten Satzes?
    c = text[k]
    if c.islower():
        return False
    return c.isupper() or c.isdigit() or c in _QUOTE_START


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Zerlegt text in Satz-Spans (start, end), die den Text lückenlos kacheln.
    Die trailing Whitespace bis zum nächsten Satz gehört zum jeweiligen Span."""
    n = len(text)
    spans: list[tuple[int, int]] = []
    start = 0
    i = 0
    while i < n:
        if text[i] in _TERMINATORS:
            j = i + 1
            while j < n and text[j] in _TERMINATORS:
                j += 1
            k = j
            while k < n and text[k].isspace():
                k += 1
            if _is_boundary(text, i, j, k, n):
                spans.append((start, k))
                start = k
                i = k
                continue
        i += 1
    if start < n:
        spans.append((start, n))
    return spans


def split_sentences_de(paragraph: str) -> list[str]:
    """Sätze eines Absatzes (getrimmt). Leere Spans werden verworfen."""
    out = []
    for a, b in sentence_spans(paragraph):
        s = paragraph[a:b].strip()
        if s:
            out.append(s)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Markdown -> Sections
# ══════════════════════════════════════════════════════════════════════════════

_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")


def parse_markdown(markdown: str, fallback_heading: str) -> list[dict]:
    """Zerlegt Markdown in [{heading, paragraphs:[str]}].

    Absätze sind durch Leerzeilen getrennt; ein Absatz behält seinen exakten
    Wortlaut (für die Rejoin-Invariante). Prosa vor der ersten Überschrift landet
    unter fallback_heading.
    """
    sections: list[dict] = []
    cur: dict | None = None
    para_lines: list[str] = []

    def flush_para():
        nonlocal para_lines, cur
        if para_lines:
            para = "\n".join(para_lines).strip()
            para_lines = []
            if para:
                if cur is None:
                    cur = {"heading": fallback_heading, "paragraphs": []}
                    sections.append(cur)
                cur["paragraphs"].append(para)

    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush_para()
            cur = {"heading": m.group(1).strip(), "paragraphs": []}
            sections.append(cur)
        elif line.strip() == "":
            flush_para()
        else:
            para_lines.append(line)
    flush_para()

    return [s for s in sections if s["paragraphs"]]


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class RejoinError(RuntimeError):
    """Rejoin-Invariante verletzt — der zerlegte Text weicht vom Original ab."""


def build_sections(markdown: str, fallback_heading: str) -> list[dict]:
    """Pass-6-Kern: Markdown -> Sections mit Sätzen + IDs.

    HARTE INVARIANTE (nur auf Absatz-Ebene, Überschriften ausgenommen): die aus
    einem Absatz gesplitteten Sätze müssen den Absatz ZEICHENGENAU rekonstruieren.
    Kleinste Abweichung -> RejoinError (Artikel wird verworfen, nie mutiert
    geschrieben)."""
    parsed = parse_markdown(markdown, fallback_heading)
    sections: list[dict] = []
    sent_no = 0

    for si, sec in enumerate(parsed, start=1):
        out_sentences: list[dict] = []
        for para in sec["paragraphs"]:
            spans = sentence_spans(para)
            # 1) Zeichengenaue Kachelung: Rohslices müssen den Absatz exakt ergeben.
            rebuilt = "".join(para[a:b] for a, b in spans)
            if rebuilt != para:
                raise RejoinError(
                    f"Section {si}: Rohkachelung != Absatz "
                    f"({len(rebuilt)} vs {len(para)} Zeichen)")
            sent_texts = [para[a:b].strip() for a, b in spans]
            sent_texts = [t for t in sent_texts if t]
            # 2) Unabhängige Gegenprobe: getrimmte Sätze rekonstruieren den Absatz
            #    (Whitespace-normalisiert), fängt Strip-/Join-Fehler.
            if _norm_ws(" ".join(sent_texts)) != _norm_ws(para):
                raise RejoinError(f"Section {si}: Rejoin (getrimmt) != Absatz")
            for t in sent_texts:
                sent_no += 1
                out_sentences.append({"id": f"s{sent_no:03d}", "text": t,
                                      "img_index": -1})
        sections.append({
            "id": f"sec{si}",
            "heading": sec["heading"],
            "section_role": "intro" if si == 1 else "body",
            "sentences": out_sentences,
            "boxes": [],
        })
    return sections


# ══════════════════════════════════════════════════════════════════════════════
# PASS 3 — BOX (entkoppelt, gegroundet) + deterministische Guards
# ══════════════════════════════════════════════════════════════════════════════

# Box-Budget je Stufe (Obergrenze): S1/S2 bis 2, S3 bis 3.
BOX_BUDGET_MAX = {1: 2, 2: 2, 3: 3}
_BOX_TYPES = {"wow", "fakt", "warnung", "stimmt_das"}

# Leichter Anti-Redundanz-Guard: Box nur bei STARKER Wort-Überlappung mit EINEM
# Satz verwerfen (klare Umformulierung). Schwelle bewusst hoch → echte Zusatz-Fakten
# bleiben erhalten.
_REDUNDANCY_THRESHOLD = 0.8
_MIN_CONTENT_WORDS = 4
_STOP = {
    "und", "oder", "aber", "der", "die", "das", "den", "dem", "des", "ein", "eine",
    "einer", "eines", "einem", "einen", "ist", "sind", "war", "waren", "wird",
    "werden", "wurde", "wurden", "hat", "haben", "hatte", "für", "mit", "von",
    "aus", "auf", "in", "im", "an", "am", "zu", "zum", "zur", "bei", "als", "auch",
    "nicht", "sich", "sie", "er", "es", "man", "dass", "wie", "was", "wenn", "dann",
    "noch", "nur", "sehr", "mehr", "über", "unter", "durch", "gegen", "ohne", "um",
    "vor", "nach", "diese", "dieser", "dieses", "viele", "viel", "einige", "ihre",
    "sein", "seine", "kann", "können", "einer",
}

PASS3_SYSTEM = (
    "Du ergänzt einen fertigen Kinderlexikon-Artikel um 1–2 Callout-Boxen. Du "
    "arbeitest AUSSCHLIESSLICH mit dem gelieferten Quelltext — nichts erfinden, "
    "kein Wissen von außerhalb. Du fasst den Fließtext NICHT an. Eine Box liefert "
    "einen zusätzlichen, im Artikel NOCH NICHT genannten Fakt aus der Quelle — nie "
    "eine Umformulierung von etwas, das schon im Text steht. Findest du nichts "
    "Passendes, gib eine leere Liste aus. Antworte NUR als JSON."
)

PASS3_SCHEMA = {
    "type": "object",
    "required": ["boxes"],
    "properties": {"boxes": {"type": "array", "items": {"type": "object",
        "required": ["type", "text", "heading"], "properties": {
            "type": {"type": "string", "enum": ["wow", "fakt", "warnung", "stimmt_das"]},
            "text": {"type": "string"},
            "reveal_text": {"type": "string"},
            "heading": {"type": "string"}}}}},
}


def _content_words(text: str) -> set[str]:
    toks = re.findall(r"[a-zA-ZäöüÄÖÜß]+", (text or "").lower())
    return {t for t in toks if len(t) >= 4 and t not in _STOP}


def _is_redundant(box_text: str, sentences: list[str]) -> bool:
    """Leicht: True nur bei starker Überlappung mit EINEM Satz (klare Dopplung)."""
    bw = _content_words(box_text)
    if len(bw) < _MIN_CONTENT_WORDS:
        return False  # zu kurz für ein verlässliches Urteil → behalten
    for sent in sentences:
        sw = _content_words(sent)
        if sw and len(bw & sw) / len(bw) >= _REDUNDANCY_THRESHOLD:
            return True
    return False


def pass3_boxes(sections: list[dict], thema: str, stufe: int, primary_text: str,
                companion_texts: dict[str, str], model: str,
                run_id: str | None = None, cache: str | None = None) -> tuple[list[dict], dict]:
    """Pass 3: gegroundete Callout-Boxen aus im Artikel FEHLENDEN Fakten.

    Gibt (roh_boxen, info) zurück — Verankerung/Guards macht _apply_boxes.
    """
    budget = BOX_BUDGET_MAX.get(stufe, 2)
    headings = [s["heading"] for s in sections]
    article_txt = "\n".join(
        f'## {s["heading"]}\n' + " ".join(x["text"] for x in s["sentences"])
        for s in sections)
    source = _source_block(thema, primary_text, companion_texts)
    body = (
        f"LESESTUFE: {_level_register(stufe)}\n"
        f"BOX-BUDGET: bis zu {budget} Boxen (weniger oder 0 ist ok).\n"
        f"ABSCHNITTE (heading exakt verwenden): {headings}\n\n"
        "FERTIGER ARTIKEL (Fließtext — Boxen müssen zusätzliche Fakten bringen, "
        "nichts hieraus wiederholen):\n" + article_txt + "\n\n"
        "AUFGABE: Finde im QUELLTEXT bis zu " + str(budget) + " Fakten, die im "
        "Artikel NOCH NICHT vorkommen und ein Kind dieser Stufe spannend findet. "
        "Je Box: {type (wow|fakt|warnung|stimmt_das), text, heading (aus der Liste), "
        "reveal_text (NUR bei stimmt_das: die Auflösung)}. wow = konkrete "
        "überraschende Tatsache; warnung = themenspezifischer Hinweis; stimmt_das = "
        "Frage, die NICHT abfragt, was im Artikel schon klar dasteht. Selbst-Check: "
        "Steht der Fakt schon im Artikel? → verwerfen. Nichts Passendes → boxes: []."
    )
    thinking = _make_thinking_config(model, 4096)
    try:
        raw = _call_pass(PASS3_SYSTEM, body, source, model, thinking, cache,
                         call_name="pass3_boxes", response_mime_type="application/json",
                         response_schema=PASS3_SCHEMA)
        _track(run_id, thema, stufe, "pass3_boxes", model)
        boxes = json.loads(raw).get("boxes", [])
    except Exception as e:
        log.warning("  Pass 3 Box-Pass fehlgeschlagen: %s — boxes leer", e)
        return [], {"error": str(e)}
    return boxes if isinstance(boxes, list) else [], {}


def _apply_boxes(raw_boxes: list[dict], sections: list[dict], stufe: int) -> dict:
    """Deterministische Guards + Verankerung. Mutiert sections (hängt boxes an).

    - Anker: heading-Match (normalisiert) → sonst verworfen (nie erfundener Anker).
    - stimmt_das: reveal_text+reveal_mode='auto' Pflicht; andere Typen: reveal_* raus.
    - Anti-Redundanz (leicht): starke Überlappung mit einem Satz → verworfen.
    - Budget-Cap je Stufe.
    """
    by_norm = {_norm_ws(s["heading"]).lower().rstrip(".!?"): s for s in sections}
    all_sentences = [x["text"] for s in sections for x in s["sentences"]]
    budget = BOX_BUDGET_MAX.get(stufe, 2)

    kept = 0
    dropped: list[str] = []
    for b in raw_boxes:
        if kept >= budget:
            dropped.append("budget")
            continue
        if not isinstance(b, dict):
            continue
        btype = (b.get("type") or "").strip()
        text = (b.get("text") or "").strip()
        if btype not in _BOX_TYPES or not text:
            dropped.append(f"typ/text ungültig ({btype!r})")
            continue
        sec = by_norm.get(_norm_ws(b.get("heading", "")).lower().rstrip(".!?"))
        if sec is None:
            dropped.append(f"kein Anker: {b.get('heading')!r}")
            continue
        # stimmt_das-Disziplin
        clean = {"type": btype, "text": text}
        if btype == "stimmt_das":
            rev = (b.get("reveal_text") or "").strip()
            if not rev:
                dropped.append("stimmt_das ohne reveal_text")
                continue
            clean["reveal_text"] = rev
            clean["reveal_mode"] = "auto"
            check_text = rev  # die Auflösung darf nicht schon im Artikel stehen
        else:
            check_text = text
        # Anti-Redundanz (leicht)
        if _is_redundant(check_text, all_sentences):
            dropped.append("redundant zum Fließtext")
            continue
        sec.setdefault("boxes", []).append(clean)
        kept += 1

    return {"boxes_kept": kept, "boxes_dropped": dropped}


# ══════════════════════════════════════════════════════════════════════════════
# PASS 6 — source_passages (Minimal-KI als reine Suche) + Stubs + Zusammenbau
# ══════════════════════════════════════════════════════════════════════════════

SOURCE_SEARCH_SYSTEM = (
    "Du bist ein reines Such-Werkzeug für die Quellenprüfung eines Kinderlexikons. "
    "Zu jedem Artikel-Satz suchst du im QUELLTEXT die Stelle, die DENSELBEN FAKT "
    "enthält, und gibst sie WÖRTLICH aus — Zeichen für Zeichen wie im Quelltext, "
    "nichts umschreiben, nichts kürzen, nichts erfinden. WICHTIG: Die Artikel-Sätze "
    "sind für Kinder oft stark vereinfacht oder umformuliert; entscheidend ist der "
    "belegte Fakt, NICHT gleiche Wörter. Nimm ruhig einen kurzen, passenden "
    "Quell-Satz. Nur wenn der Quelltext den Fakt WIRKLICH NICHT enthält, gib für "
    "passage einen leeren String. Antworte NUR als JSON."
)

SOURCE_SEARCH_SCHEMA = {
    "type": "object",
    "required": ["belege"],
    "properties": {"belege": {"type": "array", "items": {"type": "object",
        "required": ["satz_id", "source", "passage"], "properties": {
            "satz_id": {"type": "string"},
            "source": {"type": "string"},
            "passage": {"type": "string"}}}}},
}


def find_source_passages(sections: list[dict], thema: str, stufe: int,
                         primary_text: str, companion_texts: dict[str, str],
                         model: str, run_id: str | None = None,
                         cache: str | None = None) -> list[dict]:
    """Minimal-KI: je Satz das wörtliche Quellzitat suchen. Jedes passage wird
    per Substring gegen den echten Quelltext verifiziert (nicht gefunden ->
    verworfen). Das LLM ändert NIE Artikeltext, es sucht nur."""
    sentences = [s for sec in sections for s in sec["sentences"]]
    if not sentences:
        return []
    source = _source_block(thema, primary_text, companion_texts)
    sent_list = "\n".join(f'{s["id"]}: {s["text"]}' for s in sentences)
    body = (
        "ARTIKEL-SÄTZE (je Zeile: satz_id: Text):\n" + sent_list + "\n\n"
        "Gib für jeden Satz {satz_id, source (Titel des Quellartikels), passage "
        "(wörtliches Zitat aus dem Quelltext oder \"\")} zurück."
    )
    thinking = _make_thinking_config(model, 4096)
    try:
        raw = _call_pass(SOURCE_SEARCH_SYSTEM, body, source, model, thinking, cache,
                         call_name="pass6_belege", response_mime_type="application/json",
                         response_schema=SOURCE_SEARCH_SCHEMA)
        _track(run_id, thema, stufe, "pass6_belege", model)
        belege = json.loads(raw).get("belege", [])
    except Exception as e:
        log.warning("  Pass 6 Beleg-Suche fehlgeschlagen: %s — source_passages leer", e)
        return []

    # Verifikation: passage muss wörtlich (ws-normalisiert) im Quelltext stehen.
    haystacks = {thema: _norm_ws(primary_text)}
    for name, txt in companion_texts.items():
        haystacks[name] = _norm_ws(txt)
    all_hay = _norm_ws(_source_block(thema, primary_text, companion_texts))
    by_id = {s["id"]: s["text"] for s in sentences}

    passages: list[dict] = []
    for b in belege:
        if not isinstance(b, dict):
            continue
        passage = (b.get("passage") or "").strip()
        sid = b.get("satz_id", "")
        if len(passage) < 8 or sid not in by_id:
            continue
        np = _norm_ws(passage)
        src = b.get("source") or thema
        hay = haystacks.get(src, all_hay)
        if np in hay or np in all_hay:
            passages.append({"claim": by_id[sid], "source": src, "passage": passage})
        else:
            log.debug("  Beleg verworfen (nicht wörtlich): %s", passage[:60])
    return passages


def _quiz_stub(stufe: int) -> dict:
    """Statischer, strukturell app-valider Quiz-Stub (Pass 5 = Phase 3)."""
    from generate_articles import MIN_QUIZ_QUESTIONS
    n = MIN_QUIZ_QUESTIONS.get(str(stufe), 3)
    questions = []
    for i in range(1, n + 1):
        questions.append({
            "id": f"q{i}",
            "text": "Platzhalter — Quiz folgt in Phase 3.",
            "options": [
                {"key": "A", "text": "Platzhalter A"},
                {"key": "B", "text": "Platzhalter B"},
                {"key": "C", "text": "Platzhalter C"},
            ],
            "correct_key": "A",
        })
    return {"questions": questions}


def assemble_article(job: dict, plan: dict, sections: list[dict],
                     source_passages: list[dict], valid_companions: list[str],
                     word_count: int, stufe: int, model: str,
                     pass2_info: dict) -> dict:
    """Pass 6 Zusammenbau: Sections + Belege + Stubs -> app-valides Artikel-JSON."""
    thema = job.get("thema", job.get("title", ""))
    primaer = job.get("primaer_wikipedia", thema)
    now = datetime.now(timezone.utc).isoformat()

    review_reason = "MVP-Pipeline (new): Bild/Quiz sind Stubs (Phase 3)"
    if not pass2_info.get("in_band", True):
        review_reason += f"; Wortziel {pass2_info.get('band')} verfehlt ({word_count})"

    article = {
        "meta": {
            "id": job["article_id"],
            "title": thema,
            "subtitle": (plan.get("subtitle") or thema).strip(),
            "emoji": (plan.get("emoji") or "📖").strip() or "📖",
            "age_level": stufe,
            "pattern": job.get("pattern") or "tech_science",
            "theme_color": job.get("theme_color") or "#4A90D9",
            "word_count": word_count,
            "source_wikipedia_url":
                f"https://de.wikipedia.org/wiki/{quote(primaer.replace(' ', '_'))}",
            "schema_version": "1.0",
            "review_flag": True,
            "review_reason": review_reason,
            "category_top": job.get("category_top", ""),
            "category_sub": job.get("category_sub", ""),
            "generated_at": now,
            "grounding_companions": valid_companions,
            "generation_method": f"{model}/pipeline-new/pass1-2-3-6",
            "ergiebigkeit": ergiebigkeit_for(thema, stufe),
            "word_target": pass2_info.get("band", ""),
            "pipeline": "new",
        },
        "images": [],
        "sections": sections,
        "quiz": _quiz_stub(stufe),
        "related_terms": {"core": [], "discover": []},
        "source_passages": source_passages,
    }
    return article


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrierung: Pass 1 -> 2 -> 6
# ══════════════════════════════════════════════════════════════════════════════

def generate_article_new(job: dict, primary_text: str,
                         companion_texts: dict[str, str],
                         valid_companions: list[str],
                         model: str = BASELINE_MODEL,
                         run_id: str | None = None,
                         cache: str | None = None) -> tuple[dict | None, dict]:
    """Orchestriert die neue Pipeline für eine Stufe. Liefert (article|None, report)
    analog zu generate_one_level. None = Stufe übersprungen (Fehler/Rejoin), geflaggt
    im report — es wird nie mutierter Text geschrieben."""
    article_id = job["article_id"]
    thema = job.get("thema", job.get("title", ""))
    stufe = job["age_level"]
    wmin, wmax, _src = wortziel_for(thema, stufe)

    report: dict = {"article_id": article_id, "thema": thema, "stufe": stufe,
                    "pipeline": "new", "wmin": wmin, "wmax": wmax, "errors": []}
    log.info("  [new] %s: Pass 1→2→6 (Modell %s, Ziel %d–%d)",
             article_id, model, wmin, wmax)

    try:
        plan = pass1_plan(thema, stufe, wmin, wmax, primary_text, companion_texts,
                          valid_companions, model, run_id=run_id, cache=cache)
        report["plan_abschnitte"] = [a.get("heading") for a in plan.get("abschnitte", [])]

        markdown, p2info = pass2_prosa(plan, thema, stufe, wmin, wmax, primary_text,
                                       companion_texts, model, run_id=run_id, cache=cache)
        report["pass2"] = p2info
        if not markdown.strip():
            raise ValueError("Pass 2 lieferte leeren Text")

        fallback_heading = (plan.get("subtitle") or thema).strip() or thema
        sections = build_sections(markdown, fallback_heading)     # kann RejoinError werfen

        # Pass 3: gegroundete Boxen (fasst die Prosa nicht an, hängt nur an).
        raw_boxes, box_gen_info = pass3_boxes(
            sections, thema, stufe, primary_text, companion_texts, model,
            run_id=run_id, cache=cache)
        box_info = _apply_boxes(raw_boxes, sections, stufe)
        report["pass3"] = {**box_gen_info, **box_info}

        source_passages = find_source_passages(
            sections, thema, stufe, primary_text, companion_texts, model,
            run_id=run_id, cache=cache)
        report["n_source_passages"] = len(source_passages)

        # Wortzahl inkl. Boxen (wie im alten Pfad: count_article_words zählt Boxen mit).
        wc = count_article_words({"sections": sections})
        article = assemble_article(job, plan, sections, source_passages,
                                   valid_companions, wc, stufe, model, p2info)

        # Box-Verteilungs-Guard (deterministisch, aus dem alten Pfad wiederverwendet).
        try:
            from generate_grounded import _box_lint
            box_issue = _box_lint(article)
        except Exception:
            box_issue = None
        if box_issue:
            log.warning("  [new] %s: %s → review_flag", article_id, box_issue)
            article["meta"]["review_reason"] = (
                article["meta"].get("review_reason", "") + "; " + box_issue).lstrip("; ")

        report["word_count"] = wc
        report["n_sections"] = len(sections)
        report["n_sentences"] = sum(len(s["sentences"]) for s in sections)
        report["n_boxes"] = sum(len(s.get("boxes", [])) for s in sections)
        return article, report

    except RejoinError as e:
        log.error("  [new] %s: REJOIN-INVARIANTE VERLETZT — Stufe verworfen: %s",
                  article_id, e)
        report["errors"].append(f"Rejoin-Invariante: {e}")
        return None, report
    except Exception as e:
        log.error("  [new] %s: Fehler — Stufe übersprungen: %s", article_id, e)
        report["errors"].append(str(e))
        return None, report
