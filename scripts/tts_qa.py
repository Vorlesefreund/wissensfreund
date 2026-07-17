#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tts_qa.py — Qualitätsprüfung EINES synthetisierten Turns, lokal und ohne API-Kosten.

WARUM DAS EXISTIERT
-------------------
Das Vollständigkeits-Gate in ``tts_story.vertone()`` prüft nur, OB ein Turn Bytes hat. Sobald
Bytes da sind, gilt er als gut — niemand hört hinein. Bei 4.000–5.000 Vertonungen, die der PO
nie anhört, ist das die gefährlichste Lücke: Diese Fehler sind alle STUMM.

  1. **Falsche Wörter** — Flash erfindet bei kurzen Fragmenten Füllwörter (belegt 2026-07-15:
     ", erklärt Oma Rina." → "SO erklärt Oma Rina"; führendes Komma → "Ruf Kilo" statt "ruft Theo").
  2. **Audio am falschen Turn** — tts_batch ordnet Antworten per Reihenfolge zu; lässt die API
     eine Antwort AUS, verrutscht alles. Dann sagt Oma Rina Theos Satz — und jeder Turn hat Audio.
  3. **Stille / Rauschen** — eine Degenerations-Schleife (der Grund für die temperature-Hänger,
     s. reference_tts_gotchas) kann auch Bytes liefern statt zu hängen.
  4. **Abbruch mitten im Satz** — Audio da, aber nur die halbe Zeile.

WO ES GREIFT
------------
Bei der Synthese, VOR dem Cache-Schreiben und VOR der Voice-Conversion:
  - Ein durchgefallener Turn darf NIE in den Cache (sonst wird der Fehler für immer ausgeliefert —
    der Hash deckt Modell/Stimme/Stil/temperature/Text ab, nicht die Qualität).
  - Ein durchgefallener Turn wird behandelt wie eine leere Antwort → geht in die nächste
    Nachreich-Runde. Die Wiederhol-Maschinerie ist schon da; QA hängt sich nur ein.
  - Vor der VC, weil die GPU kostet und Ausschuss nicht umgefärbt werden muss.

WAS ES FÄNGT — und was NICHT (an 24 echten Produktions-Turns kalibriert, 2026-07-17)
------------------------------------------------------------------------------------
Gefangen, sicher:
  - Stille/kein Sprachanteil — der reale 54-s-Stille-Turn: RMS 20 vs. 984–3984 bei echten Turns.
  - Audio am falschen Turn — zwei fast gleich lange Turns vertauscht: Ähnlichkeit 0.54 (Schwelle 0.80).
  - Kein Audio, Kauderwelsch, Abbruch bei ≤60 % (Ähnlichkeit 0.728) bzw. ≤50 % (Tempo).
  - Fehlalarme: 0 von 24 echten Turns.

NICHT gefangen (ehrliche Grenze, nicht durch Schwellen behebbar):
  - **Angeschnittenes Ende bis ~30 %.** Die Verteilungen ÜBERLAPPEN: ein bei 80 % abgeschnittener
    Turn hat Ähnlichkeit 0.874 — BESSER als der schlechteste echte Turn (0.832). Beim Tempo dasselbe:
    echt bis 4.45 W/s, bei 70 % abgeschnitten 4.33 W/s. Jede Schwelle, die den Abbruch fängt, wirft
    echte Turns weg. Wer das dichter haben will, braucht ein anderes Verfahren (z. B. Wort-Alignment
    gegen das Transkript-Ende), nicht schärfere Zahlen.
  - **Einzelne erfundene Füllwörter** ("So erklärt Oma Rina" statt ", erklärt Oma Rina") liegen bei
    kurzen Zeilen dicht an echten Verhörern → nicht trennscharf. Gegenmittel bleibt die bekannte
    Regel: Kurzfragmente ohne Stil-Präfix synthetisieren (s. reference_tts_gotchas).

