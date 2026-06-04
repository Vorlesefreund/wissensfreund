# WISSEN: Artikel-Pipeline
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei Artikel-Themen -->
<!-- Letztes Update: 2026-06-04 -->

## Überblick

Zwei Artikel-Quellen in der App:

1. **Klexikon-ZIM** — 3.611 Artikel, lokal auf Gerät, HTML-Format → wird zu JSON konvertiert
2. **Wissensfreund-Artikel** — KI-generiert aus Wikipedia, JSON-Format, von Cloudflare R2

Langfristiges Ziel: **ein einziges JSON-Format** für beide Quellen, ein Renderer in der App.

---

## JSON-Schema (Artikel-Datenmodell)

Drei Ebenen: `meta` → `sections[]` → `sentences[]`

Jeder Satz (`sentence`) ist das atomare TTS-Element mit:
- eigenem `img_index` (0-basiert) — welches Bild aus `images[]` beim Vorlesen angezeigt wird
- eigenem `id` (z.B. `s001`) für TTS-Highlighting
- Bildwechsel findet an thematischen Grenzen statt (nicht Abschnittsgrenzen)
- Mehrere aufeinanderfolgende Sätze können denselben `img_index` haben
- Zuweisung erfolgt durch `patch_article_images_v1.py` via Claude API

Wichtige Meta-Felder:
- `schema_version: "1.0"` — für spätere Migrationen
- `age_level` (1/2/3) — Altersstufe
- `theme_color` — Farbe für AppBar und Akzente
- `review_flag` — bei sensiblen Themen setzen

Box-Typen in Abschnitten:
- `wow` (gelb) — überraschende Fakten
- `fakt` (blau) — wichtige Fakten
- `stimmt` (lila) — Klischee-Aufklärung, mit `reveal_text` und `reveal_mode`
- `warn` (orange) — kritische Inhalte (Aussterben, Umwelt)

**OFFEN — Box-Key Klärung:** Im System-Prompt und Code tauchen `myth`, `stimmt` und `stimmt_das`
als Keys auf. Der kanonische Key ist noch nicht final festgeklopft. Vor dem ersten
Produktions-Run klären und einheitlich dokumentieren.

Quiz: 3 Fragen (Stufe 3: 4 Fragen), Antworten A/B/C (für STT-Erkennung),
`correct_key` gleichmäßig auf A/B/C verteilen.

---

## Altersstufen + Wortgrenzen

**ZÄHLREGEL: Fließtext + Boxen zusammen, OHNE Quiz.**
Interest-gestaffelt über TOPIC_INTEREST (Pageviews): low / medium / high.

| Stufe | Alter | low-interest | medium-interest | high-interest | Besonderheiten |
|---|---|---|---|---|---|
| 1 | 4–6 J | 50–100 | 100–150 | 150–250 | Max. 10 Wörter/Satz, Bilder-Quiz, keine Tabellen |
| 2 | 7–9 J | 80–150 | 150–250 | 250–400 | Einleitungssatz, Fachbegriffe mit Erklärung, myth-reveal auto |
| 3 | 10–12 J | 100–200 | 200–350 | 350–650 | Tabellen erlaubt, myth-reveal manuell |

**WICHTIG (MASSGEBLICHER STAND, Entscheidung 02.06.):** Frühere Werte (~200/500/900 bzw.
~200/400/700) und die alte „nur Fließtext, Boxen on top"-Regel sind ÜBERHOLT.
Zählung: inkl. Boxen, ohne Quiz, obige Spannen.
HINWEIS: low-interest bewusst niedrig — für wenig ergiebige Themen oder wo ein Verweis ausreicht.

Genaue Zielwerte: CONTENT_DEPTH × TOPIC_APPEAL → siehe System-Prompt-Tabelle.

**Stufe 1 Sonderregel:** Keine Altersvergleiche die das Kind kleiner machen.
Kein Passiv, keine Tabellen, keine Fachbegriffe ohne Soforterklärung.

---

## Content-Sicherheit (Text)

