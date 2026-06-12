#!/usr/bin/env python3
"""
Lauf 3 Retry: nur Hund × 3 Stufen.
Netzwerk-Retry um prepare_topic_sources (3 Versuche, Backoff 2s/5s/10s).
Ersetzt die 3 Hund-Zeilen in pilot_wortzahlen3.csv.
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
from generate_articles import parse_article_json, USER_AGENT, resolve_lemma
from generate_grounded import (
    prepare_topic_sources, build_grounded_user_message,
    count_article_words, GEMINI_MODEL, SYSTEM_PROMPT_PATH,
)

WMAXES    = {1: 250, 2: 400, 3: 650}
AGE_RANGES = {1: "4–6 Jahre", 2: "7–9 Jahre", 3: "10–12 Jahre"}
OUT_DIR   = ROOT / "pilot_output3"
OUT_DIR.mkdir(exist_ok=True)
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text("utf-8")
CSV_PATH  = OUT_DIR / "pilot_wortzahlen3.csv"

try:
    phase2_cfg = gtypes.ThinkingConfig(thinking_level=gtypes.ThinkingLevel.LOW)
except AttributeError:
    phase2_cfg = gtypes.ThinkingConfig(thinking_budget=2048)

client  = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def prepare_with_retry(session, client, resolved, thema, appeal, model):
    """Netzwerk-Retry für transiente ConnectionError / Reset / Timeout."""
    backoffs = [2, 5, 10]
    for attempt, wait in enumerate(backoffs, 1):
        try:
            return prepare_topic_sources(
                session, client, resolved, thema, appeal, model, skip_images=True
            )
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                OSError) as e:
            if attempt == len(backoffs):
                raise
            print(f"  Netzwerk-Fehler (Versuch {attempt}): {e!s:.80} — warte {wait}s …")
            time.sleep(wait)


def make_user_msg(job, primary_text, companion_texts, companion_order, wmax):
    full = build_grounded_user_message(job, primary_text, companion_texts, companion_order, [])
    lines = full.rstrip("\n").split("\n")
    while lines and (lines[-1].startswith("WORTZIEL:") or lines[-1].startswith("AGE_LEVEL:")):
        lines.pop()
    stable = "\n".join(lines)
    suffix = (
        f"AGE_LEVEL: {job['age_level']}\n"
        f"WORTZIEL: Strebe {wmax} Wörter an und schöpfe den Wikipedia-Stoff so weit aus, dass du nah an {wmax} herankommst. "
        f"{wmax} ist zugleich die harte Obergrenze — schreibe nicht darüber hinaus. "
        f"Wenn nach Erreichen von {wmax} noch Stoff übrig ist, wähle die kindgerechtesten Aspekte aus, statt alles aufzunehmen. "
        f"Kürzer als {wmax} nur, wenn der Wikipedia-Stoff die Länge nicht hergibt — niemals aufblähen."
    )
    return stable + "\n" + suffix


def article_to_md(article, level, lemma, flag_strs, wc, wmax, companions):
    lines = [
        f"# Hund — Stufe {level} ({AGE_RANGES[level]})", "",
        f"**Lemma:** `{lemma}`  ",
        f"**Flags:** {', '.join(flag_strs) if flag_strs else '—'}  ",
        f"**Companions:** {', '.join(companions) if companions else '—'}  ",
        f"**Zielumfang: {wmax}** | **Ist:** {wc} | **Δ:** {wc - wmax:+d}", "", "---", "",
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


def gen_level(job, ptext, ctexts, companions, wmax):
    user_msg = make_user_msg(job, ptext, ctexts, companions, wmax)
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


print("=== Hund Retry (Lauf 3 Wording, Netzwerk-Retry aktiv) ===")

lr       = resolve_lemma(session, "Hund")
resolved = lr.get("resolved_title") or "Hund"
flags    = lr.get("flags", [])
print(f"  Lemma: {resolved!r}  {'flags='+str(flags) if flags else 'keine Flags'}")
time.sleep(1.5)

ptext, companions, ctexts, _imgs, _p1 = prepare_with_retry(
    session, client, resolved, "Hund", "medium", GEMINI_MODEL
)
quelle_kb       = round(len(ptext) / 1024, 1)
companion_count = len(ctexts)
print(f"  Lemma→WP: {quelle_kb} kB | Companions: {companion_count} {list(ctexts)}")

new_hund_rows = []
for level in (1, 2, 3):
    wmax = WMAXES[level]
    print(f"\n  Stufe {level} ({AGE_RANGES[level]}) — Ziel ~{wmax} Wörter …", end=" ", flush=True)
    job = {
        "article_id":        f"hund_l{level}",
        "thema":             "Hund",
        "primaer_wikipedia": resolved,
        "title":             "Hund",
        "age_level":         level,
        "topic_interest":    "medium",
        "resolved_appeal":   "medium",
        "pattern":           "factual",
        "category_top":      "tiere",
        "category_sub":      "haustiere",
    }
    article, err = gen_level(job, ptext, ctexts, companions, wmax)
    if err:
        print(f"FEHLER: {err}")
        new_hund_rows.append(["Hund", level, resolved, "OK", companion_count, quelle_kb, wmax, 0, 0])
        continue

    wc   = count_article_words(article)
    diff = wc - wmax
    print(f"Ist={wc}  Δ={diff:+d}")

    md_path = OUT_DIR / f"Hund_S{level}.md"
    md_path.write_text(
        article_to_md(article, level, resolved, list(flags), wc, wmax, list(ctexts)),
        encoding="utf-8",
    )
    print(f"    → {md_path.relative_to(ROOT)}")
    new_hund_rows.append(["Hund", level, resolved, "OK", companion_count, quelle_kb, wmax, wc, diff])
    time.sleep(2.0)

# Hund-Zeilen in CSV ersetzen
existing = []
if CSV_PATH.exists():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        existing = [row for row in reader if row[0] != "Hund"]

with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(existing)
    w.writerows(new_hund_rows)

print(f"\nFertig: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
print("\n── Hund Wortzahlen ──")
for row in new_hund_rows:
    _, lvl, _, _, comp, kb, ziel, ist, diff = row
    ok = "✓" if ist > 0 else "✗"
    d_str = f"{diff:+d}" if ist > 0 else "—"
    print(f"Hund  S{lvl}  Ziel={ziel}  Ist={ist}  Δ={d_str}  {kb}kB  {comp}Comp  {ok}")
