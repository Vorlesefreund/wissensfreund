#!/usr/bin/env python3
"""
Lektorat Beleg-Findungstest — Positionsabhängigkeit.

15 Fakten (5 je Thema × 3 Themen) aus 5 Positions-Bändern (0-20% … 80-100%)
des jeweiligen Primärtexts. Alle Fakten korrekt und im Quelltext belegt.

Erwartung: Lektorat gibt KEIN Flag (kein KORRIGIERT, kein PRÜFEN).
Jedes PRÜFEN oder KORRIGIERT = false-positive = Retrieval-Versagen.
"""
import json, os, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from lektorat_common import (
    build_grounded_sources_block,
    build_lektorat_parts,
    parse_lektorat_v2,
    annotate_article_lektorat_v2,
    LEKTORAT_MODEL,
    LEKTORAT_SYSTEM,
    COMPANION_CHAR_CAP,
)
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
cp = json.loads((ROOT / "articles" / "batch_output" / "stage1_checkpoint.json")
               .read_text(encoding="utf-8"))
topics = cp["topics"]


# ── Probe-Fakten: (band_label, position_pct, probe_sentence, source_quote) ────

PROBE_FACTS = {
    "Dinosaurier": [
        ("0-20%",  "8%",
         "Bis 2006 wurden 527 Dinosaurier-Gattungen wissenschaftlich beschrieben.",
         "Bis 2006 wurden 527 Gattungen von Nichtvogeldinosauriern … wissenschaftlich beschrieben"),
        ("20-40%", "30%",
         "Das erste fast vollständige Exemplar des Archaeopteryx wurde im Jahr 1861 entdeckt.",
         "das erste fast vollständige Exemplar von Archaeopteryx bereits im Jahr 1861 gefunden wurde"),
        ("40-60%", "41%",
         "Diplodocus ist der längste durch vollständige Skelette bekannte Dinosaurier — ein Fund zeigt 27 Meter.",
         "Der längste durch vollständige Skelette bekannte Dinosaurier ist Diplodocus, ein Skelettfund zeigt eine Länge von 27 Metern"),
        ("60-80%", "68%",
         "Der Prosauropode Plateosaurus konnte mindestens 27 Jahre alt werden.",
         "Die Lebenserwartung des … Plateosaurus wird auf mindestens 27 Jahre geschätzt"),
        ("80-100%","81%",
         "Die erste formelle Beschreibung eines Dinosaurierfossils fertigte Robert Plot im Jahr 1677 an.",
         "Im Jahr 1677 fertigte Robert Plot die erste formelle Beschreibung eines Dinosaurierfossils an"),
    ],
    "Elefant": [
        ("0-20%",  "3%",
         "Die meisten Verwandten der heutigen Elefanten starben vor etwa 10.000 Jahren am Ende der Eiszeit aus.",
         "Ein Großteil der Angehörigen dieser Gattungen starb im Übergang vom Pleistozän zum Holozän vor etwa 10.000 Jahren aus"),
        ("20-40%", "27%",
         "Die Haut des Afrikanischen Elefanten ist bis zu 40 mm dick, die des Asiatischen bis zu 30 mm.",
         "Die Haut ist mitunter sehr dick, beim Asiatischen Elefanten bis 30 mm, beim Afrikanischen Elefanten bis zu 40 mm"),
        ("40-60%", "50%",
         "Elefanten verwerten ihre Grasnahrung nur zu etwa 45 Prozent, da ihr Verdauungssystem weniger effizient ist als das der Wiederkäuer.",
         "Die Grasnahrung wird zu etwa 45 % verwertet, da die Tiere ein weniger effizientes Verdauungssystem haben als etwa die Wiederkäuer"),
        ("60-80%", "62%",
         "Der einzige bekannte Hybrid aus asiatischer Elefantenkuh und afrikanischem Bullen wurde 1978 im Zoo von Chester geboren.",
         "der einzige bekannte Hybride zwischen einer asiatischen Elefantenkuh und einem afrikanischen Elefantenbullen 1978 im Zoo von Chester geboren"),
        ("80-100%","83%",
         "Die Lanze von Lehringen wurde in einem Waldelefantenskelett gefunden und ist rund 120.000 Jahre alt.",
         "die rund 120.000 Jahre alte Lanze von Lehringen, die in einem Skelett eines Europäischen Waldelefanten"),
    ],
    "Zweiter Weltkrieg": [
        ("0-20%",  "0%",
         "Der Zweite Weltkrieg kostete schätzungsweise über 65 Millionen Menschen das Leben.",
         "Schätzungen zufolge wurden über 65 Millionen Menschen getötet"),
        ("20-40%", "20%",
         "Bei den Kämpfen um Dünkirchen verlor die britische Armee rund 68.000 Soldaten.",
         "Die Briten hatten bei den Kämpfen 68.000 Mann verloren"),
        ("40-60%", "40%",
         "Der Dezember 1941 wurde zum Wendepunkt: Hitlers Kriegserklärung an die USA und der Rückschlag vor Moskau markierten die Wende.",
         "Nach Hitlers Kriegserklärung an die USA und dem Rückschlag vor Moskau wurde der Dezember 1941 zum Wendepunkt der Weltpolitik"),
        ("60-80%", "60%",
         "Als 1943 die Niederlage der Achsenmächte absehbar wurde, erklärte Spaniens Diktator Franco sein Land für neutral.",
         "Als sich im Laufe des Jahres 1943 die Niederlage der Achsenmächte abzeichnete, ging Franco auf Distanz zu ihnen. Er erklärte Spanien in diesem Jahr für neutral"),
        ("80-100%","89%",
         "China hatte mit etwa 14 Millionen Kriegsopfern die zweithöchste Opferzahl im Zweiten Weltkrieg.",
         "China … hatte mit ungefähr 14 Millionen im Krieg getöteten Menschen die zweithöchste Anzahl an Todesopfern"),
    ],
}


