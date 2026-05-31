# WISSENSFREUND — ARTIKEL-PIPELINE MASTER
## Single Source of Truth | Version 3.2 | Stand: 2026-05-31

Dieses Dokument konsolidiert alle Entscheidungen aus den Chats:
- „App-Inhalte aus Wikipedia für Kinder aufbereiten"
- „Kindgerechte Zusammenfassung von Wikipedia-Artikeln"
- „Wissensfreund Artikel-Pipeline" (dieser Chat)

**Bei Widersprüchen gilt dieses Dokument.** Ältere Einzeldokumente
(wissensfreund_system_prompt.md v1, briefing.md) sind überholt.

---

## 1. GRUNDPRINZIP (EISERNE REGEL)

**Ausschließlich Wikipedia-Input — kein Trainingswissen, keine Halluzinationen.**

- Was nicht im Wikipedia-Text steht → weglassen
- Alltagsvergleiche erlaubt wenn offensichtlich korrekt ("so groß wie ein Auto")
- Zahlenvergleiche MÜSSEN rechnerisch stimmen und überprüfbar sein
- Bei Unsicherheit: lieber weglassen als erfinden

```
FALSCH: "so schnell wie 28 Kugeln nebeneinander"  ← nicht belegbar
RICHTIG: "35-mal schneller als ein Passagierflugzeug"  ← aus Artikel ableitbar
```

---

## 2. ARTIKEL-GRUNDMUSTER (4 Typen)

| Muster | `pattern`-Wert | Themen |
|--------|---------------|--------|
| Lebewesen | `living_being` | Tiere, Pflanzen |
| Orte & Geografie | `place_geography` | Länder, Städte, Landschaften |
| Geschichte & Personen | `history_person` | Epochen, Persönlichkeiten |
| Technik & Wissenschaft | `tech_science` | Erfindungen, Naturphänomene |

### Pflichtabschnitte pro Muster

`section_role: intro` ist bei ALLEN Mustern und ALLEN Stufen Pflicht
und muss immer der erste Abschnitt sein.

**living_being:**
1. `intro` — Was/Wer ist X?
2. `appearance` — Körperbau / Aussehen
3. `behavior` — Leben & Verhalten
4. `habitat` — Lebensraum & Verbreitung
5. `human_relation` — Menschen & Natur

**place_geography:**
1. `intro` — Überblick / Einordnung
2. `geography` — Lage & Geografie
3. `nature` — Natur & Klima
4. `people_culture` — Menschen & Kultur
5. `economy` — Wirtschaft & Besonderheiten

**history_person:**
1. `intro` — Wer oder was? Definition + Zeitraum
2. `historical_context` — Wie lebten/funktionierten sie?
3. `achievements` — Werk, Leistungen, Bedeutung
4. `legacy` — Wirkung bis heute
5. `myth_vs_reality` — Mythos vs. Realität (nur ab Stufe 2)

**tech_science:**
1. `intro` — Was ist das?
2. `how_it_works` — Wie funktioniert es?
3. `history` — Geschichte & Erfindung
4. `applications` — Anwendung & Alltag
5. `future_ethics` — Zukunft & Ethik (nur ab Stufe 2)

---

## 3. ALTERSGRUPPEN & ARTIKELUMFANG

### 3.1 Sprach- und Stilregeln

**Stufe 1 — 4–6 Jahre**
- Max. 10 Wörter pro Satz
- Direkte Ansprache: „Stell dir vor…", „Weißt du…?"
- Vergleiche aus der Kinderwelt: Fußball, Badewanne, Schulbus
- Kein Passiv, keine Tabellen, keine Fachbegriffe ohne Soforterklärung
- Emotional, spielerisch, viel Staunen

**Stufe 2 — 7–9 Jahre**
- Max. 18 Wörter pro Satz
- Fachbegriffe mit Soforterklärung
- Tabellen: 2 Spalten, max. 6 Zeilen
- Kausalität erklären (Warum? Wie? Was dann?)
- Keine akademischen Formulierungen

**Stufe 3 — 10–12 Jahre**
- Fachlich korrekt, kein Lehrbuchton
- Tabellen: 3 Spalten, max. 8 Zeilen
- Kritische Abschnitte, Kontroversen, Widersprüche erwünscht

