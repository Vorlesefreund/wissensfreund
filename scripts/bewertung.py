#!/usr/bin/env python3
"""bewertung.py — objektiver Rubrik-Scorer fuer Bakeoff-Vergleiche (offline).

Zweck: Bakeoff-Ausgaben (Hoerspiel/Erzaehltext) nicht mehr nur per Augenmass im
Docx bewerten, sondern auf festen Dimensionen mit verankerter 1-5-Skala scoren.
Damit werden Modelle (Flash vs. GPT vs. Claude ...) unter GLEICHEN Bedingungen
objektiv und wiederholbar vergleichbar.

Wichtig — was dieser Scorer ist und was NICHT:
  * Er beruehrt die Produktions-Pipeline NICHT. Rein additiv, offline, keine
    Kosten pro Produktionsartikel — nur pro Bewertungslauf (ein Judge-Call/Text).
  * Er ist ein RICHTUNGSGEBER, kein Schiedsrichter. Das Review-Docx bleibt die
    letzte Instanz. LLM-Judge-Scores rauschen; nutze sie fuer Trends/Regression.

Design gegen die typischen Judge-Fehler:
  * ABSOLUTE Bewertung je Text (verankerte Rubrik) statt Position-anfaelligem
    A/B — dadurch bias-frei und ueber Laeufe hinweg vergleichbar.
  * BLIND: der Judge erfaehrt NICHT, welches Modell den Text schrieb.
  * GEERDET: die Faktentreue-Dimension wird nur bewertet, wenn der Quelltext
    (--quelle) mitgegeben wird; sonst bleibt sie null (kein Raten).
  * Verankerte Skala (konkrete 1/3/5-Beschreibung je Dimension im Prompt).

CLI:
    python scripts/bewertung.py TEXT1 [TEXT2 ...] \
        [--quelle quelltext.txt] [--typ hoerspiel|erzaehltext|auto] \
        [--modell claude-sonnet-5] [--json out.json]

TEXTn: Artikel-JSON (wie aus der Pipeline) ODER reine .txt/.md-Datei.
Default-Judge: claude-sonnet-5 (stark). Fuer billige Grosslaeufe:
    --modell gemini-3.5-flash   (deutlich guenstiger, dafuer groeberes Urteil)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows-Konsole ist cp1252 -> Umlaute/Sonderzeichen (▸) crashen sonst.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import claude_client            # noqa: E402
import cost_tracker             # noqa: E402

_DEFAULT_JUDGE = "claude-sonnet-5"
_SOURCE_CHAR_CAP = 24000        # Quelltext-Deckel fuer die Faktentreue-Pruefung

# ---------------------------------------------------------------------------
# Dimensionen der Rubrik. Reihenfolge = Ausgabereihenfolge.
# 'grounded' = braucht Quelltext; ohne --quelle bleibt der Score null.
# ---------------------------------------------------------------------------
DIMENSIONEN = [
    ("verstaendlichkeit", "Verständlichkeit",
     "Altersgerecht klar? Keine unerklärten Fremdwörter, keine überladenen Sätze."),
    ("spannung", "Spannung / Dramaturgie",
     "Trägt ein Bogen (Neugier → Überraschung → Aha → Abschluss)? Zieht es weiter?"),
    ("handwerk", "Erzählhandwerk / Show-don't-tell",
     "Wird gezeigt statt behauptet (lebendige Szene, Handlung, natürlicher Dialog) "
     "statt bloß erklärt/aufgezählt?"),
    ("didaktik", "Didaktik",
     "Ist ein Lernkern klar? Könnte ein Kind der Zielstufe danach etwas erklären?"),
    ("sprachfluss", "Sprachfluss / Rhythmus",
     "Satzlängen variiert (kein Stakkato), keine wörtlichen Wiederholungen, weiche Übergänge."),
    ("faktentreue", "Faktentreue / Quellendeckung",
     "NUR mit Quelltext bewertbar: keine ungedeckten Sachaussagen, Kernfakten korrekt "
     "wiedergegeben (erfundener Story-Rahmen wie Namen/Kulisse ist erlaubt und zählt NICHT als Fehler)."),
]
_GROUNDED_DIMS = {"faktentreue"}

# Gewichte fuer den Gesamtscore (Story-first: Handwerk + Spannung hoeher).
_GEWICHT = {
    "verstaendlichkeit": 1.0,
    "spannung": 1.3,
    "handwerk": 1.3,
    "didaktik": 1.0,
    "sprachfluss": 1.0,
    "faktentreue": 1.2,
}


def _extract_text(path: Path) -> dict:
    """Liest eine Datei und liefert {title, typ, body, quiz_txt}.

    Artikel-JSON (sections[].sentences[].text) wird zu Fliesstext geflacht.
    Reine .txt/.md werden roh uebernommen.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    title, typ, quiz_txt = path.stem, None, ""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"title": title, "typ": None, "body": raw.strip(), "quiz_txt": ""}

    if not isinstance(d, dict):
        return {"title": title, "typ": None, "body": raw.strip(), "quiz_txt": ""}

    meta = d.get("meta", {}) if isinstance(d.get("meta"), dict) else {}
    title = meta.get("title") or title
    typ = meta.get("content_type")

    lines = []
    for sec in d.get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        heading = (sec.get("heading") or "").strip()
        if heading:
            lines.append(f"## {heading}")
        for sent in sec.get("sentences", []) or []:
            if isinstance(sent, dict):
                t = (sent.get("text") or "").strip()
            else:
                t = str(sent).strip()
            if t:
                lines.append(t)
    body = "\n".join(lines).strip()
    if not body:
        # Fallback: irgendein Textfeld oder Rohtext
        body = (d.get("text") or d.get("body") or raw).strip()

    quiz = d.get("quiz")
    if quiz:
        quiz_txt = json.dumps(quiz, ensure_ascii=False)[:1500]

    return {"title": title, "typ": typ, "body": body, "quiz_txt": quiz_txt}


