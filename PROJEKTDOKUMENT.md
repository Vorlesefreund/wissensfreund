# Wissensfreund — Projektdokument v21

**Stand:** 18. Juni 2026 · ersetzt v20 (1. Juni 2026)

**Pipeline-Fakten zuletzt gegen Code geprüft:** Commit `e8ad07c`, 18.06.2026, via `verify_project_facts.py` (12/12 PASS · 2 KNOWN_OPEN · 0 FAIL)

> **Wichtigste Änderung gegenüber v20:** Die Klexikon-/ZIM-Architektur ist entfallen. Die App liefert ausschließlich selbst generierte Artikel. Die alte Doku war an mehreren Stellen veraltet (u. a. „Claude generiert Artikel" — tatsächlich Gemini; feste Wortziele; 3-stufiger Bildfilter).

**Verifikations-Stempel** (vor jedem Abschnitt):
- **[✓ CI]** — unter den Fakten, die `verify_project_facts.py` + CI **automatisch** prüfen; Drift bricht den Build.
- **[✓ audit]** — am 18.06.2026 durch Lesen von Code, Daten und Lauf-Artefakten verifiziert, aber **(noch) nicht CI-geguardet** — kann unbemerkt driften.
- **[PO]** — Stand laut Product Owner (Andreas), nicht code-verifiziert.
- **[? zu prüfen]** — aus v20 übernommen, wartet auf den Review-Durchgang des PO.

> **Was die CI heute automatisch prüft (14 Fakten, 12 hart + 2 KNOWN_OPEN):** Produktions-Generator `gemini-3.5-flash`; Thinking-Stufe MEDIUM; `run_batch.py` erbt das Generator-Modell (kein eigener Owner); Lektorat `claude-sonnet-4-6`; Vision-Modell `gemini-2.5-flash`; Bild-Recheck Opus 4.8; aktiver Generator-Prompt verdrahtet; Prompt-Datei existiert; Exclude-Backstop verdrahtet; `catalog_review_master.xlsx` existiert; `ergiebigkeit_scores` deckt den Katalog (nicht der 134-Stub); `eignung_exclude.json` == XLSX-Excludes (reproduzierbar). **KNOWN_OPEN** (brechen den Build nicht): CI ruft `run_batch.py` / CI ruft *nicht* den Legacy-Claude-Generator. — Alles andere in den [✓ audit]-Abschnitten ist von Hand verifiziert, aber nicht in diesem Satz enthalten.

---

## 1. Kurzfassung — was Wissensfreund heute ist  [PO]

Wissensfreund ist ein deutschsprachiges, KI-gestütztes Kinderlexikon als Flutter-App (Android-first, Testgerät Samsung S23). Inhalte sind **ausschließlich selbst generierte, kindgerechte Artikel auf Wikipedia-Basis** — Klexikon ist vollständig abgelöst. Jeder Artikel existiert in drei Lesestufen (S1/S2/S3) mit Vorlesefunktion (TTS), Quiz, lizenzgeprüften Bildern und Freemium-Modell. Ein animierter Erklär-Charakter („Professor") ist als Figur vorgesehen, aber **noch zu erstellen**.

---

## 2. Inhalts-Generierungs-Pipeline  [✓ CI / ✓ audit]

*CI-geguardet: Modelle, Thinking-Stufe, `run_batch`-Vererbung, Prompt-Verdrahtung. Audit-Stand (18.06., nicht CI-geguardet): Lesestufen-Altersbänder, Wortziel-Formel, Eignungs-Rubrik-Details, Temperatur.*

- **Inhaltsquelle:** deutsche Wikipedia (API). Kein Fremd-/Trainingswissen. Vor-Schritt holt den Artikel und injiziert ihn als `WIKIPEDIA_TEXT`.
- **Generator:** `gemini-3.5-flash`, Thinking **MEDIUM** (`GEMINI_MODEL` in `generate_grounded.py`; `run_batch.py` importiert ihn als `GEN_MODEL` — kein eigener Model-Owner). Belegt durch den Lauf-Stempel `generation_method = "gemini-3.5-flash/batch/v3.23b"`.
- **Lektorat:** separater Pass mit `claude-sonnet-4-6` (Sprache, Quiz-Fairness, Wikipedia-Grounding, Box-Regeln, Wortzahl-Caps). Tiers: SILENT (kleine Korrekturen), KORRIGIERT (größere klare Korrekturen direkt eingebaut), PRÜFEN (Ausnahmefall).
- **Aktiver Prompt:** `wissensfreund_generator_prompt_v3.23_production.md`.
- **Lesestufen:**

| Stufe | Alter | Richtwort |
|---|---|---|
| S1 | 4–6 | kurz, direkte Ansprache, Alltagsvergleiche, viel Staunen |
| S2 | 7–9 | Einleitungssatz, erste Fachbegriffe mit Erklärung |
| S3 | 10–12 | fachlich korrekt, lockerer Ton, kritische/ethische Abschnitte |

- **Wortziele (Ergiebigkeit):** `target_S = round(Wlo + clamp((Erg−2)/6, 0, 1) × (Whi−Wlo))`; Bänder S1 [50, 250] / S2 [80, 400] / S3 [100, 650]. **Obergrenzen sind harte Limits** (S3 max **650**, nicht 700). Verdrahtet über `wortziel_for` + `ergiebigkeit_scores.json` (4.375 Einträge). Bei dünner Quelle: kürzer schreiben statt aufblähen.
- **Eignungs-Gate:** 12-Kategorien-Rubrik, Schalter `EIGNUNG_STRICT`, Loader `eignung_for()`, Exclude-Filter vor Phase 1, `age_floor`-Stufen-Skipping.
- **Temperatur:** Sync-Pfad 0.6 (`gemini_client.py`). *Batch-Pfad-Temperatur noch zu bestätigen — siehe offene Punkte.*

---

## 3. Bildsicherheit — 5 Schichten  [✓ CI / ✓ audit]

*CI-geguardet: Vision-Modell `gemini-2.5-flash`, Bild-Recheck Opus 4.8. Audit-Stand: die 5-Schichten-Struktur, `OPUS_CAP = 18`, die grenzfall-vor-ab_stufe-Reihenfolge und die Lizenz-Whitelist-Details.*

1. **Lizenz-Whitelist** als Hard-Block vor Download (CC0 / BY / BY-SA / PD / GFDL / FAL; NC und ND blockiert).
2. **Gemini-2.5-Flash-Altersrating** (`ab_stufe`: 1 = alle, 2 = ab 7, 3 = ab 10, 0 = blockiert), Thinking LOW.
3. **`grenzfall`-Upstaging** — wird **vor** der `ab_stufe`-Entscheidung ausgewertet (prüft sichtbares Leid, Krankheit, medizinische Eingriffe, verstörende Darstellungen, Tod). `grenzfall=true` + `ab_stufe=1` → 2.
4. **Opus-Recheck** (`claude-opus-4-8`) für alle akzeptierten Bilder sensibler Themen, `OPUS_CAP = 18`, relevanz-sortiert.
5. **Handaudit** durch den PO.

Bezug über die **MediaWiki-API** (Originale laden, lokal mit Pillow auf 300/800 px skalieren). Bild-Tiers: **nur 300 px und 800 px** (kein 1600 px). Kiwix/ZIM-Bildpfade sind ausgeschlossen.

---

## 4. Katalog  [✓ CI / ✓ audit]

*CI-geguardet: Existenz von `catalog_review_master.xlsx`, Reproduzierbarkeit von `eignung_exclude.json` und `ergiebigkeit_scores`. Audit-Stand: die konkreten Stückzahlen unten (Daten-Sichtung 18.06., **nicht** automatisch geprüft — wenn sich der Katalog ändert, bricht die CI nicht).*

- **~4.346 Primärthemen** (213 Leuchtturm, 563 sensibel, ~58 exclude). *[✓ audit]*
- **Einzige Wahrheitsquelle:** `catalog_review_master.xlsx`. Alle abgeleiteten Dateien sind daraus reproduzierbar.
- Abgeleitet: `catalog_full.json`, `eignung_verdicts.json`, `eignung_exclude.json` (58 normalisierte Lemmata), `ergiebigkeit_scores.json`.
- **Exclude-Gate gehärtet:** `eignung_exclude.json` wird in `eignung_for()` und `_build_catalog_jobs()` geprüft (z. B. `napoleon` → exclude, `biene` → include).

---

## 5. Qualität & Anti-Drift  [✓ CI / ✓ audit]

- **Lektorat** korrigiert aktiv (siehe Kap. 2). Geplant: PRÜFEN-Schwelle senken, im PRÜFEN-Fall zwei fertige Alternativen A/B liefern (PO setzt nur ein Häkchen). *[✓ audit]*
- **Schlüsselstein:** `verify_project_facts.py` deklariert **14 Fakten** (12 hart geprüft, 2 KNOWN_OPEN) und prüft sie gegen den Code. Die CI-Action `verify_facts.yml` bricht den Build bei jedem Drift (push auf main + PR). Aktueller Lauf: 12/12 PASS. *[✓ CI — das ist die CI selbst]*
- **Prinzip:** Doku wird aus dem Manifest abgeleitet, nicht von Hand gepflegt. Memory ist ein verlustbehafteter Cache und nie die Quelle — jede Konfig-Behauptung wird mit einem gelesenen Artefakt belegt. Rangfolge: Lauf-Artefakt > Code-Default > Prosa-Zusammenfassung.

---

## 6. Speicher & Auslieferung  [✓ audit / PO]

- **Cloudflare R2** (Bucket `wissensfreund-articles`).
- **Bild-Tiers:** Standard liefert Hero + weitere Bilder mit 300 px (Hero konfigurierbar über `STANDARD_HERO_RES`); Plus/Premium erhalten alle Bilder mit 800 px offline.

---

## 7. Produkt & App  [PO / ? zu prüfen]

- **Plattform:** Flutter, Android-first; Testgerät Samsung S23. **[PO]**
- **Inhaltsquelle:** nur generierte R2-Artikel; Klexikon vollständig raus. **[PO]**
- **Animierter Professor:** als Erklär-Figur vorgesehen, **noch zu erstellen**. **[PO]**
- **Altersmodell:** durchgängig S1 / S2 / S3 (das alte 3–10 / Mini·Normal·Erweitert entfällt). **[PO]**
- **TTS (geplant, v1.1):** Gemini 3.1 Flash TTS, Intonation über Style-Prefix + Inline-Tags steuerbar; Vorlesetext bleibt tag-frei (separate TTS-Variante). **[PO / geplant]**

**Aus v20 übernommen — Status gegen aktuellen App-Code nicht geprüft [? zu prüfen]:**
- Ansichtsmodi A (Volltext + Satz-Highlighting) / B (kompakt) / C (Vollbild-Galerie).
- Vorlese-/TTS-Chunking, Nav-Stack, Weiterhören-Funktion.
- Multi-User-Profile (bis zu 5), Eltern-Kiosk-/Lock-Modus, Onboarding-Wizard.
- Freemium (Free / Plus / Premium).
- Die in v20 beschriebenen **„8 Antwort-Kataloge"** und **„5 Gemini-Frage-Typen"** für Rückfragen — Status unklar, **möglicherweise obsolet**. Vom PO zu klären.
- **Eiserne Regel (weiterhin gültig):** Rückfragen-KI antwortet nie aus Trainingswissen, nur aus geladenem Artikeltext.

---

## 8. Markt & USP  [? zu prüfen — aus v20, an neue Richtung anzupassen]

Kernaussage der v20-Wettbewerbsanalyse: Keine App kombiniert animierten Erklär-Charakter + Vorlesen + freies Fragen + DSGVO-Konformität für die Zielgruppe; nächster Wettbewerber (Sneaky Shark Studios) hat nach Jahren zu wenig Inhalt.

**Reframe nötig:** Der USP „geprüfte Wissensbasis" stützte sich in v20 auf Klexikon. Da Klexikon raus ist, lautet der USP jetzt **„selbst generierte, geprüfte, alters-gestufte Artikel aus Wikipedia"** — mit Grounding-Garantie (kein Fremdwissen), 5-Schichten-Bildsicherheit und Eignungs-Gate. Markt-/USP-Kapitel vom PO entsprechend zu aktualisieren.

---

## 9. Entscheidungs-Log

| Datum | Entscheidung |
|---|---|
| — | Klexikon/ZIM abgelöst durch eigene Wikipedia-basierte Generierung. |
| 18.06.2026 | Klargestellt: Produktions-**Generator = Gemini 3.5 Flash** (nicht Claude); Claude (Sonnet) = **Lektorat**. Korrigiert eine frühere Falschannahme. |
| — | Bildsicherheit als **5-Schichten**-Architektur; `grenzfall` wird **vor** `ab_stufe` ausgewertet. |
| — | **Ergiebigkeits-Kurve** statt fester Wortziele; S3-Obergrenze hart bei **650**. |
| — | **Stimmt-das-Pflicht verworfen** (widerspricht der „nicht erzwingen"-Philosophie). |
| 18.06.2026 | **Schlüsselstein** eingeführt: `verify_project_facts.py` + CI-Action `verify_facts.yml`. |

---

## 10. Bekannte offene Punkte (KNOWN_OPEN)

- **CI-Migration:** `artikel_pipeline.yml` ist dispatch-only, ruft den Claude-Legacy-Generator (`generate_articles.py`) und würde mangels Prompt-Datei scheitern → auf `run_batch.py` migrieren; `generate_articles.py` stilllegen; YAML fixen/löschen.
- **Lektorat-Fehlerquote messen** (False-Positive/Negative gegen Ground-Truth) vor dem Skalieren. Ziel: ≥ 50–70 % ohne Korrektur durch.
- **Grounding v3.17/v2.8** committen und im Pipeline-Lauf validieren (in Dateien gebaut, nicht getestet).
- **Prompt v3.23 (c–f)** wurde nie in einem echten Lauf getestet (der Test-Lauf trug v3.23b) → auf **frischen** Themen prüfen. *Nicht* „Mittelalter/Ritter" — das ist ein Referenz-Artikel (Overfitting-Risiko).
- **Batch-Pfad-Temperatur** bestätigen.
- **Source-Cache vor Bulk-Run** (spart Re-Fetches, hält Lektorat auf dem Generator-Snapshot).
- **Gemini-Cache-Hygiene** (per-Topic-Löschung nach 3 Stufen, TTL ~15 min).
- **Aufräumen:** Audit-/Probe-Skripte, Spare-Clone, `scrape_out`, ZIM-Zweig einfrieren; Modell-Konstanten zentralisieren.
