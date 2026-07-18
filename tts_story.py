#!/usr/bin/env python3
"""tts_story.py — Mehrsprecher-Vertonung für den Story-Modus (4–8 J.).

Eine Wissensgeschichte hat drei Sprecher: Erzähler + neugieriges Kind + erwachsene
Person. Dieses Skript
  1) segmentiert die fertige Geschichte per Modell in Sprecher-Turns (Wortlaut bleibt),
  2) rendert jeden Turn mit der ZUGEORDNETEN Stimme (Gemini-TTS, eine Stimme je Call),
  3) schneidet die PCM-Segmente mit kurzen Pausen zu EINER WAV zusammen ("das Schneiden").

Stimmen (Prebuilt): Erzähler=Iapetus · Kind ♂=Puck ♀=Leda · Erwachsener ♂=Gacrux ♀=Vindemiatrix.

  # aus Roh-Prosa (schnell, keine Neugenerierung):
  python -X utf8 tts_story.py --story-file story.txt --titel "Leonardo" --out-dir "C:/Users/Andreas/Desktop/_vertonung"
  # oder frisch aus dem Checkpoint erzeugen und vertonen:
  python -X utf8 tts_story.py --checkpoint <cp.json> --thema "Leonardo da Vinci" --model claude-sonnet-5 --out-dir DIR
"""
from __future__ import annotations
import argparse, array, json, logging, random, re, subprocess, sys, time, wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

SAMPLE_RATE = 24000          # Gemini liefert PCM 24 kHz mono 16-bit
TTS_MODEL   = "gemini-3.1-flash-tts-preview"
GAP_TURN    = 0.35           # Pause zwischen Turns desselben Sprechers / kurzer Wechsel
GAP_SCENE   = 0.75           # Pause an Szenen-/Absatzgrenzen

TTS_TIMEOUT_MS = 60_000      # Das SDK hat KEIN Default-Timeout — ohne das hängt ein Call unbegrenzt.
RETRY_BASE_S   = 6           # Backoff: 6s → 12s → 24s … (+ bis zu 30 % Jitter)
RETRY_MAX_S    = 90
QA_VERSUCHE    = 3           # Sync: so oft neu synthetisieren, wenn die QA Ausschuss meldet.
TTS_TEMPERATURE = 0.3        # Gilt für ALLE Rollen, auch Kind-Turns mit VC.
                             # Rohe Quelle: default ±54 Hz Grundton-Streuung, t0.3 ±16 Hz.
                             # NACH der VC ist die Tonhöhe temperature-unabhängig ruhig (±2–11 Hz,
                             # egal welche Stufe) — die Tonhöhe ist also KEIN Argument mehr.
                             # Entscheidend war das Hörurteil des PO (2026-07-16): t0.3 klingt im
                             # VORTRAG am überzeugendsten. Betonung/Sprechmelodie stammen aus dem
                             # Flash-Original und überleben die VC (die überträgt nur die Klangfarbe)
                             # — deshalb wirkt temperature dort weiter, messbar ist es per F0 nicht.
                             # Samples: Desktop/_nico_temp_vergleich (2 Sätze × 3 Stufen × 3 Nahmen).

# ── Stimm-Zuordnung + (bewusst zurückgenommene) Stil-Vorgaben ──────────────────
VOICES = {
    "erzähler":          "Iapetus",
    ("kind", "m"):       "Puck",
    ("kind", "w"):       "Leda",
    ("erwachsener", "m"): "Gacrux",
    ("erwachsener", "w"): "Vindemiatrix",
}
STYLE = {
    "erzähler":     "Lies ruhig und warm vor, wie ein guter Vorlese-Erzähler. Natürlich und unaufgeregt, ein leises Lächeln in der Stimme.",
    "kind":         "Sprich als neugieriges Kind: natürlich lebendig und interessiert, aber nicht überdreht.",
    "erwachsener":  "Sprich warm, geduldig und erklärend, mit einem Lächeln — ruhig, nicht theatralisch.",
}