KOSTEN: 0 € (alles lokal). Rechenzeit ~1 s/Turn (faster-whisper small, CPU, int8) — bei 37 Turns
also ~40 s je Vertonung, parallelisierbar über Kerne.
"""
from __future__ import annotations
import difflib, io, re, wave

SAMPLE_RATE = 24000
BYTES_PER_SEC = SAMPLE_RATE * 2          # 16-bit mono

# Schwellen — bewusst großzügig: ein Gate mit Fehlalarmen wird abgeschaltet und schützt dann gar nichts.
# Alle Werte an 24 echten Produktions-Turns kalibriert (2026-07-17, articles/leo_batch_20260716).
MIN_AEHNLICHKEIT = 0.80   # ZEICHEN-Ebene (Wort-Ebene ist bei kurzen Zeilen unbrauchbar:
                          # "Oma Rina lacht." vs. Whispers "O Marina lacht." = 0.33 → Fehlalarm;
                          # auf Zeichenebene 0.93). Echte Turns: Median 1.00, schlechtester 0.832.
MIN_RMS          = 200    # 16-bit Vollaussteuerung = 32768. Echte Turns: RMS 984–3984.
                          # Der 54-s-Stille-Turn vom 16.07. hatte RMS 20 → sicher getrennt.
WPS_MIN, WPS_MAX = 1.2, 5.0   # Wörter je SPRECH-Sekunde (NACH Stille-Trim). Echte Turns: 1.65–4.45.
                              # Auf der Rohdauer waere die Regel Rauschen: das Modell haengt Stille
                              # an ("Wer ist das?" = 3 Woerter in 7,4 s Datei, aber 1,3 s Sprache).
MIN_SEC          = 0.25
STILLE_SCHWELLE  = 500    # Amplitude, ab der ein 20-ms-Fenster als "Sprache" gilt.
MAX_STILLE_ANTEIL = 0.65  # Anteil Stille am ganzen Turn. Echte Turns 18–47 %; die zwei Defekte
                          # vom 17.07. (Turn 3 = 97 %, Turn 30 = 82 %) lagen weit darüber. GENAU
                          # dieses blinde Feld hat die erste QA-Version durchgelassen: Sprech-Zeit,
                          # Pegel und Transkript stimmten je einzeln — 3 s korrekte Sprache in 51 s
                          # Stille. Nach der VC wurde aus der Stille hohes RAUSCHEN.
TRIM_PAD_S        = 0.15  # Beim Trimmen vor/nach der Sprache stehen lassen (natürlicher Ein-/Ausklang).

_MODELL = None            # faster-whisper ist teuer zu laden (~8 s) → genau einmal.


def _modell(groesse: str = "small"):
    global _MODELL
    if _MODELL is None:
        from faster_whisper import WhisperModel
        _MODELL = WhisperModel(groesse, device="cpu", compute_type="int8")
    return _MODELL


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Rohes PCM in einen WAV-Container (Gemini liefert headerlos, s. reference_tts_gotchas)."""
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        w.writeframes(pcm)
    return b.getvalue()


def _samples(pcm: bytes):
    import array
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    return a


def rms(pcm: bytes) -> float:
    """Effektivpegel. Ohne numpy-Abhängigkeit an dieser Stelle: reicht, um Stille zu erkennen."""
    a = _samples(pcm)
    if not a:
        return 0.0
    return (sum(float(x) * x for x in a) / len(a)) ** 0.5


def _laut_fenster(pcm: bytes, sample_rate: int = SAMPLE_RATE, fenster_s: float = 0.02):
    """Indexliste der 20-ms-Fenster mit Sprache (Spitze >= STILLE_SCHWELLE) + Fenstergröße."""
    a = _samples(pcm)
    fenster = max(1, int(sample_rate * fenster_s))
    laut = [j for j in range(0, len(a) - fenster + 1, fenster)
            if max((abs(x) for x in a[j:j + fenster]), default=0) >= STILLE_SCHWELLE]
    return a, laut, fenster


