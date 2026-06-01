# WISSEN: Artikel-Pipeline
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei Artikel-Themen -->
<!-- Letztes Update: 2026-06-01 -->

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
- `myth`/`stimmt` (lila) — Klischee-Aufklärung, mit `reveal_text`
- `warn` (orange) — kritische Inhalte (Aussterben, Umwelt)

Quiz: 3 Fragen, Antworten A/B/C (für STT-Erkennung), `correct_key` gleichmäßig verteilen.

---

## Altersstufen

| Stufe | Alter | Wörter | Besonderheiten |
|---|---|---|---|
| 1 | 4–6 J | ~200 | Max. 12 Wörter/Satz, Bilder-Quiz, keine Tabellen |
| 2 | 7–9 J | ~400 | Einleitungssatz, Fachbegriffe mit Erklärung, myth-reveal auto |
| 3 | 10–12 J | ~700 | Tabellen erlaubt, myth-reveal manuell |

**Stufe 1 Sonderregel:** Keine Altersvergleiche die das Kind kleiner machen ("da warst du noch jünger als du" für 4–6J. ist falsch).

---

## Pipeline-Skripte (CI-Repo / GitHub Actions)

| Skript | Zweck | Status |
|---|---|---|
| `prepare_articles.py` | Wikipedia → Job-Batches | ✅ fertig |
| `generate_articles.py` | Batches → Claude API → JSONs | ✅ fertig |
| `upload_articles.py` | Index bauen + R2-Upload | ✅ fertig |
| `convert_zim_to_json.py` | Klexikon-ZIM → JSON (~3.544 Artikel) | ✅ fertig |
| `generate_quizzes.py` | Quiz für ZIM-Artikel nachgenerieren | ✅ fertig (in CI) |
| `patch_article_images_v1.py` | Bilder + Satz-Zuweisungen via Claude API in ZIM-Artikel patchen | ✅ fertig, noch nicht produktiv gelaufen |
| `extract_related_terms_v3.py` | Related Terms + Sound + Bild-Metadaten | ✅ fertig |
| `convert_zim.yml` + `quiz_and_upload.yml` | GitHub Actions: ZIM→JSON→Quiz→R2 (zweistufig, auto-chain) | ✅ fertig |

**Noch offen in `prepare_articles.py`:**
- Wikipedia Pageviews API für `TOPIC_INTEREST`
- `CONTENT_DEPTH` aus Textlänge berechnen

---

## R2-Struktur nach Pipeline-Run

```
r2://wissensfreund-articles/
├── staging/
│   ├── articles_zim/       Zwischenstufe: von convert_zim.yml befüllt, von quiz_and_upload.yml gelesen
│   └── checkpoints/
│       └── quiz_checkpoint.json   Resume-Checkpoint für generate_quizzes.py
├── articles/          elefant_l2.json, elefant_l3.json, … (Production, nach Quiz-Run)
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

**Workflow-Chain:** `convert_zim.yml` (manuell) → lädt ZIM, konvertiert zu JSON, pusht nach `staging/articles_zim/` → triggert automatisch `quiz_and_upload.yml` → lädt Staging, generiert Quizze, pusht Production.

**rclone-Flag für R2:** Immer `--s3-no-check-bucket` angeben — Cloudflare R2 blockiert `CreateBucket`-API-Calls.

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

Sound-Thumbnail erscheint in der Thumbnail-Leiste.

**Audio-Pipeline-Status:** `download_audio.py` lief am 2026-05-28 in CI, produzierte jedoch `wissensfreund_audio.zip (0 KB, 0 files)`. Audio-Extraktion aus Wikipedia noch nicht funktionsfähig — separater Debugging-Run ausstehend.

---

## Kategorien-Whitelist

Bestimmt welche Wikipedia-Kategorien verarbeitet werden.
Datei: `wissensfreund_categories_whitelist.json` im CI-Repo.

Muster (pattern) je Kategorie:
- `living_being` — Tiere, Pflanzen
- `place_geography` — Länder, Städte
- `history_person` — Geschichte, Personen
- `tech_science` — Technik, Wissenschaft

**Wichtig:** "Neuere Geschichte" startet erst ab Stufe 2 (kein WWII für 4-Jährige).
