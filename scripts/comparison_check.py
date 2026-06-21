#!/usr/bin/env python3
"""
comparison_check.py — Faktenprüfung der comparisons[]-Metadaten eines Artikels.

Eigenständiges, importierbares Modul. KEINE Nebenwirkungen auf den
Generierungs-/Upload-Pfad: es liest nur und FLAGGT, es korrigiert nichts.

Pro comparisons[]-Eintrag
    {text, reference_object, factor, dimension, source_value, source_unit,
     relation, sentence_id}
wird geprüft:
  1. Referenzgröße  — reference_object + dimension in SEED_REFERENCE_SIZES
                      nachschlagen → [low, high] in kanonischer Einheit.
                      Nicht gefunden → FLAG, Arithmetik übersprungen.
  2. Einheit        — source_value von source_unit in die kanonische Einheit
                      der dimension umrechnen. Unkonvertibel → FLAG.
  3. Erwartung      — [factor×low, factor×high].
  4. relation       — approx (Toleranzband TOL) / greater / less (strikt).
  5. Zahl-Bindung   — factor muss im referenzierten SATZ vorkommen (Ziffer
                      ODER deutsches Zahlwort).
  6. Bezugs-Bindung — reference_object (Hauptwort, plural-/flexionstolerant)
                      muss im referenzierten Satz vorkommen. Beide Bindungen
                      gegen den über sentence_id referenzierten Satz, Fallback
                      ganzer Body. text bleibt nur Anzeige-/Review-Feld.

Robust: fehlende Felder / unbekannte Einheiten führen zu FLAG, nie zu Crash.

CLI (optional, nur Diagnose):
    python comparison_check.py <artikel.json> [<artikel.json> ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Tuning-Konstanten (EINZIGER Ort für Referenzwerte / Toleranz) ───────────────

# Toleranzband für relation="approx" (±30 %).
TOL = 0.30

# Referenz-Saat-Tabelle: kanonische Objektnamen → {dimension: (low, high)} in
# KANONISCHER Einheit (Masse=kg, Länge=m, Höhe=m). Erststand, frei tunbar —
# der EINZIGE Ort, an dem Referenzgrößen stehen.
SEED_REFERENCE_SIZES: dict[str, dict[str, tuple[float, float]]] = {
    "afrikanischer elefant": {"masse":  (4000.0, 6500.0)},
    "linienbus":             {"länge":  (11.0, 13.0)},
    "gelenkbus":             {"länge":  (17.0, 19.0)},
    "auto":                  {"länge":  (4.0, 5.0), "masse": (1200.0, 1800.0)},
    "mensch":                {"höhe":   (1.6, 1.9), "masse": (60.0, 90.0)},
    "stockwerk":             {"höhe":   (2.5, 3.5)},
    "einfamilienhaus":       {"höhe":   (6.0, 10.0)},
    "fußballfeld":           {"länge":  (100.0, 110.0)},
    "fußballtor":            {"höhe":   (2.44, 2.44)},
    "eiffelturm":            {"höhe":   (300.0, 330.0)},
    # Erweiterung Schritt 3: häufige Alltags-Bezugsobjekte (Erststand, tunbar).
    "pferd":                 {"masse":  (400.0, 1000.0), "höhe": (1.4, 1.8)},
    "transporter":           {"länge":  (5.0, 7.5)},
    "lkw":                   {"länge":  (12.0, 18.75)},
    "giraffe":               {"höhe":   (4.5, 5.5)},
    "banane":                {"länge":  (0.15, 0.25)},
    "fußball":               {"länge":  (0.20, 0.23)},
    "tür":                   {"höhe":   (1.9, 2.1)},
    "kühlschrank":           {"höhe":   (1.5, 2.0)},
    "katze":                 {"länge":  (0.40, 0.50), "masse": (3.0, 6.0)},
    "eisbär":                {"länge":  (2.0, 2.5),   "masse": (300.0, 600.0)},
}

# Synonyme → kanonischer Schlüssel in SEED_REFERENCE_SIZES (alles lowercase,
# ß→ss-tolerant beim Lookup). Bewusst klein gehalten, nicht überengineert.
_REFERENCE_SYNONYMS: dict[str, str] = {
    "elefant": "afrikanischer elefant",
    "afrikanischer elefant": "afrikanischer elefant",
    "bus": "linienbus",
    "linienbus": "linienbus",
    "solobus": "linienbus",
    "gelenkbus": "gelenkbus",
    "auto": "auto",
    "pkw": "auto",
    "wagen": "auto",
    "mensch": "mensch",
    "person": "mensch",
    "erwachsener": "mensch",
    "erwachsener mensch": "mensch",
    "stockwerk": "stockwerk",
    "etage": "stockwerk",
    "stockwerke": "stockwerk",
    "etagen": "stockwerk",
    "einfamilienhaus": "einfamilienhaus",
    "haus": "einfamilienhaus",
    "fußballfeld": "fußballfeld",
    "fussballfeld": "fußballfeld",
    "fußballplatz": "fußballfeld",
    "fußballtor": "fußballtor",
    "fussballtor": "fußballtor",
    "eiffelturm": "eiffelturm",
    # Erweiterung Schritt 3:
    "reisebus": "linienbus",
    "pferd": "pferd",
    "transporter": "transporter",
    "lieferwagen": "transporter",
    "kleintransporter": "transporter",
    "lkw": "lkw",
    "lastwagen": "lkw",
    "laster": "lkw",
    "sattelschlepper": "lkw",
    "sattelzug": "lkw",
    "giraffe": "giraffe",
    "banane": "banane",
    "fußball": "fußball",
    "fussball": "fußball",
    "tür": "tür",
    "tuer": "tür",
    "zimmertür": "tür",
    "kühlschrank": "kühlschrank",
    "kuehlschrank": "kühlschrank",
    "katze": "katze",
    "hauskatze": "katze",
    "eisbär": "eisbär",
    "eisbaer": "eisbär",
    "polarbär": "eisbär",
}

# Dimension-Aliase → kanonische Dimension.
_DIMENSION_ALIASES: dict[str, str] = {
    "masse": "masse", "gewicht": "masse",
    "länge": "länge", "laenge": "länge",
    "höhe": "höhe", "hoehe": "höhe", "hohe": "höhe",
    "breite": "länge",  # Breite teilt sich die kanonische Einheit (m) mit Länge
}

# Einheitenumrechnung in die kanonische Einheit je Dimension.
_CANONICAL_UNIT = {"masse": "kg", "länge": "m", "höhe": "m"}
_UNIT_FACTORS: dict[str, dict[str, float]] = {
    "masse": {"kg": 1.0, "t": 1000.0, "tonne": 1000.0, "tonnen": 1000.0,
              "g": 0.001, "mg": 1e-6},
    "länge": {"m": 1.0, "cm": 0.01, "km": 1000.0, "mm": 0.001},
    "höhe":  {"m": 1.0, "cm": 0.01, "km": 1000.0, "mm": 0.001},
}

_VALID_RELATIONS = ("approx", "greater", "less")


# ── Deutsche Zahlwörter (Ziffer ↔ Wort, 0–100 + runde Hunderter/Tausender) ──────

_ONES = {0: "null", 1: "eins", 2: "zwei", 3: "drei", 4: "vier",
         5: "fünf", 6: "sechs", 7: "sieben", 8: "acht", 9: "neun"}
_PREFIX = {1: "ein", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf",
           6: "sechs", 7: "sieben", 8: "acht", 9: "neun"}
_TEENS = {10: "zehn", 11: "elf", 12: "zwölf", 13: "dreizehn", 14: "vierzehn",
          15: "fünfzehn", 16: "sechzehn", 17: "siebzehn", 18: "achtzehn",
          19: "neunzehn"}
_TENS = {20: "zwanzig", 30: "dreißig", 40: "vierzig", 50: "fünfzig",
         60: "sechzig", 70: "siebzig", 80: "achtzig", 90: "neunzig"}


def _spell_1_99(n: int) -> str:
    if n in _ONES:
        return _ONES[n]
    if n in _TEENS:
        return _TEENS[n]
    if n in _TENS:
        return _TENS[n]
    u = n % 10
    t = n - u
    return f"{_PREFIX[u]}und{_TENS[t]}"


def number_words(n: int) -> set[str]:
    """Akzeptierte deutsche Schreibweisen einer Grundzahl 0–9999 (lowercase)."""
    out: set[str] = set()
    if n < 0 or n > 9999:
        return out
    if n == 0:
        out.add("null")
    elif n < 100:
        out.add(_spell_1_99(n))
    elif n < 1000:
        h, rem = divmod(n, 100)
        hw = ("ein" if h == 1 else _PREFIX[h]) + "hundert"
        out.add(hw if rem == 0 else hw + _spell_1_99(rem))
        if h == 1:  # "hundert" ohne "ein"
            out.add("hundert" if rem == 0 else "hundert" + _spell_1_99(rem))
    else:
        th, rem = divmod(n, 1000)
        tw = ("ein" if th == 1 else _PREFIX[th]) + "tausend"
        rem_w = "" if rem == 0 else next(iter(number_words(rem)))
        out.add(tw + rem_w)
        if th == 1:
            out.add("tausend" + rem_w)
    if n == 1:
        out |= {"ein", "eine", "eins"}
    return out


def factor_in_text(factor, text: str) -> bool:
    """True, wenn factor als Ziffer oder deutsches Zahlwort im text vorkommt."""
    if not isinstance(text, str) or not text.strip():
        return False
    text_l = text.lower()
    try:
        fval = float(factor)
    except (TypeError, ValueError):
        return False
    if fval.is_integer():
        iv = int(fval)
        if re.search(rf"(?<!\d){iv}(?!\d)", text):
            return True
        for w in number_words(iv):
            if re.search(rf"\b{re.escape(w)}\b", text_l):
                return True
        return False
    # Nicht-ganzzahliger Faktor → nur Ziffernform (Punkt oder Komma).
    cand = {repr(fval), str(fval), str(fval).replace(".", ",")}
    return any(c in text for c in cand)


# ── Normalisierungs-Helfer ──────────────────────────────────────────────────────

def _norm(s) -> str:
    return s.strip().lower() if isinstance(s, str) else ""


def _resolve_reference(reference_object) -> str | None:
    """reference_object → kanonischer Schlüssel oder None."""
    key = _norm(reference_object)
    if not key:
        return None
    for variant in (key, key.replace("ß", "ss"), key.replace("ss", "ß")):
        if variant in _REFERENCE_SYNONYMS:
            return _REFERENCE_SYNONYMS[variant]
        if variant in SEED_REFERENCE_SIZES:
            return variant
    return None


def _resolve_dimension(dimension) -> str | None:
    return _DIMENSION_ALIASES.get(_norm(dimension))


def _to_canonical(value: float, unit, dim: str) -> float | None:
    """source_value in kanonische Einheit der Dimension umrechnen; None = unbekannt."""
    u = _norm(unit)
    factor = _UNIT_FACTORS.get(dim, {}).get(u)
    if factor is None:
        return None
    return value * factor


def _head_noun(s) -> str:
    """Letztes Token (Hauptwort) eines normalisierten Strings, lowercase."""
    n = _norm(s)
    return n.split()[-1] if n else ""


def _reference_tokens(reference_object) -> set[str]:
    """Hauptwort-Kandidaten für die Satz-Bindung: das reference_object selbst plus
    alle Synonyme, die auf denselben kanonischen Schlüssel zeigen (deren Hauptwörter).
    Substring-Match ist plural-/flexionstolerant ('bus' in 'busse', 'elefant' in
    'elefanten')."""
    out: set[str] = set()
    base = _norm(reference_object)
    if not base:
        return out
    out.add(_head_noun(base))
    key = _resolve_reference(reference_object)
    if key:
        out.add(_head_noun(key))
        for syn, target in _REFERENCE_SYNONYMS.items():
            if target == key:
                out.add(_head_noun(syn))
    return {t for t in out if t}


# ── Kernprüfung ─────────────────────────────────────────────────────────────────

class CheckResult:
    """Ergebnis einer Einzelprüfung. ok=True ⇔ keine Flags."""

    __slots__ = ("entry_index", "sentence_id", "flags", "info")

    def __init__(self, entry_index=None, sentence_id=None):
        self.entry_index = entry_index
        self.sentence_id = sentence_id
        self.flags: list[dict] = []   # je {code, detail}
        self.info: dict = {}          # diagnostische Zwischenwerte

    @property
    def ok(self) -> bool:
        return not self.flags

    def flag(self, code: str, detail: str) -> None:
        self.flags.append({"code": code, "detail": detail})

    def has(self, code: str) -> bool:
        return any(f["code"] == code for f in self.flags)

    def __repr__(self) -> str:
        if self.ok:
            return f"<PASS sid={self.sentence_id}>"
        codes = ", ".join(f["code"] for f in self.flags)
        return f"<FLAG sid={self.sentence_id} [{codes}]>"


def check_comparison(comp: dict, *, body: str = "", sentence_text: str | None = None,
                     entry_index=None) -> CheckResult:
    """Einen comparisons[]-Eintrag prüfen. body = ganzer Artikeltext (Fallback)."""
    res = CheckResult(entry_index=entry_index,
                      sentence_id=(comp.get("sentence_id") if isinstance(comp, dict) else None))

    if not isinstance(comp, dict):
        res.flag("kein_objekt", f"Eintrag ist {type(comp).__name__}, kein Objekt")
        return res

    text = comp.get("text")
    reference_object = comp.get("reference_object")
    factor = comp.get("factor")
    dimension = comp.get("dimension")
    source_value = comp.get("source_value")
    source_unit = comp.get("source_unit")
    relation = comp.get("relation") or "approx"

    if relation not in _VALID_RELATIONS:
        res.flag("ungueltige_relation",
                 f"relation '{relation}' nicht in {_VALID_RELATIONS}")
        relation = "approx"  # für die weitere Prüfung neutral annehmen

    # ── 5./6. Satz-Bindung (Token-Bindung statt Phrasen-Substring) ───────────────
    # Deutsche Vergleiche weben Wörter ein ("…ist so schwer wie vierzig … Elefanten…"),
    # darum ist der wörtliche text-Substring zu brüchig (er bricht schon an einem
    # eingeschobenen Verb). Stattdessen muss der referenzierte SATZ (über sentence_id;
    # Fallback: ganzer Body) BEIDES enthalten: den factor (Ziffer/Zahlwort) UND das
    # reference_object (Hauptwort, plural-/flexionstolerant). Das text-Feld bleibt im
    # Schema für Anzeige/Review, wird aber nicht mehr als wörtlicher Substring verlangt.
    sent = sentence_text if (isinstance(sentence_text, str) and sentence_text.strip()) else body

    # factor im Satz
    if factor is None or isinstance(factor, bool) or not isinstance(factor, (int, float)):
        res.flag("fehlender_factor", f"factor fehlt/nicht numerisch: {factor!r}")
    elif not (isinstance(sent, str) and sent.strip()):
        res.flag("kein_satztext",
                 "weder sentence_id-Satz noch Body verfügbar — Satz-Bindung nicht prüfbar")
    elif not factor_in_text(factor, sent):
        res.flag("zahl_nicht_im_satz",
                 f"factor {factor} weder als Ziffer noch als Zahlwort im Satz {res.sentence_id}")

    # reference_object im Satz
    if isinstance(sent, str) and sent.strip():
        ref_tokens = _reference_tokens(reference_object)
        sent_l = sent.lower()
        if not ref_tokens:
            res.flag("fehlendes_bezugsobjekt", f"reference_object fehlt: {reference_object!r}")
        elif not any(tok in sent_l for tok in ref_tokens):
            res.flag("bezug_nicht_im_satz",
                     f"reference_object '{reference_object}' (Token {sorted(ref_tokens)}) "
                     f"nicht im Satz {res.sentence_id}")

    # ── 1./2./3./4. Arithmetik ──────────────────────────────────────────────────
    dim = _resolve_dimension(dimension)
    if dim is None:
        res.flag("unbekannte_dimension", f"dimension '{dimension}' unbekannt")
        return res

    ref_key = _resolve_reference(reference_object)
    if ref_key is None:
        res.flag("unbekanntes_bezugsobjekt",
                 f"reference_object '{reference_object}' nicht in Saat-Tabelle")
        return res  # Arithmetik überspringen

    bounds = SEED_REFERENCE_SIZES[ref_key].get(dim)
    if bounds is None:
        res.flag("dimension_fehlt_fuer_objekt",
                 f"'{ref_key}' hat keine Referenz für Dimension '{dim}' "
                 f"(vorhanden: {sorted(SEED_REFERENCE_SIZES[ref_key])})")
        return res

    if source_value is None or isinstance(source_value, bool) \
            or not isinstance(source_value, (int, float)):
        res.flag("fehlender_source_value",
                 f"source_value fehlt/nicht numerisch: {source_value!r}")
        return res
    if factor is None or isinstance(factor, bool) or not isinstance(factor, (int, float)):
        return res  # factor-Flag oben bereits gesetzt; Arithmetik nicht möglich

    src = _to_canonical(float(source_value), source_unit, dim)
    if src is None:
        res.flag("unbekannte_einheit",
                 f"source_unit '{source_unit}' für Dimension '{dim}' nicht konvertierbar "
                 f"(bekannt: {sorted(_UNIT_FACTORS[dim])})")
        return res

    low, high = bounds
    exp_low = factor * low
    exp_high = factor * high
    canon = _CANONICAL_UNIT[dim]
    res.info.update(source_canonical=src, expected_low=exp_low, expected_high=exp_high,
                    unit=canon, relation=relation)

    if relation == "approx":
        ok = exp_low * (1 - TOL) <= src <= exp_high * (1 + TOL)
        if not ok:
            res.flag("wert_ausserhalb_approx",
                     f"{src:g} {canon} nicht in approx-Band "
                     f"[{exp_low*(1-TOL):g}, {exp_high*(1+TOL):g}] {canon} "
                     f"(factor {factor} × {ref_key} {dim} [{low:g},{high:g}], TOL={TOL})")
    elif relation == "greater":
        if not (src >= exp_low):
            res.flag("greater_verletzt",
                     f"{src:g} {canon} ≥ {exp_low:g} {canon} verlangt, aber kleiner "
                     f"(factor {factor} × {ref_key} {dim} low {low:g})")
    elif relation == "less":
        if not (src <= exp_high):
            res.flag("less_verletzt",
                     f"{src:g} {canon} ≤ {exp_high:g} {canon} verlangt, aber größer "
                     f"(factor {factor} × {ref_key} {dim} high {high:g})")

    return res


# ── Artikel-Ebene (echte Struktur: sections[].sentences[] = {id, text}) ─────────

def article_body_text(article: dict) -> str:
    """Ganzer Fließtext: alle Satz-Texte über alle Sections, mit \\n verbunden."""
    parts: list[str] = []
    for sec in article.get("sections", []) or []:
        for s in sec.get("sentences", []) or []:
            t = s.get("text")
            if isinstance(t, str):
                parts.append(t)
    return "\n".join(parts)


def sentence_text_map(article: dict) -> dict[str, str]:
    """sentence_id → Satztext."""
    out: dict[str, str] = {}
    for sec in article.get("sections", []) or []:
        for s in sec.get("sentences", []) or []:
            sid = s.get("id")
            if isinstance(sid, str):
                out[sid] = s.get("text", "")
    return out


def check_article(article: dict) -> list[CheckResult]:
    """Alle comparisons[] eines Artikels prüfen. Leer, wenn keine vorhanden."""
    comps = article.get("comparisons")
    if not isinstance(comps, list):
        return []
    body = article_body_text(article)
    smap = sentence_text_map(article)
    results = []
    for i, comp in enumerate(comps):
        sid = comp.get("sentence_id") if isinstance(comp, dict) else None
        results.append(check_comparison(comp, body=body, sentence_text=smap.get(sid),
                                        entry_index=i))
    return results


# ── CLI (nur Diagnose) ──────────────────────────────────────────────────────────

def _cli(paths: list[str]) -> int:
    import json
    n_flag = 0
    for p in paths:
        art = json.loads(Path(p).read_text(encoding="utf-8"))
        results = check_article(art)
        print(f"\n=== {p} — {len(results)} Vergleich(e) ===")
        for r in results:
            mark = "PASS" if r.ok else "FLAG"
            print(f"  [{mark}] #{r.entry_index} sid={r.sentence_id}")
            for f in r.flags:
                n_flag += 1
                print(f"        ! {f['code']}: {f['detail']}")
    return 1 if n_flag else 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]) if len(sys.argv) > 1 else 0)
