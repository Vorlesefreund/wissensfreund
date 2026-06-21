#!/usr/bin/env python3
"""
test_comparison_check.py — Unit-Tests für comparison_check.py (stdlib unittest).

Lauf:  python scripts/test_comparison_check.py
       (oder: python -m unittest scripts/test_comparison_check.py)
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import comparison_check as cc  # noqa: E402


def _comp(**over):
    """Vollständig gültiger Beispiel-Eintrag (Elefant/Masse), per kwargs überschreibbar."""
    base = {
        "text": "so viel wie vierzig Elefanten",
        "reference_object": "Elefant",
        "factor": 40,
        "dimension": "Masse",
        "source_value": 200000,
        "source_unit": "kg",
        "relation": "approx",
        "sentence_id": "s001",
    }
    base.update(over)
    return base


# Body, in dem die Default-Phrase wörtlich vorkommt:
_BODY = "Ein Blauwal wiegt so viel wie vierzig Elefanten und ist riesig."


class TestNumberWords(unittest.TestCase):
    def test_digit_present(self):
        self.assertTrue(cc.factor_in_text(40, "etwa 40 Stück"))

    def test_spelled_present(self):
        self.assertTrue(cc.factor_in_text(40, "so viel wie vierzig Elefanten"))

    def test_spelled_compound(self):
        self.assertTrue(cc.factor_in_text(21, "rund einundzwanzig Meter"))

    def test_hundred(self):
        self.assertTrue(cc.factor_in_text(100, "fast hundert Tiere"))
        self.assertTrue(cc.factor_in_text(100, "einhundert Tiere"))

    def test_digit_not_substring_of_larger(self):
        # 40 darf NICHT in "240" matchen
        self.assertFalse(cc.factor_in_text(40, "es waren 240 Tiere"))

    def test_spelled_not_substring(self):
        # "vier" (4) darf NICHT in "vierzig" matchen
        self.assertFalse(cc.factor_in_text(4, "so viel wie vierzig Elefanten"))


class TestCheckComparison(unittest.TestCase):

    # ── Kronzeuge: Gelenkbus muss anschlagen ────────────────────────────────────
    def test_gelenkbus_greater_flags(self):
        body = "Der Blauwal ist länger als zwei große Gelenkbusse."
        comp = _comp(text="länger als zwei große Gelenkbusse",
                     reference_object="Gelenkbus", factor=2, dimension="Länge",
                     source_value=33, source_unit="m", relation="greater")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertFalse(r.ok, f"Gelenkbus-Fall sollte FLAGGEN, war PASS: {r.flags}")
        self.assertTrue(r.has("greater_verletzt"),
                        f"erwartete greater_verletzt, bekam {r.flags}")

    # ── approx-Band ─────────────────────────────────────────────────────────────
    def test_approx_valid_pass(self):
        r = cc.check_comparison(_comp(), body=_BODY, sentence_text=_BODY)
        self.assertTrue(r.ok, f"erwartete PASS, bekam {r.flags}")

    def test_approx_within_tolerance_pass(self):
        # factor 30 × Elefant: 30×4000=120000 .. 30×6500=195000; mit +30 % bis 253500.
        # 200000 liegt im Band → PASS.
        body = "Er wiegt so viel wie dreißig Elefanten."
        r = cc.check_comparison(
            _comp(text="so viel wie dreißig Elefanten", factor=30),
            body=body, sentence_text=body)
        self.assertTrue(r.ok, f"erwartete PASS (Toleranz), bekam {r.flags}")

    def test_approx_grossly_wrong_flags(self):
        # factor 100 × Elefant: 400000..650000 (+30 % bis 845000); 200000 weit darunter.
        body = "Er wiegt so viel wie hundert Elefanten."
        r = cc.check_comparison(
            _comp(text="so viel wie hundert Elefanten", factor=100),
            body=body, sentence_text=body)
        self.assertFalse(r.ok, "grob falscher approx sollte FLAGGEN")
        self.assertTrue(r.has("wert_ausserhalb_approx"), r.flags)

    # ── Satz-Bindung: factor im Satz ────────────────────────────────────────────
    def test_number_mismatch_flags(self):
        # Metadaten factor 3, aber der Satz nennt "vier" → zahl_nicht_im_satz
        sent = "Er ist so lang wie vier Busse."
        comp = _comp(text="so lang wie vier Busse", reference_object="Bus",
                     factor=3, dimension="Länge", source_value=36, source_unit="m",
                     relation="approx")
        r = cc.check_comparison(comp, body=sent, sentence_text=sent)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("zahl_nicht_im_satz"), r.flags)

    def test_spelled_number_binding_pass(self):
        # "vierzig" + factor 40 → Zahl-Bindung erfüllt (kein zahl_nicht_im_satz)
        r = cc.check_comparison(_comp(), body=_BODY, sentence_text=_BODY)
        self.assertFalse(r.has("zahl_nicht_im_satz"), r.flags)

    def test_factor_in_sentence_differs_flags(self):
        # (b) Metadaten factor 40, aber der Satz nennt "dreißig" → FLAG
        sent = "Es ist so schwer wie dreißig große Elefanten zusammen."
        comp = _comp(factor=40)
        r = cc.check_comparison(comp, body=sent, sentence_text=sent)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("zahl_nicht_im_satz"), r.flags)

    # ── Satz-Bindung: eingewobenes Verb (Kern des Tunings) ──────────────────────
    def test_woven_verb_pass(self):
        # (a) "…ist so schwer wie vierzig … Elefanten…" → PASS trotz eingeschobenem Verb
        sent = ("Stell dir ein Lebewesen vor, das so schwer ist wie vierzig "
                "große afrikanische Elefanten zusammen.")
        comp = _comp(text="so schwer wie vierzig große afrikanische Elefanten zusammen",
                     reference_object="afrikanischer Elefant")
        r = cc.check_comparison(comp, body=sent, sentence_text=sent)
        self.assertTrue(r.ok, f"eingewobenes Verb sollte PASS sein, bekam {r.flags}")

    # ── Satz-Bindung: Bezugsobjekt fehlt im Satz ────────────────────────────────
    def test_reference_not_in_sentence_flags(self):
        # (c) Satz nennt den factor, aber nicht das reference_object → FLAG
        sent = "Es ist so schwer wie vierzig große Tiere zusammen."
        r = cc.check_comparison(_comp(), body=sent, sentence_text=sent)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("bezug_nicht_im_satz"), r.flags)

    # ── Bezugsobjekt / Einheit ──────────────────────────────────────────────────
    def test_unknown_reference_flags(self):
        body = "so viel wie vierzig Einhörner"
        comp = _comp(text="so viel wie vierzig Einhörner",
                     reference_object="Einhorn")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("unbekanntes_bezugsobjekt"), r.flags)

    def test_unit_tonnes_to_kg_pass(self):
        # 200 t == 200000 kg → identisch zum kg-Fall → PASS
        body = "so viel wie vierzig Elefanten"
        comp = _comp(text="so viel wie vierzig Elefanten",
                     source_value=200, source_unit="t")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertTrue(r.ok, f"t→kg sollte PASS sein, bekam {r.flags}")
        self.assertAlmostEqual(r.info["source_canonical"], 200000.0)

    def test_unknown_unit_flags(self):
        body = "so viel wie vierzig Elefanten"
        comp = _comp(text="so viel wie vierzig Elefanten",
                     source_value=200000, source_unit="Pfund")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("unbekannte_einheit"), r.flags)

    # ── Neue Saat-Tabellen-Objekte (d) ──────────────────────────────────────────
    def test_new_seed_pferd_pass(self):
        # Pferd Masse (400,1000); factor 1 → 400..1000 (+30 % bis 1300); 1000 kg → PASS
        sent = "Sein Herz ist so schwer wie ein großes Pferd."
        comp = _comp(text="so schwer wie ein großes Pferd", reference_object="Pferd",
                     factor=1, dimension="Masse", source_value=1000, source_unit="kg")
        r = cc.check_comparison(comp, body=sent, sentence_text=sent)
        self.assertTrue(r.ok, f"Pferd sollte PASS sein, bekam {r.flags}")

    def test_new_seed_transporter_pass(self):
        # Transporter Länge (5.0,7.5); factor 1 → 5..7.5 (+30 % bis 9.75); 7 m → PASS
        sent = "Allein die Schwanzflosse ist so lang wie ein großer Transporter."
        comp = _comp(text="so lang wie ein großer Transporter",
                     reference_object="Transporter", factor=1, dimension="Länge",
                     source_value=7, source_unit="m")
        r = cc.check_comparison(comp, body=sent, sentence_text=sent)
        self.assertTrue(r.ok, f"Transporter sollte PASS sein, bekam {r.flags}")

    # ── relation less: erfüllt + verletzt ───────────────────────────────────────
    def test_less_satisfied_pass(self):
        # Mensch Höhe high=1.9; factor 2 → exp_high 3.8; source 3.0 ≤ 3.8 → PASS
        body = "kleiner als zwei Menschen hoch"
        comp = _comp(text="kleiner als zwei Menschen hoch", reference_object="Mensch",
                     factor=2, dimension="Höhe", source_value=3.0, source_unit="m",
                     relation="less")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertTrue(r.ok, f"erwartete PASS, bekam {r.flags}")

    def test_less_violated_flags(self):
        # factor 2 → exp_high 3.8; source 5.0 > 3.8 → FLAG
        body = "kleiner als zwei Menschen hoch"
        comp = _comp(text="kleiner als zwei Menschen hoch", reference_object="Mensch",
                     factor=2, dimension="Höhe", source_value=5.0, source_unit="m",
                     relation="less")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertFalse(r.ok)
        self.assertTrue(r.has("less_verletzt"), r.flags)

    # ── relation greater: erfüllter Fall ────────────────────────────────────────
    def test_greater_satisfied_pass(self):
        # Gelenkbus low=17; factor 2 → exp_low 34; source 40 ≥ 34 → PASS
        body = "länger als zwei Gelenkbusse"
        comp = _comp(text="länger als zwei Gelenkbusse", reference_object="Gelenkbus",
                     factor=2, dimension="Länge", source_value=40, source_unit="m",
                     relation="greater")
        r = cc.check_comparison(comp, body=body, sentence_text=body)
        self.assertTrue(r.ok, f"erwartete PASS, bekam {r.flags}")

    # ── Robustheit: fehlende Felder → FLAG, kein Crash ──────────────────────────
    def test_missing_fields_no_crash(self):
        r = cc.check_comparison({}, body="", sentence_text=None)
        self.assertFalse(r.ok)  # diverse Flags, aber kein Crash

    def test_relation_default_approx(self):
        # ohne relation → wie approx behandelt; gültiger Fall bleibt PASS
        comp = _comp()
        del comp["relation"]
        r = cc.check_comparison(comp, body=_BODY, sentence_text=_BODY)
        self.assertTrue(r.ok, f"Default approx sollte PASS sein, bekam {r.flags}")


class TestSynonyms(unittest.TestCase):
    def test_bus_synonym(self):
        self.assertEqual(cc._resolve_reference("Bus"), "linienbus")

    def test_elefant_synonym(self):
        self.assertEqual(cc._resolve_reference("Afrikanischer Elefant"),
                         "afrikanischer elefant")

    def test_case_insensitive(self):
        self.assertEqual(cc._resolve_reference("GELENKBUS"), "gelenkbus")

    def test_unknown_returns_none(self):
        self.assertIsNone(cc._resolve_reference("Einhorn"))


class TestRealArtefact(unittest.TestCase):
    """Bindet an die echte Artikel-Struktur (sections[].sentences[])."""

    def test_body_extraction_on_real_article(self):
        p = ROOT / "articles" / "test_v324" / "articles" / "blauwal_l2.json"
        if not p.exists():
            self.skipTest(f"Artefakt fehlt: {p}")
        import json
        art = json.loads(p.read_text(encoding="utf-8"))
        body = cc.article_body_text(art)
        self.assertIsInstance(body, str)
        self.assertGreater(len(body), 100)
        smap = cc.sentence_text_map(art)
        self.assertIn("s001", smap)
        # check_article läuft ohne Crash (Bestandsartikel hat i. d. R. keine comparisons)
        results = cc.check_article(art)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
