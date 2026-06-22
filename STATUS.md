# Wissensfreund — STATUS
<!-- updated: 2026-06-22T13:34:14Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Abgeschlossen (2026-06-22)

**Quell-Snapshot-Konsistenz CI-geguardet.** Diagnose bestätigt: Sync-Lektorat prüft gegen den
Phase-1-Snapshot (`primary_text`/`companion_texts` → `sources_block`), kein eigener Fetch/`resolve_lemma`
im Lektorat-Pfad → kein Phantom-Beanstandungs-Risiko durch Quell-Drift. Neuer `regex_absent`-Check in
`verify_project_facts.py` (auf `lektorat_common.py`, robust gegen Docstring-/Kommentar-Falschtreffer)
schlägt fehl, falls je ein Re-Fetch eingebaut wird. Fakten-Check jetzt 16 (14 hart) → 14/14 PASS · 2 KNOWN_OPEN.

**Lektorat-Box-Apply-Bug behoben** (`_apply_auto_correction`, lektorat_common.py). Aufgedeckt durch die
E2E-Validierung (Titanic-S3-wow-Box: `BOX[wow]:`-Leak + duplizierter Satz + doppelte 1:7-Fassung).
Fix: (A) interne Render-Marker (`BOX[...]:`) aus claim/korrektur strippen; (B) Granularitäts-Guard
(Option A, covers_all über ≥0,5-Pro-Satz-Alignment) — Ganzbox-Korrektur ersetzt die Box ganz,
Ein-Satz-Korrektur nur den Satz, mehrdeutiger Mehr-Satz-Match → PRÜFEN statt Spleiß. Plus Display-Strip
vor `_diff_excerpt` (kein Label-Fragment im Prüfbericht). Verifiziert: Titanic-S3 sauber + Ein-Satz-
Regressionen (Carpathia/Sperrklinken/reveal) + Flag-Fall (17/17 Checks).

**E2E-Validierung (v4 + Kompass + Lektorat)** als Meilenstein: voller Pfad 4 Themen × S1/S2/S3 + Lektorat
sauber; S1-Floor-88 korrekt (Elektron S1 word_target 62–88). Offen: Lektorat-Fehlflag-Qualitätspass,
Dosierungs-Nuance (Titanic-S2-Opferzahl), strukturiertes Box-Korrektur-Protokoll (Härtung).

