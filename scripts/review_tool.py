#!/usr/bin/env python3
"""
review_tool.py — Baustein 2: lokaler Lektorat-Review-Server (stdlib only).

Andreas startet:
    python scripts/review_tool.py articles/verify_20260623b
Dann im Browser http://localhost:8080 öffnen, reviewen, "Review speichern".

Datenfluss
----------
Input  (beim Start / bei jedem GET frisch von Platte):
  RUN_DIR/articles/<id>.json            — Artikel
  RUN_DIR/lektorat/lektorat_<id>.json   — Lektorat (pruefbericht.findings[])

Output (bei POST /submit):
  - Artikel-JSON in-place (nur bei Annehmen/Revert mit Treffer), atomarer Write
  - Lektorat-JSON: findings[i]["review_decision"] + ["reviewed_at"] gesetzt, atomar

Bewusst KEIN _apply_auto_correction (Jaccard) — der Artikel kann schon verändert
sein. Stattdessen direkte String-Suche (exakt, dann Teilstring) in
sections[].sentences[].text sowie boxes[].text / boxes[].reveal_text.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


def _strip_box_prefix(s):
    """Entfernt BOX[type]: Präfix aus Lektorat-Claims.

    Lektorat-Findings tragen im claim_original/korrektur_* oft ein
    'BOX[fakt]: '-Präfix, das im Artikel-Body (boxes[].text) nicht vorkommt.
    Ohne Strip findet _replace_in_article den Zielsatz nicht (einbau_fehlgeschlagen).
    """
    if s is None:
        return s
    return re.sub(r'^BOX\[[^\]]*\]:\s*', '', s)


# ── Pfade (werden in main() gesetzt) ─────────────────────────────────────────
RUN_DIR:  Path
ART_DIR:  Path
LEKT_DIR: Path


# ── CSS (kopiert aus render_review_html.py + Formular-Ergänzungen) ────────────
CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 16px; line-height: 1.6; color: #1a1a1a;
  background: #f4f4f0; padding: 32px 16px 120px;
}
.article-wrapper {
  max-width: 760px; margin: 0 auto 40px; background: white;
  border-radius: 4px; box-shadow: 0 2px 12px rgba(0,0,0,.1);
  padding: 36px 44px 32px;
}
.page-head {
  max-width: 760px; margin: 0 auto 28px; background: #263238; color: #fff;
  border-radius: 4px; padding: 22px 28px;
}
.page-head h1 { font-size: 1.5rem; margin-bottom: 8px; }
.page-head .summary { font-family: sans-serif; font-size: 0.85rem; color: #cfd8dc; }
.article-header { margin-bottom: 22px; border-bottom: 2px solid #e0e0e0; padding-bottom: 14px; }
.article-emoji { font-size: 2.2rem; }
.article-title { font-size: 1.7rem; font-weight: 700; margin-top: 4px; }
.chip {
  display: inline-block; padding: 3px 12px; border-radius: 20px; margin-top: 10px;
  font-family: sans-serif; font-size: 0.78rem; font-weight: 600;
  background: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7;
}
.warn-missing {
  max-width: 760px; margin: 0 auto 20px; padding: 14px 20px;
  background: #FFEBEE; border-left: 4px solid #B71C1C; border-radius: 0 4px 4px 0;
  font-family: sans-serif; font-size: 0.85rem; color: #7f1414;
}
.sec-label {
  font-family: sans-serif; font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: #555; margin: 22px 0 10px;
}
.card { margin-bottom: 14px; padding: 14px 18px; border-left: 4px solid; border-radius: 0 4px 4px 0; }
.card.pruefen   { background: #fff3cd; border-left-color: #E65100; }
.card.korrigiert{ background: #e8f5e9; border-left-color: #2E7D32; }
.card-verdikt {
  font-family: sans-serif; font-size: 0.74rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px;
}
.card.pruefen .card-verdikt   { color: #E65100; }
.card.korrigiert .card-verdikt{ color: #2E7D32; }
.lbl {
  font-family: sans-serif; font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .04em; color: #888; margin: 8px 0 3px;
}
.orig { font-style: italic; color: #777; text-decoration: line-through; }
.vorschlag { font-style: italic; color: #1B5E20; font-weight: 600; background:#d7f0d9;
  padding:3px 6px; border-radius:3px; display:inline-block; }
.vorschlag-alt { font-style: italic; color: #0D47A1; font-weight: 600; background:#d6e4fb;
  padding:3px 6px; border-radius:3px; display:inline-block; }
.korr { font-style: italic; color: #1B5E20; font-weight: 600; }
.problem { color: #5d4037; font-size: 0.9rem; margin-top: 4px; }
.begruendung { color: #6d4c41; font-size: 0.85rem; margin-top: 3px; font-style: italic; }
.beleg { color: #555; font-size: 0.8rem; margin-top: 6px; }
.choices { margin-top: 10px; font-family: sans-serif; font-size: 0.9rem; }
.choices label { display: block; padding: 4px 0; cursor: pointer; }
.choices input { margin-right: 8px; }
details.silent { margin-top: 18px; }
details.silent summary {
  font-family: sans-serif; font-size: 0.8rem; font-weight: 700; color: #666; cursor: pointer;
}
.silent-line { font-size: 0.85rem; color: #555; padding: 4px 0; border-bottom: 1px dotted #ddd; }
.silent-line .o { text-decoration: line-through; color: #999; }
.silent-line .n { color: #1B5E20; }
.decided { font-family: sans-serif; font-size: 0.72rem; font-weight: 700; color: #00695C;
  margin-left: 8px; }
.toolbar {
  position: fixed; bottom: 0; left: 0; right: 0; background: #263238;
  padding: 14px 16px; text-align: center; box-shadow: 0 -2px 12px rgba(0,0,0,.2);
}
.toolbar button, .btn {
  font-family: sans-serif; font-size: 0.95rem; font-weight: 700; cursor: pointer;
  border: none; border-radius: 4px; padding: 12px 24px; margin: 0 6px;
}
.btn-primary { background: #2E7D32; color: white; }
.btn-ghost { background: #455A64; color: #fff; font-size: 0.82rem; padding: 10px 16px; }
.result-box { max-width: 760px; margin: 40px auto; background: white; border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0,0,0,.1); padding: 36px 44px; }
.result-box h1 { font-size: 1.6rem; margin-bottom: 16px; }
.result-box li { margin-left: 22px; margin-bottom: 4px; }
.result-box a { color: #1565C0; }
"""