def make_probe_article(thema: str, facts: list) -> dict:
    """Minimales Artikel-JSON: eine Section mit 5 Probe-Sätzen."""
    sentences = [
        {"id": f"probe_{i+1}", "text": fact[2]}
        for i, fact in enumerate(facts)
    ]
    return {
        "meta": {
            "id": f"probe_{thema.lower().replace(' ','_')}",
            "title": thema,
            "age_level": 3,
        },
        "sections": [
            {
                "id": "sec1",
                "heading": f"Probe-Fakten {thema}",
                "sentences": sentences,
                "boxes": [],
            }
        ],
        "quiz": {},
    }


def run_lektorat(thema: str, article: dict, t: dict) -> dict:
    primary_title = t.get("primary_wikipedia") or thema
    primary_text  = t.get("primary_text", "")
    companion_texts = t.get("companion_texts") or {}
    companion_order = list(companion_texts.keys())

    sources_block = build_grounded_sources_block(
        primary_title, primary_text, companion_order, companion_texts
    )
    sources_prefix, article_task = build_lektorat_parts(article, sources_block)

    # Token-Info
    sources_chars = len(sources_block)
    print(f"  Quellblock: {sources_chars:,} Zeichen "
          f"(~{sources_chars/3.8:.0f} Tokens, "
          f"{sources_chars/3.8/200000*100:.1f}% von 200k)")

    msg = client.messages.create(
        model=LEKTORAT_MODEL,
        max_tokens=4000,
        system=[{"type": "text", "text": LEKTORAT_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": [
            {"type": "text", "text": sources_prefix,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": article_task},
        ]}],
    )
    u = msg.usage
    print(f"  Tokens: in={u.input_tokens} cc={getattr(u,'cache_creation_input_tokens',0)} "
          f"cr={getattr(u,'cache_read_input_tokens',0)} out={u.output_tokens}")
    return parse_lektorat_v2(msg.content[0].text)


# ── Ergebnis-Analyse ──────────────────────────────────────────────────────────

