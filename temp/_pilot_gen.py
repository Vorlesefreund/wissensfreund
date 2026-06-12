#!/usr/bin/env python3
"""
Pilot-Generierung: 12 Themen × 3 Stufen mit grounded pipeline + neuen Wortzielen.
Ausgabe: pilot_output/<Thema>_S<N>.md + pilot_wortzahlen.csv
"""
import csv, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
import requests
from google import genai
from google.genai import types as gtypes
import gemini_client
from generate_articles import (
    fetch_wikipedia_text, parse_article_json, WIKIPEDIA_API, USER_AGENT,
)
from generate_articles import resolve_lemma
from generate_grounded import (
    prepare_topic_sources, build_grounded_user_message,
    count_article_words, GEMINI_MODEL, SYSTEM_PROMPT_PATH,
)

# ── Pilot-Wortziele (Obergrenzen) ─────────────────────────────────────────────
PILOT_TARGETS = {  # thema → (S1, S2, S3)
    "Indianer":      (183, 400, 650),
    "Elefant":       (250, 400, 650),
    "Dinosaurier":   (250, 400, 650),
    "Vulkan":        (217, 400, 650),
    "Fußball":       (183, 400, 650),
    "Hund":          (250, 400, 650),
    "Schmetterling": (217, 347, 467),
    "Düsseldorf":    (217, 400, 650),
    "Wirtschaft":    (117, 347, 650),
    "Viereck":       (117, 187, 283),
    "Kühlschrank":    (83, 240, 375),
    "Pangolin":      (117, 293, 467),
}
AGE_RANGES = {1: "4–6 Jahre", 2: "7–9 Jahre", 3: "10–12 Jahre"}

OUT_DIR = ROOT / "pilot_output"
OUT_DIR.mkdir(exist_ok=True)
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text("utf-8")

try:
    phase2_cfg = gtypes.ThinkingConfig(thinking_level=gtypes.ThinkingLevel.LOW)
except AttributeError:
    phase2_cfg = gtypes.ThinkingConfig(thinking_budget=2048)

client  = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def make_user_msg(job, primary_text, companion_texts, companion_order, ceiling):
    """Stabiler Prefix via build_grounded_user_message, eigener WORTZIEL-Suffix."""
    full = build_grounded_user_message(
        job, primary_text, companion_texts, companion_order, []  # keine Bilder
    )
    lines = full.rstrip("\n").split("\n")
    while lines and (lines[-1].startswith("WORTZIEL:") or lines[-1].startswith("AGE_LEVEL:")):
        lines.pop()
    stable = "\n".join(lines)
    suffix = (
        f"AGE_LEVEL: {job['age_level']}\n"
        f"WORTZIEL: bis zu {ceiling} Wörter, aber nur so weit, wie der Wikipedia-Stoff trägt — "
        f"nicht aufblähen. Harte Obergrenze {ceiling} Wörter."
    )
    return stable + "\n" + suffix


def article_to_md(article, thema, level, lemma, flag_strs, wc, ceiling, companions):
    lines = [
        f"# {thema} — Stufe {level} ({AGE_RANGES[level]})",
        "",
        f"**Lemma:** `{lemma}`  ",
        f"**Flags:** {', '.join(flag_strs) if flag_strs else '—'}  ",
        f"**Companions:** {', '.join(companions) if companions else '—'}  ",
        f"**Wortziel (Obergrenze):** {ceiling} | **Ist:** {wc} | **Δ:** {wc - ceiling:+d}",
        "",
        "---",
        "",
    ]
    for sec in article.get("sections", []):
        hdg = sec.get("heading", "")
        if hdg:
            lines += [f"## {hdg}", ""]
        for s in sec.get("sentences", []):
            t = s.get("text", "").strip()
            if t:
                lines.append(t)
        lines.append("")
        for box in sec.get("boxes", []):
            bt = box.get("text", "").strip()
            rt = box.get("reveal_text", "").strip()
            btype = box.get("type", "Box")
            if bt:
                lines += [f"> **{btype}:** {bt}", ""]
            if rt:
                lines += [f"> *(Aufklapp: {rt})*", ""]
    quiz = article.get("quiz", [])
    if quiz:
        lines += ["## Quiz", ""]
        for q in quiz:
            if isinstance(q, dict):
                lines += [f"**F:** {q.get('question', '')}  ", f"**A:** {q.get('answer', '')}  ", ""]
            elif isinstance(q, str):
                lines += [f"- {q}", ""]
    return "\n".join(lines)


def gen_level(job, primary_text, companion_texts, companions, ceiling):
    """Generiert einen Artikel (max 3 Versuche)."""
    user_msg = make_user_msg(job, primary_text, companion_texts, companions, ceiling)
    for attempt in range(1, 4):
        try:
            raw = gemini_client.call_gemini(
                SYSTEM_PROMPT, user_msg,
                model=GEMINI_MODEL, thinking_config=phase2_cfg,
                response_mime_type="application/json",
            )
            art = parse_article_json(raw)
            n_s = sum(len(s.get("sentences", [])) for s in art.get("sections", []))
            if n_s < 3:
                raise RuntimeError(f"Nur {n_s} Sätze — nicht plausibel")
            return art, None
        except Exception as e:
            wait = [30, 60, 120][attempt - 1]
            if attempt < 3:
                print(f"      Versuch {attempt}: {e!s:.80} — warte {wait}s …")
                time.sleep(wait)
            else:
                return None, str(e)