JS = """
function setAllPruefen(val){
  document.querySelectorAll('input[type=radio][value=\\"'+val+'\\"]').forEach(function(r){
    r.checked = true;
  });
}
"""


# ── Helfer ───────────────────────────────────────────────────────────────────
def e(text) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _vorschlag_of(f: dict) -> str:
    """PRÜFEN-Vorschlag: bevorzugt korrektur_vorschlag, sonst korrektur_neu."""
    return (f.get("korrektur_vorschlag") or f.get("korrektur_neu") or "").strip()


def _alt_of(f: dict) -> str:
    return (f.get("korrektur_alt") or "").strip()


def _replace_in_article(article: dict, needle: str, replacement: str) -> bool:
    """Ersetzt needle durch replacement im Artikel (exakt, dann Teilstring).

    Durchsucht sections[].sentences[].text, boxes[].text, boxes[].reveal_text,
    boxes[].sentences[].text. Gibt True bei erstem Ersatz zurück.
    """
    needle = (needle or "").strip()
    if not needle or not replacement:
        return False

    # Pass 1: exakte Gleichheit (ganzer Satz / ganzes Feld)
    for sec in article.get("sections", []):
        for sent in sec.get("sentences", []):
            if (sent.get("text") or "").strip() == needle:
                sent["text"] = replacement
                return True
        for box in sec.get("boxes", []):
            if (box.get("text") or "").strip() == needle:
                box["text"] = replacement
                return True
            if (box.get("reveal_text") or "").strip() == needle:
                box["reveal_text"] = replacement
                return True
            for bs in box.get("sentences", []) or []:
                if isinstance(bs, dict) and (bs.get("text") or "").strip() == needle:
                    bs["text"] = replacement
                    return True

    # Pass 2: Teilstring-Treffer (needle als Teil eines Feldes)
    for sec in article.get("sections", []):
        for sent in sec.get("sentences", []):
            t = sent.get("text") or ""
            if needle in t:
                sent["text"] = t.replace(needle, replacement, 1)
                return True
        for box in sec.get("boxes", []):
            t = box.get("text") or ""
            if needle in t:
                box["text"] = t.replace(needle, replacement, 1)
                return True
            r = box.get("reveal_text") or ""
            if needle in r:
                box["reveal_text"] = r.replace(needle, replacement, 1)
                return True
            for bs in box.get("sentences", []) or []:
                if isinstance(bs, dict):
                    bt = bs.get("text") or ""
                    if needle in bt:
                        bs["text"] = bt.replace(needle, replacement, 1)
                        return True
    return False


