#!/usr/bin/env python3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv; load_dotenv(ROOT / ".env")

from generate_grounded import (
    _trim_article_to_cap,
    GEMINI_MODEL,
    _make_thinking_config,
    count_article_words,
)

# Künstlich langer Fake-Artikel (~200 Wörter)
fake_article = {
    "title": "Tiere im Wald",
    "intro": "Der Wald ist ein wichtiger Lebensraum für viele Tiere.",
    "sections": [
        {
            "heading": "Rehe und Hirsche",
            "sentences": [
                {"text": "Rehe leben in fast allen Wäldern Europas und ernähren sich von Gras, Blättern und Kräutern."},
                {"text": "Ein Hirsch kann bis zu 200 Kilogramm schwer werden und trägt ein beeindruckendes Geweih."},
                {"text": "Im Herbst kämpfen Hirsche mit ihren Geweihen um die besten Weibchen."},
                {"text": "Rehkitze werden im Frühjahr geboren und können kurz nach der Geburt bereits stehen."},
            ],
        },
        {
            "heading": "Füchse",
            "sentences": [
                {"text": "Der Rotfuchs ist das häufigste Raubtier in deutschen Wäldern."},
                {"text": "Füchse fressen Mäuse, Insekten, Beeren und manchmal auch Vogeleiern."},
                {"text": "Sie leben in Erdbauten, die sie selbst graben oder von anderen Tieren übernehmen."},
                {"text": "Junge Füchse heißen Welpen und werden im Frühling geboren."},
            ],
        },
        {
            "heading": "Wildschweine",
            "sentences": [
                {"text": "Wildschweine sind sehr intelligente Tiere und leben in Familiengruppen, den sogenannten Rotten."},
                {"text": "Mit ihrem Rüssel wühlen sie die Erde auf der Suche nach Wurzeln, Würmern und Eicheln."},
                {"text": "Ein ausgewachsener Keiler kann über 150 Kilogramm wiegen."},
                {"text": "Frischlinge, die Jungtiere der Wildschweine, haben ein gestreiftes Fell."},
            ],
        },
        {
            "heading": "Eulen",
            "sentences": [
                {"text": "Eulen sind nachtaktive Raubtiere mit außergewöhnlich gutem Gehör und Nachtsicht."},
                {"text": "Die Schleiereule kann eine Maus noch unter einer 30 Zentimeter dicken Schneeschicht hören."},
                {"text": "Eulen können ihren Kopf fast um 270 Grad drehen, weil ihre Augen fest im Schädel sitzen."},
                {"text": "Sie nisten in hohlen Baumstämmen oder verlassenen Scheunen."},
            ],
        },
        {
            "heading": "Eichhörnchen",
            "sentences": [
                {"text": "Eichhörnchen sind flinke Kletterer und verbringen den größten Teil ihres Lebens in Baumkronen."},
                {"text": "Im Herbst verstecken sie Nüsse und Eicheln in der Erde, um sie im Winter zu fressen."},
                {"text": "Manchmal vergessen sie ihre Verstecke, und aus den vergrabenen Samen wachsen neue Bäume."},
                {"text": "Ihr buschiger Schwanz hilft ihnen beim Balancieren und wärmt sie im Schlaf."},
            ],
        },
    ],
    "quiz": [
        {"question": "Wie schwer kann ein Hirsch werden?", "answer": "bis zu 200 Kilogramm"},
        {"question": "Wie heißen junge Wildschweine?", "answer": "Frischlinge"},
    ],
    "meta": {"thema": "Tiere im Wald", "age_level": 2},
}

wc_alt = count_article_words(fake_article)
wmax = 60
thinking_config = _make_thinking_config(GEMINI_MODEL, budget_for_2_5=1024)

print(f"Fake-Artikel: {wc_alt} Wörter — trimme auf ≤ {wmax}")
trimmed, wc_neu = _trim_article_to_cap(fake_article, wmax, GEMINI_MODEL, thinking_config)
print(f"Nach Trim:    {wc_neu} Wörter")

assert wc_neu < wc_alt, f"Trim hat nicht gekürzt: {wc_alt} → {wc_neu}"
print(f"\nERGEBNIS: PASS  ({wc_alt} → {wc_neu} Wörter)")