# ── Segmentierung (Modell) ─────────────────────────────────────────────────────
SEG_SYSTEM = """Du zerlegst eine vorgelesene Kindergeschichte in SPRECHER-ABSCHNITTE für eine Vertonung mit verschiedenen Stimmen. Der vertonte Text MUSS Wort für Wort der Vorlage entsprechen (Text = Audio, damit die Mitlese-Lupe am Tablet exakt mitgleitet): NICHTS weglassen, NICHTS umformulieren, NICHTS hinzufügen. Aufgeteilt wird NUR an den Grenzen der wörtlichen Rede, und jede Hälfte bekommt die richtige Stimme.

Drei Sprecher-Rollen:
- "kind": die wörtliche Rede des neugierigen Kindes (nur der Teil in Anführungszeichen).
- "erwachsener": die wörtliche Rede der erwachsenen Person, die erklärt (nur der Teil in Anführungszeichen).
- "erzähler": ALLES ANDERE — Umgebung, Szene, Handlungen UND die Redebegleitsätze ("fragt Theo", "sagt Oma Rina", "antwortet sie"). Der Erzähler SPRICHT diese Redebegleitsätze MIT; sie werden NICHT weggelassen.

REGELN (Text = Audio, verbatim):
- Teile jeden Satz an den Anführungszeichen: der Teil INNERHALB der Anführungszeichen wird ein Turn mit der Rolle des Sprechers, der Teil AUSSERHALB (Redebegleitsatz + Handlung + Erzählung) wird ein erzähler-Turn. Beispiel: `"Wer ist das?", fragt Theo und tippt mit dem Finger auf das Bild.` → kind: "Wer ist das?" · erzähler: "fragt Theo und tippt mit dem Finger auf das Bild." — Beispiel: `"Das ist die Mona Lisa", sagt Oma Rina.` → erwachsener: "Das ist die Mona Lisa" · erzähler: "sagt Oma Rina."
- Reihenfolge = exakte Textreihenfolge. Wird wörtliche Rede durch einen Redebegleitsatz UNTERBROCHEN ("A", sagt X, "B"), entstehen DREI Turns in genau dieser Reihenfolge: Sprecher "A" · erzähler "sagt X," · Sprecher "B". NICHT zusammenziehen.
- Aus der wörtlichen Rede werden NUR die Anführungszeichen entfernt; die Wörter und die Satzzeichen INNERHALB (z. B. das "?") bleiben unverändert. Der erzähler-Text bleibt vollständig verbatim (inkl. "fragt Theo", "und tippt…"); Satzzeichen am Rand (Komma/Punkt) bleiben.
- Fasse direkt aufeinanderfolgende Abschnitte DERSELBEN Rolle zu EINEM Turn zusammen (z. B. mehrere reine Erzählsätze hintereinander, oder Redebegleitsatz + direkt folgender Erzählsatz). Sprecher-Rede und Erzähler-Teil aber NIE mischen. KEINE Umformulierung, damit ein Fragment „grammatisch" wird — der Wortlaut der Vorlage zählt.
- Ordne jede Rede der richtigen Rolle zu (an der Redebegleitung erkennbar: sagt Oma → erwachsener; fragt Nico → kind).
- setze szene=true beim ersten Turn eines neuen Absatzes/Schauplatzwechsels, sonst false.

VORTRAG / EMOTION (Feld "emotion", kurzer deutscher Hinweis 1–4 Wörter, sonst ""):
- Gib pro Sprech-Turn (kind/erwachsener) einen Vortrags-Hinweis, abgeleitet aus Redebegleitsatz UND Kontext: z. B. "lächelnd", "amüsiert", "aufgeregt", "leise, geheimnisvoll", "ernst, behutsam", "staunend", "traurig". Neutral → "".
- Beschreibt eine UNMITTELBAR davorstehende Handlung die Stimmung der folgenden Rede ("Oma Rina lacht." vor Omas Satz), übernimm sie in das emotion-Feld dieses Sprech-Turns (z. B. "amüsiert, lachend").
- Passt der ernste/fröhliche Charakter des INHALTS (z. B. ein trauriges Thema), darf das die emotion mitbestimmen.
- erzähler-Turns: "emotion" meist "".

Bestimme außerdem den CAST: Name + Geschlecht (m/w) des Kindes und der erwachsenen Person.

Antworte NUR als JSON: {"cast":{"kind":{"name":"...","geschlecht":"m|w"},"erwachsener":{"name":"...","geschlecht":"m|w"}},"turns":[{"rolle":"erzähler|kind|erwachsener","text":"...","szene":true|false,"emotion":"..."}]}"""

SEG_SCHEMA = {
    "type": "object",
    "required": ["cast", "turns"],
    "properties": {
        "cast": {"type": "object", "required": ["kind", "erwachsener"], "properties": {
            "kind":       {"type": "object", "required": ["name", "geschlecht"],
                           "properties": {"name": {"type": "string"}, "geschlecht": {"type": "string"}}},
            "erwachsener": {"type": "object", "required": ["name", "geschlecht"],
                           "properties": {"name": {"type": "string"}, "geschlecht": {"type": "string"}}}}},
        "turns": {"type": "array", "items": {
            "type": "object", "required": ["rolle", "text", "szene", "emotion"],
            "properties": {"rolle": {"type": "string"}, "text": {"type": "string"},
                           "szene": {"type": "boolean"}, "emotion": {"type": "string"}}}},
    },
}


def segment_story(story_text: str, model: str = "claude-sonnet-5") -> dict:
    body = ("GESCHICHTE:\n" + story_text + "\n\n"
            "AUFGABE: Zerlege sie nach deinen Regeln in Sprecher-Turns und bestimme den Cast. Nur JSON.")
    if model.startswith("claude"):
        import claude_client
        return claude_client.call_claude_json(SEG_SYSTEM, body, SEG_SCHEMA,
                                               model=model, max_tokens=8192, call_name="tts_seg") or {}
    import gemini_client
    raw = gemini_client.call_gemini(SEG_SYSTEM, body, model=model,
                                    response_mime_type="application/json",
                                    response_schema=SEG_SCHEMA, call_name="tts_seg")
    return json.loads(raw)