# ── Laden ─────────────────────────────────────────────────────────────────────
def _load_pairs() -> list[dict]:
    """Liefert sortierte Liste von {id, article, article_path, lektorat, lektorat_path}.

    article kann None sein (fehlt) → in der HTML als Warnung angezeigt.
    """
    pairs = []
    for lpath in sorted(LEKT_DIR.glob("lektorat_*.json")):
        aid = lpath.name[len("lektorat_"):-len(".json")]
        try:
            lekt = json.loads(lpath.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: Lektorat unlesbar {lpath.name}: {exc}")
            continue
        # Option A: Edit-Ziel ist der Lektorat-Body selbst (sections/boxes mit
        # KORRIGIERT+SILENT bereits eingebaut) UND pruefbericht in EINER Datei.
        # articles/<id>.json (Pre-Lektorat-Quelle) wird weder gelesen noch geschrieben.
        pairs.append({
            "id": aid, "article": lekt, "article_path": lpath,
            "lektorat": lekt, "lektorat_path": lpath,
        })
    pairs.sort(key=lambda p: (
        (p["article"] or {}).get("meta", {}).get("title", p["id"]).lower(),
        (p["article"] or {}).get("meta", {}).get("age_level", 0),
    ))
    return pairs


# ── HTML rendern ──────────────────────────────────────────────────────────────
def _radio(name: str, value: str, label_html: str, checked: bool) -> str:
    ck = " checked" if checked else ""
    return (f'<label><input type="radio" name="{e(name)}" value="{e(value)}"{ck}>'
            f'{label_html}</label>')


def _render_pruefen_card(aid: str, idx: int, f: dict) -> str:
    name      = f"finding_{aid}_{idx}"
    claim     = f.get("claim_original", "")
    problem   = f.get("problem", "")
    begr      = f.get("begruendung", "")
    beleg     = f.get("beleg", "")
    vor       = _vorschlag_of(f)
    alt       = _alt_of(f)
    decision  = f.get("review_decision")
    variant   = f.get("review_variant")  # "vorschlag" | "alt" (additiv gespeichert)

    # Default konservativ: ablehnen. Vorherige Entscheidung vorauswählen (idempotent).
    sel_vor = decision == "angenommen" and variant != "alt"
    sel_alt = decision == "angenommen" and variant == "alt"
    sel_abl = decision in (None, "offen", "abgelehnt", "einbau_fehlgeschlagen")
    if decision == "angenommen":
        sel_abl = False

    decided_badge = ""
    if decision and decision != "offen":
        decided_badge = f'<span class="decided">[zuletzt: {e(decision)}]</span>'

    parts = [f'<div class="card pruefen">',
             f'<div class="card-verdikt">⚠ PRÜFEN{decided_badge}</div>',
             f'<div class="lbl">Original</div><div class="orig">{e(claim)}</div>']
    if problem:
        parts.append(f'<div class="problem">Problem: {e(problem)}</div>')
    if begr:
        parts.append(f'<div class="begruendung">Begründung: {e(begr)}</div>')
    if vor:
        parts.append(f'<div class="lbl">Vorschlag</div>'
                     f'<div class="vorschlag">{e(vor)}</div>')
    if alt:
        parts.append(f'<div class="lbl">Alternativ-Vorschlag</div>'
                     f'<div class="vorschlag-alt">{e(alt)}</div>')
    if beleg:
        parts.append(f'<div class="beleg">Beleg: {e(beleg)}</div>')

    parts.append('<div class="choices">')
    if vor:
        parts.append(_radio(name, "annehmen_vorschlag",
                            " Vorschlag annehmen", sel_vor))
    if alt:
        parts.append(_radio(name, "annehmen_alt",
                            " Alt-Vorschlag annehmen", sel_alt))
    parts.append(_radio(name, "ablehnen",
                        " Ablehnen — Original behalten", sel_abl))
    parts.append('</div></div>')
    return "".join(parts)


def _render_korrigiert_card(aid: str, idx: int, f: dict) -> str:
    name     = f"revert_{aid}_{idx}"
    claim    = f.get("claim_original", "")
    kor      = f.get("korrektur_neu", "")
    beleg    = f.get("beleg", "")
    decision = f.get("review_decision")
    checked  = decision == "revertiert"

    badge = ""
    if decision and decision != "offen":
        badge = f'<span class="decided">[zuletzt: {e(decision)}]</span>'

    ck = " checked" if checked else ""
    seen = f'<input type="hidden" name="seen_korr_{e(aid)}_{idx}" value="1">'
    return (
        f'<div class="card korrigiert">'
        f'{seen}'
        f'<div class="card-verdikt">✓ AUTO-KORRIGIERT{badge}</div>'
        f'<div class="lbl">Original</div><div class="orig">{e(claim)}</div>'
        f'<div class="lbl">Korrektur (eingebaut)</div><div class="korr">{e(kor)}</div>'
        + (f'<div class="beleg">Beleg: {e(beleg)}</div>' if beleg else "")
        + f'<div class="choices"><label>'
          f'<input type="checkbox" name="{e(name)}" value="1"{ck}>'
          f' Rückgängig machen (Original wiederherstellen)</label></div>'
        + '</div>'
    )


def _render_article_block(pair: dict) -> str:
    aid  = pair["id"]
    art  = pair["article"]
    lekt = pair["lektorat"]
    findings = (lekt.get("pruefbericht", {}) or {}).get("findings", []) or []

    if art is None:
        return (f'<div class="warn-missing">⚠ Artikel-JSON fehlt für '
                f'<b>{e(aid)}</b> (erwartet: articles/{e(aid)}.json) — übersprungen. '
                f'Lektorat hat {len(findings)} Findings.</div>')

    meta  = art.get("meta", {})
    title = meta.get("title", aid)
    emoji = meta.get("emoji", "")
    age   = meta.get("age_level", "?")

    pruefen     = [(i, f) for i, f in enumerate(findings) if f.get("verdikt") == "PRÜFEN"]
    korrigiert  = [(i, f) for i, f in enumerate(findings) if f.get("verdikt") == "KORRIGIERT"]
    silent      = [(i, f) for i, f in enumerate(findings) if f.get("verdikt") == "SILENT"]
    fehl        = [(i, f) for i, f in enumerate(findings)
                   if f.get("verdikt") == "EINBAU_FEHLGESCHLAGEN"]

    parts = [f'<div class="article-wrapper" id="art-{e(aid)}">',
             f'<div class="article-header">'
             f'<div class="article-emoji">{e(emoji)}</div>'
             f'<div class="article-title">{e(title)}</div>'
             f'<span class="chip">Stufe {e(age)} · {e(aid)}</span></div>']

    if pruefen:
        parts.append('<div class="sec-label">PRÜFEN — Entscheidung nötig</div>')
        for i, f in pruefen:
            parts.append(_render_pruefen_card(aid, i, f))

    if korrigiert:
        parts.append('<div class="sec-label">Auto-Korrigiert — bei Bedarf zurücknehmen</div>')
        for i, f in korrigiert:
            parts.append(_render_korrigiert_card(aid, i, f))

    if fehl:
        parts.append('<div class="sec-label">Einbau fehlgeschlagen (nur Info)</div>')
        for i, f in fehl:
            parts.append(
                f'<div class="card pruefen"><div class="card-verdikt">⚠ EINBAU FEHLGESCHLAGEN</div>'
                f'<div class="orig">{e(f.get("claim_original",""))}</div>'
                + (f'<div class="vorschlag">{e(f.get("korrektur_neu",""))}</div>'
                   if f.get("korrektur_neu") else "")
                + '</div>'
            )

    if silent:
        lines = "".join(
            f'<input type="hidden" name="seen_silent_{e(aid)}_{i}" value="1">'
            f'<div class="silent-line"><span class="o">{e(f.get("claim_original",""))}</span>'
            f' → <span class="n">{e(f.get("korrektur_neu",""))}</span></div>'
            for i, f in silent
        )
        parts.append(
            f'<details class="silent"><summary>SILENT ({len(silent)}) — '
            f'automatisch eingebaut, kein Eingriff</summary>{lines}</details>'
        )

    if not findings:
        parts.append('<div class="silent-line">Keine Findings — nichts zu reviewen.</div>')

    parts.append('</div>')
    return "".join(parts)


def render_review_page() -> str:
    pairs = _load_pairs()
    n_art    = sum(1 for p in pairs if p["article"] is not None)
    n_pruef_offen = 0
    n_korr   = 0
    for p in pairs:
        for f in (p["lektorat"].get("pruefbericht", {}) or {}).get("findings", []) or []:
            v = f.get("verdikt")
            if v == "PRÜFEN" and f.get("review_decision") in (None, "offen"):
                n_pruef_offen += 1
            elif v == "KORRIGIERT":
                n_korr += 1

    blocks = "".join(_render_article_block(p) for p in pairs)
    summary = (f"{n_art} Artikel · {n_pruef_offen} PRÜFEN offen · "
               f"{n_korr} KORRIGIERT auto-applied")

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wissensfreund Review — {e(RUN_DIR.name)}</title>
<style>{CSS}</style></head>
<body>
<div class="page-head">
  <h1>Wissensfreund Review — {e(RUN_DIR.name)}</h1>
  <div class="summary">{e(summary)}</div>
  <div class="summary">Lektorat-JSONs werden in-place überschrieben (Pre-Lektorat-Artikel bleiben erhalten)</div>
</div>
<form method="POST" action="/submit">
{blocks}
<div class="toolbar">
  <button type="button" class="btn btn-ghost" onclick="setAllPruefen('annehmen_vorschlag')">Alle PRÜFEN annehmen</button>
  <button type="button" class="btn btn-ghost" onclick="setAllPruefen('ablehnen')">Alle PRÜFEN ablehnen</button>
  <button type="submit" class="btn btn-primary">Review speichern und anwenden</button>
</div>
</form>
<script>{JS}</script>
</body></html>"""


def render_result_page(counts: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review gespeichert</title><style>{CSS}</style></head>
<body>
<div class="result-box">
  <h1>✓ Review gespeichert</h1>
  <ul>
    <li>{counts['angenommen']} angenommen (PRÜFEN-Vorschlag eingebaut bzw. KORRIGIERT bestätigt)</li>
    <li>{counts['abgelehnt']} PRÜFEN abgelehnt (Original behalten)</li>
    <li>{counts['revertiert']} Auto-Korrekturen zurückgenommen</li>
    <li>{counts['auto']} SILENT auto-bestätigt</li>
    <li>{counts['fehlgeschlagen']} Einbau fehlgeschlagen (Zielsatz nicht gefunden)</li>
  </ul>
  <p style="margin-top:18px"><a href="/">← Nochmal reviewen</a></p>
</div>
</body></html>"""


# ── Submit verarbeiten ────────────────────────────────────────────────────────
def _parse_name(field: str, prefix: str) -> tuple[str, int] | None:
    """'finding_vulkan_l3_4' + 'finding_' → ('vulkan_l3', 4)."""
    if not field.startswith(prefix):
        return None
    rest = field[len(prefix):]
    base, _, idx = rest.rpartition("_")
    if not base or not idx.isdigit():
        return None
    return base, int(idx)


def handle_submit(body: str) -> dict:
    form = parse_qs(body, keep_blank_values=True)
    counts = {"angenommen": 0, "abgelehnt": 0, "revertiert": 0,
              "fehlgeschlagen": 0, "auto": 0}
    now = _now_iso()

    # form ist flach (Feldname → [werte]); wir brauchen Zugriff je Artikel.
    pairs = {p["id"]: p for p in _load_pairs()}
    dirty: dict[str, dict] = {}  # id → {"article":bool, "lektorat":bool}

    def mark(aid: str, art=False, lekt=False):
        d = dirty.setdefault(aid, {"article": False, "lektorat": False})
        d["article"] = d["article"] or art
        d["lektorat"] = d["lektorat"] or lekt

    # 1) PRÜFEN-Radios
    for field, values in form.items():
        parsed = _parse_name(field, "finding_")
        if not parsed:
            continue
        aid, idx = parsed
        pair = pairs.get(aid)
        if not pair or pair["article"] is None:
            continue
        findings = (pair["lektorat"].get("pruefbericht", {}) or {}).get("findings", [])
        if idx >= len(findings):
            continue
        f = findings[idx]
        choice = values[-1]

        if choice == "ablehnen":
            f["review_decision"] = "abgelehnt"
            f.pop("review_variant", None)
            f["reviewed_at"] = now
            counts["abgelehnt"] += 1
            mark(aid, lekt=True)
        elif choice in ("annehmen_vorschlag", "annehmen_alt"):
            target = _strip_box_prefix(
                _alt_of(f) if choice == "annehmen_alt" else _vorschlag_of(f))
            claim  = _strip_box_prefix(f.get("claim_original", ""))
            if target and _replace_in_article(pair["article"], claim, target):
                f["review_decision"] = "angenommen"
                f["review_variant"] = "alt" if choice == "annehmen_alt" else "vorschlag"
                f["reviewed_at"] = now
                counts["angenommen"] += 1
                mark(aid, art=True, lekt=True)
            else:
                f["review_decision"] = "einbau_fehlgeschlagen"
                f["reviewed_at"] = now
                counts["fehlgeschlagen"] += 1
                mark(aid, lekt=True)

    # 2) KORRIGIERT-Revert-Checkboxen
    for field, values in form.items():
        parsed = _parse_name(field, "revert_")
        if not parsed:
            continue
        aid, idx = parsed
        pair = pairs.get(aid)
        if not pair or pair["article"] is None:
            continue
        findings = (pair["lektorat"].get("pruefbericht", {}) or {}).get("findings", [])
        if idx >= len(findings):
            continue
        f = findings[idx]
        kor   = _strip_box_prefix(f.get("korrektur_neu", ""))
        claim = _strip_box_prefix(f.get("claim_original", ""))
        if kor and claim and _replace_in_article(pair["article"], kor, claim):
            f["review_decision"] = "revertiert"
            f["reviewed_at"] = now
            counts["revertiert"] += 1
            mark(aid, art=True, lekt=True)
        else:
            f["review_decision"] = "einbau_fehlgeschlagen"
            f["reviewed_at"] = now
            counts["fehlgeschlagen"] += 1
            mark(aid, lekt=True)

    # 2b) Angezeigte KORRIGIERT (nicht revertiert) → "angenommen"; SILENT → "auto".
    #     Hidden-Felder signalisieren, dass das Finding im Review sichtbar war.
    for field in form:
        parsed = _parse_name(field, "seen_korr_")
        if not parsed:
            continue
        aid, idx = parsed
        pair = pairs.get(aid)
        if not pair or pair["article"] is None:
            continue
        findings = (pair["lektorat"].get("pruefbericht", {}) or {}).get("findings", [])
        if idx >= len(findings):
            continue
        # Wurde dieselbe Position revertiert? Dann nicht überschreiben.
        if f"revert_{aid}_{idx}" in form:
            continue
        f = findings[idx]
        f["review_decision"] = "angenommen"
        f["reviewed_at"] = now
        counts["angenommen"] += 1
        mark(aid, lekt=True)

    for field in form:
        parsed = _parse_name(field, "seen_silent_")
        if not parsed:
            continue
        aid, idx = parsed
        pair = pairs.get(aid)
        if not pair or pair["article"] is None:
            continue
        findings = (pair["lektorat"].get("pruefbericht", {}) or {}).get("findings", [])
        if idx >= len(findings):
            continue
        f = findings[idx]
        f["review_decision"] = "auto"
        f["reviewed_at"] = now
        counts["auto"] += 1
        mark(aid, lekt=True)

    # 3) Atomar zurückschreiben — nur lektorat_*.json (enthält Body + findings[]).
    #    articles/ bleibt unangetastet (Pre-Lektorat-Quelle).
    for aid, d in dirty.items():
        pair = pairs[aid]
        if d["article"] or d["lektorat"]:
            _atomic_write_json(pair["lektorat_path"], pair["lektorat"])

    return counts


# ── HTTP-Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/") or self.path.startswith("/?"):
            self._send(render_review_page())
        else:
            self._send("<h1>404</h1><p><a href='/'>Zur Übersicht</a></p>", 404)

    def do_POST(self):
        if self.path.rstrip("/") != "/submit":
            self._send("<h1>404</h1>", 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        counts = handle_submit(body)
        print(f"  Submit: {counts}")
        self._send(render_result_page(counts))

    def log_message(self, fmt, *args):  # ruhiger Server
        return


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    global RUN_DIR, ART_DIR, LEKT_DIR
    parser = argparse.ArgumentParser(
        description="Lokaler Lektorat-Review-Server (Baustein 2).")
    parser.add_argument("run_dir", type=Path,
                        help="Lauf-Ordner mit articles/ und lektorat/ (z.B. articles/verify_20260623b)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP-Port (Default 8080)")
    args = parser.parse_args()

    RUN_DIR  = args.run_dir.resolve()
    ART_DIR  = RUN_DIR / "articles"
    LEKT_DIR = RUN_DIR / "lektorat"

    if not ART_DIR.is_dir():
        print(f"FEHLER: Artikel-Ordner fehlt: {ART_DIR}", file=sys.stderr)
        return 2
    if not LEKT_DIR.is_dir():
        print(f"FEHLER: Lektorat-Ordner fehlt: {LEKT_DIR}", file=sys.stderr)
        return 2

    n_lekt = len(list(LEKT_DIR.glob("lektorat_*.json")))
    server = ThreadingHTTPServer(("localhost", args.port), Handler)
    print(f"Review-Tool läuft: http://localhost:{args.port} — Strg+C zum Beenden "
          f"({n_lekt} Lektorat-Dateien in {RUN_DIR.name})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