def stille_anteil(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> float:
    """Anteil des Turns OHNE Sprache (0..1). Fängt Turns, die fast nur aus Stille bestehen —
    der Defekt, den die reine Sprech-Zeit-Messung nicht sieht (die stimmt ja, es ist nur wenig)."""
    a, laut, fenster = _laut_fenster(pcm, sample_rate)
    n = max(1, len(a) // fenster)
    return 1.0 - len(laut) / n


def trim_stille(pcm: bytes, sample_rate: int = SAMPLE_RATE, pad_s: float = TRIM_PAD_S) -> bytes:
    """Führende/abschließende Stille abschneiden, kurzen Puffer stehen lassen.

    Der eigentliche Fix für Fehler 1: Turn 3 war 48 s Stille + 3 s Sprache. Getrimmt bleiben ~3 s
    saubere Sprache — und die VC sieht keine Stille mehr, aus der sie Rauschen macht. Interne
    Pausen bleiben unangetastet (nur der Rand wird geschnitten); Inhalt geht nie verloren."""
    a, laut, fenster = _laut_fenster(pcm, sample_rate)
    if not laut:
        return pcm                       # gar keine Sprache → nicht anfassen, das faengt die QA
    pad = int(sample_rate * pad_s)
    # laut[] sind bereits SAMPLE-Indizes (Fensteranfänge). Das letzte Sprachfenster reicht bis +fenster.
    start = max(0, laut[0] - pad)
    ende = min(len(a), laut[-1] + fenster + pad)
    return a[start:ende].tobytes()


def sprech_sekunden(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> float:
    """Sekunden mit tatsächlicher Sprache (Stille-Fenster zählen nicht mit).

    Warum nicht einfach die Dauer: Das TTS-Modell hängt unterschiedlich viel Stille an — an echten
    Turns gemessen zwischen 0,5 s und mehreren Sekunden. Auf der Rohdauer ist jede Wörter/Sekunde-
    Regel deshalb Rauschen. Auf der Sprechzeit wird sie trennscharf — und ein Stille-Turn faellt
    sofort auf 0 s."""
    _, laut, fenster = _laut_fenster(pcm, sample_rate)
    return len(laut) * fenster / sample_rate


# Whisper schreibt Zahlen als ZIFFERN ("500"), die Quelle schreibt sie aus ("fünfhundert").
# Ohne das hier meldet das Gate korrekte Turns als Fehler — gemessen 2026-07-17 an echtem Audio.
_ZAHLWORT = re.compile(
    r"^(null|ein|eine|einen|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|"
    r"dreizehn|vierzehn|fünfzehn|sechzehn|siebzehn|achtzehn|neunzehn|zwanzig|dreißig|vierzig|"
    r"fünfzig|sechzig|siebzig|achtzig|neunzig|hundert|tausend|million(en)?|milliarde(n)?|und)+$")


def _tokens(s: str) -> list[str]:
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^a-zäöüß0-9 ]", " ", s)
    out = []
    for t in s.split():
        # Ziffern UND ausgeschriebene Zahlen auf dasselbe Symbol → "500" == "fünfhundert".
        if t.isdigit() or _ZAHLWORT.match(t.replace("ss", "ß")):
            out.append("<zahl>")
        else:
            out.append(t)
    return out


def aehnlichkeit(soll: str, hyp: str) -> float:
    """Zeichen-Ähnlichkeit der normalisierten Wortfolge.

    Zeichen- statt Wortebene, weil kurze Turns sonst an einem einzigen verhörten Eigennamen
    scheitern: „Oma Rina lacht." vs. Whispers „O Marina lacht." ist auf Wortebene 0.33 (Fehlalarm),
    auf Zeichenebene ~0.93. Grobe Fehler — falscher Turn, Stille, Kauderwelsch — fallen trotzdem
    weit unter die Schwelle, weil dann kaum ein Zeichen passt."""
    return difflib.SequenceMatcher(None, " ".join(_tokens(soll)), " ".join(_tokens(hyp))).ratio()


def transkribiere(pcm: bytes, sample_rate: int = SAMPLE_RATE, groesse: str = "small") -> str:
    segs, _ = _modell(groesse).transcribe(
        io.BytesIO(pcm_to_wav(pcm, sample_rate)), language="de", beam_size=1)
    return " ".join(s.text for s in segs).strip()


def pruefe(pcm: bytes | None, text: str, sample_rate: int = SAMPLE_RATE,
           mit_whisper: bool = True) -> tuple[bool, str]:
    """(ok, grund). ``grund`` ist leer, wenn der Turn sauber ist.

    Reihenfolge ist Absicht: die billigen Prüfungen zuerst, Whisper (~1 s) nur, wenn nötig."""
    if not pcm:
        return False, "kein Audio"
    sek = len(pcm) / BYTES_PER_SEC
    if sek < MIN_SEC:
        return False, f"zu kurz ({sek:.2f}s)"
    pegel = rms(pcm)
    if pegel < MIN_RMS:
        return False, f"faktisch stumm (RMS {pegel:.0f}, {sek:.1f}s)"
    sprech = sprech_sekunden(pcm, sample_rate)
    if sprech < MIN_SEC:
        return False, f"keine Sprache erkennbar ({sek:.1f}s Datei, {sprech:.2f}s Sprache)"
    stille = 1.0 - sprech / sek if sek else 1.0
    if stille > MAX_STILLE_ANTEIL:
        # Der Fehler vom 17.07.: korrekte Sprache in einem Meer aus Stille. Jede Einzelprüfung
        # stimmt, aber der Turn ist zu >65 % Stille → nach der VC wird Rauschen daraus.
        return False, f"zu viel Stille ({stille*100:.0f}%: {sprech:.1f}s Sprache in {sek:.1f}s)"
    woerter = len(text.split())
    wps = woerter / sprech
    if woerter and not (WPS_MIN <= wps <= WPS_MAX):
        # Zu langsam = Stille-/Dehnungs-Schleife; zu schnell = Abbruch mitten im Satz.
        return False, (f"unplausibles Tempo: {woerter} Wörter in {sprech:.1f}s Sprache "
                       f"= {wps:.1f} W/s (Datei {sek:.1f}s)")
    if not mit_whisper:
        return True, ""
    hyp = transkribiere(pcm, sample_rate)
    r = aehnlichkeit(text, hyp)
    if r < MIN_AEHNLICHKEIT:
        return False, f"Transkript weicht ab ({r:.2f}): „{hyp[:60]}“"
    return True, ""