def _voice_for(rolle: str, cast: dict) -> str:
    if rolle == "erzähler":
        return VOICES["erzähler"]
    g = ((cast.get(rolle) or {}).get("geschlecht") or "m").lower()[:1]
    g = g if g in ("m", "w") else "m"
    return VOICES.get((rolle, g), VOICES["erzähler"])


def _style_for(rolle: str, turn: dict) -> str:
    """Rollen-Grundstil + optionaler Vortrags-Hinweis (emotion) aus der Segmentierung."""
    base = STYLE.get(rolle, STYLE["erzähler"])
    emo = (turn.get("emotion") or "").strip()
    return f"{base} Sprich diesen Satz {emo}." if emo else base


# ── TTS + Schnitt ──────────────────────────────────────────────────────────────
def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(round(seconds * SAMPLE_RATE))


def _trim_stille(pcm: bytes) -> bytes:
    """Führende/abschließende Stille abschneiden (Detail + Begründung in tts_qa.trim_stille).
    Lazy import: zieht faster-whisper NICHT mit (das lädt tts_qa erst bei der Transkription)."""
    from tts_qa import trim_stille
    return trim_stille(pcm, sample_rate=SAMPLE_RATE)


ZIEL_SPRECH_RMS = 6000      # Sprech-RMS-Zielpegel, gemessen am Median korrekt normalisierter Turns
PEAK_LIMIT      = 30000     # int16-Headroom gegen Clipping (max 32767)


def _sprech_rms(pcm: bytes) -> float:
    """RMS NUR über die Sprech-Samples (Stille raus) — so hängt der Pegel nicht an der Cliplänge
    oder am Stille-Anteil. Ein kurzer „sagt Oma Rina."-Fetzen und ein langer Satz werden vergleichbar."""
    if not pcm:
        return 0.0
    a = array.array("h"); a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    laut = [x for x in a if abs(x) > 200]
    if not laut:
        return 0.0
    return (sum(x * x for x in laut) / len(laut)) ** 0.5


def _loudnorm(pcm: bytes, sr: int = SAMPLE_RATE) -> bytes:
    """Bringt jeden Turn auf einen EINHEITLICHEN Sprech-Pegel — wichtig, weil VC-Kind-Turns und
    Flash-Erwachsenen-/Erzähler-Turns sonst im Pegel springen.

    Bewusst RMS-Gain statt ffmpeg ``loudnorm=I=-16``: der EBU-R128-loudnorm ist bei KURZEN Clips
    unzuverlässig — auf dem Pod lieferte er am 18.07. bei „Wer ist das?", „sagt Oma Rina.",
    „erklärt Oma Rina." still bis viel zu leise, obwohl das Roh-Audio sauber war (RMS ~4700). RMS-Gain
    über die Sprech-Samples wirkt längenunabhängig und deterministisch; ein Peak-Limit verhindert Clipping."""
    a = array.array("h"); a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not a:
        return pcm
    cur = _sprech_rms(pcm)
    if cur < 1:
        return pcm
    peak = max((abs(x) for x in a), default=1) or 1
    gain = min(ZIEL_SPRECH_RMS / cur, PEAK_LIMIT / peak)
    return array.array("h", (max(-32768, min(32767, int(x * gain))) for x in a)).tobytes()


def _tts_call(client, voice: str, content: str, temperature: float | None = None):
    """Ein einzelner TTS-Aufruf. Gibt (pcm|None, block_reason|None) zurück.
    Wirft bei echten API-Fehlern (Timeout/5xx) — die fängt synth_pcm ab."""
    from google.genai import types
    cfg = dict(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
    )
    if temperature is not None:
        cfg["temperature"] = temperature
    resp = client.models.generate_content(
        model=TTS_MODEL, contents=content,
        config=types.GenerateContentConfig(**cfg),
    )
    pf = getattr(resp, "prompt_feedback", None)
    block = getattr(pf, "block_reason", None) if pf else None
    cand = resp.candidates[0] if resp.candidates else None
    parts = cand.content.parts if (cand and cand.content) else None
    pcm = parts[0].inline_data.data if (parts and getattr(parts[0], "inline_data", None)) else None
    return pcm, block


