#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_tts_batch.py — tts_batch.py gegen einen Fake-Client, der die ECHTEN Ausfälle nachstellt.

Die Fake-Antworten sind keine Erfindung, sondern am 2026-07-16 gegen die echte Batch-API
beobachtet: leere Antwort (`finish_reason=OTHER`, `content.parts=None`, kein Fehlerfeld,
kein Safety-Grund — bei `JOB_STATE_SUCCEEDED`!), PROHIBITED_CONTENT-Block, Fehler-Feld.

    python -X utf8 scripts/test_tts_batch.py            # Exit 0 = alles grün

Kein Netz, keine Kosten.
"""
import sys, tempfile, types as pytypes
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent      # Repo-Wurzel aus dem Skriptpfad
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts'))
import tts_batch as B

TMP = Path(tempfile.mkdtemp())
PCM = b"\x11\x22" * 2400
fails = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond: fails.append(name)

# ---- Fakes, die die echten Antwortformen nachbilden ----
def resp_audio():
    blob = pytypes.SimpleNamespace(data=PCM)
    part = pytypes.SimpleNamespace(inline_data=blob)
    cand = pytypes.SimpleNamespace(content=pytypes.SimpleNamespace(parts=[part]), finish_reason="STOP")
    return pytypes.SimpleNamespace(candidates=[cand], prompt_feedback=None)
def resp_leer():   # der reale Hauptausfall vom 16.07.
    cand = pytypes.SimpleNamespace(content=pytypes.SimpleNamespace(parts=None), finish_reason="OTHER")
    return pytypes.SimpleNamespace(candidates=[cand], prompt_feedback=None)
def resp_block():
    return pytypes.SimpleNamespace(candidates=[], prompt_feedback=pytypes.SimpleNamespace(
        block_reason="PROHIBITED_CONTENT"))

class FakeBatches:
    def __init__(self, plan): self.plan, self.runde, self.gesehen = plan, 0, []
    def create(self, model, src):
        self.runde += 1
        self.gesehen.append([r.contents for r in src])
        self._src = src
        return pytypes.SimpleNamespace(name=f"batches/fake{self.runde}")
    def get(self, name):
        verhalten = self.plan[min(self.runde, len(self.plan)) - 1]
        resps = []
        for i, _ in enumerate(self._src):
            art = verhalten(i)
            resps.append(pytypes.SimpleNamespace(
                response=art if not isinstance(art, str) else None,
                error="kaputt" if art == "error" else None))
        return pytypes.SimpleNamespace(state=pytypes.SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
                                       dest=pytypes.SimpleNamespace(inlined_responses=resps))
class FakeClient:
    def __init__(self, plan): self.batches = FakeBatches(plan)

R = [B.TtsRequest.build(voice="Puck", style="Stil-Praefix", text=f"Satz {i}", temperature=0.3)
     for i in range(3)]

print("\n1) Alles klappt in Runde 1")
c = FakeClient([lambda i: resp_audio()])
pcms, offen = B.batch_synthesize(c, R, TMP / "c1", poll_seconds=0)
check("3 PCMs", len(pcms) == 3, str(len(pcms)))
check("nichts offen", offen == [])
check("nur 1 Runde", c.batches.runde == 1, str(c.batches.runde))

print("\n2) Cache greift beim zweiten Lauf (0 neue Calls)")
c2 = FakeClient([lambda i: resp_audio()])
pcms2, offen2 = B.batch_synthesize(c2, R, TMP / "c1", poll_seconds=0)
check("3 PCMs aus Cache", len(pcms2) == 3)
check("KEIN Batch eingereicht", c2.batches.runde == 0, str(c2.batches.runde))
check("Inhalt identisch (kein Drift)", pcms2[R[0].key] == PCM)

print("\n3) Leere Antwort (finish_reason=OTHER) -> Nachreich-Runde")
# Runde 1: Request 0 leer, Rest Audio. Runde 2: alles Audio.
c3 = FakeClient([lambda i: resp_leer() if i == 0 else resp_audio(), lambda i: resp_audio()])
pcms3, offen3 = B.batch_synthesize(c3, R, TMP / "c3", poll_seconds=0)
check("am Ende 3 PCMs", len(pcms3) == 3, str(len(pcms3)))
check("nichts offen", offen3 == [])
check("2 Runden gebraucht", c3.batches.runde == 2, str(c3.batches.runde))
check("Runde 2 reichte nur den EINEN nach", len(c3.batches.gesehen[1]) == 1,
      str(len(c3.batches.gesehen[1])))

print("\n4) PROHIBITED_CONTENT -> Runde 2 OHNE Stil-Praefix (nackter Text)")
c4 = FakeClient([lambda i: resp_block() if i == 0 else resp_audio(), lambda i: resp_audio()])
pcms4, offen4 = B.batch_synthesize(c4, R, TMP / "c4", poll_seconds=0)
check("am Ende vollstaendig", len(pcms4) == 3 and offen4 == [])
check("Runde 2 schickte NUR den geblockten nach", len(c4.batches.gesehen[1]) == 1)
check("Runde 1 hatte den Stil-Praefix", c4.batches.gesehen[0][0] == "Stil-Praefix\n\nSatz 0",
      repr(c4.batches.gesehen[0][0]))
check("Runde 2 schickte NACKTEN Text (kein Praefix)", c4.batches.gesehen[1][0] == "Satz 0",
      repr(c4.batches.gesehen[1][0]))
check("Wortlaut dabei UNVERAENDERT", "Satz 0" in c4.batches.gesehen[1][0])
# Gegenprobe: eine leere Antwort (kein Block) darf NICHT auf nackten Text wechseln
c4b = FakeClient([lambda i: resp_leer() if i == 0 else resp_audio(), lambda i: resp_audio()])
B.batch_synthesize(c4b, R, TMP / "c4b", poll_seconds=0)
check("leere Antwort -> Praefix BLEIBT (nur Block schaltet um)",
      c4b.batches.gesehen[1][0] == "Stil-Praefix\n\nSatz 0", repr(c4b.batches.gesehen[1][0]))

print("\n5) Dauerausfall -> laut melden, nicht still liefern")
c5 = FakeClient([lambda i: resp_leer() if i == 0 else resp_audio()] * 3)
pcms5, offen5 = B.batch_synthesize(c5, R, TMP / "c5", poll_seconds=0)
check("2 PCMs da", len(pcms5) == 2, str(len(pcms5)))
check("1 als NICHT vertont gemeldet", len(offen5) == 1, str(len(offen5)))
check("max_rounds eingehalten", c5.batches.runde == 3, str(c5.batches.runde))

print("\n6) Fehler-Feld in der Antwort -> Nachreichen")
c6 = FakeClient([lambda i: "error" if i == 1 else resp_audio(), lambda i: resp_audio()])
pcms6, offen6 = B.batch_synthesize(c6, R, TMP / "c6", poll_seconds=0)
check("am Ende vollstaendig", len(pcms6) == 3 and offen6 == [])

print("\n7) Hash: was den Klang bestimmt, aendert den Key")
a = B.TtsRequest.build(voice="Puck", style="S", text="Hallo", temperature=0.3)
check("gleicher Inhalt -> gleicher Key",
      a.key == B.TtsRequest.build(voice="Puck", style="S", text="Hallo", temperature=0.3).key)
check("andere temperature -> anderer Key",
      a.key != B.TtsRequest.build(voice="Puck", style="S", text="Hallo", temperature=0.6).key)
check("andere Stimme -> anderer Key",
      a.key != B.TtsRequest.build(voice="Leda", style="S", text="Hallo", temperature=0.3).key)
check("anderer Stil -> anderer Key",
      a.key != B.TtsRequest.build(voice="Puck", style="X", text="Hallo", temperature=0.3).key)
check("anderer Text -> anderer Key",
      a.key != B.TtsRequest.build(voice="Puck", style="S", text="Hallo!", temperature=0.3).key)
check("bare=True laesst Stil weg", a.contents(bare=True) == "Hallo")
check("normal mit Stil-Praefix", a.contents() == "S\n\nHallo")

print("\n8) Doppelte Inhalte werden nur EINMAL synthetisiert")
dup = [B.TtsRequest.build(voice="Puck", style="S", text="Gleich", temperature=0.3) for _ in range(4)]
c8 = FakeClient([lambda i: resp_audio()])
pcms8, offen8 = B.batch_synthesize(c8, dup, TMP / "c8", poll_seconds=0)
check("1 Call statt 4", len(c8.batches.gesehen[0]) == 1, str(len(c8.batches.gesehen[0])))
check("1 PCM", len(pcms8) == 1)

print("\n" + ("ALLE TESTS OK" if not fails else f"{len(fails)} FEHLER: {fails}"))
sys.exit(1 if fails else 0)
