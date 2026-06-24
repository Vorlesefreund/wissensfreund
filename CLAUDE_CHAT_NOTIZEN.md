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

---

## Review-Tool (review_tool.py) — Workflow-Hinweise (2026-06-24)

- Starten: python scripts/review_tool.py <RUN_DIR> [--port 8091]
- RUN_DIR erwartet: <RUN_DIR>/lektorat/lektorat_*.json (Body + pruefbericht)
- Pre-Lektorat-Artikel (articles/*.json) werden NICHT angefasst
- Submit via Browser: automatisch korrekt (seen_-Hidden-Felder werden mitgesendet)
- Submit via curl/Skript: ERST GET /, alle seen_korr_*/seen_silent_*-Felder aus dem
  HTML extrahieren und beim POST mitsenden — sonst bleiben KORRIGIERT/SILENT auf OFFEN
- review_decision-Werte: "angenommen" (KORRIGIERT ohne Revert) · "abgelehnt" (PRÜFEN
  oder KORRIGIERT mit Revert) · "auto" (SILENT) · "einbau_fehlgeschlagen" (Treffer-Miss)
- Idempotent: Re-Run überschreibt review_decision + reviewed_at, Body-Korrekturen
  werden erneut angewendet (bei unverändertem Body: replace findet claim_original)
- Pompeji/Herculaneum-Entscheidung (vulkan_l3 PRÜFEN[4]): abgelehnt — zeitliche
  Kompression ist zulässige Vereinfachung für S3, kein Widerspruch zur Quelle