def synth_pcm(client, voice: str, style: str, text: str, retries: int = 6,
              temperature: float | None = None) -> bytes | None:
    """Rendert Text als PCM — robust gegen den Safety-False-Positive.

    Flash blockt deterministisch die Kombination (Stil-Präfix + kurzes/heikles
    Fragment) mit block_reason=PROHIBITED_CONTENT, obwohl der Text harmlos ist
    (z. B. „Das", „so wie er"). Erneutes Senden desselben Prompts hilft NIE.
    Fallback: denselben Wortlaut OHNE Stil-Präfix senden — der nackte Text
    liefert zuverlässig Audio. Wortlaut und Reihenfolge bleiben UNVERÄNDERT;
    nur die feine Stilsteuerung entfällt bei dem einen betroffenen Clip
    (Timbre/Charakter trägt bei Nico ohnehin Stimme + Voice-Conversion)."""
    full = f"{style}\n\n{text}"
    for attempt in range(retries):
        try:
            pcm, block = _tts_call(client, voice, full, temperature)
            if pcm is not None:
                return pcm
            if block is not None:                       # deterministischer Block → Präfix weglassen
                print(f"      TTS-Block ({block}) — Fallback ohne Stil-Präfix")
                pcm2, block2 = _tts_call(client, voice, text, temperature)
                if pcm2 is not None:
                    return pcm2
                print(f"      ! Fallback weiter blockiert ({block2}) — Turn übersprungen")
                return None                             # nackter Text blockt praktisch nie
            print(f"      TTS leer (kein Block) — Retry {attempt+1}")   # transient
        except Exception as e:
            print(f"      TTS-Retry {attempt+1}: {str(e)[:60]}")
        if attempt < retries - 1:
            # Exponentiell + Jitter: gegen 500/503/504-Wellen ist starres Warten chancenlos —
            # alle Turns liefen sonst im Gleichschritt in dieselbe ueberlastete Minute.
            pause = min(RETRY_BASE_S * (2 ** attempt), RETRY_MAX_S)
            pause += random.uniform(0, pause * 0.3)
            print(f"      … {pause:.0f}s warten")
            time.sleep(pause)
    return None


def _turn_requests(turns: list[dict], cast: dict, temperature: float | None):
    """Baut die TTS-Einheiten aller nicht-leeren Turns → [(turn_index, TtsRequest)]."""
    from tts_batch import TtsRequest
    out = []
    for i, t in enumerate(turns):
        text = (t.get("text") or "").strip()
        if not text:
            continue
        rolle = t.get("rolle", "erzähler")
        # hat_emotion steuert die Eskalations-Reihenfolge: Turns MIT Regieanweisung behalten den
        # Stil-Präfix so lange wie möglich (Temperatur zuerst hoch), sonst geht die Emotion
        # verloren — genau das ließ am 17.07. „Oma Rina lacht" das Lachen einbüßen.
        out.append((i, TtsRequest.build(
            voice=_voice_for(rolle, cast), style=_style_for(rolle, t),
            text=text, temperature=temperature, turn=i, rolle=rolle,
            hat_emotion=bool((t.get("emotion") or "").strip()))))
    return out


def _qa_pruefer(aktiv: bool):
    """(pcm, text) -> (ok, grund). None = QA aus."""
    if not aktiv:
        return None
    from tts_qa import pruefe
    return lambda pcm, text: pruefe(pcm, text, sample_rate=SAMPLE_RATE)


def _sync_pcm_cached(client, cache_dir: Path, req, voice: str, style: str, text: str,
                     temperature: float | None, qa=None) -> bytes | None:
    """Sync-Synthese MIT Cache: derselbe Inhalts-Hash wie im Batch-Pfad (tts_batch.TtsRequest).

    Ein fertiger Turn wird nie zweimal bezahlt — entscheidend, weil mit temperature=0.3 rund jeder
    2.-3. Call haengt und ein Wiederholungslauf sonst bei null anfinge. Cache-Treffer ueberspringen
    den Call komplett; Modell/Stimme/Stil/temperature stecken im Hash, also kann kein Treffer aus
    einer anderen Konfiguration stammen."""
    from tts_batch import _cache_path
    if req is not None:
        p = _cache_path(cache_dir, req.key)
        if p.exists() and p.stat().st_size > 0:
            print("      (aus Cache)")
            return p.read_bytes()
    # QA-Ausschuss wird wie ein Fehlschlag behandelt → neuer Versuch. Nicht cachen: ein kaputtes
    # PCM im Cache waere fuer immer ausgeliefert (der Hash kennt die Qualitaet nicht).
    for versuch in range(QA_VERSUCHE):
        pcm = synth_pcm(client, voice, style, text, temperature=temperature)
        if pcm is None or qa is None:
            break
        ok, grund = qa(pcm, text)
        if ok:
            break
        print(f"      QA durchgefallen ({grund}) — neu synthetisieren "
              f"[{versuch + 1}/{QA_VERSUCHE}]")
        pcm = None
    if pcm and req is not None:
        _cache_path(cache_dir, req.key).write_bytes(pcm)
    return pcm