### 3.2 PERSPEKTIVREGEL STUFE 1 ← NEU

Keine Altersvergleiche die das Kind kleiner machen als es ist.

```
FALSCH: „Mit 7 Jahren — da warst du noch jünger als du jetzt bist"
        (für 4–6-Jährige ist das falsch oder verwirrend)
FALSCH: „Mit 7 Jahren — genauso alt wie du"
        (stimmt nicht für alle Kinder der Stufe)
RICHTIG: „Mit 7 Jahren begann die Ausbildung — also noch als Kind"
RICHTIG: Altersangaben ohne Vergleich: „schon als kleines Kind"
```

### 3.3 TON-REGEL STUFE 1+2 ← NEU

Keine moralischen Werturteile über reale Personen.

```
FALSCH: „Er nutzte das Talent seines Sohnes gnadenlos aus"
RICHTIG: „Er ließ Ludwig viele Stunden täglich üben — das war oft sehr streng"
```

### 3.4 Artikelumfang: TARGET_WORDS Tabelle ← NEU

`CONTENT_DEPTH` (1–3, aus Wikipedia-Textlänge) und `TOPIC_INTEREST`
(low/medium/high, aus Kategorie + Pageviews) bestimmen den Zielumfang.

**Das Ziel ist ein Richtwert — kein Minimum.**
Schreibe so viel wie nötig, aber fülle niemals künstlich auf.
Wenn Stoff vorhanden ist und das Thema es rechtfertigt: Zielwert ausschöpfen.

#### Fließtext-Ziel gesamt (ohne Callouts, ohne Quiz)

| CONTENT_DEPTH | TOPIC_INTEREST | Stufe 1 | Stufe 2 | Stufe 3 |
|---------------|---------------|---------|---------|---------|
| 1 | low | 80 W. | 200 W. | 300 W. |
| 1 | medium | 120 W. | 280 W. | 400 W. |
| 1 | high | 160 W. | 350 W. | 500 W. |
| 2 | low | 120 W. | 280 W. | 450 W. |
| 2 | medium | 170 W. | 380 W. | 600 W. |
| 2 | high | 200 W. | 480 W. | 750 W. |
| 3 | low | 160 W. | 350 W. | 550 W. |
| 3 | medium | 200 W. | 500 W. | 750 W. |
| 3 | high | 250 W. | 650 W. | 950 W. |

#### Absolute Maximalgrenze (nie überschreiten)

| Stufe 1 | Stufe 2 | Stufe 3 |
|---------|---------|---------|
| 300 W. | 800 W. | 1.200 W. |

#### Abschnittszahl nach CONTENT_DEPTH × TOPIC_INTEREST

| CONTENT_DEPTH | TOPIC_INTEREST | Stufe 1 | Stufe 2 | Stufe 3 |
|---------------|---------------|---------|---------|---------|
| 1 | low/medium | 2–3 | 3–4 | 4–5 |
| 1–2 | high | 3–4 | 4–5 | 5–6 |
| 2–3 | medium | 3–4 | 4–6 | 5–7 |
| 3 | high | 4 | 5–6 | 6–8 |

---

## 4. ARTIKEL-ELEMENTE

### 4.1 Satz-Objekt (atomare TTS-Einheit)

```json
{
  "id": "s001",
  "text": "Elefanten sind die größten Landtiere der Welt.",
  "img_index": 0
}
```

- IDs fortlaufend über alle Abschnitte: s001, s002, …
- Kein HTML im Text — TTS-tauglich
- img_index 0–5 → welches Bild beim Vorlesen dieses Satzes angezeigt wird

### 4.2 Callout-Boxen

**wow** (alle Stufen, animiert)
- Überraschende Fakten, Superlative — nur aus Wikipedia-Text
- Vergleiche müssen rechnerisch korrekt und vorstellbar sein

**fakt** (ab Stufe 2, blau)
- Präzise Zusatzinfo — nie spekulativ