# ── Hauptschleife ─────────────────────────────────────────────────────────────

csv_rows = []
all_errors = []

for thema, (c1, c2, c3) in PILOT_TARGETS.items():
    ceilings = {1: c1, 2: c2, 3: c3}
    print(f"\n{'='*62}")
    print(f"THEMA: {thema}  Ziele: S1={c1} S2={c2} S3={c3}")
    print("="*62)

    # Lemma auflösen
    resolved = thema
    flags    = []
    dd_note  = ""
    try:
        lr       = resolve_lemma(session, thema)
        resolved = lr.get("resolved_title") or thema
        flags    = lr.get("flags", [])
        dd       = lr.get("doppelbedeutung_directive")
        if dd:
            dd_note = dd.get("directive", "")
        flag_info = f"flags={flags}" if flags else "keine Flags"
        print(f"  Lemma: {resolved!r}  {flag_info}")
        if dd_note:
            print(f"  Direktive: {dd_note}")
        time.sleep(1.5)
    except Exception as e:
        print(f"  resolve_lemma Fehler: {e} — nutze thema direkt")

    # LISTENARTIKEL: weiter, aber flaggen
    has_list = any("Listenartikel" in f for f in flags)
    if has_list:
        print("  ⚠  LISTENARTIKEL-Flag — generiere trotzdem (manuelles Review nötig)")

    # Phase 1
    try:
        ptext, companions, ctexts, _imgs, _p1 = prepare_topic_sources(
            session, client, resolved, thema, "medium", GEMINI_MODEL, skip_images=True
        )
        print(f"  Companions: {companions or '—'}")
    except Exception as e:
        msg = f"Phase 1 FEHLER: {e}"
        print(f"  ✗ {msg}")
        all_errors.append(f"{thema}: {msg}")
        for lvl in (1, 2, 3):
            csv_rows.append([thema, lvl, resolved, ceilings[lvl], 0, 0, "FEHLER Phase 1"])
        continue

    # Phase 2: Stufen sequenziell
    for level in (1, 2, 3):
        ceiling = ceilings[level]
        print(f"\n  Stufe {level} ({AGE_RANGES[level]}) — Obergrenze {ceiling} Wörter …",
              end=" ", flush=True)

        job = {
            "article_id":        f"{re.sub(r'[^a-z0-9]', '_', thema.lower())}_l{level}",
            "thema":             thema,
            "primaer_wikipedia": resolved,
            "title":             thema,
            "age_level":         level,
            "topic_interest":    "medium",
            "resolved_appeal":   "medium",
            "pattern":           "factual",
            "category_top":      "diverses",
            "category_sub":      "diverses",
        }

        article, err = gen_level(job, ptext, ctexts, companions, ceiling)
        if err:
            print(f"FEHLER")
            all_errors.append(f"{thema} S{level}: {err}")
            csv_rows.append([thema, level, resolved, ceiling, 0, 0, f"FEHLER: {err[:60]}"])
            continue

        wc   = count_article_words(article)
        diff = wc - ceiling
        print(f"Ist={wc}  Δ={diff:+d}")

        # Flag-Strings für Markdown + CSV
        flag_strs = list(flags)  # z.B. ["BITTE PRUEFEN: Listenartikel"]
        if dd_note:
            flag_strs = [f for f in flag_strs if "Listenartikel" not in f]  # no dup
            flag_strs.append(f"DOPPELBEDEUTUNG: {dd_note}")
        csv_note = " | ".join(flag_strs) if flag_strs else "OK"

        # Markdown schreiben
        safe = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]", "_", thema)
        md_path = OUT_DIR / f"{safe}_S{level}.md"
        md_path.write_text(
            article_to_md(article, thema, level, resolved, flag_strs, wc, ceiling, companions),
            encoding="utf-8",
        )
        print(f"    → {md_path.relative_to(ROOT)}")

        csv_rows.append([thema, level, resolved, ceiling, wc, diff, csv_note])
        time.sleep(2.0)

# ── CSV ────────────────────────────────────────────────────────────────────────

csv_path = OUT_DIR / "pilot_wortzahlen.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Thema","Stufe","aufgelöstes_Lemma","Wortziel","Ist-Wortzahl","Differenz","Flags"])
    w.writerows(csv_rows)

print(f"\n{'='*62}")
print(f"CSV: {csv_path}")
print(f"Fertig: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC | "
      f"Fehler: {len(all_errors)}")
for e in all_errors:
    print(f"  ✗ {e}")

# Übersicht
print("\n── Wortzahl-Übersicht ──")
print(f"{'Thema':<16} {'S':>2}  {'Ziel':>5}  {'Ist':>5}  {'Δ':>5}  Flags")
print("-" * 55)
for row in csv_rows:
    thema_, lvl, _lem, ziel, ist, diff, note = row
    ok = "✓" if ist > 0 else "✗"
    d_str = f"{diff:+d}" if ist > 0 else "—"
    print(f"{thema_:<16} {lvl:>2}  {ziel:>5}  {ist:>5}  {d_str:>5}  {ok} {note}")
