# build_ergiebigkeit_scores.py — Rebuild aus catalog_full.json, Format aus Altdatei gespiegelt
import json, shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"C:\Users\Andreas\wissensfreund_repo")
SRC, OUT = REPO/"catalog_full.json", REPO/"ergiebigkeit_scores.json"
ALT = REPO/"_alt"; ALT.mkdir(exist_ok=True)

def to_int(v):
    try: return int(round(float(str(v).replace(",", "."))))
    except: return None

old = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {}
old_scores = old.get("scores", old) if isinstance(old, dict) else {}
sample = next(iter(old_scores.values()), None)
print(f"Altes Wertformat: {sample!r}")

def make_emit(s):
    if isinstance(s, dict):
        for ks in (["s1","s2","s3"],["S1","S2","S3"],["erg_s1","erg_s2","erg_s3"],["1","2","3"]):
            if all(k in s for k in ks):
                return lambda a,b,c: {ks[0]:a, ks[1]:b, ks[2]:c}
        raise SystemExit(f"ABBRUCH: dict-Format unbekannt {list(s.keys())} - bitte melden")
    if isinstance(s,(list,tuple)) and len(s)>=3:
        return lambda a,b,c: [a,b,c]
    if s is None:
        return lambda a,b,c: {"s1":a,"s2":b,"s3":c}
    raise SystemExit(f"ABBRUCH: Einzelwert {s!r} nicht stufenweise - bitte melden")
emit = make_emit(sample)

cf = json.load(open(SRC, encoding="utf-8"))
assert isinstance(cf, list), "catalog_full.json soll Array sein"
tk = next((k for k in cf[0] if k.lower() in ["thema","titel","lemma","title","name"]), None)
assert tk, f"Kein Titel-Feld: {list(cf[0].keys())}"
print(f"Titel-Feld: '{tk}'")

if OUT.exists():
    st = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(OUT, ALT/f"ergiebigkeit_scores_{st}.json")
    print(f"Archiviert -> _alt/ergiebigkeit_scores_{st}.json")

scores, skip = {}, []
none_s1=none_s2=none_s3=0
for e in cf:
    key = str(e.get(tk)).strip().lower()
    s1,s2,s3 = to_int(e.get("erg_s1")), to_int(e.get("erg_s2")), to_int(e.get("erg_s3"))
    if s1 is None and s2 is None and s3 is None: skip.append(key); continue
    none_s1 += s1 is None; none_s2 += s2 is None; none_s3 += s3 is None
    scores[key] = emit(s1,s2,s3)

rescued=0
for k,v in old_scores.items():
    kk=str(k).strip().lower()
    if kk not in scores: scores[kk]=v; rescued+=1

json.dump({"_meta":{"source":"catalog_full.json (+alt-rescue)",
                    "built":datetime.now(timezone.utc).isoformat(),
                    "count":len(scores),
                    "note":"XLSX==catalog_full verifiziert (Audit 2026-06-18); Format aus Altdatei gespiegelt"},
           "scores":scores},
          open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\nGeschrieben: {len(scores)} Scores ({rescued} Altanker uebernommen, {len(skip)} leer uebersprungen)")
print(f"Stufen-Luecken (None): s1={none_s1}  s2={none_s2}  s3={none_s3}  -> S-Fallback")
