#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_tts_story_guards.py — die Schutzregeln in tts_story.vertone(), OHNE API-Calls.

Sichert die drei Bugs ab, die am 2026-07-16 gefunden wurden — alle vom Typ „stiller Fehlschlag":
ein print, und am Ende liegt eine Datei da, die fertig aussieht.
  1. Kind-Turns ohne Voice-Conversion (rohes Puck ist ein Platzhalter und klingt erwachsen)
  2. VC-Fehler fiel still auf die Platzhalter-Stimme zurück
  3. Fehlgeschlagener TTS-Call riss ein Loch in die Geschichte (real: 7 von 23 Turns weg)
Dazu: temperature-Weitergabe, Vollständigkeits-Fahne, Batch-Pfad (Gate VOR der VC).

    python -X utf8 scripts/test_tts_story_guards.py     # Exit 0 = alles grün

TTS und Converter sind gefälscht → kein Netz, keine Kosten, keine GPU.
"""
import itertools, sys, tempfile, wave
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent      # Repo-Wurzel aus dem Skriptpfad
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts'))
import tts_story as T

TMP = Path(tempfile.mkdtemp())
SEG = {"cast": {"kind": {"name": "Theo", "geschlecht": "m"},
                "erwachsener": {"name": "Oma Rina", "geschlecht": "w"}},
       "turns": [{"rolle": "erzähler", "text": "Theo schaut auf das Bild."},
                 {"rolle": "kind", "text": "Warum ist die Farbe so blass?"},
                 {"rolle": "erwachsener", "text": "Das ist sehr alt."}]}
SEG_NOKID = {"cast": SEG["cast"], "turns": [SEG["turns"][0], SEG["turns"][2]]}

# Fake-TTS: kein Netz. Merkt sich die temperature je Rolle.
CALLS = []
def fake_synth(client, voice, style, text, retries=3, temperature=None):
    CALLS.append({"voice": voice, "temp": temperature, "text": text})
    return b"\x00\x00" * 2400            # 0,1 s Stille
T.synth_pcm = fake_synth
T._loudnorm = lambda pcm, sr=T.SAMPLE_RATE: pcm
class FakeClient:  pass
import types as _t
T.genai = _t.SimpleNamespace(Client=lambda **kw: FakeClient())

def _patch_client(monkey_ok=True):
    """vertone() baut den Client selbst → google.genai wegfaken."""
    import google.genai as g
    g.Client = lambda **kw: FakeClient()

_patch_client()

# Tests 1-6b pruefen die SCHUTZLOGIK, nicht den Synthese-Weg → dort sync (kein Batch-API-Call).
# Test 6c schaltet auf den echten Default (batch) mit gefaelschtem batch_synthesize zurueck.
_vertone = T.vertone
_cache_nr = itertools.count()

def _vertone_isoliert(*a, **kw):
    kw.setdefault("synth_mode", "sync")
    # Das Fake-TTS liefert 0,1 s Stille — die echte QA (Whisper/Pegel/Tempo) lehnt das zu Recht ab.
    # Diese Tests pruefen die SCHUTZLOGIK, nicht die QA → QA aus. Eigene QA-Tests: Abschnitt 8.
    kw.setdefault("qa", False)
    # Seit der Sync-Pfad den PCM-Cache nutzt, teilen sich sonst ALLE Tests einen Ordner
    # (cache_dir leitet sich aus out_wav.parent ab, und alle WAVs liegen in TMP). Test 5 saehe
    # dann Cache-Treffer aus Test 4 → synth_pcm wird nie gerufen, temperature nie geprueft; der
    # Fehlschlag-Test bekaeme seinen "kaputten" Turn fertig aus dem Cache. Jeder Sync-Test ist ein
    # eigenes Szenario → eigener Cache. Batch-Tests bleiben unangetastet (sie pruefen den Default).
    if kw["synth_mode"] == "sync":
        kw.setdefault("pcm_cache", TMP / f"cache_{next(_cache_nr)}")
    return _vertone(*a, **kw)

T.vertone = _vertone_isoliert

fails = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond: fails.append(name)

print("\n1) Kind-Turns OHNE VC -> muss abbrechen")
try:
    T.vertone(SEG, TMP / "a.wav")
    check("RuntimeError geworfen", False, "kein Abbruch — roher Puck waere durchgerutscht")
except RuntimeError as e:
    check("RuntimeError geworfen", True)
    check("Meldung nennt Platzhalter + Auswege", "Platzhalter" in str(e) and "--nico-ref" in str(e)
          and "--allow-raw-kind" in str(e), str(e)[:80])

print("\n2) Kind-Turns OHNE VC + --allow-raw-kind -> laeuft, aber gestempelt")
CALLS.clear()
info = T.vertone(SEG, TMP / "b.wav", allow_raw_kind=True)
check("laeuft durch", info["n_rendered"] == 3)
check("raw_kind_turns == 1", info["raw_kind_turns"] == 1, str(info["raw_kind_turns"]))
check("nico_vc == False", info["nico_vc"] is False)
check("Kind-Turn im Manifest als raw_kind", any(m["raw_kind"] for m in info["turns"] if m["rolle"] == "kind"))

print("\n3) Story OHNE Kind-Turns -> laeuft ohne VC (Erzaehler/Erwachsene brauchen keine)")
info = T.vertone(SEG_NOKID, TMP / "c.wav")
check("laeuft durch", info["n_rendered"] == 2)
check("raw_kind_turns == 0", info["raw_kind_turns"] == 0)

print("\n4) MIT VC -> Kind wird umgefaerbt, kein raw_kind")
CALLS.clear()
vc_called = []
def good_vc(pcm, sr):
    vc_called.append(sr); return b"\x11\x11" * 2400
info = T.vertone(SEG, TMP / "d.wav", nico_converter=good_vc)
check("VC genau 1x aufgerufen (nur Kind)", len(vc_called) == 1, str(len(vc_called)))
check("VC bekam SAMPLE_RATE", vc_called == [T.SAMPLE_RATE])
check("raw_kind_turns == 0", info["raw_kind_turns"] == 0)
check("nico_vc == True", info["nico_vc"] is True)
check("Kind-Turn hat vc=True", all(m["vc"] for m in info["turns"] if m["rolle"] == "kind"))

print("\n5) temperature 0.3 fuer ALLE Rollen (Hoerurteil PO, auch Kind mit VC)")
temps = {c["voice"]: c["temp"] for c in CALLS}
check("Erzaehler (Iapetus) -> 0.3", temps.get("Iapetus") == 0.3, str(temps.get("Iapetus")))
check("Erwachsene (Vindemiatrix) -> 0.3", temps.get("Vindemiatrix") == 0.3, str(temps.get("Vindemiatrix")))
check("Kind MIT VC (Puck) -> 0.3", temps.get("Puck") == 0.3, str(temps.get("Puck")))
check("Konstante ist 0.3", T.TTS_TEMPERATURE == 0.3)
CALLS.clear()
T.vertone(SEG, TMP / "e.wav", nico_converter=good_vc, temperature=None)
check("temperature=None wird durchgereicht (SDK-Default)",
      all(c["temp"] is None for c in CALLS), str({c["voice"]: c["temp"] for c in CALLS}))

print("\n6) VC schlaegt fehl -> Abbruch statt stillem Rohton")
for name, bad in [("wirft Exception", lambda p, s: (_ for _ in ()).throw(RuntimeError("GPU weg"))),
                  ("liefert nichts", lambda p, s: None)]:
    try:
        T.vertone(SEG, TMP / "f.wav", nico_converter=bad)
        check(f"VC {name} -> RuntimeError", False, "still weitergelaufen!")
    except RuntimeError as e:
        check(f"VC {name} -> RuntimeError", "Abbruch" in str(e), str(e)[:70])
try:
    T.vertone(SEG, TMP / "g.wav", nico_converter=lambda p, s: None, allow_raw_kind=True)
    check("mit --allow-raw-kind laeuft VC-Fehler durch", True)
except RuntimeError:
    check("mit --allow-raw-kind laeuft VC-Fehler durch", False)

print("\n6b) TTS-Fehlschlag -> Abbruch statt stillem Loch (der Bug vom 16.07.)")
def fail_second(client, voice, style, text, retries=3, temperature=None):
    CALLS.append({"voice": voice, "temp": temperature, "text": text})
    return None if voice == "Puck" else b"\x00\x00" * 2400   # Kind-Turn schlaegt fehl
T.synth_pcm = fail_second
try:
    T.vertone(SEG, TMP / "h.wav", nico_converter=good_vc)
    check("fehlgeschlagener Turn -> RuntimeError", False, "still uebersprungen — Loch entstanden!")
except RuntimeError as e:
    check("fehlgeschlagener Turn -> RuntimeError", "Loch in der Geschichte" in str(e), str(e)[:70])
info = T.vertone(SEG, TMP / "i.wav", nico_converter=good_vc, allow_incomplete=True)
check("--allow-incomplete laeuft durch", info["n_rendered"] == 2)
check("fehlende_turns == [2]", info["fehlende_turns"] == [2], str(info["fehlende_turns"]))
check("vollstaendig == False", info["vollstaendig"] is False)
T.synth_pcm = fake_synth
info = T.vertone(SEG, TMP / "j.wav", nico_converter=good_vc)
check("sauberer Lauf -> vollstaendig == True", info["vollstaendig"] is True)
check("n_soll zaehlt nur nicht-leere Turns", info["n_soll"] == 3, str(info["n_soll"]))
leer = {"cast": SEG["cast"], "turns": SEG["turns"] + [{"rolle": "erzähler", "text": "   "}]}
info = T.vertone(leer, TMP / "k.wav", nico_converter=good_vc)
check("leerer Turn macht Lauf NICHT unvollstaendig", info["vollstaendig"] is True,
      f"n_soll={info['n_soll']} n_rendered={info['n_rendered']}")

print("\n6c) Batch-Pfad: Gate greift VOR der VC (keine GPU-Arbeit an Unvollstaendigem)")
T.vertone = _vertone          # ab hier der echte Default (batch)
_ohne_qa = lambda *a, **kw: _vertone(*a, **{"qa": False, **kw})   # Fake-PCM besteht keine echte QA
T.vertone = _ohne_qa
import inspect
_sig = inspect.signature(_vertone)
check("Standard synth_mode ist 'batch'", _sig.parameters["synth_mode"].default == "batch",
      str(_sig.parameters["synth_mode"].default))
check("Standard pcm_cache ist None (= out_dir/pcm_cache)",
      _sig.parameters["pcm_cache"].default is None)
sys.path.insert(0, str(REPO / 'scripts'))
import tts_batch as B
BATCH_CALLS = {"n": 0}
def fake_batch(client, reqs, cache_dir, **kw):
    BATCH_CALLS["n"] += 1
    BATCH_CALLS["reqs"] = reqs
    BATCH_CALLS["cache_dir"] = cache_dir
    if BATCH_CALLS.get("fehlend"):
        return ({r.key: b"\x00\x00" * 2400 for r in reqs[:-1]}, [reqs[-1]])
    return ({r.key: b"\x00\x00" * 2400 for r in reqs}, [])
B.batch_synthesize = fake_batch
import tts_batch
sys.modules['tts_batch'].batch_synthesize = fake_batch
T.synth_pcm = fake_synth

vc_calls = []
def zaehl_vc(pcm, sr):
    vc_calls.append(1); return b"\x11\x11" * 2400
BATCH_CALLS["fehlend"] = True
try:
    T.vertone(SEG, TMP / "m.wav", nico_converter=zaehl_vc, synth_mode="batch")
    check("unvollstaendiger Batch -> RuntimeError", False, "durchgelaufen!")
except RuntimeError as e:
    check("unvollstaendiger Batch -> RuntimeError", "VOR der Voice-Conversion" in str(e), str(e)[:60])
check("VC wurde NICHT aufgerufen (kein GPU-Verbrauch)", len(vc_calls) == 0, str(len(vc_calls)))

BATCH_CALLS["fehlend"] = False
CALLS.clear()
info = T.vertone(SEG, TMP / "n.wav", nico_converter=zaehl_vc, synth_mode="batch")
check("sauberer Batch-Lauf -> vollstaendig", info["vollstaendig"] is True)
check("3 Turns gerendert", info["n_rendered"] == 3, str(info["n_rendered"]))
check("VC lief auf dem Kind-Turn", len(vc_calls) == 1, str(len(vc_calls)))
check("KEIN sync-Call im Batch-Modus", len(CALLS) == 0, str(len(CALLS)))
check("Requests tragen temperature 0.3", all(r.temperature == 0.3 for r in BATCH_CALLS["reqs"]))
check("Cache-Default = out_wav.parent/pcm_cache",
      BATCH_CALLS["cache_dir"] == TMP / "pcm_cache", str(BATCH_CALLS["cache_dir"]))
info = T.vertone(SEG, TMP / "o.wav", nico_converter=zaehl_vc, synth_mode="batch",
                 pcm_cache=TMP / "geteilt")
check("--pcm-cache wird durchgereicht", BATCH_CALLS["cache_dir"] == TMP / "geteilt")
check("leere Turns kommen NICHT in den Batch",
      len(T._turn_requests(SEG["turns"] + [{"rolle": "erzähler", "text": "  "}], SEG["cast"], 0.3)) == 3)
try:
    T.vertone(SEG, TMP / "p.wav", nico_converter=good_vc, synth_mode="quatsch")
    check("unbekannter synth_mode -> ValueError", False)
except ValueError:
    check("unbekannter synth_mode -> ValueError", True)

print("\n6d) Sync-Pfad nutzt den PCM-Cache (Wiederaufsetzen nach Abbruch)")
# Warum das zaehlt: mit temperature=0.3 haengt ~jeder 2.-3. Call. Ohne Cache im Sync-Pfad begann
# jeder Wiederholungslauf bei null — der Abbruch vom 17.07. warf 11 fertige Turns weg.
cache_gt = TMP / "sync_cache_test"
CALLS.clear()
T.vertone(SEG, TMP / "q.wav", nico_converter=good_vc, pcm_cache=cache_gt, synth_mode="sync")
n_erst = len(CALLS)
check("1. Lauf ruft die API fuer alle 3 Turns", n_erst == 3, str(n_erst))
check("Cache-Dateien liegen da", len(list(cache_gt.glob("*.pcm"))) == 3,
      str(len(list(cache_gt.glob("*.pcm")))))
CALLS.clear()
info = T.vertone(SEG, TMP / "r.wav", nico_converter=good_vc, pcm_cache=cache_gt, synth_mode="sync")
check("2. Lauf ruft die API GAR NICHT (alles aus Cache)", len(CALLS) == 0, str(len(CALLS)))
check("2. Lauf ist trotzdem vollstaendig", info["vollstaendig"] is True)
check("2. Lauf rendert alle 3 Turns", info["n_rendered"] == 3, str(info["n_rendered"]))
# Ein anderer temperature-Wert MUSS am Cache vorbei (sonst liefert er Audio der falschen Stufe).
CALLS.clear()
T.vertone(SEG, TMP / "s.wav", nico_converter=good_vc, pcm_cache=cache_gt, temperature=0.9, synth_mode="sync")
check("anderer temperature-Wert -> KEIN Cache-Treffer", len(CALLS) == 3, str(len(CALLS)))

print("\n7) WAV wird geschrieben + Timeout-Konstanten gesetzt")
check("WAV existiert", (TMP / "d.wav").exists())
with wave.open(str(TMP / "d.wav")) as w:
    check("24 kHz mono 16-bit", (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2))
check("TTS_TIMEOUT_MS == 60000", T.TTS_TIMEOUT_MS == 60_000)
import tts_produce as P
check("tts_produce.TTS_TIMEOUT_MS == 60000", P.TTS_TIMEOUT_MS == 60_000)

print("\n" + ("ALLE TESTS OK" if not fails else f"{len(fails)} FEHLER: {fails}"))
sys.exit(1 if fails else 0)