- **Halluzinations-Schutz (Eiserne Regel):** Vollständiger Wikipedia-Text kommt in den Prompt.
  Das Modell formuliert AUSSCHLIESSLICH daraus — kein Web, kein Trainingswissen, kein Fallback.
  Grundsatz: jede Aussage im Artikel muss einer Stelle im Wikipedia-Input zuordenbar sein
  (RAG-Grounding-Prinzip).
- **Alterseignung:** Enthält der Wikipedia-Input für die Altersstufe ungeeignetes Material
  (detaillierte Gewalt, explizite medizinische Details o.ä.), wird es WEGGELASSEN —
  nicht umgeschrieben, nicht ersetzt. Der Artikel wird ggf. kürzer, bleibt aber sauber.
- **Themen-/Kategorie-Blacklist VOR der Generierung:** bestimmte Wikipedia-Kategorien werden
  gar nicht erst als Input zugelassen. "Neuere Geschichte" (WWII, Holocaust etc.) erst ab Stufe 2
  (`age_level_minimum: 2` in Whitelist). Kategorien wie "Pornografie", "Sexualität (explizit)"
  sind in `global_exclusions.topics` der Whitelist gelistet — **aber derzeit kein aktiver Code**
  prüft diese topics-Liste. Als offenen Punkt markiert (→ Content-Sicherheit Bilder unten).

---

## Content-Sicherheit (Bilder) — KINDERSCHUTZ

Geplante dreistufige Filterung (Konzept):

- **Stufe 1 — Lizenz-Whitelist:** nur CC0, CC-BY, CC-BY-SA → **aktiv implementiert** in
  `_is_free_license()` (generate_articles.py) und Commons-API `LicenseShortName`-Filter
  (patch_article_images_v1.py)
- **Stufe 2 — Kategorie-Blacklist:** Wikipedia-Bildkategorien (Human_sexuality, War_photographs,
  Medical_imaging, Nudity u.a.) grundsätzlich ausschließen → **NICHT implementiert.**
  `global_exclusions.topics` in der Whitelist ist totes Konzept-JSON — kein Code prüft es.
  Wikipedia-Bildkategorien werden nirgends abgefragt.
- **Stufe 3 — Automatische Bildanalyse:** Content-Moderation vor Aufnahme → **partiell.**
  `call_claude_image_filter()` in patch_article_images_v1.py sendet altersgerechte Regeln
  an Claude (`"Stufe 1: Keine Skelette, Fossilien, Anatomie, tote Tiere, Jagdszenen"`),
  aber Claude sieht nur **Dateinamen**, nicht die Bilder selbst. Kein Vision-Model,
  kein Safe-Search-API. Noch nicht produktiv gelaufen.

**⚠️ OFFEN (Kinderschutz, Hoch):** Stufe 2 + 3 fehlen als aktiver Code-Filter.
Frage vor Produktions-Bild-Run: Reicht Dateiname-basierter Claude-Filter,
oder braucht es Wikipedia-Kategorienabruf + Vision-API?

---

## Qualitäts-Methodik — woran die KI kindgerecht/interessant erkennt

Sprachliche Marker im Wikipedia-Text (→ steuern Selektion + Fokus):
- Superlative/Rekorde: „größtes", „schnellstes", „einziges"
- Zahlenvergleiche mit Alltagsbezug: „so groß wie ein Bus"
- Kausalformulierungen: „weil", „deshalb", „dadurch"
- Überraschungsmarker: „obwohl", „entgegen", „tatsächlich"

Strukturelle Signale:
- Erster Satz/Absatz enthält das „Kernwunder" des Themas
- Konkrete Beispiele > abstrakte Definitionen
- Bildunterschriften verraten, was visuell interessant ist

Alters→Filter-Raster:
| Stufe | Filter-Kriterium |
|---|---|
| 1 (5–7 J.) | Sinnlich / emotional / Jetzt-Zustand |
| 2 (8–10 J.) | Kausalität / Rekorde / früher-vs-heute |
| 3 (11–13 J.) | Systemzusammenhänge / Kontroverse / Statistik |

---

## "Stimmt das?"-Regel (stimmt-Box)

- Korrigiert ein **WEIT VERBREITETES** Klischee/Missverständnis zum Artikelthema —
  NICHT eine Aussage aus dem unmittelbar vorherigen Absatz.
