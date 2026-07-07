#!/usr/bin/env python3
"""lektorat_new.py — Neuarchitektur Lektorat (Phase 4).

Zwei fokussierte, gegroundete Pässe, feste Reihenfolge A→B:
  Pass A — FAKTEN-ABGLEICH (entschlackt): je Satz Faktentreue gegen die Quelle,
           meldet nur Widerspruch/ungedeckten Zusatz. KEIN Stil.
  Pass B — STIL/TON/GRAMMATIK mit PFLICHT-RE-GROUNDING: verbessert nur Sprache;
           jeder geänderte Satz muss durch ein wörtliches Quellzitat gedeckt sein,
           das der Code gegen die Quelle verifiziert — sonst wird die Änderung
           verworfen.

Grounding-Regel (eisern): geprüft wird gegen den Quelltext-SNAPSHOT der
Generierungszeit (Phase-1-Sourcing), nie gegen ein nachgeladenes Exemplar.
Modell: Anthropic Sonnet (claude-sonnet-4-6), temperature=0 (reproduzierbar).
Prompt-Caching über cached_prefix (Quellblock) — Pass B trifft den A-Cache.

Kein Rückgriff auf die alte Monolith-Logik (lektorat_common). Das Ausgabeformat
`article['pruefbericht']` ist bewusst review-kompatibel (review_tool.py / Docx).
"""
from __future__ import annotations

import logging
import re

import claude_client
import stage_models
from generate_grounded import count_article_words, COMPANION_CHAR_CAP

log = logging.getLogger("lektorat_new")

LEKTORAT_MODEL = stage_models.get_stage_config("lektorat")["model"]  # claude-sonnet-4-6
# COMPANION_CHAR_CAP (kanonisch = 30_000) importiert — MUSS mit pipeline_new._source_block
# übereinstimmen, sonst prüft das Lektorat gegen einen anderen Snapshot als die Generierung.


# ══════════════════════════════════════════════════════════════════════════════
# Quellblock + Rendering + Grounding-Verifikation
# ══════════════════════════════════════════════════════════════════════════════

def build_sources_block(primary_title: str, primary_text: str,
                        companion_texts: dict[str, str]) -> str:
    parts = [f"### Quelle: {primary_title}\n{primary_text}"]
    for title, text in companion_texts.items():
        if text:
            parts.append(f"### Quelle: {title}\n{text[:COMPANION_CHAR_CAP]}")
    return "DEKLARIERTE QUELLEN (Snapshot der Generierungszeit):\n" + "\n\n".join(parts)


def _render_sentences(article: dict) -> str:
    """Nummerierte Sätze je Abschnitt (satz_id: Text) für den Prüf-Prompt."""
    lines = []
    for sec in article.get("sections", []):
        lines.append(f'## {sec.get("heading", "")}')
        for s in sec.get("sentences", []):
            lines.append(f'{s["id"]}: {s["text"]}')
    return "\n".join(lines)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _beleg_in_source(beleg: str, source_norm: str) -> bool:
    # >=5, damit auch kurze, spezifische Belege greifen ("30 km", "79 n"); kürzer
    # wäre zu unspezifisch (Substring-Rauschen).
    b = _norm(beleg)
    return len(b) >= 5 and b in source_norm


def _sentence_index(article: dict) -> dict[str, dict]:
    return {s["id"]: s for sec in article.get("sections", []) for s in sec.get("sentences", [])}


# ══════════════════════════════════════════════════════════════════════════════
# PASS A — FAKTEN-ABGLEICH
# ══════════════════════════════════════════════════════════════════════════════

