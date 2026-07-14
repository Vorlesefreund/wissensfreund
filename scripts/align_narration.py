#!/usr/bin/env python3
"""
align_narration.py — Track B / M1: Forced Alignment → Wort-Timing-Sidecar.

Erzeugt aus (Artikel-JSON + Narrations-Audio) ein `{stem}.timing.json` mit
echten Wort-Zeitstempeln (torchaudio MMS_FA Forced Alignment), gemappt auf
Zeichen-Offsets im App-`plainText`. Läuft auf der GPU (RunPod). Nutzt das in der
Nico-Umgebung bereits vorhandene torch/torchaudio (kein Zusatz-Install).
Ersetzt das proportionale Test-Sidecar.

Kernidee — compose vs. plainText sauber trennen:
  * Das AUDIO spricht compose(): Überschrift(als Satz) + Sätze + Box-Intros + Box-Text,
    plus [pause]/[style]-Steuertags (keine Wörter). → wird 1:1 für das Alignment gebaut.
  * Der CURSOR indiziert plainText: NUR Überschriften + Sätze (WfArticleConverter).
  → Wir rekonstruieren die gesprochene Wortfolge MIT Herkunft: Überschrift-/Satz-Wörter
    tragen ihren plainText-Zeichen-Offset, Box-/Intro-Wörter tragen None (Cursor hält).
    WhisperX aligned die volle Wortfolge; wir emittieren Timings nur für gemappte Wörter.

Aufruf (auf dem Pod):
  python align_narration.py --json vulkan_l3.json --audio vulkan_l3_artikel.wav \
      --out vulkan_l3_artikel.timing.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# tts_compose liefert dieselben Intro-Phrasen/Emoji-Regeln wie die echte Vertonung.
import tts_compose as tc

CTRL_TAG = re.compile(r"\[[^\]]*\]")   # [pause=2.0], [thoughtful], [excited], [serious] …
WORD_RE  = re.compile(r"\S+")


def _norm(w: str) -> str:
    return re.sub(r"[^\wäöüÄÖÜß]", "", w.lower())


# MMS_FA-Wörterbuch kennt nur [a-z']; Deutsch romanisieren (nur fürs Alignment;
# die echten Zeichen-Offsets bleiben vom Rohtext).
_ROMAN = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s",
                        "é": "e", "è": "e", "ê": "e", "á": "a", "à": "a", "ó": "o"})

def _mms(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower().translate(_ROMAN))


def build_units(article: dict, stufe: str):
    """
    Baut die gesprochene Wortfolge in compose()-Reihenfolge, jedes Wort mit
    (token, cs, ce) — cs/ce = plainText-Zeichenbereich, oder (token, None, None)
    für Box-/Intro-Wörter (nicht im plainText). Parallel: plainText-Rekonstruktion
    identisch zu WfArticleConverter (Heading+\\n, Satz+' ' falls kein Space, trimRight).
    """
    buf: list[str] = []
    length = 0
    def emit(s: str):
        nonlocal length
        buf.append(s); length += len(s)

    units: list[tuple[str, int | None, int | None]] = []
    # plainText-Segmentgrenzen (Überschriften + Sätze) für echte Satz-Gruppierung.
    spans: list[tuple[int, int]] = []

    def add_mapped(raw: str, span_start: int):
        # Wörter aus dem ROHEN Text (= plainText-Inhalt) mit absoluten Offsets.
        for m in WORD_RE.finditer(raw):
            units.append((m.group(0), span_start + m.start(), span_start + m.end()))

    def add_skip(text: str):
        for m in WORD_RE.finditer(text):
            units.append((m.group(0), None, None))

    for sec in article.get("sections", []):
        heading = (sec.get("heading") or "")
        if heading.strip():
            start = length
            emit(heading); emit("\n")
            add_mapped(heading, start)          # Überschrift ist im plainText
            spans.append((start, start + len(heading)))

        for sent in sec.get("sentences", []):
            t = (sent.get("text") or "")
            if not t:
                continue
            start = length
            emit(t)
            if not t.endswith(" "):
                emit(" ")
            add_mapped(t, start)
            spans.append((start, start + len(t.rstrip())))

        # Boxen: gesprochen, aber NICHT im plainText → skip (Cursor hält).
        for box in sec.get("boxes", []):
            bt = tc.strip_emoji((box.get("text") or "").strip())
            if not bt:
                continue
            btype = (box.get("type") or "").strip()
            if btype == "stimmt_das":
                reveal = tc.strip_emoji((box.get("reveal_text") or "").strip())
                intro  = tc._phrase("stimmt_das", stufe)
                add_skip(f"{intro}{bt}")
                if reveal:
                    add_skip(tc._REVEAL_INTRO.get(stufe, "") + reveal)
            elif btype in ("wow", "warnung"):
                add_skip(tc._phrase(btype, stufe) + bt)
            else:
                add_skip(tc._phrase(btype, stufe) + bt)

    plain = "".join(buf).rstrip()
    return plain, units, spans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="de")
    args = ap.parse_args()

    article = json.loads(Path(args.json).read_text(encoding="utf-8"))
    level = article.get("meta", {}).get("age_level", 2)
    stufe = f"S{max(1, min(3, int(level)))}"

    plain, units, spans = build_units(article, stufe)
    print(f"[{Path(args.json).stem}] plainText={len(plain)} Zeichen | "
          f"gesprochene Wörter={len(units)} (davon gemappt {sum(1 for u in units if u[1] is not None)})")

    import torch, torchaudio
    from torchaudio.pipelines import MMS_FA as bundle
    device = "cuda" if torch.cuda.is_available() else "cpu"
    sr = bundle.sample_rate  # 16000

    wav, in_sr = torchaudio.load(args.audio)
    if wav.size(0) > 1:
        wav = wav.mean(0, keepdim=True)          # mono
    if in_sr != sr:
        wav = torchaudio.functional.resample(wav, in_sr, sr)
    dur = wav.size(1) / sr

    model = bundle.get_model().to(device)
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()

    # Transkript = romanisierte Wörter; leere (reine Satzzeichen) rausfiltern,
    # Index-Rückabbildung merken.
    mms_words, idx_map = [], []
    for i, (tok, _cs, _ce) in enumerate(units):
        m = _mms(tok)
        if m:
            mms_words.append(m); idx_map.append(i)

    with torch.inference_mode():
        emission, _ = model(wav.to(device))
    token_spans = aligner(emission[0], tokenizer(mms_words))
    ratio = wav.size(1) / emission.size(1) / sr  # Frame → Sekunden

    # Zeiten je Unit (leer-normalisierte Units erben die Nachbarzeit).
    t0s = [None] * len(units)
    t1s = [None] * len(units)
    for spans, ui in zip(token_spans, idx_map):
        t0s[ui] = spans[0].start * ratio
        t1s[ui] = spans[-1].end * ratio
    print(f"  aligned {len(token_spans)}/{len(mms_words)} Wörter | Audio {dur:.1f}s")

    words_out = []
    last_t = 0.0
    for i, (tok, cs, ce) in enumerate(units):
        t0 = t0s[i] if t0s[i] is not None else last_t
        t1 = t1s[i] if t1s[i] is not None else t0
        last_t = t1
        if cs is not None:  # nur plainText-Wörter in die Cursor-Timeline
            words_out.append({"cs": cs, "ce": ce,
                              "t0": round(t0 * 1000), "t1": round(t1 * 1000)})

    # Sätze: echte plainText-Segmentgrenzen (Überschriften + Sätze). Jedes Segment
    # sammelt die Wörter, deren Zeichenbereich hineinfällt, und erbt deren Zeitspanne.
    sentences = []
    for (ss, se) in spans:
        inside = [w for w in words_out if w["cs"] >= ss and w["ce"] <= se]
        if not inside:
            continue
        sentences.append({
            "cs": ss, "ce": se,
            "t0": min(w["t0"] for w in inside),
            "t1": max(w["t1"] for w in inside),
        })

    Path(args.out).write_text(json.dumps({
        "audio": Path(args.audio).name,
        "dur_ms": round(dur * 1000),
        "words": words_out,
        "sentences": sentences,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {args.out} ({len(words_out)} Cursor-Wörter, {len(sentences)} Sätze)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
