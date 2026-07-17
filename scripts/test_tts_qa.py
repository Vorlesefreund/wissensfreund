#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_tts_qa.py — sichert das Qualitäts-Gate (tts_qa) und seine Verdrahtung.

Die reinen Rechenregeln (Pegel, Sprechzeit, Zahl-Normalisierung, Ähnlichkeit) laufen IMMER —
kein Netz, kein Modell. Die Whisper-Prüfungen laufen nur, wenn echte Produktions-PCMs im Repo
liegen (articles/leo_batch_20260716/pcm_cache) — sonst werden sie sauber übersprungen statt
falsch grün zu melden.

    python -X utf8 scripts/test_tts_qa.py

Kalibrierbasis: 24 echte Turns, 2026-07-17. Siehe Modul-Docstring von tts_qa.
"""
import json, sys, tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import tts_qa as Q

fails = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond: fails.append(name)

def ton(sekunden: float, amplitude: int = 3000) -> bytes:
    """Synthetischer „Sprach"-Ton — laut genug, dass der Stille-Trim ihn als Sprache zählt."""
    import array, math
    n = int(Q.SAMPLE_RATE * sekunden)
    a = array.array("h", (int(amplitude * math.sin(2 * math.pi * 220 * i / Q.SAMPLE_RATE))
                          for i in range(n)))
    return a.tobytes()

print("\n1) Pegel + Sprechzeit (ohne Whisper, reine Rechnung)")
check("Stille -> RMS ~0", Q.rms(b"\x00\x00" * 24000) < 1)
check("Ton -> RMS deutlich ueber Schwelle", Q.rms(ton(1.0)) > Q.MIN_RMS * 5, f"{Q.rms(ton(1.0)):.0f}")
check("Stille zaehlt NICHT als Sprechzeit", Q.sprech_sekunden(b"\x00\x00" * 24000 * 3) == 0.0)
check("1s Ton ~= 1s Sprechzeit", abs(Q.sprech_sekunden(ton(1.0)) - 1.0) < 0.1,
      f"{Q.sprech_sekunden(ton(1.0)):.2f}")
# Der Kern des Stille-Trims: 0,5 s Sprache in 5 s Datei -> Sprechzeit 0,5 s, nicht 5 s.
gemischt = ton(0.5) + b"\x00\x00" * int(Q.SAMPLE_RATE * 4.5)
check("Trim: 0,5s Sprache in 5s Datei", abs(Q.sprech_sekunden(gemischt) - 0.5) < 0.1,
      f"{Q.sprech_sekunden(gemischt):.2f}")

print("\n2) Zahl-Normalisierung (sonst Fehlalarm bei jeder Jahreszahl)")
# Whisper schreibt Ziffern, die Quelle schreibt aus — real gemessen an "vor ueber fuenfhundert Jahren".
check("'fünfhundert' == '500'", Q.aehnlichkeit("vor über fünfhundert Jahren",
                                               "vor über 500 Jahren") > 0.95,
      f"{Q.aehnlichkeit('vor über fünfhundert Jahren', 'vor über 500 Jahren'):.2f}")
check("'zwei' == '2'", Q.aehnlichkeit("er hat zwei Hände", "er hat 2 Hände") > 0.95)
check("Interpunktion egal", Q.aehnlichkeit("Das ist die Mona Lisa.", "das ist die mona lisa") > 0.98)
check("verhoerter Eigenname bleibt ueber der Schwelle (kein Fehlalarm)",
      Q.aehnlichkeit("Oma Rina lacht.", "O Marina lacht.") >= Q.MIN_AEHNLICHKEIT,
      f"{Q.aehnlichkeit('Oma Rina lacht.', 'O Marina lacht.'):.2f}")
check("voellig anderer Text faellt durch (der zip-Bug)",
      Q.aehnlichkeit("Warum hat er das gemacht?", "Hat er auch Maschinen gebaut?") < Q.MIN_AEHNLICHKEIT,
      f"{Q.aehnlichkeit('Warum hat er das gemacht?', 'Hat er auch Maschinen gebaut?'):.2f}")

print("\n3) pruefe() faengt die billigen Faelle OHNE Whisper")
ok, g = Q.pruefe(None, "egal", mit_whisper=False)
check("kein Audio -> abgelehnt", not ok and "kein Audio" in g, g)
ok, g = Q.pruefe(b"\x00\x00" * 24000 * 3, "Er hat nicht vier Arme, Theo.", mit_whisper=False)
check("3s Stille -> abgelehnt", not ok, g)
ok, g = Q.pruefe(ton(0.1), "Hallo", mit_whisper=False)
check("zu kurz -> abgelehnt", not ok, g)
# Der reale Defekt vom 16.07.: 54 s Datei, praktisch stumm, gueltiger Audio-Blob.
ok, g = Q.pruefe(b"\x01\x00" * int(Q.SAMPLE_RATE * 54), "Er hat nicht vier Arme, Theo. " * 3,
                 mit_whisper=False)
check("54s Stille (realer Defekt) -> abgelehnt", not ok, g)
ok, g = Q.pruefe(ton(4.0), "Dies sind sieben Woerter in Folge", mit_whisper=False)
check("plausibler Ton+Text -> durch", ok, g)
ok, g = Q.pruefe(ton(40.0), "Drei kurze Woerter", mit_whisper=False)
check("40s fuer 3 Woerter -> abgelehnt (Dehnungs-Schleife)", not ok, g)