LEKTORAT_A_SYSTEM = (
    "Du bist Faktenprüfer für ein deutsches Kinderlexikon. Du erhältst den QUELLTEXT "
    "und einen fertigen Artikel als nummerierte Sätze (satz_id: Text). Prüfe JEDEN "
    "Satz AUSSCHLIESSLICH auf Faktentreue gegen die Quelle — NICHT auf Stil, Ton oder "
    "Grammatik. Melde nur zwei Fälle:\n"
    "1. Widerspruch zur Quelle (der Satz sagt etwas, das die Quelle anders sagt).\n"
    "2. Ungedeckter Zusatz (ein Detail/Attribut, das die Quelle NICHT hergibt).\n"
    "Unvollständigkeit ist KEIN Fehler — eine quellentreue Verkürzung bleibt "
    "unangetastet. STILMITTEL SIND KEIN FEHLER: direkte Ansprache, kleine Fragen, "
    "Vorlese-Rahmung (z. B. 'Stell dir vor') und bildhafte Verständnis-Vergleiche "
    "('flüssig wie eine Suppe') sind erlaubt und KEIN ungedeckter Zusatz, solange sie "
    "keinen neuen FAKT behaupten — nicht melden, nicht entfernen. "
    "Für jede Meldung gib den minimal korrigierten Satz (quellenbasiert, "
    "gleiches kindgerechtes Register, kleinster Eingriff) und ein WÖRTLICHES Quellzitat "
    "(beleg) an. stufe=SILENT für kleine, klar belegbare Korrekturen; stufe=KORRIGIERT "
    "für größere, aber klare. Nicht eindeutig auflösbar → pruefen (nicht corrections). "
    "Ist alles gedeckt: leere Listen. Erfinde nichts."
)

LEKTORAT_A_SCHEMA = {
    "type": "object",
    "required": ["corrections", "pruefen"],
    "properties": {
        "corrections": {"type": "array", "items": {"type": "object",
            "required": ["satz_id", "korrektur_neu", "stufe", "beleg"], "properties": {
                "satz_id": {"type": "string"},
                "korrektur_neu": {"type": "string"},
                "stufe": {"type": "string", "enum": ["SILENT", "KORRIGIERT"]},
                "beleg": {"type": "string"}}}},
        "pruefen": {"type": "array", "items": {"type": "object",
            "required": ["satz_id", "korrektur_vorschlag", "problem", "begruendung"],
            "properties": {
                "satz_id": {"type": "string"},
                "korrektur_vorschlag": {"type": "string"},
                "problem": {"type": "string"},
                "begruendung": {"type": "string"}}}},
    },
}


def pass_a_fakten(article: dict, sources_block: str, stufe: int,
                  model: str) -> dict:
    user = (
        f"LESESTUFE: {stufe} (Register beim Korrigieren wahren).\n\n"
        "ARTIKEL (nummerierte Sätze):\n" + _render_sentences(article) + "\n\n"
        "Gib corrections (Faktenkorrekturen mit satz_id, korrektur_neu, stufe, beleg) "
        "und pruefen (nicht eindeutige Fälle) aus."
    )
    return claude_client.call_claude_json(
        LEKTORAT_A_SYSTEM, user, LEKTORAT_A_SCHEMA, model=model,
        max_tokens=8192, thinking_budget=0, temperature=0,
        cached_prefix=sources_block, call_name="lektorat_a")


# ══════════════════════════════════════════════════════════════════════════════
# PASS B — STIL/TON/GRAMMATIK (mit Pflicht-Re-Grounding)
# ══════════════════════════════════════════════════════════════════════════════

LEKTORAT_B_SYSTEM = (
    "Du bist Stil-Lektor für ein deutsches Kinderlexikon. Du erhältst den QUELLTEXT "
    "und einen bereits faktengeprüften Artikel (nummerierte Sätze). Verbessere "
    "AUSSCHLIESSLICH die Sprache: Register für die Lesestufe, Grammatik, Lesefluss, "
    "kindgerechte Klarheit. Führe KEINE neuen Fakten ein und entferne keine belegten "
    "Fakten. ERHALTE die kindgerechten Stilmittel (direkte Ansprache, kleine Fragen, "
    "Vorlese-Rahmung, bildhafte Vergleiche) — flache sie NICHT zu nüchternem "
    "Lexikonton ab; sie sind gewollt. Minimaler Eingriff — ändere nur Sätze, die "
    "sprachlich wirklich besser werden. PFLICHT: Für JEDEN geänderten Satz gib ein "
    "WÖRTLICHES Quellzitat (beleg), "
    "das der geänderte Satz weiterhin einhält. Kannst du einen Satz nicht ohne neuen, "
    "unbelegten Inhalt verbessern, lass ihn unverändert. Antworte NUR mit den "
    "geänderten Sätzen."
)

