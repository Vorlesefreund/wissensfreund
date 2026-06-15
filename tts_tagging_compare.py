#!/usr/bin/env python3
"""
tts_tagging_compare.py  v1  (2026-06-15)
Wissensfreund — TTS-Tagging Modell-Vergleich

Taggt dieselben Artikel-Stufen mit Flash, Haiku und Sonnet und erzeugt
einen HTML-Vergleich (getaggter Text nebeneinander + sound_mood).
KEIN TTS-Audio — nur die Tag-Annotation (das ist der zu vergleichende Schritt).

Nutzung:
  python tts_tagging_compare.py --articles Elefant Vulkan Weihnachten
  python tts_tagging_compare.py --dir pilot_output3   # alle .md dort

Voraussetzung:
  pip install anthropic google-genai
  ANTHROPIC_API_KEY + GEMINI_API_KEY in .env oder Umgebung
"""

import os, sys, json, re, pathlib, argparse, time

TAGGING_PROMPT = pathlib.Path("wissensfreund_tts_tagging_v1.md")
OUT_DIR        = pathlib.Path("tts_tagging_compare_out")

# Modelle: (Anzeigename, Provider, Modell-ID)
MODELS = [
    ("Gemini Flash", "gemini",    "gemini-3.5-flash"),
    ("Haiku 4.5",    "anthropic", "claude-haiku-4-5-20251001"),
    ("Sonnet 4.6",   "anthropic", "claude-sonnet-4-6"),
]

STUFE_LABEL = {"1": "S1", "2": "S2", "3": "S3"}


def load_env():
    env = pathlib.Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def load_system_prompt() -> str:
    if not TAGGING_PROMPT.exists():
        sys.exit(f"FEHLER: {TAGGING_PROMPT} nicht gefunden.")
    return TAGGING_PROMPT.read_text(encoding="utf-8")


def build_user_msg(text: str, stufe: str) -> str:
    return (
        f"Stufe: {stufe}\n\n"
        f"Artikeltext (tag-frei):\n{text}\n\n"
        f"Füge Inline-Tags gemäß den Regeln für {stufe} ein und gib das JSON-Objekt aus.\n"
        f"WICHTIG JSON: Typografische Anführungszeichen (‚', „“, »«) exakt beibehalten. "
        f"Gerade ASCII-Anführungszeichen (\") im tts_text-Wert IMMER als \\\" escapen."
    )


def _decode_json_str(s: str) -> str:
    """Decode standard JSON string escape sequences."""
    return (s.replace("\\n", "\n").replace("\\t", "\t")
             .replace('\\"', '"').replace("\\\\", "\\")
             .replace("\\r", "\r").replace("\\/", "/"))


def extract_json(raw: str) -> dict | None:
    t = raw.strip()
    t = re.sub(r"^```[a-z]*\n?", "", t).rstrip("`").strip()

    # Standard parse
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    # Positional fallback: extract tts_text and sound_mood by location.
    # Works even when the model emits unescaped " inside the tts_text value.
    sound_m = re.search(r'"sound_mood"\s*:\s*"([^"]*)"', t)
    tts_key_m = re.search(r'"tts_text"\s*:\s*"', t)
    if tts_key_m and sound_m:
        val_start = tts_key_m.end()           # char after opening "
        sound_pos = sound_m.start()
        # rightmost " before the sound_mood key = closing " of tts_text value
        val_end = t.rfind('"', val_start, sound_pos)
        if val_end > val_start:
            tts_decoded = _decode_json_str(t[val_start:val_end])
            stufe_m = re.search(r'"stufe"\s*:\s*"([^"]*)"', t)
            return {
                "tts_text": tts_decoded,
                "sound_mood": sound_m.group(1),
                "stufe": stufe_m.group(1) if stufe_m else "",
                "_fallback": True,
            }
    return None


def call_anthropic(model_id: str, system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model_id, max_tokens=8192,
        system=system, messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def call_gemini(model_id: str, system: str, user: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=8192,
                    temperature=0.7,
                ),
            )
            if resp.text is None:
                raise ValueError("Leere Antwort (None)")
            return resp.text
        except Exception as e:
            if "503" in str(e) and attempt == 0:
                time.sleep(5)
                continue
            raise


def tag_one(provider: str, model_id: str, system: str, text: str, stufe: str) -> dict:
    user = build_user_msg(text, stufe)
    try:
        raw = call_gemini(model_id, system, user) if provider == "gemini" \
              else call_anthropic(model_id, system, user)
    except Exception as e:
        return {"error": str(e), "tts_text": "", "sound_mood": ""}
    data = extract_json(raw)
    if not data:
        return {"error": "JSON-Parse fehlgeschlagen", "raw": raw[:500],
                "tts_text": "", "sound_mood": ""}
    return data