- Test: Würde ein Kind das glauben, BEVOR es den Artikel liest?
  Ja → gutes Stimmt-da / Nein → weglassen.
- Max. 1 bei Stufe 2, max. 2 bei Stufe 3, gleichmäßig verteilt.
- Abschnittstitel darf NICHT denselben Namen tragen wie ein Element darin
  (z.B. nicht „Stimmt das?" als Titel wenn drin eine stimmt-Box steht).
- Brückensatz vor einer Box muss echten Inhalt liefern — kein dünner Übergangssatz
  wie „Es gibt viele Missverständnisse darüber."

---

## living_being — Pflichtmuster

**Stufe 1+2:** Aussehen → Verhalten/Ernährung → Fortpflanzung → Bedrohung/Mensch

**Stufe 3 (nur bei CONTENT_DEPTH 3) — zusätzliche optionale Rollen:**
`body_functions`, `social_behavior`, `reproduction`, `predators_ecosystem`, `human_animal`

---

## CONTENT_DEPTH + TOPIC_INTEREST

`CONTENT_DEPTH` (1–3) wird in `prepare_articles.py` aus der Wikipedia-Textlänge berechnet:
```python
< 3000 Zeichen → 1 | < 8000 → 2 | ≥ 8000 → 3
```
Kein KI-Call. Steuert die Ziel-Abschnittszahl im Prompt.

`TOPIC_INTEREST` (low/medium/high) wird aus Wikipedia-Pageviews + Kategorie-Bonus berechnet:
```python
bonus = 1.5 wenn Kategorie in HIGH_INTEREST_CATEGORIES, sonst 1.0
adjusted = pageviews * bonus
> 50.000 → "high" | > 10.000 → "medium" | sonst "low"
```
**KORREKTUR:** Beides ist in `prepare_articles.py` vollständig implementiert
(`fetch_pageviews()` + `compute_content_depth()` + `compute_topic_interest()`).
Frühere WISSEN-Einträge die das als "offen" vermerkt haben, sind veraltet.

---

## System-Prompt-Versionslinie

`v3_2` → `v3_3` (Stimmt-Abschnittsregel + Quiz-Balancing) → `v3_4` (2026-06-04)

Dateien: `wissensfreund_system_prompt_v3_2.md`, `wissensfreund_system_prompt_v3_4.md`

**OFFEN — Code↔v3.4-Abgleich:**
`generate_articles.py` sendet noch v3.2-Feldnamen; v3.4 erwartet geänderte/neue Felder:

| Feld | v3.4 erwartet | Code sendet heute |
|---|---|---|
| Interesse | `TOPIC_APPEAL` + neues `TOPIC_FAMILIARITY` | `TOPIC_INTEREST` |
| Verknüpfungen | `WIKIPEDIA_LINKS` | nicht gesendet |
| Index | `ARTICLE_INDEX` | nicht gesendet |
| Bilder | `IMAGE_METADATA` | `IMAGES:` (JSON-Label) |

Wird in Phase 1 der Pipeline-Arbeit behoben. Bis dahin interpretiert das Modell
`TOPIC_INTEREST` als Fallback; Related Terms ohne `ARTICLE_INDEX` nicht korrekt.

**OFFEN — Fehlende kanonische Prompt-Datei:**
Workflow-Variable `SYSTEM_PROMPT: "wissensfreund_system_prompt.md"` — diese Datei
existiert nicht im Repo. Nur `v3_2.md` und `v3_4.md` vorhanden. Pipeline-Job würde
scheitern. Vor erstem Produktions-Run lösen (Datei anlegen oder Workflow anpassen).

---

## Pipeline-Skripte (CI-Repo / GitHub Actions)

| Skript | Zweck | Status |
|---|---|---|
| `prepare_articles.py` | Wikipedia → Job-Batches (mit Pageviews + CONTENT_DEPTH) | ✅ fertig |
| `generate_articles.py` | Batches → Claude API → JSONs | ✅ fertig |
| `upload_articles.py` | Index bauen + R2-Upload | ✅ fertig |
| `convert_zim_to_json.py` | Klexikon-ZIM → JSON (~3.544 Artikel) | ✅ fertig |
| `generate_quizzes.py` | Quiz für ZIM-Artikel nachgenerieren | ✅ fertig (in CI, geparkt) |
| `patch_article_images_v1.py` | Bilder + Satz-Zuweisungen via Claude API in ZIM-Artikel patchen | ✅ fertig, noch nicht produktiv gelaufen |
| `extract_related_terms_v3.py` | Related Terms + Sound + Bild-Metadaten | ✅ fertig |
| `convert_zim.yml` + `quiz_and_upload.yml` | GitHub Actions: ZIM→JSON→Quiz→R2 | ✅ fertig; Auto-Chain entfernt (→ manuell) |

---

## R2-Struktur nach Pipeline-Run

```
r2://wissensfreund-articles/
├── staging/
│   ├── articles_zim/       Zwischenstufe: von convert_zim.yml befüllt, von quiz_and_upload.yml gelesen
│   └── checkpoints/
│       └── quiz_checkpoint.json   Resume-Checkpoint für generate_quizzes.py (609 Einträge, geparkt)
├── articles/          Production (beide Artikel-Quellen nach R2-Trennungs-Entscheidung → s.u.)
├── index/
│   ├── global.json         alle Artikel (schlanke Einträge)
│   ├── level_1/2/3.json    nach Altersstufe
│   ├── new.json            50 neueste
│   ├── topic_tree.json     angereichert mit Artikel-Counts
│   ├── categories/         cat_tiere.json, …
│   └── subcategories/      sub_tiere_saeugetiere.json, …
└── meta/
    └── pipeline_run.json   Statistiken
```

**Workflow-Chain:** `convert_zim.yml` (manuell) → lädt ZIM, konvertiert zu JSON, pusht
nach `staging/articles_zim/`. `quiz_and_upload.yml` nur noch **manuell** (Auto-Trigger
entfernt 2026-06-04, commit `2cc9779`).

**rclone-Flag für R2:** Immer `--s3-no-check-bucket` angeben — Cloudflare R2 blockiert
`CreateBucket`-API-Calls.

---

## R2-Koexistenz-Konflikt + Entscheidung

**Problem:** `upload_articles.py` nutzt `rclone sync` auf den gemeinsamen `articles/`-Pfad.
`rclone sync` löscht Dateien im Ziel, die nicht in der Quelle sind — ZIM- und Wikipedia-
Artikel würden sich bei getrennten Runs gegenseitig überschreiben.

**Entscheidung (Konzeptchat 29.05.):** getrennte R2-Präfixe für beide Artikel-Sätze,
damit beide koexistieren. Konkreter Pfad-Split noch zu implementieren.

**App-Lookup-Reihenfolge:** erst eigene JSON-Artikel (Wikipedia), dann ZIM-konvertierte.
KI-Antworten dürfen aus BEIDEN Artikeln schöpfen.
Langfristiges Ziel: ganzer Artikel-Korpus per Retrieval (Kosten/Latenz/offline noch offen).

---

## R2-Bestandsaufnahme (2026-06-04)

| Quelle | Anzahl | Stufen | Quiz | thumb_url | Bilder-Patch |
|---|---|---|---|---|---|
| ZIM-konvertierte Artikel | 3.544 | nur Stufe 2 | Platzhalter | leer | nicht gelaufen |
| Selbst produzierte (Wikipedia→Claude) | **0** | — | — | — | — |

Quiz-Checkpoint auf R2: `staging/checkpoints/quiz_checkpoint.json` — 609 Einträge (geparkt,
Auto-Trigger entfernt). Vor manueller Aktivierung löschen, sonst werden 609 Artikel
übersprungen und mit Platzhalter-Quizzen ausgeliefert.

**Credentials-Speicherort lokal:** `C:\Users\Andreas\Wissensfreund\Anthropic API Key für Wissensfreund Pipeline.docx`
(CF Account ID = `b5bffc31dcd02623c9f8a2b01d8ea58e`)

R2-Endpoint: `https://b5bffc31dcd02623c9f8a2b01d8ea58e.r2.cloudflarestorage.com`

---

## Mengenziele (Konzeptchat 2026-05-29)

- ~10.000 Artikel für die älteste Stufe (Stufe 3)
- ~5.000–7.000 Artikel je für Stufe 1 und Stufe 2
- Produktionsgeschwindigkeit: ~100–200 Artikel/Woche
- Bei 3 Stufen: ~300–600 Claude-API-Calls/Woche
- Pipeline-Parallelität: max 3 parallele Batch-Jobs à 50 Artikel → max 1.000 Artikel/Run

---

## Quiz-Strategie

Quiz gehört primär zu den selbst produzierten Artikeln (werden mit Quiz generiert).

Der **Klexikon-Quiz-Run** (generate_quizzes.py) ist **geparkt (Hedge)**: falls selbst
produzierte Artikel zu teuer oder langsam werden, kann der Klexikon-Quiz-Run als Fallback
aktiviert werden. Auto-Trigger wurde entfernt (commit `2cc9779`, 2026-06-04) — nur noch
manuell startbar.

Vor Aktivierung: R2-Checkpoint `staging/checkpoints/quiz_checkpoint.json` löschen.

---

## App-Integration (Flutter)

- `JsonArticleService` — R2-Download, lokaler Cache
- `WfArticle` / `WfArticleIndexEntry` — Datenmodell in Dart
- `ProfileService.activeAgeLevel` — welche Stufe ist aktiv (1/2/3)
- `loadAndSpeakJsonArticle()` im Provider — befüllt `_mediaItems` direkt

**ZIM-Artikel:** werden über `convert_zim_to_json.py` einmalig konvertiert,
dann identisch wie JSON-Artikel behandelt. Kein Doppel-Renderer.

---

## Related Terms (Verknüpfte Artikel)

Jeder Artikel hat `related_terms[]` mit:
- `core` — direkt im Fließtext erwähnte Begriffe
- `discover` — thematisch verwandte Begriffe (nicht direkt erwähnt)

Die App zeigt nur Related Terms für die ein Wissensfreund-Artikel existiert.
Der Artikel-Index auf R2 ist die Quelle der Wahrheit (`true`/`false` pro Slug).
Kein App-Update nötig wenn neue Artikel produziert werden — Index wird automatisch aktualisiert.

---

## Sound / Audio in Artikeln

Wikipedia-Artikel enthalten `.ogg`-Dateien (Tierlaute, Musikstücke, Aussprachebeispiele).
Diese werden als Sound-Thumbnail neben Bildern angezeigt (Notenschlüssel-Icon).

Im JSON:
```json
"images": [
  {
    "index": 2,
    "filename": "beethoven_ode.jpg",
    "sound": {
      "filename": "Ode_an_die_Freude.ogg",
      "duration_sec": 12,
      "caption": "So klingt die Ode an die Freude"
    }
  }
]
```

**Audio-Pipeline-Status:** `download_audio.py` lief am 2026-05-28 in CI, produzierte
`wissensfreund_audio.zip (0 KB, 0 files)`. Audio-Extraktion aus Wikipedia noch nicht
funktionsfähig — Debugging ausstehend (v1.1).

---

## Kategorien-Whitelist + categories[]-Array

Bestimmt welche Wikipedia-Kategorien verarbeitet werden.
Datei: `wissensfreund_categories_whitelist.json` im CI-Repo.

Muster (pattern) je Kategorie:
- `living_being` — Tiere, Pflanzen
- `place_geography` — Länder, Städte
- `history_person` — Geschichte, Personen
- `tech_science` — Technik, Wissenschaft

**Wichtig:** "Neuere Geschichte" startet erst ab Stufe 2 (kein WWII für 4-Jährige).

**categories[] im Artikel-JSON:** Array — Mehrfachzuordnung möglich
(z.B. Löwe = raubtiere + katzen + afrika + tiere).

**OFFEN:**
- Primärkategorie-Konvention: erste in der Liste vs. KI entscheidet via `primary: true`
- Hierarchie-Ebenen: werden alle Ebenen (top + sub) explizit gespeichert?
- Beide Fragen wurden im Konzeptchat nie final entschieden.