print("\n4) Verdrahtung: durchgefallenes Audio wird NICHT gecacht")
import tts_story as T
import tts_batch as B
cache = Path(tempfile.mkdtemp())
req = B.TtsRequest.build(voice="Puck", text="Hallo Welt", temperature=0.3)
T.synth_pcm = lambda *a, **kw: b"\x00\x00" * 2400          # immer Ausschuss (Stille)
pcm = T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3,
                         qa=lambda p, t: (False, "Testausschuss"))
check("Ausschuss -> kein PCM zurueck", pcm is None)
check("Ausschuss -> NICHTS im Cache (kein vergifteter Cache)",
      not (cache / f"{req.key}.pcm").exists())
gut = ton(1.0)
T.synth_pcm = lambda *a, **kw: gut
pcm = T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3,
                         qa=lambda p, t: (True, ""))
check("sauberes Audio -> gecacht", (cache / f"{req.key}.pcm").exists())
rufe = []
T.synth_pcm = lambda *a, **kw: rufe.append(1) or gut
T._sync_pcm_cached(None, cache, req, "Puck", "", "Hallo Welt", 0.3, qa=lambda p, t: (True, ""))
check("Cache-Treffer -> kein neuer Call", len(rufe) == 0, str(len(rufe)))

print("\n5) Whisper gegen ECHTE Produktions-Turns")
CD = REPO / "articles" / "leo_batch_20260716" / "pcm_cache"
idx_p = CD / "_index.json"
if not idx_p.exists():
    print("  uebersprungen — keine echten PCMs im Repo (articles/leo_batch_20260716/pcm_cache)")
else:
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    paare = [(k, v) for k, v in idx.items() if (CD / f"{k}.pcm").exists()]
    echte = [(k, v) for k, v in paare if Q.rms((CD / f"{k}.pcm").read_bytes()) > 500]
    kaputt = [(k, v) for k, v in paare if Q.rms((CD / f"{k}.pcm").read_bytes()) <= 500]
    print(f"  ({len(echte)} intakte + {len(kaputt)} defekte Turns gefunden)")
    fehlalarme = []
    for k, v in echte[:8]:
        ok, g = Q.pruefe((CD / f"{k}.pcm").read_bytes(), v["text"])
        if not ok: fehlalarme.append((v["text"][:40], g))
    check("KEIN Fehlalarm auf echten Turns", not fehlalarme, str(fehlalarme[:2]))
    for k, v in kaputt:
        ok, g = Q.pruefe((CD / f"{k}.pcm").read_bytes(), v["text"])
        check(f"realer Defekt erkannt ({v['text'][:28]}…)", not ok, g)
    if len(echte) >= 2:
        (k1, v1), (k2, v2) = echte[0], echte[1]
        ok, g = Q.pruefe((CD / f"{k2}.pcm").read_bytes(), v1["text"])
        check("vertauschtes Audio erkannt (zip-Bug)", not ok, g)

# ── 6) Zuordnung Request→Antwort (der zip-Bug) ────────────────────────────────
print("\n6) Zuordnung per metadata statt per Reihenfolge (zip-Bug an der Wurzel)")
import tts_batch as B2
from types import SimpleNamespace as NS

r1 = B2.TtsRequest.build(voice="Iapetus", text="Turn eins")
r2 = B2.TtsRequest.build(voice="Puck",    text="Turn zwei")
r3 = B2.TtsRequest.build(voice="Gacrux",  text="Turn drei")
offen = [r1, r2, r3]

# Fall A: API antwortet in ANDERER Reihenfolge → metadata rettet die Zuordnung.
resp = [NS(metadata={"key": r3.key}, response="C", error=None),
        NS(metadata={"key": r1.key}, response="A", error=None),
        NS(metadata={"key": r2.key}, response="B", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
zuordnung = {r.key: rw.response for r, rw in paare}
check("vertauschte Reihenfolge -> per metadata korrekt zugeordnet",
      zuordnung == {r1.key: "A", r2.key: "B", r3.key: "C"}, str(zuordnung))
check("nichts faelschlich als fehlend gemeldet", ohne == [])

# Fall B: der eigentliche Bug — mittlere Antwort FEHLT. zip haette r3 das Audio von r2 gegeben.
resp = [NS(metadata={"key": r1.key}, response="A", error=None),
        NS(metadata={"key": r3.key}, response="C", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
zuordnung = {r.key: rw.response for r, rw in paare}
check("fehlende Antwort -> KEIN Verrutschen (r3 behaelt C)",
      zuordnung == {r1.key: "A", r3.key: "C"}, str(zuordnung))
check("fehlender Request kommt in die naechste Runde", [r.key for r in ohne] == [r2.key])

# Fall C: kein metadata, Anzahl passt -> Reihenfolge ist vertretbar.
resp = [NS(metadata=None, response="A", error=None),
        NS(metadata=None, response="B", error=None),
        NS(metadata=None, response="C", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
check("ohne metadata + Anzahl passt -> Reihenfolge", [rw.response for _, rw in paare] == ["A","B","C"])

# Fall D: kein metadata UND Anzahl passt nicht -> raten ist verboten.
resp = [NS(metadata=None, response="A", error=None),
        NS(metadata=None, response="B", error=None)]
paare, ohne = B2._zuordnen(offen, resp)
check("ohne metadata + Anzahl falsch -> NICHTS zuordnen", paare == [])
check("ohne metadata + Anzahl falsch -> alles in die naechste Runde", len(ohne) == 3)

print("\n" + ("ALLE TESTS OK" if not fails else f"{len(fails)} FEHLER: {fails}"))
sys.exit(1 if fails else 0)
