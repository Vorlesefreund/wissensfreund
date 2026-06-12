#!/usr/bin/env python3
"""
Pilot-Generierung 2: 7 Themen × 3 Stufen — Verifikation WORTZIEL-Fix.
Geänderte Variable: WORTZIEL-Wording (angestrebte Länge, nicht Obergrenze).
Ausgabe: pilot_output2/<Thema>_S<N>.md + pilot_wortzahlen2.csv
"""
import csv, os, re, sys, time
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
from generate_articles import parse_article_json, USER_AGENT
from generate_articles import resolve_lemma
from generate_grounded import (
    prepare_topic_sources, build_grounded_user_message,
    count_article_words, GEMINI_MODEL, SYSTEM_PROMPT_PATH,
)

# ── 7 Verifikations-Themen (identische Ziele wie Lauf 1) ─────────────────────
PILOT_TARGETS = {  # thema → (wmax_S1, wmax_S2, wmax_S3)
    "Elefant":     (250, 400, 650),
    "Hund":        (250, 400, 650),
    "Dinosaurier": (250, 400, 650),
    "Vulkan":      (217, 400, 650),
    "Fußball":     (183, 400, 650),
    "Wirtschaft":  (117, 347, 650),
    "Kühlschrank":  (83, 240, 375),
}

# wmin je Stufe (Untergrenze der Ziel-Spanne) — unveränderlich
WMIN = {1: 50, 2: 80, 3: 100}

AGE_RANGES = {1: "4–6 Jahre", 2: "7–9 Jahre", 3: "10–12 Jahre"}

OUT_DIR = ROOT / "pilot_output2"
OUT_DIR.mkdir(exist_ok=True)
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text("utf-8")

# Identische Konfiguration wie Lauf 1
try:
    phase2_cfg = gtypes.ThinkingConfig(thinking_level=gtypes.ThinkingLevel.LOW)
except AttributeError:
    phase2_cfg = gtypes.ThinkingConfig(thinking_budget=2048)

client  = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def make_user_msg(job, primary_text, companion_texts, companion_order, wmax):
    """Stabiler Prefix + neues WORTZIEL-Wording mit angestrebter Länge."""
    full = build_grounded_user_message(
        job, primary_text, companion_texts, companion_order, []
    )
    lines = full.rstrip("\n").split("\n")
    while lines and (lines[-1].startswith("WORTZIEL:") or lines[-1].startswith("AGE_LEVEL:")):
        lines.pop()
    stable = "\n".join(lines)
    wmin = WMIN[job["age_level"]]
    suffix = (
        f"AGE_LEVEL: {job['age_level']}\n"
        f"WORTZIEL: Zielumfang ungefähr {wmax} Wörter. Das ist die ANGESTREBTE Länge, KEINE Obergrenze. "
        f"Schöpfe den Wikipedia-Stoff aus und entfalte alle Aspekte vollständig, bis du den Zielumfang erreichst. "
        f"Kürzer (minimal {wmin} Wörter) nur, wenn der Wikipedia-Artikel den Stoff für {wmax} nicht hergibt — niemals aufblähen."
    )
    return stable + "\n" + suffix


def article_to_md(article, thema, level, lemma, flag_strs, wc, wmax, companions):
    lines = [
        f"# {thema} — Stufe {level} ({AGE_RANGES[level]})",
        "",
        f"**Lemma:** `{lemma}`  ",
        f"**Flags:** {', '.join(flag_strs) if flag_strs else '—'}  ",
        f"**Companions:** {', '.join(companions) if companions else '—'}  ",
        f"**Zielumfang: {wmax}** | **Ist:** {wc} | **Δ:** {wc - wmax:+d}",
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


def gen_level(job, primary_text, companion_texts, companions, wmax):
    user_msg = make_user_msg(job, primary_text, companion_texts, companions, wmax)
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
                raise RuntimeError(f"Nur {n_s} Sätze")
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
    wmaxes = {1: c1, 2: c2, 3: c3}
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

    if any("Listenartikel" in f for f in flags):
        print("  ⚠  LISTENARTIKEL-Flag")

    # Phase 1
    try:
        ptext, companions, ctexts, _imgs, _p1 = prepare_topic_sources(
            session, client, resolved, thema, "medium", GEMINI_MODEL, skip_images=True
        )
        quelle_kb = round(len(ptext) / 1024, 1)
        companion_count = len(ctexts)
        print(f"  Lemma→WP: {quelle_kb} kB | Companions geladen: {companion_count} {list(ctexts)}")
    except Exception as e:
        msg = f"Phase 1 FEHLER: {e}"
        print(f"  ✗ {msg}")
        all_errors.append(f"{thema}: {msg}")
        flag_str = " | ".join(flags) if flags else "OK"
        for lvl in (1, 2, 3):
            csv_rows.append([thema, lvl, resolved, flag_str, 0, 0, wmaxes[lvl], 0, 0])
        continue

    # Phase 2: Stufen sequenziell
    for level in (1, 2, 3):
        wmax = wmaxes[level]
        print(f"\n  Stufe {level} ({AGE_RANGES[level]}) — Ziel ~{wmax} Wörter …",
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

        article, err = gen_level(job, ptext, ctexts, companions, wmax)
        if err:
            print("FEHLER")
            all_errors.append(f"{thema} S{level}: {err}")
            flag_str = " | ".join(flags) if flags else "OK"
            csv_rows.append([thema, level, resolved, flag_str, companion_count,
                             quelle_kb, wmax, 0, 0])
            continue

        wc   = count_article_words(article)
        diff = wc - wmax
        print(f"Ist={wc}  Δ={diff:+d}")

        flag_strs = list(flags)
        if dd_note:
            flag_strs = [f for f in flag_strs if "Listenartikel" not in f]
            flag_strs.append(f"DOPPELBEDEUTUNG: {dd_note}")
        flag_str = " | ".join(flag_strs) if flag_strs else "OK"

        safe = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]", "_", thema)
        md_path = OUT_DIR / f"{safe}_S{level}.md"
        md_path.write_text(
            article_to_md(article, thema, level, resolved, flag_strs, wc, wmax, list(ctexts)),
            encoding="utf-8",
        )
        print(f"    → {md_path.relative_to(ROOT)}")

        csv_rows.append([thema, level, resolved, flag_str, companion_count,
                         quelle_kb, wmax, wc, diff])
        time.sleep(2.0)


# ── CSV ────────────────────────────────────────────────────────────────────────

csv_path = OUT_DIR / "pilot_wortzahlen2.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["thema", "stufe", "lemma", "flags", "companion_count",
                "quelle_kB", "zielumfang_wmax", "ist_woerter", "delta"])
    w.writerows(csv_rows)

print(f"\n{'='*62}")
print(f"CSV: {csv_path}")
print(f"Fertig: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC | Fehler: {len(all_errors)}")
for e in all_errors:
    print(f"  ✗ {e}")

# Übersicht
print("\n── Wortzahl-Übersicht ──")
print(f"{'Thema':<14} {'S':>2}  {'Ziel':>5}  {'Ist':>5}  {'Δ':>6}  {'kB':>5}  {'Comp':>4}")
print("-" * 55)
for row in csv_rows:
    thema_, lvl, _lem, _fl, comp, kb, ziel, ist, diff = row
    ok = "✓" if ist > 0 else "✗"
    d_str = f"{diff:+d}" if ist > 0 else "—"
    print(f"{thema_:<14} {lvl:>2}  {ziel:>5}  {ist:>5}  {d_str:>6}  {kb:>5}  {comp:>4}  {ok}")