LEKTORAT_B_SCHEMA = {
    "type": "object",
    "required": ["corrections"],
    "properties": {"corrections": {"type": "array", "items": {"type": "object",
        "required": ["satz_id", "korrektur_neu", "beleg"], "properties": {
            "satz_id": {"type": "string"},
            "korrektur_neu": {"type": "string"},
            "beleg": {"type": "string"}}}}},
}


def pass_b_stil(article: dict, sources_block: str, stufe: int, model: str) -> dict:
    user = (
        f"LESESTUFE: {stufe} (Register maßgeblich).\n\n"
        "ARTIKEL (nummerierte Sätze):\n" + _render_sentences(article) + "\n\n"
        "Gib nur die sprachlich verbesserten Sätze (satz_id, korrektur_neu, beleg)."
    )
    return claude_client.call_claude_json(
        LEKTORAT_B_SYSTEM, user, LEKTORAT_B_SCHEMA, model=model,
        max_tokens=8192, thinking_budget=0, temperature=0,
        cached_prefix=sources_block, call_name="lektorat_b")


# ══════════════════════════════════════════════════════════════════════════════
# Anwenden + review-kompatibler pruefbericht
# ══════════════════════════════════════════════════════════════════════════════

def _apply_corrections(article: dict, corrections: list[dict], source_norm: str,
                       phase: str) -> list[dict]:
    """Wendet Korrekturen deterministisch an (Satz-Ersatz per satz_id).

    Re-Grounding (beide Pässe gleich): der Beleg muss wörtlich in der Quelle stehen,
    sonst wird die Änderung NICHT angewandt und als offener Vorschlag geflaggt — eine
    Faktenkorrektur ohne verifizierbaren Beleg wird also bewusst nicht automatisch
    geschrieben, sondern dem Review überlassen. Gibt Findings (review-kompatibel) zurück."""
    sidx = _sentence_index(article)
    findings: list[dict] = []
    for c in corrections or []:
        if not isinstance(c, dict):
            continue
        sid = c.get("satz_id", "")
        neu = (c.get("korrektur_neu") or "").strip()
        beleg = (c.get("beleg") or "").strip()
        stufe = c.get("stufe", "KORRIGIERT")
        sent = sidx.get(sid)
        if sent is None or not neu:
            continue
        alt = sent["text"]
        if _norm(neu) == _norm(alt):
            continue  # keine echte Änderung
        beleg_ok = _beleg_in_source(beleg, source_norm)
        if not beleg_ok:
            # Re-Grounding verletzt → nicht anwenden, als Vorschlag flaggen.
            findings.append({
                "claim_original": alt, "verdikt": "PRÜFEN", "tier": "VORSCHLAG",
                "beleg_oder_begruendung":
                    f"[{phase}] Beleg nicht wörtlich in der Quelle — nicht angewandt",
                "korrektur_neu": neu, "beleg_fuer_korrektur": beleg,
                "status": "vorschlag_offen"})
            continue
        # anwenden
        sent["text"] = neu
        findings.append({
            "claim_original": alt, "verdikt": "KORRIGIERT",
            "tier": stufe if phase == "A" else "SILENT",
            "beleg_oder_begruendung": beleg,
            "korrektur_neu": neu, "beleg_fuer_korrektur": beleg,
            "status": "auto_angewandt", "phase": phase})
    return findings