def read_articles_from_dir(d: pathlib.Path) -> list[tuple[str, str, str]]:
    """Liest *_S{1,2,3}.md → (thema, stufe, text)."""
    out = []
    for f in sorted(d.glob("*_S*.md")):
        m = re.match(r"(.+)_S([123])\.md$", f.name)
        if not m:
            continue
        thema, stufe = m.group(1), STUFE_LABEL[m.group(2)]
        out.append((thema, stufe, f.read_text(encoding="utf-8")))
    return out


def build_html(results: list[dict]) -> str:
    """results: [{thema, stufe, original, models:{name:{tts_text,sound_mood,error}}}]"""
    rows = ""
    for r in results:
        model_cols = ""
        for name, _, _ in MODELS:
            md = r["models"].get(name, {})
            if md.get("error"):
                body = f'<div class="err">FEHLER: {md["error"]}</div>'
            else:
                tts = (md.get("tts_text", "") or "").replace("[", '<span class="tag">[').replace("]", "]</span>")
                mood = md.get("sound_mood", "—")
                body = f'<div class="tts">{tts}</div><div class="mood">🎵 {mood}</div>'
            model_cols += f'<td><div class="mname">{name}</div>{body}</td>'
        rows += (
            f'<tr><td class="meta"><b>{r["thema"]}</b><br>{r["stufe"]}'
            f'<div class="orig">{r["original"][:400]}…</div></td>'
            f'{model_cols}</tr>'
        )

    headers = "".join(f"<th>{n}</th>" for n, _, _ in MODELS)
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>TTS-Tagging Vergleich</title><style>
body{{font-family:Arial,sans-serif;margin:16px;background:#f5f5f5}}
h1{{color:#1F4E79}}
table{{border-collapse:collapse;width:100%;background:white}}
th,td{{border:1px solid #ddd;padding:10px;vertical-align:top;font-size:.85em}}
th{{background:#1F4E79;color:white;position:sticky;top:0}}
td.meta{{width:200px;background:#fafafa;font-size:.8em}}
.orig{{color:#999;font-size:.85em;margin-top:6px;font-style:italic}}
.mname{{font-weight:bold;color:#1F4E79;margin-bottom:4px}}
.tts{{line-height:1.6}}
.tag{{color:#2E7D32;font-weight:bold;font-size:.9em}}
.mood{{margin-top:8px;color:#666;font-size:.8em;font-style:italic}}
.err{{color:#c00}}
</style></head><body>
<h1>🎙️ TTS-Tagging Modell-Vergleich</h1>
<p>Grün = eingefügte Tags. Vergleiche Platzierung, Dichte, Stufengerechtigkeit.</p>
<table><thead><tr><th>Artikel</th>{headers}</tr></thead>
<tbody>{rows}</tbody></table></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="Verzeichnis mit *_S{1,2,3}.md Dateien")
    ap.add_argument("--articles", nargs="+",
                    help="Einzelne Themen (sucht *_S*.md in pilot_output3/)")
    args = ap.parse_args()

    load_env()
    OUT_DIR.mkdir(exist_ok=True)
    system = load_system_prompt()

    # Artikel sammeln
    articles = []
    if args.dir:
        articles = read_articles_from_dir(pathlib.Path(args.dir))
    elif args.articles:
        base = pathlib.Path("pilot_output3")
        for thema in args.articles:
            for f in sorted(base.glob(f"{thema}_S*.md")):
                m = re.match(r"(.+)_S([123])\.md$", f.name)
                if m:
                    articles.append((m.group(1), STUFE_LABEL[m.group(2)],
                                     f.read_text(encoding="utf-8")))
    if not articles:
        sys.exit("Keine Artikel gefunden. --dir oder --articles angeben.")

    print(f"{len(articles)} Artikel-Stufen × {len(MODELS)} Modelle = "
          f"{len(articles)*len(MODELS)} Tagging-Calls\n")

    results = []
    for thema, stufe, text in articles:
        print(f"  {thema} {stufe}")
        entry = {"thema": thema, "stufe": stufe, "original": text, "models": {}}
        for name, provider, model_id in MODELS:
            print(f"    → {name} …", end=" ", flush=True)
            t0 = time.time()
            md = tag_one(provider, model_id, system, text, stufe)
            entry["models"][name] = md
            status = "OK" if not md.get("error") else f"FEHLER ({md['error'][:40]})"
            print(f"{status} [{time.time()-t0:.1f}s]")
            time.sleep(1)
        results.append(entry)

    # JSON + HTML speichern
    (OUT_DIR / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = OUT_DIR / "tts_tagging_compare.html"
    html_path.write_text(build_html(results), encoding="utf-8")
    print(f"\nVergleich: {html_path.resolve()}")
    print("→ Im Browser öffnen, Tag-Platzierung der 3 Modelle vergleichen.")


if __name__ == "__main__":
    main()
