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

---

## Pipeline-Workflow-Hinweise (2026-06-24)

### Staged-Lauf (empfohlen für Produktionsläufe):
  python scripts/run_batch.py --themen X Y Z --stufen 1 2 3 \
    --output-dir articles/<run> --stage 1
  python scripts/vision_retry.py articles/<run>   # falls Exit 1: erneut ausführen
  python scripts/run_batch.py --themen X Y Z --stufen 1 2 3 \
    --output-dir articles/<run> --stage 2
  python scripts/run_batch.py --themen X Y Z --stufen 1 2 3 \
    --output-dir articles/<run> --stage 3

### NICHT: Voll-Lauf (--stage 0 / kein --stage) wenn Vision-Retry nötig ist
  Alle Stages laufen inline im selben Prozess — externer Kill nach Stage 1 nicht möglich.
  Voll-Lauf nur wenn 503-Lage stabil und Vision-Ausfälle akzeptabel.

### Server-Stop in Git-Bash (pkill nicht verfügbar):
  PowerShell: Get-NetTCPConnection -LocalPort 8093 | Stop-Process
  Oder: netstat -ano | findstr :8093  dann  taskkill /PID <pid> /F

### Vision-Retry-Gate:
  Bei images_vision_failed > 0 blockiert Stage 2 (sys.exit(2)).
  Bypass nur mit --force-stage2 (bewusste Entscheidung dokumentieren).

### Erde/Solitär-Lemmata:
  Kompass findet für manche Top-Lemmata keine Companions (503 oder thematisch isoliert).
  Retry bei stabiler API — falls erneut 0 Companions: Einzelfall-Entscheidung
  (Stage 2 ohne Companions via --force-stage2, oder Thema zurückstellen).

---

## TTS — Festgelegte Parameter (Stand 15.06.2026)

Im Chat-Thread festgelegt, hier nachgetragen (war nie in der Projektdoku).

**Stimme:** Iapetus

**TTS-Modell:** `gemini-3.1-flash-tts-preview` (verifiziert lauffähig — liefert
rohes PCM `audio/L16;rate=24000`, muss in WAV-Container gewrappt werden).

**Tagging-Modell:** `gemini-3.5-flash` (503-anfällig; stabile Fallback-Option:
`gemini-2.5-flash-lite`).

**Kompositions-Skript:** `tts_compose.py` (committed af78549). JSON-nativ
(sections/sentences/boxes), erzeugt ProfessorPhrasen, vertont `stimmt_das`
mit Absatzpause (Frage → Pause → Antwort). Quiz wird bewusst ausgelassen —
interaktive Komponente = separater Schritt.

**Scene-Instructions** (ruhiger Professor-Charakter, final gewählt von Andreas):

**S1 (4–6 Jahre):**
> Read aloud as a good-natured professor sharing something with a young
> child, as if sitting together quietly. Calm, warm, a little slower than
> normal. Friendly but understated — let the wonder come from the words,
> not loud emphasis.

**S2 (7–9 Jahre):**
> Read aloud as a relaxed, good-natured professor sharing a story with a
> child. Conversational and unhurried, as if chatting at the kitchen table.
> Understated, warm, natural — no dramatic emphasis.

**S3 (10–12 Jahre):**
> Read aloud as a calm, knowledgeable professor explaining something to an
> older child. Conversational and even, quietly engaged. Natural pace,
> minimal emphasis — clear and grounded, never dramatic.