def _schema() -> dict:
    # Flache Liste statt Objekt-mit-dynamischen-Keys: das Modell serialisiert
    # verschachtelte Objekt-Maps sonst gern faelschlich als JSON-String.
    return {
        "type": "object",
        "properties": {
            "dimensionen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dim": {"type": "string", "enum": [k for k, _, _ in DIMENSIONEN]},
                        "score": {"type": ["integer", "null"],
                                  "description": "1-5, oder null wenn ohne Quelltext nicht bewertbar"},
                        "begruendung": {"type": "string",
                                        "description": "1 knapper Satz, konkret am Text belegt"},
                    },
                    "required": ["dim", "score", "begruendung"],
                },
            },
            "groesste_schwaeche": {"type": "string",
                                   "description": "Der konkreteste Verbesserungspunkt, 1 Satz."},
            "groesste_staerke": {"type": "string", "description": "1 Satz."},
        },
        "required": ["dimensionen", "groesste_schwaeche", "groesste_staerke"],
    }


def _normalize(result: dict) -> dict:
    """Bringt die Judge-Antwort in die kanonische Form
    {dimensionen: {key: {score, begruendung}}, groesste_schwaeche, groesste_staerke}.
    Robust gegen (a) Liste-Form aus dem Schema und (b) faelschlich als String
    serialisierte Felder.
    """
    def _decode(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return v
        return v

    result = {k: _decode(v) for k, v in dict(result).items()}
    dims_raw = _decode(result.get("dimensionen"))
    dims: dict = {}
    if isinstance(dims_raw, list):
        for item in dims_raw:
            if isinstance(item, dict) and item.get("dim"):
                dims[item["dim"]] = {"score": item.get("score"),
                                     "begruendung": item.get("begruendung", "")}
    elif isinstance(dims_raw, dict):
        for key, val in dims_raw.items():
            val = _decode(val)
            if isinstance(val, dict):
                dims[key] = {"score": val.get("score"),
                             "begruendung": val.get("begruendung", "")}
    # fehlende Dimensionen auffuellen
    for key, _, _ in DIMENSIONEN:
        dims.setdefault(key, {"score": None, "begruendung": ""})
    return {"dimensionen": dims,
            "groesste_schwaeche": result.get("groesste_schwaeche", ""),
            "groesste_staerke": result.get("groesste_staerke", "")}


_SYSTEM = (
    "Du bist strenge, erfahrene Lektorin eines deutschen Kinderlexikons. Du bewertest "
    "EINEN Text objektiv auf einer verankerten 1-5-Skala. Du weißt NICHT, welches Modell "
    "ihn geschrieben hat — bewerte nur den Text.\n\n"
    "Skala je Dimension:\n"
    "  1 = schwerer Mangel · 2 = deutlich schwach · 3 = brauchbar/durchschnittlich · "
    "4 = gut · 5 = herausragend.\n"
    "Sei kalibriert: 3 ist der Normalfall. Vergib 5 nur bei echter Exzellenz, 1 nur bei echtem Bruch.\n\n"
    "WICHTIG:\n"
    "- Ein erfundener Story-RAHMEN (Namen, Kulisse, Dialog) ist im Hörspiel ausdrücklich erlaubt "
    "und niemals ein Faktenfehler. Faktentreue bezieht sich NUR auf Sachaussagen über das Thema.\n"
    "- Bewerte 'faktentreue' mit score=null, wenn dir KEIN Quelltext vorliegt.\n"
    "- Jede Begründung MUSS konkret am Text belegt sein (kurzes Beispiel), keine Floskeln.\n"
    "Gib das Ergebnis über das emit-Tool zurück."
)


def _bewerte_text(entry: dict, typ: str, quelle: str | None, modell: str,
                  run_id: str) -> dict:
    ziel = "4-9 Jahre (Hörspiel, Story-first)" if typ == "hoerspiel" \
        else "10-12 Jahre (Erzähltext)" if typ == "erzaehltext" \
        else "Kinder"
    dim_txt = "\n".join(
        f"- {label} ({key}): {desc}" for key, label, desc in DIMENSIONEN
    )
    parts = [
        f"ZIELGRUPPE: {ziel}",
        f"\nDIMENSIONEN:\n{dim_txt}",
    ]
    if quelle:
        parts.append(
            "\nQUELLTEXT (nur für die Dimension Faktentreue — Sachaussagen des Textes "
            "müssen hierdurch gedeckt sein):\n\"\"\"\n" + quelle[:_SOURCE_CHAR_CAP] + "\n\"\"\"")
    else:
        parts.append("\n(KEIN Quelltext vorhanden → 'faktentreue' mit score=null bewerten.)")
    parts.append("\nZU BEWERTENDER TEXT:\n\"\"\"\n" + entry["body"] + "\n\"\"\"")
    if entry.get("quiz_txt"):
        parts.append("\nQUIZ (als Kontext, fließt in 'didaktik' ein):\n" + entry["quiz_txt"])
    user_msg = "\n".join(parts)

    result = claude_client.call_claude_json(
        _SYSTEM, user_msg, _schema(),
        model=modell, max_tokens=2000, call_name="bewertung",
    )
    usage = claude_client.get_last_usage()
    cost_tracker.track(
        run_id=run_id, thema=entry["title"], stufe=(typ or "?"),
        schritt="bewertung", modell=modell,
        input_tok=usage.get("input_tokens", 0),
        output_tok=usage.get("output_tokens", 0),
    )
    return _normalize(result)


def _gesamt(result: dict) -> tuple[float, int]:
    """Gewichteter Mittelwert ueber die bewerteten (nicht-null) Dimensionen."""
    num = den = 0.0
    n = 0
    for key, _, _ in DIMENSIONEN:
        sc = result.get("dimensionen", {}).get(key, {}).get("score")
        if isinstance(sc, (int, float)):
            w = _GEWICHT.get(key, 1.0)
            num += sc * w
            den += w
            n += 1
    return (num / den if den else 0.0), n


def main() -> None:
    ap = argparse.ArgumentParser(description="Objektiver Rubrik-Scorer fuer Bakeoff-Vergleiche")
    ap.add_argument("texte", nargs="+", help="Artikel-JSON oder .txt/.md (ein oder mehrere)")
    ap.add_argument("--quelle", default=None, help="Quelltext-Datei (aktiviert Faktentreue-Pruefung)")
    ap.add_argument("--typ", default="auto", choices=["auto", "hoerspiel", "erzaehltext"],
                    help="Inhaltstyp (auto = aus JSON-meta.content_type)")
    ap.add_argument("--modell", default=_DEFAULT_JUDGE, help=f"Judge-Modell (default {_DEFAULT_JUDGE})")
    ap.add_argument("--json", default=None, help="Ergebnis zusaetzlich als JSON hierhin schreiben")
    ap.add_argument("--run-id", default="bewertung", help="run_id fuer cost_tracker")
    args = ap.parse_args()

    quelle = None
    if args.quelle:
        quelle = Path(args.quelle).read_text(encoding="utf-8", errors="replace")

    ergebnisse = []
    for pth in args.texte:
        p = Path(pth)
        if not p.exists():
            print(f"!! Datei fehlt: {pth}", file=sys.stderr)
            continue
        entry = _extract_text(p)
        typ = entry["typ"] if args.typ == "auto" else args.typ
        typ = typ or "auto"
        print(f"… bewerte {p.name}  (Typ={typ}, Judge={args.modell}) …", file=sys.stderr)
        res = _bewerte_text(entry, typ, quelle, args.modell, args.run_id)
        gesamt, n_dim = _gesamt(res)
        ergebnisse.append({"datei": p.name, "titel": entry["title"], "typ": typ,
                           "gesamt": round(gesamt, 2), "n_dim": n_dim, "detail": res})

    if not ergebnisse:
        print("Nichts bewertet.", file=sys.stderr)
        sys.exit(1)

    # ---- Ausgabe ----------------------------------------------------------
    ergebnisse.sort(key=lambda e: -e["gesamt"])
    W = 26
    print("\n" + "=" * 72)
    print("  BAKEOFF-BEWERTUNG  (Judge: %s, verankert 1-5, gewichtet)" % args.modell)
    if not quelle:
        print("  Hinweis: ohne --quelle wird 'Faktentreue' nicht bewertet.")
    print("=" * 72)

    # Score-Matrix
    header = f"  {'Dimension':<{W}}" + "".join(f"{e['datei'][:14]:>16}" for e in ergebnisse)
    print("\n" + header)
    print("  " + "-" * (W + 16 * len(ergebnisse)))
    for key, label, _ in DIMENSIONEN:
        row = f"  {label:<{W}}"
        for e in ergebnisse:
            sc = e["detail"]["dimensionen"].get(key, {}).get("score")
            row += f"{('—' if sc is None else str(sc)):>16}"
        print(row)
    print("  " + "-" * (W + 16 * len(ergebnisse)))
    grow = f"  {'GESAMT (gewichtet)':<{W}}"
    for e in ergebnisse:
        grow += f"{e['gesamt']:>16.2f}"
    print(grow)

    # Begruendungen je Text
    for e in ergebnisse:
        print("\n" + "-" * 72)
        print(f"  {e['datei']}  —  {e['titel']}  —  GESAMT {e['gesamt']:.2f}")
        print("-" * 72)
        for key, label, _ in DIMENSIONEN:
            d = e["detail"]["dimensionen"].get(key, {})
            sc = d.get("score")
            print(f"  [{('—' if sc is None else sc)}] {label}: {d.get('begruendung', '').strip()}")
        print(f"  ▸ Stärke:   {e['detail'].get('groesste_staerke', '').strip()}")
        print(f"  ▸ Schwäche: {e['detail'].get('groesste_schwaeche', '').strip()}")

    if len(ergebnisse) > 1:
        best = ergebnisse[0]
        print("\n" + "=" * 72)
        print(f"  SIEGER (Score): {best['datei']}  ({best['gesamt']:.2f})")
        print("  (Richtungsgeber — Review-Docx bleibt letzte Instanz.)")
        print("=" * 72)

    if args.json:
        Path(args.json).write_text(
            json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON geschrieben: {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