def _pruefen_findings(pruefen: list[dict], article: dict) -> list[dict]:
    sidx = _sentence_index(article)
    out = []
    for p in pruefen or []:
        if not isinstance(p, dict):
            continue
        sent = sidx.get(p.get("satz_id", ""))
        out.append({
            "claim_original": sent["text"] if sent else p.get("satz_id", ""),
            "verdikt": "PRÜFEN", "tier": "VORSCHLAG",
            "beleg_oder_begruendung": (p.get("problem", "") + " — "
                                       + p.get("begruendung", "")).strip(" —"),
            "korrektur_neu": p.get("korrektur_vorschlag", ""),
            "beleg_fuer_korrektur": "", "status": "vorschlag_offen"})
    return out


def _build_pruefbericht(findings: list[dict]) -> dict:
    summary = {
        "auto_angewandt": sum(1 for f in findings if f["status"] == "auto_angewandt"),
        "vorschlag_offen": sum(1 for f in findings if f["status"] == "vorschlag_offen"),
        "eskaliert": 0,
    }
    return {"findings": findings, "summary": summary, "lektorat": "new/A+B"}


def run_lektorat_new(article: dict, primary_title: str, primary_text: str,
                     companion_texts: dict[str, str], stufe: int,
                     model: str | None = None) -> tuple[dict, dict]:
    """Führt Pass A (Fakten) dann Pass B (Stil, re-grounded) aus, schreibt einen
    review-kompatiblen pruefbericht ins Artikel-JSON und wendet Korrekturen an.
    Gibt (article, stats) zurück."""
    model = model or LEKTORAT_MODEL
    sources_block = build_sources_block(primary_title, primary_text, companion_texts)
    source_norm = _norm(sources_block)
    findings: list[dict] = []
    stats = {"a_applied": 0, "a_pruefen": 0, "b_applied": 0, "b_rejected": 0, "errors": []}

    # ── Pass A: Fakten ────────────────────────────────────────────────────────
    try:
        res_a = pass_a_fakten(article, sources_block, stufe, model)
        fa = _apply_corrections(article, res_a.get("corrections", []), source_norm,
                                phase="A")
        fp = _pruefen_findings(res_a.get("pruefen", []), article)
        findings.extend(fa)
        findings.extend(fp)
        stats["a_applied"] = sum(1 for f in fa if f["status"] == "auto_angewandt")
        stats["a_pruefen"] = len(fp) + sum(1 for f in fa if f["status"] == "vorschlag_offen")
        log.info("  [lektorat-new] Pass A: %d angewandt, %d Vorschlag/PRÜFEN",
                 stats["a_applied"], stats["a_pruefen"])
    except Exception as e:
        log.error("  [lektorat-new] Pass A fehlgeschlagen: %s", e)
        stats["errors"].append(f"Pass A: {e}")

    # ── Pass B: Stil (mit Pflicht-Re-Grounding) ───────────────────────────────
    try:
        res_b = pass_b_stil(article, sources_block, stufe, model)
        fb = _apply_corrections(article, res_b.get("corrections", []), source_norm,
                                phase="B")
        findings.extend(fb)
        stats["b_applied"] = sum(1 for f in fb if f["status"] == "auto_angewandt")
        stats["b_rejected"] = sum(1 for f in fb if f["status"] == "vorschlag_offen")
        log.info("  [lektorat-new] Pass B: %d angewandt, %d verworfen (Re-Grounding)",
                 stats["b_applied"], stats["b_rejected"])
    except Exception as e:
        log.error("  [lektorat-new] Pass B fehlgeschlagen: %s", e)
        stats["errors"].append(f"Pass B: {e}")

    # Wortzahl nach Korrekturen aktualisieren
    article.setdefault("meta", {})["word_count"] = count_article_words(article)
    article["pruefbericht"] = _build_pruefbericht(findings)
    article["meta"]["lektorat"] = "new/A+B"
    return article, stats
