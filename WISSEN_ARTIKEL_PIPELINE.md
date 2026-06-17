# WISSEN: Artikel-Pipeline
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei Artikel-Themen -->
<!-- Letztes Update: 2026-06-12 -->

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
Länge je Thema über die Ergiebigkeits-Kurve (s. Abschnitt „Ergiebigkeits-Wortbudget"), nicht mehr über Pageviews-Interest. Die folgenden Spannen sind die Bänder, in denen target_S liegt.

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
- Pflicht: mind. eine stimmt_das-Box pro S2/S3-Artikel. Max. 1 bei Stufe 2, max. 2 bei Stufe 3, gleichmäßig über den Artikel verteilt — keine Box-Clusterung am Ende (s. „Box-Regeln" im Grounded-Abschnitt).
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

---

## Flash Link-Folgen-Mechanismus (NICHT brechen)

**Stand: 2026-06-08 — Befund aus Produktions-Pipeline-Analyse**

### Zwei Modi im System-Prompt (v3.17+)

Der System-Prompt beschreibt zwei Betriebsmodi:

- **Option A (URL-Context-Tool):** Flash bekommt nur den Artikeltitel, nutzt das `url_context`-Tool
  um Wikipedia-Seiten zu laden und folgt internen Links aktiv. Nur für interaktive Tests / AI Studio.
- **Option B (Injected Text):** Das Backend injiziert Primär- und Begleitartikel als fertigen Text
  (`WIKIPEDIA_TEXT_1`, `WIKIPEDIA_TEXT_2` …). Kein URL-Tool nötig.
  Prompt-Kommentar: *"Das URL-Context-Tool ist nur für Tests aktiv."*

### Was unsere Pipeline tatsächlich macht

`gemini_client.py` → `call_gemini()` übergibt an `GenerateContentConfig` ausschließlich:
```python
types.GenerateContentConfig(
    system_instruction=system_prompt,
    temperature=0.6,
    thinking_config=types.ThinkingConfig(thinking_budget=8192),
)
```
Kein `tools=`, kein `tool_config=`, kein `google_search_retrieval`, kein `url_context`.
Flash erhält den Primärtext (injiziert von `generate_articles.py` in den `user_message`)
und hat keinen Netz-Zugriff.

**→ Unsere Pipeline ist Option B — aber aktuell ohne Begleitartikel-Injektion.**
Nur der Primärtext wird injiziert. Begleitartikel noch nicht implementiert (offen).

### "AFC is enabled with max remote calls: 10" — was dieser Log bedeutet

Erscheint in den Logs VOR jedem API-Call. Kommt aus SDK-Interna (`google.genai`-Bibliothek) —
AFC = Automatic Function Calling, der SDK-seitige Handler für Tool-Aufrufe in Antworten.
Da wir keine Tools konfigurieren, ist AFC zwar "bereit", kann aber nie feuern.
**Kein Handlungsbedarf, kein eigener Code dahinter.**

### "Verwendete Artikel" im Flash-Output

Der System-Prompt schreibt vor: *"Liste am Ende der Ausgabe ALLE verwendeten Artikel."*
Ohne URL-Context-Tool kann Flash keine Links wirklich folgen.
Die Quellenliste im Output entsteht durch:
1. den injizierten Wikipedia-Primärtext (einzige echte Quelle)
2. Trainings-Wissen über Wikipedia-Verlinkungen (Flash kennt de.Wikipedia aus dem Training)

Das bedeutet: **"Verwendete Artikel" im Output ist eine Schätzung, kein Beweis.**
Das Lektorat darf sich NICHT auf diese Liste verlassen — es muss gegen den tatsächlich
injizierten Text prüfen.

### Empirischer Befund url_context-Tool (2026-06-08)

Test mit `types.Tool(url_context=types.UrlContext())` auf "Bienen" (biene_l3):

**Schritt 1 (Primärartikel):** Flash fetcht `https://de.wikipedia.org/wiki/Bienen` erfolgreich.
`url_context_metadata` zeigt `URL_RETRIEVAL_STATUS_SUCCESS` — echter Fetch, kein Training.

**Schritt 2 (interne Links):** Flash versucht, Sekundärartikel zu laden
(`Westliche_Honigbiene`, `Wildbienen`, `Honigbiene`) — bekommt aber vom Tool:
> "The provided url does not match the one in the prompt"

**Befund:** Das url_context-Tool fetcht AUSSCHLIESSLICH URLs, die im ursprünglichen
User-Prompt wörtlich stehen. Dynamisch konstruierte Wikipedia-Links werden abgelehnt.
Eigenständiges Link-Folgen (Flash entscheidet selbst) ist API-seitig gesperrt.

**`url_context_metadata` bei unserem Produktions-Setup (Option B, kein url_context):**
Leer — Flash kann keine URLs fetchen. "Verwendete Artikel" im Output = Schätzung.

### Was NICHT brechen

- `tools=` NIEMALS unbeabsichtigt zur `GenerateContentConfig` hinzufügen.
  Sobald `tools=[types.Tool(url_context=types.UrlContext())]` gesetzt ist, wird Flash
  wirklich URLs fetchen — aber NUR explizit im Prompt genannte URLs.
- Bei Option-B-Betrieb: Der injizierte Text ist die einzige Wahrheitsquelle.
  Kein Trainingswissen, kein URL-Zugriff.

### Ausbau-Pfad (korrekte Implementierung)

Für echtes Multi-Artikel-Grounding gibt es zwei Wege:

**Weg A — Option B komplett:** `generate_articles.py` pre-fetcht 1–2 Begleitartikel
aus den Wikipedia-Links und injiziert sie als `WIKIPEDIA_TEXT_2`, `WIKIPEDIA_TEXT_3`.
Flash bekommt alles als Text — kein URL-Tool nötig. **Empfohlen.**

**Weg B — Option A explizit:** `generate_articles.py` legt 2–3 Wikipedia-URLs
in den User-Message (`COMPANION_URL_1: https://...`), aktiviert url_context-Tool.
Flash fetcht explizit genannte URLs zur Laufzeit. Teurer + langsamer als Weg A,
aber ohne pre-fetch nötig. url_context_metadata gibt echten Beweis zurück.

---

## Grounded Pipeline (generate_grounded.py) — Stand 2026-06-12

**Produktionsdatei:** `scripts/generate_grounded.py`  
**Modell:** `gemini-3.5-flash` (ThinkingLevel.MEDIUM in Phase 2)  
**System-Prompt:** `wissensfreund_generator_prompt_v3.23_production.md`  
**Output-Dir:** `articles/test_grounded/`

### Zwei-Phasen-Architektur

**Phase 1 — Kompass (einmal pro Thema):**
1. `fetch_wikipedia_text(session, primary_wikipedia)` → Primärtext (BKS-Guard integriert)
2. `select_companions_raw(client, thema, primary_text, model)` → Flash wählt 4–6 Begleitartikel frei
3. `validate_and_resolve_companions(session, raw_companions, primary_wikipedia, cap)` → WP-Existenzprüfung + Redirect-Auflösung
4. Companion-Volltexte fetchen → `companion_texts: dict[str, str]`
5. Vision-Bildanalyse (überspringbar via `skip_images=True`)

**Phase 2 — Generierung je Stufe:**
1. `build_grounded_user_message(job, primary_text, companion_texts, companion_order, images)` → User-Message
2. Stabiler Prefix + variables WORTZIEL/AGE_LEVEL-Suffix → Gemini Context Cache möglich
3. `gemini_client.call_gemini(SYSTEM_PROMPT, user_msg, ...)` → JSON-Rohtext
4. `parse_article_json(raw)` → Article-Dict
5. `count_article_words(article)` → Wortzahl (Fließtext + Boxen, OHNE Quiz)
6. Lektorat (optional, `--skip-lektorat` Flag)

**Companion-Cap gestaffelt nach Appeal:** low=4 / medium=5 / high=6  
**Prompt-Caching:** Stabiler Prefix (Quelltext) = unveränderlich; nur AGE_LEVEL+WORTZIEL wechselt → Gemini Context Cache spart ~80 % der Token-Kosten für Stufen 2+3.

### WORTZIEL-Injektion (auskonvergiert, 2026-06-12)
In `build_grounded_user_message()` + `_split_grounded_user_message()`. Finale Formulierung
(nach Pilot-Läufen 1–3, byte-identisch in beiden Funktionen, da `_split` per
`full[:len(full)-len(variable)]` schneidet):
```
WORTZIEL: Strebe {wmax} Wörter an und schöpfe den Wikipedia-Stoff so weit aus, dass du nah
an {wmax} herankommst. {wmax} ist zugleich die harte Obergrenze — schreibe nicht darüber
hinaus. Wenn nach Erreichen von {wmax} noch Stoff übrig ist, wähle die kindgerechtesten
Aspekte aus, statt alles aufzunehmen. Kürzer als {wmax} nur, wenn der Wikipedia-Stoff die
Länge nicht hergibt — niemals aufblähen.
```
Entwicklung: Ceiling-Wording („bis zu X … nicht überschreiten") → systematisches Untertreiben
(Lauf 1). „Angestrebte Länge ohne Deckel" → Untertreiben behoben, aber Overshoot bei
companion-reichen Themen (Lauf 2: Vulkan S3 848/650). Finale Fassung („strebe an" + harter
Deckel + Auswahlregel) → Deckel hält weitgehend selbst (Lauf 3: Vulkan S3 644, Kühlschrank
punktgenau), Untergrenze weich. Wording gilt als abgeschlossen — Resthärte am Cap gehört in
den Wortzahl-Guard, nicht in weiteres Prompt-Tuning.

### Ergiebigkeits-Wortbudget (kalibriert + verdrahtet, 2026-06-12)
Modellwechsel (2026-06-12): Das frühere Modell (content_richness_v2 / fasc-Norm / wc=0 /
Klexikon-Abwesenheits-Deckel) ist ÜBERHOLT. Länge wird jetzt von Claude-bewerteter
Ergiebigkeit gesteuert.

Längen-Signal = ERGIEBIGKEIT (spannend + unterhaltsam + wissenswert, aus Kind-Neugier).
Nicht Flash, nicht die „Wichtigkeit"-Achse. Claude-Rater korreliert 0,74 mit Andreas' Noten,
Flash nur 0,53 (Flash versagt bei vielschichtigen Themen, z. B. Indianer).
Kurve: target_S = Wlo + frac · (Whi − Wlo), frac = clamp((score − 2) / 6, 0, 1).
Score 2 → Bandboden, Score 8 → Bandlimit, 9–10 sättigen. Bänder: S1 [50, 250], S2 [80, 400],
S3 [100, 650]. Bewusst großzügig nach oben.
Boost: Lebens-Zentralität / Strategie / Heimat hebt nach oben, NIE nach unten. Geboostet
u. a. Wirtschaft, Gemüse, Markt, Lexikon, Düsseldorf (Launch-Heimatstadt). Zugehörigkeits-
Sockel für deutsche Orte + Herkunftssprachen.
Füllbarkeit: kein eigenes Modul — reine Generator-Prompt-Regel (s. WORTZIEL oben).
Wortziel = angestrebte Länge, Stoff ausschöpfen, nur bei erschöpfter Quelle kürzer, nie
aufblähen.
Rater: starkes Claude-Modell (Opus-Klasse) per API, verankert an die 134 Anker-Themen.
API-Kosten separat vom Chat-Budget.
Anker-Artefakt: `wortziele_ergiebigkeit_134_v2.xlsx` (134 Themen mit Ergiebigkeit /
Wortzielen / Flags) = Ground-Truth fürs Voll-Rating.

Verdrahtet: `WORTZIEL_TABLE` ersetzt durch `wortziel_for(thema, level)` + `appeal_for(thema)` aus
`ergiebigkeit_scores.json`. Funktionen `_load_ergiebigkeit()` / `wortziel_for()` / `appeal_for()` in
`generate_grounded.py` Z. 101+. Fallback bei fehlendem Score → ERG_FALLBACK_SCORE=6 (sichtbar geloggt).

### Wortzahl-Guard (implementiert, 2026-06-12)
Implementiert in `generate_grounded.py`. Cap = `round(wmax * 1.05)`. Bis zu `TRIM_MAX_ATTEMPTS=2`
Trim-Pässe via `_trim_article_to_cap()` + `TRIM_SYSTEM_PROMPT` (Lektor-Prompt, JSON-Rückgabe).
Nach max. Versuchen → `review_flag`. Verifiziert: 238→18W (Netz-Test PASS).

### Box-Verteilungs-Guard (implementiert, 2026-06-12)
`_box_lint()`: erkennt deterministisch Clusterung (≥2 Boxen im letzten Abschnitt) und fehlendes
Mitteldrittel (bei n≥3 Abschnitten). Bei Verstoß: `_box_repair_pass()` lässt Modell Boxen
umordnen (nur Platzierung). `_box_signature()` prüft Inhalts-Gleichheit (Box-Multiset + Sätze
wortgleich) — akzeptiert nur bei `same_content AND lint(repaired) is None`, sonst `review_flag`.
stimmt_das-Pflicht bewusst NICHT eingebaut (widerspricht Prompt-Philosophie).

### resolve_lemma-Integration (implementiert, 2026-06-12)
Verdrahtet im Hauptloop von `generate_grounded.py` (nach `levels = [...]`, vor Phase 1).
`resolve_lemma(session, thema)` → `resolved_title` überschreibt `primary_wikipedia`;
`lemma_flags` mit BITTE_PRUEFEN/LEMMA_GEWECHSELT → `review_flag`; `doppelbedeutung_directive`
→ `job["doppelbedeutung_directive"]` → in stabilen Prefix injiziert.
BKS-Fix (2026-06-12): `resolve_lemma` erkennt zusätzlich wenn Lemma selbst eine BKS ist
(`pageprops.disambiguation`) → `_resolve_bks()` → BITTE PRUEFEN-Flag.

### Pilot-Lauf-Befunde (2026-06-12, Läufe 1–3)

- **Lauf 1** (`temp/_pilot_gen.py`, 36 Artikel, ~16 Min, 0 Fehler): reiche Themen unterschreiten
  stark (Hund S2 188/400, Dino S2 291/400) → Ceiling-Wording als Ursache identifiziert.
- **Lauf 2** (7×3, `_pilot_gen2.py`): „angestrebte Länge"-Fix → Undershoot behoben
  (Elefant/Dino/Fußball/Wirtschaft ±26), aber Deckel-Entfernung → Vulkan S2/S3 über Cap (848/650).
- **Lauf 3** (4×3 + Hund-Nachzug, `_pilot_gen3.py`): finales Wording → Deckel hält weitgehend
  selbst, Dino-Regressionskontrolle bestanden (S3 636/650). Rest-Breaches Vulkan S2 (+61),
  Hund S3 (+17) → Wortzahl-Guard. Hund S3 −115 aus Lauf 2 war zaghaftes Untertreiben, kein
  erschöpfter Stoff (jetzt 667, randvoll). Kühlschrank S1 79 W akzeptiert (kein Floor-Eingriff).
- Doppelbedeutungs-Direktive (Fußball, Wirtschaft) korrekt erkannt + injiziert. BKS-Auflösungen
  korrekt (Pangolin → Schuppentiere, Schmetterling → Schmetterlinge, Hund → Haushund).
- Companion-Auswahl nicht-deterministisch zwischen Läufen (Kühlschrank: „Carl von Linde" statt
  „Gefrierbrand") — unkritisch, gelegentlich qualitativ besser.

### Eignungs-Gate (implementiert, 2026-06-12)

`eignung_for(thema)` liest `eignung_verdicts.json` (ROOT) → `{eignung, age_floor, framing_note, source}`.
Fallback: `EIGNUNG_STRICT=False` → permissive (include/S1); `True` → exclude (vor Bulk setzen).
Im Hauptloop (nach Eignungs-Gate, vor Lemma-Auflösung):
- `eignung == "exclude"` → `continue` (Thema übersprungen)
- `age_floor > 1` → Stufen unter Floor aus `topic_jobs` gefiltert
- `framing_note` → `job["framing_note"]` → `FRAMING: …` in stabilen Prefix injiziert

System-Prompt v3.23b: FRAMING-Direktive dokumentiert (Terminologie, keine Wertung/Moralisierung,
Vorrang vor stilistischer Freiheit). Rubrik 10 Kategorien (explizit Sexuelles → exclude; Sexualität
→ S3/sachlich; NS/Holocaust → S3/nüchtern; Politik → S2/neutral; …).
`eignung_verdicts.json` noch nicht befüllt — Fallback läuft bis Excel-Freigabe nach Katalog-Lauf.

### Katalog-Rater-Instruktion (angelegt, 2026-06-12)

System-Prompt: `wissensfreund_rater_kuratierung_v1.md` (Repo-Stamm).
Modell: Opus. ~5000 Themen, 19 Gebiete. Je Aufruf: Themengebiet + ~20 Kalibrier-Anker aus
`wortziele_ergiebigkeit_134_v2.xlsx`. Ausgabe: JSON-Array mit `thema / themengebiet / leuchtturm /
erg_s1..s3 / eignung / age_floor / kategorie_nr / framing_note / sensibel / begruendung_eignung /
dublette_von / notiz`.
Nachgelagert (Skript): Cross-Gebiet-Merge + Dedup + Round-Robin-Reihenfolge + erste 500 aus
`leuchtturm`-Themen → Export Excel-Freigabeliste → `eignung_verdicts.json` + Produktionskatalog.
Kleinstädte (> 10 000 EW, ohne Bedeutung) vorerst ausgenommen — separater späterer Lauf.

---

## Lektorat (Stage 3)

### LEKTORAT-DESIGNPRINZIP (nicht verhandelbar)

Das Lektorat arbeitet selbstständig. Andreas macht KEINE vollständige Artikel-Review. Er setzt
maximal ein Häkchen bei wenigen, echten Grenzfällen. Die PRÜFEN-Quote muss nahe Null sein —
nur bei echter, fundamentaler Unsicherheit wo eine falsche Auto-Korrektur schlimmer wäre als
gar keine. In allen anderen Fällen entscheidet das Lektorat selbst: entweder SILENT
(auto-korrigiert, still) oder KORRIGIERT (auto-korrigiert, sichtbar markiert). PRÜFEN ist die
absolute Ausnahme, nicht die Regel. Eine PRÜFEN-Quote von 71% bedeutet, das Lektorat hat versagt.

### Drei Korrektur-Stufen (v3.1)

| Stufe | Bedeutung | Wann |
|---|---|---|
| SILENT | Auto-korrigiert, im Artikel unsichtbar | Klare Fehler ohne Leser-Relevanz |
| KORRIGIERT | Auto-korrigiert, im Review markiert | Sichtbare Änderung am Inhalt |
| PRÜFEN | Nur flaggen, kein Auto-Fix | Echte fundamentale Unsicherheit |

Architektur + Großlauf-Strategie: → `scripts/WISSEN_PIPELINE_PRODUKTION.md`, Abschnitt Lektorat.