def analyze_results(thema: str, facts: list, result: dict) -> int:
    """parse_lektorat_v2 gibt {"corrections": [...], "pruefen": [...]} zurück."""
    corrections = result.get("corrections", [])
    pruefen     = result.get("pruefen", [])

    # Index: Claim-Anfang → Eintrag
    def find_flag(probe_sent: str):
        key = probe_sent[:40].lower()
        for c in corrections:
            if key in c.get("claim_original", "").lower():
                return c.get("stufe", "KORRIGIERT"), c
        for p in pruefen:
            if key in p.get("claim_original", "").lower():
                return "PRÜFEN", p
        return None, None

    print(f"\n  {'Band':<8} {'Pos':>4}  {'Tier':<12} {'Satz (Anfang)':<55} {'Status'}")
    print(f"  {'─'*8} {'─'*4}  {'─'*12} {'─'*55} {'─'*12}")

    found_flags = 0
    for i, (band, pos_pct, probe_sent, source_quote) in enumerate(facts):
        tier, entry = find_flag(probe_sent)
        if tier is None:
            tier_disp = "kein Flag ✓"
            status = "OK"
        elif tier in ("PRÜFEN",):
            found_flags += 1
            tier_disp = f"PRÜFEN ⚠"
            status = "FALSE-POS"
        elif tier == "SILENT":
            # SILENT = vollständig belegt, keine Änderung — kein false positive
            tier_disp = f"SILENT ✓"
            status = "OK"
        elif tier == "KORRIGIERT":
            found_flags += 1
            tier_disp = f"KORRIGIERT ⚠"
            status = "FALSE-POS"
        else:
            tier_disp = tier
            status = "?"

        print(f"  {band:<8} {pos_pct:>4}  {tier_disp:<12} {probe_sent[:55]:<55} {status}")
        if entry:
            # Zeige was das Lektorat gesagt hat
            beleg_or_prob = entry.get("beleg","") or entry.get("problem","")
            print(f"  {'':>14}  → Lektorat: {beleg_or_prob[:90]}")

    print(f"\n  → {found_flags}/{len(facts)} false positives")
    return found_flags


def dump_raw_entries(result: dict) -> None:
    corrections = result.get("corrections", [])
    pruefen     = result.get("pruefen", [])
    if corrections:
        print(f"\n  Corrections ({len(corrections)}):")
        for c in corrections:
            print(f"    [{c.get('stufe','?')}] {c.get('claim_original','')[:70]}")
            print(f"           neu: {c.get('korrektur_neu','')[:70]}")
            print(f"           WP:  {c.get('beleg','')[:80]}")
    if pruefen:
        print(f"\n  PRÜFEN ({len(pruefen)}):")
        for p in pruefen:
            print(f"    {p.get('claim_original','')[:70]}")
            print(f"           {p.get('problem','')[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────

all_false_positives = []

for thema, facts in PROBE_FACTS.items():
    print(f"\n{'='*75}")
    print(f"  THEMA: {thema}")
    print(f"{'='*75}")

    t = topics.get(thema, {})
    article = make_probe_article(thema, facts)

    result = run_lektorat(thema, article, t)
    fp_count = analyze_results(thema, facts, result)
    all_false_positives.append((thema, fp_count, len(facts)))

    dump_raw_entries(result)

    time.sleep(2)  # API-Pause

# ── Gesamt-Tabelle ────────────────────────────────────────────────────────────

print(f"\n{'='*75}")
print("  GESAMT-ERGEBNIS")
print(f"{'='*75}")
print(f"  {'Thema':<22} {'False Positives':<18} {'Primärtext'}")
lengths = {"Dinosaurier": "68k Zeichen", "Elefant": "116k Zeichen", "Zweiter Weltkrieg": "273k Zeichen"}
for thema, fp, total in all_false_positives:
    rate = fp/total*100
    bar = "⚠️ " * fp + "✓ " * (total-fp)
    print(f"  {thema:<22} {fp}/{total} ({rate:.0f}%)  {bar}  [{lengths.get(thema,'')}]")

print()
print("  Position-Profil (alle Themen zusammen):")
band_labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
# Diese Auswertung ist nur sinnvoll wenn wir die Ergebnisse je Band kennen
# → done oben in analyze_results
