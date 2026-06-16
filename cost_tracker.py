#!/usr/bin/env python3
"""
cost_tracker.py  v1  (2026-06-16)
Zentrales Token- + Kosten-Tracking fuer die Wissensfreund-Pipeline.

Usage (als Modul):
    from cost_tracker import track
    track(run_id="mini_001", thema="Vulkan", stufe="S1", schritt="article_gen",
          modell="gemini-2.5-flash", input_tok=1234, output_tok=567)
    track(..., schritt="tts", modell="gemini-3.1-flash-tts-preview", tts_chars=2400)

Usage (CLI):
    python cost_tracker.py --report
    python cost_tracker.py --report --run mini_001
    python cost_tracker.py --reset
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / "cost_log.json"

log = logging.getLogger(__name__)

# -- Preis-Tabelle (USD pro 1 Mio Token, ausser TTS: USD pro 1 Mio Zeichen) --
# Stand: 2026-06. Jederzeit hier editieren wenn Preise sich aendern.
#
# HINWEIS TTS-Preis: gemini-3.1-flash-tts-preview ist ein Vorschau-Modell.
# Der unten gesetzte Wert (5.00 USD / 1 Mio Zeichen) ist ein PLATZHALTER.
# Andreas muss den echten TTS-Preis auf der Google AI / Gemini Pricing-Seite
# verifizieren und diesen Wert anpassen bevor der Mini-Lauf kostenbewertet wird.
#
# Format Text-Modelle: {"in": X, "out": Y}     (USD / 1M Token)
# Format TTS-Modelle:  {"tts_chars": Z}         (USD / 1M Zeichen)
PRICE_TABLE: dict[str, dict] = {
    "gemini-2.5-flash":              {"in": 0.30,  "out": 2.50},
    "gemini-2.5-flash-lite":         {"in": 0.10,  "out": 0.40},
    # [!] PLATZHALTER -- TTS-Preis bitte auf Google AI Pricing-Seite verifizieren:
    "gemini-3.1-flash-tts-preview":  {"tts_chars": 5.00},
    "gemini-3.5-flash":              {"in": 0.30,  "out": 2.50},
    "claude-haiku-4-5":              {"in": 1.00,  "out": 5.00},
    "claude-haiku-4-5-20251001":     {"in": 1.00,  "out": 5.00},
    "claude-sonnet-4-6":             {"in": 3.00,  "out": 15.00},
    "claude-opus-4-8":               {"in": 15.00, "out": 75.00},
}

TOTAL_CATALOG_TOPICS = 4346  # Stand 2026-06-16, catalog_full.json primary


# -- Kern-API -----------------------------------------------------------------

def _calc_cost(modell: str, input_tok: int, output_tok: int,
               cached_tok: int, thoughts_tok: int, tts_chars: int) -> float:
    """Berechnet Kosten in USD aus Preis-Tabelle. 0.0 bei unbekanntem Modell."""
    prices = PRICE_TABLE.get(modell)
    if prices is None:
        log.warning("cost_tracker: unbekanntes Modell '%s' -- Kosten werden als 0 erfasst", modell)
        return 0.0

    try:
        if "tts_chars" in prices:
            return tts_chars / 1_000_000 * prices["tts_chars"]

        # Cached Token werden konservativ wie normale Input-Token berechnet
        # (Gemini berechnet sie derzeit gleich; bei Preisaenderung hier anpassen)
        return (
            input_tok  / 1_000_000 * prices["in"] +
            output_tok / 1_000_000 * prices["out"]
        )
    except Exception as exc:
        log.warning("cost_tracker: Kostenfehler Modell '%s': %s -- setze 0", modell, exc)
        return 0.0


def track(
    *,
    run_id: str,
    thema: str,
    stufe: str,
    schritt: str,
    modell: str,
    input_tok: int = 0,
    output_tok: int = 0,
    cached_tok: int = 0,
    thoughts_tok: int = 0,
    tts_chars: int = 0,
    tts_audio_sec: float = 0.0,
) -> dict:
    """
    Loggt einen API-Call in cost_log.json.

    Pflichtfelder: run_id, thema, stufe, schritt, modell
    Rueckgabe: der geschriebene Eintrag (inkl. berechneter kosten_usd).
    """
    kosten = _calc_cost(modell, input_tok, output_tok, cached_tok, thoughts_tok, tts_chars)

    entry = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "run_id":        run_id,
        "thema":         thema,
        "stufe":         stufe,
        "schritt":       schritt,
        "modell":        modell,
        "input_tok":     input_tok,
        "output_tok":    output_tok,
        "cached_tok":    cached_tok,
        "thoughts_tok":  thoughts_tok,
        "tts_chars":     tts_chars,
        "tts_audio_sec": tts_audio_sec,
        "kosten_usd":    round(kosten, 8),
    }

    _append_entry(entry)
    return entry


def _append_entry(entry: dict) -> None:
    entries = _load_log()
    entries.append(entry)
    _write_log(entries)


def _load_log() -> list[dict]:
    """Laedt cost_log.json. Bei Parse-Fehler: Backup anlegen, leere Liste zurueck."""
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        backup = LOG_PATH.with_suffix(".json.bak")
        shutil.copy2(LOG_PATH, backup)
        log.error(
            "cost_tracker: cost_log.json kaputt (%s) -- Backup: %s, starte neu",
            exc, backup,
        )
        return []


def _write_log(entries: list[dict]) -> None:
    LOG_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# -- Report -------------------------------------------------------------------

def report(run_id: str | None = None) -> None:
    entries = _load_log()
    if not entries:
        print("cost_log.json ist leer oder existiert nicht.")
        return

    if run_id:
        entries = [e for e in entries if e.get("run_id") == run_id]
        if not entries:
            print(f"Kein Eintrag fuer run_id='{run_id}'.")
            return

    total_cost = sum(e.get("kosten_usd", 0) for e in entries)
    n_entries  = len(entries)

    # Kosten je Schritt
    by_schritt: dict[str, float] = {}
    for e in entries:
        by_schritt[e["schritt"]] = by_schritt.get(e["schritt"], 0) + e.get("kosten_usd", 0)

    # Kosten je Modell + Token-Summen
    by_model: dict[str, dict] = {}
    for e in entries:
        m = e["modell"]
        if m not in by_model:
            by_model[m] = {"kosten": 0.0, "input_tok": 0, "output_tok": 0,
                           "cached_tok": 0, "thoughts_tok": 0, "tts_chars": 0, "calls": 0}
        bm = by_model[m]
        bm["kosten"]       += e.get("kosten_usd", 0)
        bm["input_tok"]    += e.get("input_tok", 0)
        bm["output_tok"]   += e.get("output_tok", 0)
        bm["cached_tok"]   += e.get("cached_tok", 0)
        bm["thoughts_tok"] += e.get("thoughts_tok", 0)
        bm["tts_chars"]    += e.get("tts_chars", 0)
        bm["calls"]        += 1

    # Kosten je Thema (alle Stufen + Schritte zusammen)
    by_thema: dict[str, float] = {}
    for e in entries:
        key = f"{e['thema']} [{e['run_id']}]"
        by_thema[key] = by_thema.get(key, 0) + e.get("kosten_usd", 0)

    # Kosten je Artikel-Variante (Thema + Stufe)
    by_variante: dict[str, float] = {}
    for e in entries:
        key = f"{e['thema']} {e['stufe']}"
        by_variante[key] = by_variante.get(key, 0) + e.get("kosten_usd", 0)

    avg_per_variante = (sum(by_variante.values()) / len(by_variante)) if by_variante else 0
    avg_per_thema    = (sum(by_thema.values())    / len(by_thema))    if by_thema    else 0

    SEP  = "-" * 60
    SEP2 = "=" * 60

    print(f"\n{SEP2}")
    hdr = "  COST REPORT" + (f"  (run: {run_id})" if run_id else "")
    print(hdr)
    print(SEP2)
    print(f"  Eintraege gesamt:       {n_entries}")
    print(f"  Gesamtkosten:           ${total_cost:.6f}")
    print()

    print(f"  {SEP}")
    print("  Kosten je Schritt")
    print(f"  {SEP}")
    for schritt, cost in sorted(by_schritt.items(), key=lambda x: -x[1]):
        print(f"    {schritt:<22} ${cost:.6f}")

    print()
    print(f"  {SEP}")
    print("  Kosten je Modell")
    print(f"  {SEP}")
    for modell, bm in sorted(by_model.items(), key=lambda x: -x[1]["kosten"]):
        tts_info = f"  tts_chars={bm['tts_chars']:,}" if bm["tts_chars"] else ""
        print(
            f"    {modell:<42} ${bm['kosten']:.6f}"
            f"  ({bm['calls']} calls,"
            f" in={bm['input_tok']:,} out={bm['output_tok']:,}"
            f" cached={bm['cached_tok']:,}"
            + tts_info + ")"
        )

    print()
    print(f"  {SEP}")
    print("  Kosten je Artikel-Variante")
    print(f"  {SEP}")
    for var, cost in sorted(by_variante.items(), key=lambda x: -x[1]):
        print(f"    {var:<32} ${cost:.6f}")
    print(f"\n    Avg je Variante (Thema+Stufe):  ${avg_per_variante:.6f}")
    print(f"    Avg je Thema (3 Stufen):        ${avg_per_thema:.6f}")

    print()
    print(f"  {SEP}")
    print(f"  HOCHRECHNUNG: {TOTAL_CATALOG_TOPICS} Themen x 3 Stufen (Vollkatalog)")
    print(f"  {SEP}")
    print(f"  Annahme: Avg Kosten/Thema = ${avg_per_thema:.6f} (aus diesem Log-Ausschnitt)")

    proj_total = avg_per_thema * TOTAL_CATALOG_TOPICS

    text_cost = sum(
        e.get("kosten_usd", 0) for e in entries
        if e["schritt"] not in ("tts", "quiz_tts")
    )
    tts_cost = sum(
        e.get("kosten_usd", 0) for e in entries
        if e["schritt"] in ("tts", "quiz_tts")
    )
    vision_cost = sum(
        e.get("kosten_usd", 0) for e in entries
        if e["schritt"] == "vision"
    )
    n_themen_in_run = len({(e["thema"], e["run_id"]) for e in entries})
    if n_themen_in_run > 0:
        avg_text   = (text_cost   / n_themen_in_run) * TOTAL_CATALOG_TOPICS
        avg_tts    = (tts_cost    / n_themen_in_run) * TOTAL_CATALOG_TOPICS
        avg_vision = (vision_cost / n_themen_in_run) * TOTAL_CATALOG_TOPICS
    else:
        avg_text = avg_tts = avg_vision = 0.0

    print(f"\n    Text-Pipeline:            ${avg_text:.2f}")
    print(f"    Vision:                   ${avg_vision:.2f}")
    print(f"    TTS-Pipeline:             ${avg_tts:.2f}")
    print(f"    [!] TTS-Preis ist PLATZHALTER (5.00 USD/1M Zeichen)")
    print(f"        -> Bitte auf Google AI Pricing-Seite verifizieren!")
    print(f"\n    GESAMT (geschaetzt):      ${proj_total:.2f}")
    print(f"\n  Hochrechnung basiert auf {n_themen_in_run} Thema/Themen im Log-Ausschnitt.")
    print(f"  Mehr Themen im Mini-Lauf = stabilere Schaetzung.")
    print(f"\n{SEP2}\n")


# -- CLI ----------------------------------------------------------------------

def _cmd_reset() -> None:
    if not LOG_PATH.exists():
        print("cost_log.json existiert nicht -- nichts zu tun.")
        return
    entries = _load_log()
    print(f"cost_log.json enthaelt {len(entries)} Eintraege.")
    answer = input("Wirklich loeschen? [ja/N] ").strip().lower()
    if answer == "ja":
        LOG_PATH.unlink()
        print("cost_log.json geloescht.")
    else:
        print("Abgebrochen.")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Wissensfreund Pipeline -- Cost Tracker")
    ap.add_argument("--report", action="store_true", help="Kosten-Report ausgeben")
    ap.add_argument("--run",    default=None,         help="Nur diesen run_id auswerten")
    ap.add_argument("--reset",  action="store_true",  help="cost_log.json leeren")
    args = ap.parse_args()

    if args.reset:
        _cmd_reset()
    elif args.report or args.run:
        report(run_id=args.run)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