**stimmt** (ab Stufe 2, lila — „Stimmt das?") ← AKTUALISIERT
- Greift ein weit verbreitetes Klischee auf
- Stammt aus Filmen, Volksmund, Schulwissen — NICHT aus dem Artikeltext selbst
- Test: „Würde ein Kind das glauben, bevor es den Artikel liest?"
  - Ja → gutes Stimmt-das
  - Nein → weglassen
- Max. 1 bei Stufe 2, max. 2 bei Stufe 3 (in verschiedenen Abschnitten)
- reveal_mode: `auto` (Stufe 2, nach 3,5s) | `manual` (Stufe 3, Tippen)
- Das Thema der Box MUSS im Fließtext behandelt sein

**STIMMT-ABSCHNITTSREGEL:** ← NEU
Wenn stimmt-Callout in einem eigenen Abschnitt steht:
- Abschnittstitel darf NICHT „Stimmt das?" lauten (doppelt zum Box-Label)
- Abschnitt braucht mindestens 2–3 echte Inhaltssätze vor der Box
- Abschnitt unter thematischem Titel: „Ein weit verbreiteter Irrtum",
  „Was viele falsch glauben", „Mythos und Wirklichkeit"

```
FALSCH:
  Abschnittstitel: "Stimmt das? 🤔"
  Fließtext: "Es gibt viele Missverständnisse."
  [stimmt-Box]

RICHTIG:
  Abschnittstitel: "Ein weit verbreiteter Irrtum 🤔"
  Fließtext: "Viele glauben, Raketen bräuchten Luft wie Flugzeuge.
              Das stimmt nicht — und genau das macht Raketen so besonders."
  [stimmt-Box]
```

**warn** (alle Stufen, orange)
- Für kritische oder sensible Inhalte (Aussterben, Umwelt, Krieg)
- Sachlich, nicht erschreckend

Kein Callout im `intro`. Max. 1 Callout pro Abschnitt.

### 4.3 Quiz ← AKTUALISIERT

- Immer genau A / B / C — App fügt Präfix hinzu, Kind antwortet per Sprache
- 3 Fragen Stufe 1–2, 4–5 Fragen Stufe 3
- Fragen testen Textverständnis — kein Auswendiglernen
- correct_key gleichmäßig verteilen: nicht immer derselbe Buchstabe

**Längenregel für Antwortoptionen:** ← NEU
Alle drei Optionen müssen ähnlich lang sein.
Die richtige Antwort darf nicht systematisch die längste sein.

```
FALSCH (richtige Antwort immer am längsten):
  A: "Weil er Hunger hatte"
  B: "Weil er schlafen wollte"
  C: "Weil er Wasser suchte, um seinen Rüssel zu füllen"  ← richtig, zu lang

RICHTIG (ähnliche Länge):
  A: "Weil er einen Fluss suchte"
  B: "Weil er Hunger auf Blätter hatte"
  C: "Weil er ein Wasserloch finden wollte"  ← richtig, gleiche Länge
```

### 4.4 Bilder

- 1 Hero-Bild oben (wechselt mit Abschnitt)
- Thumbnail-Strip unten (bis zu 6 Bilder, wischbar)
- Jeder Satz hat `img_index` (0–5)
- Pro Bild: mindestens 2 Sätze, maximal 8 Sätze
- Lizenz: CC0, CC BY, CC BY-SA, Public Domain

### 4.5 Sound (optional)

Nur wenn .ogg-Datei explizit im Wikipedia-Text vorkommt.
Max. 1 Sound pro Artikel, `tts_pause: true`.

---

## 5. PIPELINE-EINGABE

### 5.1 Pflicht-Parameter

```
WIKIPEDIA_TEXT:     {bereinigter Plaintext, ohne Infobox}
ARTICLE_TITLE:      {Titel}
AGE_LEVEL:          {1 | 2 | 3}
ARTICLE_PATTERN:    {living_being | place_geography | history_person | tech_science}
CONTENT_DEPTH:      {1 | 2 | 3}
TOPIC_INTEREST:     {low | medium | high}
THEME_COLOR:        {CSS-Hex}
SOURCE_URL:         {Wikipedia-URL}
SOURCE_REV:         {Revisions-ID}
IMAGES:             {JSON-Array aus Pipeline}
```

### 5.2 Optionale Parameter

```
WIKIPEDIA_LINKS:    extrahierte interne Links mit Position + Häufigkeit
ARTICLE_INDEX:      verfügbare Artikel-Slugs im Wissensfreund-Index
```

### 5.3 CONTENT_DEPTH berechnen (in prepare_articles.py)

```python
def compute_content_depth(text_length: int) -> int:
    if text_length < 3000:  return 1
    if text_length < 8000:  return 2
    return 3
```

### 5.4 TOPIC_INTEREST berechnen (in prepare_articles.py)

Basis: Wikipedia-Aufrufstatistik (pageviews/Monat) + Kategorie-Bonus

```python
def compute_topic_interest(pageviews: int, category_id: str) -> str:
    HIGH_CATEGORIES = {
        "tiere", "tiere_saeugetiere", "tiere_voegel", "tiere_dinos",
        "weltall", "weltall_raumfahrt", "geschichte_antike",
        "geschichte_mittelalter", "kultur_sport", "kultur_essen",
    }
    bonus = 1.5 if category_id in HIGH_CATEGORIES else 1.0
    adjusted = pageviews * bonus
    if adjusted > 50000:  return "high"
    if adjusted > 10000:  return "medium"
    return "low"
```

---

## 6. JSON-SCHEMA (v1.0 — vollständig)

### 6.1 Artikel-Wurzel

```json
{
  "meta": { ... },
  "images": [ ... ],
  "sections": [ ... ],
  "quiz": { ... },
  "tts_config": { ... }
}
```

### 6.2 meta (alle Pflichtfelder)

```json
{
  "id":                   "elefant_l2",
  "title":                "Elefanten",
  "subtitle":             "Die größten Landtiere der Welt",
  "emoji":                "🐘",
  "age_level":            2,
  "pattern":              "living_being",
  "theme_color":          "#4caf50",
  "word_count":           420,
  "source_wikipedia_url": "https://de.wikipedia.org/wiki/Elefant",
  "source_wikipedia_rev": "12345678",
  "generated_at":         "2026-05-31T10:00:00Z",
  "schema_version":       "1.0",
  "review_flag":          false,
  "review_reason":        "",
  "category_top":         "tiere",
  "category_sub":         "tiere_saeugetiere",
  "content_depth":        3,
  "topic_interest":       "high"
}
```

ID-Format: `{titel_snake_case}_l{age_level}` → `elefant_l2`

### 6.3 Section

```json
{
  "id":           "sec_01",
  "heading":      "Was sind Elefanten?",
  "section_role": "intro",
  "sentences": [
    { "id": "s001", "text": "Elefanten sind die größten Tiere der Welt.", "img_index": 0 }
  ],
  "boxes":  [],
  "table":  null,
  "sound_marker": null
}
```

### 6.4 Callout-Box

```json
{
  "type":         "stimmt",
  "headline":     "Ein weit verbreiteter Irrtum",
  "text":         "Viele glauben, Elefanten vergessen nie.",
  "reveal_mode":  "auto",
  "reveal_text":  "Das stimmt nur teilweise — Elefanten haben ein sehr gutes Gedächtnis, aber nicht unfehlbar.",
  "img_index":    null
}
```

### 6.5 Quiz-Frage

```json
{
  "id":          "q01",
  "question":    "Wie viel kann ein Elefant am Tag fressen?",
  "options": [
    { "key": "A", "text": "Etwa 50 Kilogramm Pflanzen" },
    { "key": "B", "text": "Bis zu 200 Kilogramm Gras und Blätter" },
    { "key": "C", "text": "Rund 30 Kilogramm Früchte" }
  ],
  "correct_key": "B",
  "explanation": "Elefanten sind riesige Tiere — da brauchen sie auch sehr viel Nahrung.",
  "image_quiz":  false
}
```

---

## 7. THEMENFARBEN

| Thema | Farbe |
|-------|-------|
| Tiere / Natur | `#4caf50` |
| Pflanzen | `#33691e` |
| Länder / Städte | `#e65100` |
| Geschichte / Personen | `#795548` |
| Personen (Kunst/Wissenschaft) | `#6a1b9a` |
| Technik / Wissenschaft | `#37474f` |
| Weltall | `#283593` |
| Erde / Natur | `#1565c0` |
| Kultur / Gesellschaft | `#c62828` |
| Sprache / Medien | `#00838f` |

---

## 8. QUALITÄTSCHECKLISTE (vor JSON-Ausgabe)

- [ ] Alle Informationen aus WIKIPEDIA_TEXT
- [ ] Zahlvergleiche rechnerisch korrekt und nachvollziehbar
- [ ] Satz-IDs fortlaufend (s001, s002, …)
- [ ] Jeder Satz hat img_index (0–5)
- [ ] section_role: intro ist erster Abschnitt
- [ ] Stufe 1: kein Altersvergleich der Kind kleiner macht (Perspektivregel)
- [ ] Stufe 1+2: kein moralisches Urteil über reale Personen (Ton-Regel)
- [ ] stimmt-Box: Thema im Fließtext behandelt, Abschnittstitel ≠ „Stimmt das?"
- [ ] Quiz: correct_key gleichmäßig verteilt, Optionen ähnlich lang
- [ ] word_count liegt im TARGET_WORDS-Bereich (±20%)
- [ ] schema_version: "1.0" gesetzt
- [ ] review_flag korrekt gesetzt

---

## 9. REVIEW-FLAG setzen bei

- Sensiblen Themen (Tod, Krieg, Sexualität, Religion im Konflikt)
- Medizinischen Themen mit konkreten Risiken
- Politisch strittigen Themen
- Widersprüchlichem Wikipedia-Text
- Zu wenig Quell-Inhalt für Zielstufe
- Validierungsfehlern (automatisch durch Pipeline)

---

## 10. PIPELINE-SKRIPTE (Überblick)

| Skript | Zweck | Status |
|--------|-------|--------|
| `prepare_articles.py` | Wikipedia → Job-Batches | ✅ fertig |
| `generate_articles.py` | Batches → Claude API → JSONs | ✅ fertig |
| `upload_articles.py` | Index bauen + R2-Upload | ✅ fertig |
| `convert_zim_to_json.py` | Klexikon-ZIM → JSON | ✅ fertig |
| `generate_quizzes.py` | Quiz-Platzhalter nachgenerieren | ✅ fertig |
| `artikel_pipeline.yml` | GitHub Actions Workflow | ✅ fertig |

**Noch zu ergänzen in prepare_articles.py:**
- Wikipedia Pageviews API abfragen für TOPIC_INTEREST
- CONTENT_DEPTH aus Textlänge berechnen (Formel oben)
- Beide Werte in Job-JSON eintragen

---

## 11. OFFENE PUNKTE (noch nicht implementiert)

1. **Pageviews-Abfrage** in `prepare_articles.py` (Wikimedia REST API)
2. **Flutter-Integration**: ArticleService + JSON-Renderer (separate Session)
3. **Altersgruppen-Profil** im ProfileService der App (separate Session)
4. **Topic-Tree Kachel-Navigation** in der App (separate Session)
5. **Quiz-Nachgenerierung** für ZIM-konvertierte Artikel (generate_quizzes.py)
6. **Gallery-Artikel** (111 Artikel im ZIM ohne Standard-Struktur) → Version 1.1

---

## 12. DATEIEN DIESER PIPELINE (Ablage im CI-Repo)

```
wissensfreund_repo/
├── ARTIKEL_PIPELINE_MASTER.md          ← dieses Dokument
├── wissensfreund_article_schema.json   ← JSON-Schema Referenz
├── wissensfreund_categories_whitelist.json
├── wissensfreund_topic_tree.json
├── scripts/
│   ├── prepare_articles.py
│   ├── generate_articles.py
│   ├── upload_articles.py
│   ├── convert_zim_to_json.py
│   └── generate_quizzes.py
└── .github/workflows/
    └── artikel_pipeline.yml
```

Der **System-Prompt** (`wissensfreund_system_prompt.md`) wird direkt
aus diesem Master-Dokument abgeleitet — Abschnitte 1–8 sind sein Inhalt.