def vertone(seg: dict, out_wav: Path, nico_converter=None, normalize: bool | None = None,
            allow_raw_kind: bool = False, temperature: float | None = TTS_TEMPERATURE,
            allow_incomplete: bool = False, synth_mode: str = "batch",
            pcm_cache: Path | None = None, qa: bool = True) -> dict:
    """Rendert alle Turns und schneidet sie zu einer WAV. Gibt ein Manifest zurück.

    nico_converter: Callable ``(pcm: bytes, sr: int) -> bytes``. KIND-Turns gehen durch diese
        Voice-Conversion (Flash-Quellstimme → Klangfarbe des Sohnes). PFLICHT, sobald die
        Segmentierung Kind-Turns enthält — die Prebuilt-Stimme (Puck) ist nur ein Platzhalter
        und klingt nicht wie ein Kind. Ohne Converter bricht der Lauf ab.
    allow_raw_kind: Notausgang für Tests/Platzhalter-Renders — lässt Kind-Turns bewusst OHNE VC
        zu und stempelt sie im Manifest (``raw_kind``). Niemals für einen Build verwenden.
    normalize: Turn-Pegel per loudnorm angleichen. Standard = an, sobald ein Converter
        aktiv ist (Kind-VC und Flash-Turns stammen dann aus verschiedenen Quellen).
    temperature: gilt für ALLE Turns (auch Kind mit VC — per Hörurteil festgelegt, s.
        TTS_TEMPERATURE). None = SDK-Default.
    allow_incomplete: Notausgang für Tests — lässt fehlgeschlagene Turns überspringen statt
        abzubrechen. Ein übersprungener Turn hinterlässt ein LOCH in der Geschichte, das der
        fertigen Datei nicht anzusehen ist → im Build niemals verwenden.
    synth_mode: ``"batch"`` (Standard, Produktion) = alle Turns über die Batch-API, mit Cache
        und Nachreich-Runden (tts_batch). Unempfindlich gegen die 504/503-Stürme, die den
        sync-Pfad am 16.07. zerlegt haben, und halber Preis — dafür LANGSAM (Warteschlange;
        2 Sätze brauchten 15 Min). ``"sync"`` = ein Call je Turn, schnell, aber bricht bei
        API-Stau ab → nur zum Iterieren, nicht für Läufe.
    pcm_cache: Cache-Ordner (Inhalts-Hash → PCM). Standard ``out_wav.parent/pcm_cache``.
        Für Mehr-Themen-Läufe EINEN gemeinsamen Ordner übergeben (maximale Wiederverwendung).

    Hinweis zur Batch-Synthese: gleiche (Stimme, Stil, Text, temperature) = EIN Call, das
    Audio wird geteilt. Zwei wortgleiche Turns klingen dadurch identisch statt leicht
    verschieden — gewollt (kein Neuwürfeln beim Rebuild), fällt bei echten Dialogen nicht auf."""
    import os
    from google import genai
    from google.genai import types
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
    # Ohne http_options hat das SDK KEIN Timeout — ein stehender Call blockiert den Lauf endlos.
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=TTS_TIMEOUT_MS))
    if normalize is None:
        normalize = nico_converter is not None

    cast, turns = seg.get("cast", {}), seg.get("turns", [])
    # Leere Turns sind kein Inhalt → sie zählen nicht als "zu rendern" (sonst meldet ein
    # perfekter Lauf faelschlich Unvollstaendigkeit).
    n_soll = sum(1 for t in turns if (t.get("text") or "").strip())
    n_kind = sum(1 for t in turns if t.get("rolle") == "kind" and (t.get("text") or "").strip())
    if n_kind and nico_converter is None and not allow_raw_kind:
        raise RuntimeError(
            f"{n_kind} Kind-Turns, aber keine Nico-VC konfiguriert. Die Flash-Prebuilt-Stimme "
            f"({VOICES[('kind', 'm')]}/{VOICES[('kind', 'w')]}) ist nur ein Platzhalter und klingt "
            f"nicht wie ein Kind — sie darf nicht in einen Build. Entweder --nico-ref + --nico-ckpt "
            f"setzen oder bewusst --allow-raw-kind angeben.")
    if synth_mode not in ("batch", "sync"):
        raise ValueError(f"synth_mode muss 'batch' oder 'sync' sein, nicht {synth_mode!r}")
    print(f"  Cast: Kind={cast.get('kind')} · Erwachsener={cast.get('erwachsener')} · {len(turns)} Turns"
          f" · {synth_mode}"
          f"{' · Nico-VC AN' if nico_converter else ''}{' · loudnorm' if normalize else ''}"
          f"{f' · temp {temperature}' if temperature is not None else ''}"
          f"{f' · !! {n_kind} Kind-Turns ROH (--allow-raw-kind)' if n_kind and not nico_converter else ''}")

    # ── Synthese vorab (Batch): ALLE Turns auf einmal, mit Cache + Nachreich-Runden ──
    # Das Vollstaendigkeits-Gate greift HIER — vor der VC. Sonst faerbt die (teure, GPU-
    # gebundene) Umfaerbung Audio um, aus dem ohnehin kein Artefakt werden darf.
    # Der Cache gilt fuer BEIDE Pfade. Frueher hing er ganz im batch-Zweig: --pcm-cache wurde im
    # Sync-Modus stillschweigend ignoriert → ein Abbruch bei Turn 12 warf 11 fertige Turns weg.
    # Mit temperature=0.3 haengt ~jeder 2.-3. Call, also ist Wiederaufsetzen der Normalfall.
    cache_dir = pcm_cache or (out_wav.parent / "pcm_cache")
    paare = _turn_requests(turns, cast, temperature)
    req_by_turn = {i: r for i, r in paare}
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Der Cache heisst nach Inhalts-Hashes. Ohne diese Zuordnung ist nach einem Abbruch nicht mehr
    # feststellbar, WELCHE Turns geklemmt haben — die Segmentierung lebt sonst nur im Speicher.
    (cache_dir / "_index.json").write_text(json.dumps(
        {r.key: {"turn": i, "rolle": r.meta.get("rolle"), "voice": r.voice, "text": r.text}
         for i, r in paare}, ensure_ascii=False, indent=2), encoding="utf-8")

    qa_fn = _qa_pruefer(qa)
    eskalations_protokoll: dict = {}
    vorab: dict[int, bytes] = {}
    if synth_mode == "batch":
        from tts_batch import batch_synthesize
        pcms, fehlgeschlagen = batch_synthesize(client, [r for _, r in paare], cache_dir=cache_dir,
                                                qa=qa_fn, protokoll=eskalations_protokoll)
        vorab = {i: pcms[r.key] for i, r in paare if r.key in pcms}
        if fehlgeschlagen:
            (cache_dir / "_fehlgeschlagen.json").write_text(json.dumps(
                [{"key": r.key, "turn": r.meta.get("turn"), "rolle": r.meta.get("rolle"),
                  "voice": r.voice, "style": r.style, "text": r.text}
                 for r in fehlgeschlagen], ensure_ascii=False, indent=2), encoding="utf-8")
        if fehlgeschlagen and not allow_incomplete:
            raise RuntimeError(
                f"{len(fehlgeschlagen)} von {len(paare)} Turns konnten auch nach den Nachreich-Runden "
                f"nicht vertont werden — Abbruch VOR der Voice-Conversion. Ein fehlender Turn "
                f"hinterlässt ein Loch in der Geschichte, das der fertigen Datei nicht anzusehen ist. "
                f"Erster Ausfall: \"{fehlgeschlagen[0].text[:60]}\". (Notausgang: --allow-incomplete.)")

    chunks: list[bytes] = []
    manifest = []
    fehlende: list[int] = []
    for i, t in enumerate(turns):
        rolle = t.get("rolle", "erzähler")
        text  = (t.get("text") or "").strip()
        if not text:
            continue
        voice = _voice_for(rolle, cast)
        style = _style_for(rolle, t)
        print(f"    [{i+1:02}/{len(turns)}] {rolle:12} {voice:12} \"{text[:48]}…\"")
        if synth_mode == "batch":
            pcm = vorab.get(i)
        else:
            pcm = _sync_pcm_cached(client, cache_dir, req_by_turn.get(i),
                                   voice, style, text, temperature, qa=qa_fn)
        if pcm is None:
            if not allow_incomplete:
                raise RuntimeError(
                    f"Turn {i+1}/{len(turns)} ({rolle}) konnte nicht vertont werden: \"{text[:60]}\". "
                    f"Abbruch — ein übersprungener Turn hinterlässt ein Loch in der Geschichte, das "
                    f"der fertigen Datei nicht anzusehen ist. (Notausgang: --allow-incomplete.)")
            fehlende.append(i + 1)
            print(f"      ! Turn {i+1} fehlgeschlagen — übersprungen (--allow-incomplete)")
            continue
        # Führende/abschließende Stille abschneiden — VOR der VC. Sonst macht die VC aus langer
        # Stille hohes Rauschen (Fehler 1 vom 17.07.: Turn 3 = 48 s Stille → 48 s Rauschen nach VC).
        # Interne Pausen bleiben; der Wortlaut ist unberührt.
        roh_sek = len(pcm) / 2 / SAMPLE_RATE
        pcm = _trim_stille(pcm)
        if roh_sek - len(pcm) / 2 / SAMPLE_RATE > 1.0:
            print(f"      Stille getrimmt: {roh_sek:.1f}s → {len(pcm)/2/SAMPLE_RATE:.1f}s")
        vc = False
        if rolle == "kind" and nico_converter is not None:
            conv = None
            try:
                conv = nico_converter(pcm, SAMPLE_RATE)
            except Exception as e:
                if not allow_raw_kind:
                    raise RuntimeError(
                        f"Nico-VC bei Kind-Turn {i+1} fehlgeschlagen: {e}. Abbruch — sonst landet die "
                        f"rohe Platzhalter-Stimme im Build.") from e
                print(f"      ! Nico-VC fehlgeschlagen ({str(e)[:60]}) — rohes Flash-Kind behalten")
            if conv:
                pcm, vc = conv, True
            elif not allow_raw_kind:
                raise RuntimeError(
                    f"Nico-VC lieferte bei Kind-Turn {i+1} kein Audio. Abbruch — sonst landet die "
                    f"rohe Platzhalter-Stimme im Build.")
        if normalize:
            pcm = _loudnorm(pcm)
        if chunks:                                   # Pause VOR diesem Turn (nur wenn schon Audio da ist)
            chunks.append(_silence(GAP_SCENE if t.get("szene") else GAP_TURN))
        chunks.append(pcm)
        # Welche Stufe hat diesen Turn geliefert? Ohne Eintrag: die Basis-Stufe (Runde 1/2 oder Cache).
        stufe = eskalations_protokoll.get(req_by_turn[i].key) if i in req_by_turn else None
        ist_temp = stufe["temperature"] if stufe else temperature
        eskaliert = bool(stufe) and (ist_temp != temperature or stufe.get("ohne_stil"))
        manifest.append({"i": i, "rolle": rolle, "voice": voice, "vc": vc,
                         "raw_kind": rolle == "kind" and not vc, "temp": ist_temp,
                         "eskaliert": eskaliert,
                         "ohne_stil": bool(stufe and stufe.get("ohne_stil")),
                         "sec": round(len(pcm) / 2 / SAMPLE_RATE, 2), "text": text[:80]})
        time.sleep(0.8)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))
    total = sum(len(c) for c in chunks) / 2 / SAMPLE_RATE
    n_raw = sum(1 for m in manifest if m["raw_kind"])
    # EINE Fahne, an der nachgelagerte Schritte (Schnitt/Upload) entscheiden koennen.
    vollstaendig = not fehlende and len(manifest) == n_soll and n_raw == 0
    if n_raw:
        print(f"  !! {n_raw} Kind-Turns OHNE Nico-VC (Platzhalter-Stimme) — nicht ausliefern.")
    if fehlende:
        print(f"  !! {len(fehlende)} Turns FEHLEN im Audio (Nr. {fehlende}) — Loch in der Geschichte, "
              f"nicht ausliefern.")
    # Die Liste fuer das PO-Ohr: NUR diese Turns weichen vom eingefrorenen Rezept ab. Der PO hoert
    # 4.000+ Vertonungen nicht durch — er soll die Handvoll Ausnahmen pruefen koennen, nicht alles.
    eskalierte = [m for m in manifest if m.get("eskaliert")]
    if eskalierte:
        print(f"\n  ESKALIERT: {len(eskalierte)} von {n_soll} Turns brauchten eine andere Stufe "
              f"(anderer Vortrag als der Rest — nur diese pruefen):")
        for m in eskalierte:
            wie = f"temperature {m['temp']}" if m["temp"] != temperature else ""
            wie += (" · " if wie and m["ohne_stil"] else "") + ("ohne Stil-Präfix" if m["ohne_stil"] else "")
            print(f"     Turn {m['i']+1:02d} [{m['rolle']}] {wie} — \"{m['text'][:44]}\"")
    return {"cast": cast, "n_turns": len(turns), "n_soll": n_soll, "n_rendered": len(manifest),
            "n_eskaliert": len(eskalierte), "eskalierte_turns": [m["i"] + 1 for m in eskalierte],
            "nico_vc": nico_converter is not None, "raw_kind_turns": n_raw,
            "fehlende_turns": fehlende, "vollstaendig": vollstaendig,
            "total_sec": round(total, 1), "wav": str(out_wav), "turns": manifest}