**Kompass-Anker nach main** (rebased auf v4-Stand, FF→main). +2 Kriterien in `COMPANION_PROMPT_TMPL`:
höchstens ein konkreter, kindgerechter, belegbarer Anker je Thema; drastische Tod-/Gewalt-/Katastrophe-Anker
meiden. Eignungs-geprüft (companion-only, 5 Themen × 2 Läufe): Leitplanke hält auf heiklen Themen
(WW2 → Enigma/Luftschutzbunker; Titanic → Ballard/Olympic, „Wrack der Titanic" verworfen). Offen: BKS-Über-
Verwerfung (Cheops: Sonnenbarke/Kufu-Schiff verworfen — selbe Familie wie Knappe/Rüstung).

**v4 als Produktions-Generator-Prompt** (Commit aa88200 auf main). `wissensfreund_generator_prompt_v4_production.md`
(„v4.0 — Produktion"); `SYSTEM_PROMPT_PATH` → v4; **S1-ERG_BANDS-Untergrenze 75→88**; `generation_method`
in beiden Pfaden aus Prompt-Pfad abgeleitet (Batch-Hardcode `v3.23b` entfernt) → `…/v4`. `verify_project_facts.py`
nachgezogen (15 Fakten, 13 hart, 13/13 PASS). Alte v3.23-Datei bleibt unreferenziert als Historie.

**BKS-Companion-Fehlauflösung behoben** (Commit folgt, fix/bks-companion → main). `validate_and_resolve_companions`
erkennt Begriffsklärungsseiten jetzt per `pageprops.disambiguation` und plausibilisiert BKS-Companions

**BKS-Companion-Fehlauflösung behoben** (Commit folgt, fix/bks-companion → main). `validate_and_resolve_companions`
erkennt Begriffsklärungsseiten jetzt per `pageprops.disambiguation` und plausibilisiert BKS-Companions
über `_flash_check_doppelbedeutung` statt sie größenbasiert (`_resolve_bks` = größter Byte-Umfang, keine
Plausibilität) auf den falschen Treffer aufzulösen. Neuer Guard `_companion_target_ok` verwirft Ziel,
wenn es nicht existiert, selbst noch BKS ist oder = Ausgangs-BKS (verhindert Knappe→Knappe→Schalke-Schleife).
Funktion gibt jetzt 3-Tupel `(valid, rejected, resolution)` zurück; `companion_resolution` wird in
report.json (phase1) persistiert. Beide Aufrufer angepasst (prepare_topic_sources / stage1_sourcing),
Grep bestätigt: keine weiteren Aufrufer. Normale Companions unverändert.

## Abgeschlossen (2026-06-21)

**Prompt-Disziplin-Edits gelandet** (Commit ed0fc2f). Drei Schaden-Muster an der LEKTORAT_SYSTEM-
Quelle entschärft: (1) GRUNDPRINZIP „bewahren oder verbessern" → „bewahren" + Verbot, bei Korrektur
Sprachkolorit/Sinnesdetail/neuen Vergleich hinzuzufügen (kein Ausschmücken); (2) KORREKTIONS-PRINZIP
neuer Bullet „Minimaler Eingriff" — kleinste Änderung, jedes nicht ausdrücklich korrigierte
quellbelegte Detail erhalten («stumpfe» Lanze nicht fallen lassen); (3) SUBSTANZ-PRÜFUNG: engagierende
Hinführungen/«Warum»-Fragen/Denkanstöße sind KEINE Leerformeln, nur echte Tautologien streichen
(Rhetorik geschützt). Aggressivitäts-Bias (ENTSCHEIDUNGSPRINZIP „im Zweifel KORRIGIERT statt PRÜFEN")
bewusst behalten — dokumentiert begründet durch das 71-%-PRÜFEN-Versagen (85fc5c9/5573986).

**Box-internes Satz-Matching gelandet** (Commit 3702399). `_apply_auto_correction` teilt Mehr-Satz-
Box-Strings (`box.text`/`reveal_text`) jetzt in Sätze, matcht satz-granular (gleiche `_jaccard`-Logik,
Schwelle ≥0.40) und ersetzt nur den getroffenen Satz. Behebt „Einbau fehlgeschlagen" bei
box-zielenden Korrekturen (Jaccard-Verdünnung gegen Ganzfeld) und schließt den latenten
Geschwister-Lösch-Datenverlust (Ganzfeld-Überschreibung). Verifiziert an den 3 ritter_l2-Box-Fällen
(test_syncv2) + Regressionen (Abschnitt/box.sentences/Ein-Satz-Feld/kein-Treffer). Geteilt von V1+V2.
- Offene Folge: Teil B — Kategorientrennung „Einbau fehlgeschlagen" (Matcher-Limit) ≠ inhaltliches
  PRÜFEN (echte Eskalation); abhängig davon, wie viele Rest-Fehlschläge nach diesem Fix bleiben.

**Sync-Lektorat-V2-Mismatch behoben & de-dupliziert** (Commit 5989ee6). Sync-Pfad parste die
V2-Prompt-Ausgabe mit V1-Funktionen → `verdikt`→UNBEKANNT, `claim_original`→"", 0 Korrekturen
angewandt. Sync UND die generate_grounded-lokale Batch-Sub-Option auf `parse_lektorat_v2` /
`annotate_article_lektorat_v2` umgestellt (run_batch-Pipeline war schon V2). Via 3-Themen-Lauf
(Schwerkraft/Ritter/Vulkan, 9 Artikel) verifiziert: KORRIGIERT wird in `sentences[].text` eingebaut,
PRÜFEN eskaliert mit `review_flag`, Header themen-/stufenkorrekt. Auf main.
- Offene Folge: V1-Cleanup — `annotate_article_lektorat` ist verwaist; `parse_lektorat_json` noch von
  `run_lektorat_catchtest.py` genutzt → separat aufräumen. Strukturiertes `findings[]` im V2-pruefbericht
  (PROJEKTDOKUMENT Kap. 10) als eigener Schritt.

**review_flag-Fix auf main.** In beiden Pfaden (`generate_grounded.py`/`run_batch.py`) im
`if val_errors:`-Block `setdefault("review_flag", True)` → hartes Setzen `["review_flag"] = True`,
damit echte Validierungsfehler `review_flag` auch dann heben, wenn der Generator
`review_flag:false` ins JSON vorsetzt (`setdefault` wäre dann No-op). Kein-Fehler-Pfad unverändert.

**Deterministischer Vergleichs-Check verworfen** (Entscheidung). Falsches Werkzeug:
Referenzgrößen sind offenes Weltwissen, nicht tabellierbar — 14/37 Objekte unbekannt; 0 echte
Arithmetik-Treffer in 37 Vergleichen; Fehlalarm-dominiert; und Kinderwelt-Qualität (das eigentliche
Anliegen) ist arithmetisch gar nicht prüfbar. `comparisons[]`-Feld + `comparison_check.py` + Wiring
bleiben **unmerged auf `feature/comparisons-metadata`** (Archiv, nicht gelöscht). Vergleichs-Qualität
wandert in Generator-Anleitung (Kinderwelt-/Tier-Bevorzugung, grob stimmig — Generator macht das
laut Diagnose schon größtenteils gut) + fokussierte Plausibilitätsprüfung im Lektorat-Umbau
(Komponente C). Die früheren OFFEN-Punkte (b)/(c) des Vergleichs-Checks sind damit obsolet.

## Abgeschlossen (2026-06-20)

**Generator-Revision v3.24** (Prompt + ERG_BANDS).
- S1-Kern-Strategie umgestellt: Kern durch EINE durchgehende, konkrete Szene aus der Kinder-Lebenswelt
  statt abstrakter Definition (Zwei-Fälle-Logik leicht/schwer). Als allgemeine S1-Regel zu den Stufen-
  Satzlängenregeln verschoben (nicht mehr nur im Schwere-Inhalte-Kontext).
- R46 geschärft: Gladiatoren NICHT als „Schausteller"/„zur Unterhaltung" (sachlich falsch + verharmlosend)
  — schließt die Generator-Lücke, die im v3.23f-Test erst das Lektorat fing.
- Neue Regeln R48 (Begriffe stufengerecht + belegt erklären, deferiert an R44/R45), R49 (Schlüsselbegriff-
  Konsistenz), R50 (STIMMT_DAS-Struktur), R51 (Box am Anker), R52 (Geltungsbereich/Quantoren nicht aufblähen).
- ERG_BANDS-Untergrenzen 50/80/100 → 75/100/150 (S1/S2/S3): hebt das Wortbudget abstrakt-schwerer
  Themen (erg 1–2) an, damit S1 nicht auf ~50 Wörter kollabiert. Obergrenzen unverändert. Greift ab nächstem Gen-Lauf.

**v3.23f-Test (3 neue Themen) + Validator-Fix.**
- Pipeline-Lauf Zugvögel/Demokratie/Sklaverei (S1–3) komplett durch alle 3 Stages. Lektorat:
  15 SILENT / 11 KORRIGIERT / 3 PRÜFEN (alle 3 redaktionelle Grenzfälle, kein klarer Fehler:
  Pfuhlschnepfe-Box „kleiner Vogel"/Dauer · Kranich V- vs. Ketten-Formation · Dreieckshandel-Mythos).
  Lesefassung: articles/test_v323f/LESEFASSUNG_v323f.md.
- BEFUND: Satz-Untergrenze (MIN_SENTENCES {1:8,2:15,3:25}) kollidierte mit Wortbudget (ERG_BANDS):
  bei Erg 1–2 ist wmax≈50 → 8 Sätze mathematisch unerfüllbar → Falsch-Positive (demokratie/
  sklaverei S1, demokratie S2 bei 14<15 trotz gesundem Budget).
- FIX: validate_article(…, word_floor=wmin) — untere Satzgrenze flaggt nur noch bei
  word_count < wmin (echtes Stub-Signal). Obergrenze + Legacy-Pfad unverändert. Empirisch
  verifiziert: 3 FP weg, Stub-Erkennung intakt. Zusätzlich word_target + ergiebigkeit in
  article.meta persistiert (waren bisher None → nicht auditierbar; greift ab nächstem Gen-Lauf).

**Daten-Konsistenz-Audit + Exclude-Backstop** (Commit 4db81a2).
- ergiebigkeit_scores.json aus catalog_full.json neu gebaut: 134 → 4375. XLSX==catalog_full
  für erg verifiziert. Pipeline nutzt echte Scores statt Fallback-6. Builder:
  build_ergiebigkeit_scores.py (Format aus Altdatei gespiegelt; bricht bei unbekanntem ab).
- Exclude-Gate: 58 XLSX-Excludes NICHT in catalog_full (per Omission unerreichbar). Zusätzlich
  gehärtet: eignung_exclude.json (Positiv-Liste aus XLSX) → eignung_for() + _build_catalog_jobs
  prüfen sie; Laufzeit-Gate (Z.1515) feuert auf JEDEM Pfad. Verifiziert napoleon→exclude.
- Schema-Drift bestätigt: Excludes in 3 Dateien unterschiedlich markiert; Positiv-Liste vereinheitlicht.

**Architektur-Review begonnen — Datenfluss-Karte.**
- Katalog-Zweig vollständig aus catalog_review_master.xlsx reproduzierbar über 4 Skripte:
  catalog_merge → catalog_full (+reserve, +review.xlsx=throwaway);
  catalog_verdicts_parser → eignung_verdicts (+categories_backlog);
  build_eignung_exclude → eignung_exclude; build_ergiebigkeit_scores → ergiebigkeit_scores.
  ZWEISTUFIG: build_ergiebigkeit_scores liest catalog_full → Rebuild-Reihenfolge beachten.
- Zweite Wurzelquelle: klexikon.zim (build_title_map/build_image_map/generate_license_json/
  extract_article_audio → title_map/image_map/media_licenses/article_audio_refs). NICHT aus XLSX.
  = Legacy-aber-LIVE: die aktuell ausgelieferte App läuft noch auf Klexikon-Artikeln/-Bildern.
  Klexikon sonst nur noch Orientierung für Flash (Themenwahl/Register), kein Inhalts-Feed.

## Architektur-Befunde / Entscheidungen offen

- **rebuild_all_derived-Wrapper bauen**: ein Skript, das die 4 Builder in korrekter Reihenfolge
  ausführt (catalog_merge VOR build_ergiebigkeit_scores). Verhindert vergessene Nachzüge.
- **Exclude-Quelle konsolidieren**: exclude liegt jetzt in eignung_exclude.json UND (leer) in
  eignung_verdicts.json. Eine kanonische Quelle festlegen (Vorschlag: eignung_exclude.json).
- **ZIM-Zweig eingefroren** bis App auf generierte Artikel (R2) umgestellt ist — dann stilllegen.

## Derived-File-Disziplin (einhalten)

catalog_review_master.xlsx = EINZIGE Wahrheitsquelle. Bei jeder XLSX-Änderung neu bauen:
build_ergiebigkeit_scores.py + build_eignung_exclude.py (+ catalog_merge, verdicts_parser).

## Nächste Schritte (Reihenfolge)

1. Aufräumen — drei Töpfe:
   (a) jetzt streichbar (nach Verifikation): audit_*.py, _probe/_validation, Spare-Clone, scrape_out, temp/;
   (b) eingefroren bis App-Umstellung: klexikon.zim + 4 ZIM-Skripte + Artefakte;
   (c) Kern bleibt: catalog_merge, verdicts_parser, build_eignung_exclude, build_erg_scores,
       generate_grounded, run_batch, Lektorat.
2. PROJEKTDOKUMENT.md NACH dem Aufräumen neu generieren (nicht vorher).
3. KERN: Generierung + Lektorat (eigentlicher Engpass).
4. Danach Bilder, dann TTS.

## Restlücken (niedrigprior)

- ~249 erg_s1-Lücken in XLSX UND catalog_full (gleicher Stand, kein Sync-Problem) → S1-Fallback.
- EIGNUNG_STRICT=False (Bulk-Default); "True vor Bulk" unrealistisch (3813 ohne Verdict).

## Offen aus Artikel-Review

1. PRÜFEN braucht immer Korrekturvorschlag (A/B). 2. Lektorat mehr auto-korrigieren statt PRÜFEN
(Pest "goldene Säule Wien"). 3. Innerartikel-Konsistenz Fließtext vs. Box (Blauwal). 4. Sprachliche
Fehlbezüge ("dankbare Denkmäler", "Wärmestrahlung"). 5. Roter Faden / Wesentliches zuerst, bes. S1.
6. Lektorat-Gründlichkeit ungleich über Stufen. 7. EINBAU-BUG: Korrekturen zerstören Satzgrammatik
(Wikinger S3, technisch). — Nächster Test: 3 NEUE Themen (Overfitting-Check).

## Weiter offen (unverändert)

age_floor-Gate Stage 2 · Stage 4 TTS (tts_produce.py fehlt) · Bildbaustelle · Stage-3-Idempotenz
· Box-Sentiment-Feinschliff · Quiz/stimmt_das schema mismatch (Flutter)

---

Catalog: 4346 primary · 213 Leuchtturm · 563 sensibel · 58 exclude (XLSX) ·
App-Inhalt aktuell: klexikon.zim (Umstellung auf generierte Artikel ausstehend)
