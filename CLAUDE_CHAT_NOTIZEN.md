# Claude Chat — Notizen für nächste Session

<!-- Zweck: Chat→Code-Übergabe für konkrete offene Aufgaben -->

---

## Offen: Related Terms (WIKIPEDIA_LINKS + ARTICLE_INDEX)

**Priorität:** nicht-blockierend — Pipeline kann ohne diese Felder laufen;
Related Terms werden dann im Artikel weggelassen (generate_articles.py überspringt sie lautlos).
**Bearbeiten nach:** erster Generierungs- + Lektorats-Validierungsrun.

**Was fehlt:**
`prepare_articles.py` befüllt `WIKIPEDIA_LINKS` und `ARTICLE_INDEX` noch nicht;
`generate_articles.py` erwartet sie als optionale Job-Felder (v3.7-Vertrag).

**Was zu tun ist:**

1. `WIKIPEDIA_LINKS` — interne Wikipedia-Links mit Position + Häufigkeit, für Related Terms.
   Quelle: Wikipedia API `prop=links` auf den Artikel.
   Format (aus v3.7-Prompt): Liste von `{slug, position, count}` oder ähnlich —
   genaues Format noch zu klären (v3.7-Prompt sagt nur "interne Links mit Position + Häufigkeit").

2. `ARTICLE_INDEX` — verfügbare Slugs im Wissensfreund-Index (welche Artikel gibt es schon?).
   Quelle: Liste aller bekannten WF-Slugs (aus `klexikon_appeal_quartil.json` + bereits generierten
   articles/*.json + ggf. topic_tree featured_articles).
   Wird im Prompt für Related Terms (core + discover) genutzt: nur Slugs aus ARTICLE_INDEX verwenden.

**Kein Blocker:** Erste Pipeline-Läufe laufen ohne diese Felder durch.
Related Terms werden dann vom Modell weggelassen — das ist dokumentiertes Verhalten in v3.7.