# ── Story beschaffen ───────────────────────────────────────────────────────────
def _story_from_checkpoint(cp: Path, thema: str, model: str) -> str:
    import story_mode_v2 as sm
    d = json.loads(cp.read_text(encoding="utf-8"))
    topics = d.get("topics") or d.get("topics_data") or d
    res = sm.build_story(thema, topics[thema], model)
    return res["story_clean"]


def main():
    # Die Fortschritts-Prints enthalten → und Umlaute; eine cp1252-Konsole killt sonst den
    # ganzen Lauf an einer Ausgabezeile. Ohne basicConfig verwirft Python zudem jedes
    # log.info aus tts_batch — ein stundenlanger Batch-Lauf liefe dann ohne Rundenmeldung.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")

    ap = argparse.ArgumentParser()
    ap.add_argument("--story-file", help="Roh-Prosa der Geschichte (txt) — direkt vertonen")
    ap.add_argument("--checkpoint", help="Stage-1-Checkpoint (alternativ: frisch erzeugen)")
    ap.add_argument("--thema", help="Thema im Checkpoint")
    ap.add_argument("--model", default="claude-sonnet-5", help="Generierungsmodell (mit --checkpoint)")
    ap.add_argument("--seg-model", default="claude-sonnet-5", help="Segmentierungsmodell")
    ap.add_argument("--titel", default="story", help="Dateiname-Basis")
    ap.add_argument("--out-dir", required=True)
    # Nico-Voice-Conversion (braucht GPU + OpenVoice; siehe nico_vc.py).
    # PFLICHT, sobald die Story Kind-Turns hat — sonst bricht vertone() ab (--allow-raw-kind übergeht das).
    ap.add_argument("--nico-ref", help="Ordner mit Sohn-Referenz-WAVs → Kind-Turns per VC umfärben")
    ap.add_argument("--nico-ckpt", help="OpenVoice-converter-Checkpoint-Ordner (config.json + checkpoint.pth)")
    ap.add_argument("--nico-tau", type=float, default=0.7, help="VC-Stärke (Standard 0.7)")
    ap.add_argument("--openvoice-path", help="Pfad zum geklonten OpenVoice-Repo (für den Import)")
    ap.add_argument("--allow-raw-kind", action="store_true",
                    help="NUR für Tests: Kind-Turns ohne VC zulassen (rohe Platzhalter-Stimme, nie ausliefern)")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="NUR für Tests: fehlgeschlagene Turns überspringen statt abzubrechen "
                         "(erzeugt ein Loch in der Geschichte — nie ausliefern)")
    ap.add_argument("--tts-temperature", type=float, default=TTS_TEMPERATURE,
                    help=f"temperature für alle Turns (Standard {TTS_TEMPERATURE} = Hörurteil; "
                         f"-1 = SDK-Default)")
    ap.add_argument("--sync", action="store_true",
                    help="Synchron statt Batch synthetisieren: schnell zum Iterieren, aber bricht "
                         "bei API-Stau ab. Für Läufe NICHT verwenden (Standard = Batch).")
    ap.add_argument("--pcm-cache", help="Cache-Ordner für synthetisierte Turns "
                                        "(Standard: <out-dir>/pcm_cache; für Mehr-Themen-Läufe "
                                        "einen gemeinsamen Ordner angeben)")
    ap.add_argument("--no-qa", action="store_true",
                    help="Qualitaetspruefung (lokales Whisper + Pegel + Tempo) abschalten. "
                         "NUR fuer Tests — ohne QA rutscht Stille/falsch zugeordnetes Audio durch.")
    ap.add_argument("--tts-model", default=TTS_MODEL,
                    help=f"TTS-Modell (Standard: {TTS_MODEL}). Fuer A/B-Vergleiche, z.B. "
                         f"gemini-2.5-flash-preview-tts. Geht in den Cache-Hash ein → "
                         f"kein Vermischen verschiedener Modelle im selben Cache.")
    ap.add_argument("--seg-file", help="Fertige Segmentierung (JSON) statt frisch segmentieren. "
                                       "Macht einen Wiederholungslauf reproduzierbar und spart "
                                       "den Seg-Call. Jeder Lauf schreibt seine Segmentierung "
                                       "nach <out-dir>/<titel>_segmentierung.json.")
    args = ap.parse_args()

    # Das Modell steckt als Konstante in beiden Modulen (Sync-Call hier, Cache-Hash + Einreichung
    # in tts_batch). Beide umstellen, sonst rendert der Sync-Pfad Modell A und der Hash behauptet B.
    if args.tts_model != TTS_MODEL:
        globals()["TTS_MODEL"] = args.tts_model
        import tts_batch
        tts_batch.TTS_MODEL = args.tts_model
        print(f"TTS-Modell: {args.tts_model}")

    out_dir = Path(args.out_dir)
    safe = re.sub(r"[^\w]+", "_", args.titel).strip("_")

    if args.seg_file:
        seg = json.loads(Path(args.seg_file).read_text(encoding="utf-8"))
        print(f"Segmentierung aus {args.seg_file} ({len(seg.get('turns', []))} Turns)")
    else:
        if args.story_file:
            story = Path(args.story_file).read_text(encoding="utf-8").strip()
        elif args.checkpoint and args.thema:
            print(f"Erzeuge Geschichte ({args.model}) …")
            story = _story_from_checkpoint(Path(args.checkpoint), args.thema, args.model)
        else:
            sys.exit("Entweder --story-file ODER (--checkpoint + --thema) ODER --seg-file angeben.")

        print(f"Segmentiere ({args.seg_model}) …")
        seg = segment_story(story, args.seg_model)
        # Vor der teuren Synthese sichern: sonst ist nach einem Abbruch weder nachvollziehbar,
        # WAS vertont wurde, noch laesst sich derselbe Lauf wiederholen (Seg ist nicht deterministisch).
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{safe}_segmentierung.json").write_text(
            json.dumps(seg, ensure_ascii=False, indent=2), encoding="utf-8")

    nico_converter = None
    if args.nico_ref:
        if not args.nico_ckpt:
            sys.exit("--nico-ref braucht auch --nico-ckpt (OpenVoice-converter-Ordner).")
        from nico_vc import OpenVoiceNicoConverter
        print(f"Nico-VC aktiv (ref={args.nico_ref}, tau={args.nico_tau}) …")
        nico_converter = OpenVoiceNicoConverter(
            args.nico_ref, args.nico_ckpt, tau=args.nico_tau, openvoice_path=args.openvoice_path)

    wav = out_dir / f"{safe}.wav"
    print(f"Vertone → {wav}")
    temp = None if args.tts_temperature < 0 else args.tts_temperature
    info = vertone(seg, wav, nico_converter=nico_converter,
                   allow_raw_kind=args.allow_raw_kind, temperature=temp,
                   allow_incomplete=args.allow_incomplete,
                   synth_mode="sync" if args.sync else "batch",
                   pcm_cache=Path(args.pcm_cache) if args.pcm_cache else None,
                   qa=not args.no_qa)

    (out_dir / f"{safe}_manifest.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFERTIG: {info['n_rendered']}/{info['n_soll']} Turns · "
          f"{info['total_sec']} s · {wav}")
    if not info["vollstaendig"]:
        print("!! NICHT AUSLIEFERN:"
              + (f" {info['raw_kind_turns']} Kind-Turns mit Platzhalter-Stimme."
                 if info["raw_kind_turns"] else "")
              + (f" {len(info['fehlende_turns'])} Turns fehlen im Audio (Nr. {info['fehlende_turns']})."
                 if info["fehlende_turns"] else ""))
        sys.exit(1)


if __name__ == "__main__":
    main()
