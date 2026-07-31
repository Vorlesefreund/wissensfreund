# Wissensfreund — Projektdokument v21

**Stand:** 2. Juli 2026 · ersetzt v20 (1. Juni 2026)

**Pipeline-Fakten zuletzt gegen Code geprüft:** 02.07.2026, via `verify_project_facts.py` (19/19 PASS · 2 KNOWN_OPEN · 0 FAIL)

> **Wichtigste Änderung gegenüber v20:** Die Klexikon-/ZIM-Architektur als Inhaltsquelle ist entfallen — das Inhaltsmodell sind ausschließlich selbst generierte, Wikipedia-basierte Artikel. (Übergang: die ausgelieferte App liefert noch Klexikon-Inhalt, siehe Kap. 1/7.) Die alte Doku war an mehreren Stellen veraltet (u. a. „Claude generiert Artikel" — tatsächlich Gemini; feste Wortziele; 3-stufiger Bildfilter).

**Verifikations-Stempel** (vor jedem Abschnitt):
- **[✓ CI]** — unter den Fakten, die `verify_project_facts.py` + CI **automatisch** prüfen; Drift bricht den Build.
- **[✓ audit]** — am 18.06.2026 durch Lesen von Code, Daten und Lauf-Artefakten verifiziert, aber **(noch) nicht CI-geguardet** — kann unbemerkt driften.
- **[PO]** — Stand laut Product Owner (Andreas), nicht code-verifiziert.
- **[? zu prüfen]** — aus v20 übernommen, wartet auf den Review-Durchgang des PO.

> **Was die CI heute automatisch prüft (21 Fakten, 19 hart + 2 KNOWN_OPEN):** Produktions-Generator `gemini-3.5-flash`; Thinking-Stufe MEDIUM; `run_batch.py` erbt das Generator-Modell (kein eigener Owner); Lektorat `claude-sonnet-4-6`; Vision-Modell `gemini-2.5-flash`; Bild-Recheck Opus 4.8; aktiver Generator-Prompt verdrahtet (`wissensfreund_generator_prompt_v5_2.md`); Prompt-Datei existiert; S1-Wortziel-Untergrenze `ERG_BANDS[1]=(88,250)`; Exclude-Backstop verdrahtet; `catalog_review_master.xlsx` existiert; `ergiebigkeit_scores` deckt den Katalog (nicht der 134-Stub); `eignung_exclude.json` == XLSX-Excludes (reproduzierbar); Lektorat prüft den Phase-1-Snapshot (kein eigener Quell-Fetch im Lektorat-Pfad). **KNOWN_OPEN** (brechen den Build nicht): CI ruft `run_batch.py` / CI ruft *nicht* den Legacy-Claude-Generator. — Alles andere in den [✓ audit]-Abschnitten ist von Hand verifiziert, aber nicht in diesem Satz enthalten.

---

## 1. Kurzfassung — was Wissensfreund heute ist  [PO]

Wissensfreund ist ein deutschsprachiges, KI-gestütztes Kinderlexikon als Flutter-App (Android-first, Testgerät Samsung S23). Das Inhaltsmodell sind **ausschließlich selbst generierte, kindgerechte Artikel auf Wikipedia-Basis**; Klexikon ist als Inhalts-/Faktenquelle abgelöst und dient nur noch als informelle Orientierung (Register, Themenauswahl), nie als Quelle. **Übergang:** Die aktuell ausgelieferte App liefert noch Klexikon-Artikel; sie werden ersetzt, sobald genügend finale generierte Artikel vorliegen. Jeder Artikel existiert in drei Lesestufen (S1/S2/S3) mit Vorlesefunktion (TTS), Quiz, lizenzgeprüften Bildern und Freemium-Modell. Ein animierter Erklär-Charakter („Professor") ist als Figur vorgesehen, aber **noch zu erstellen**.

---

## 2. Inhalts-Generierungs-Pipeline  [✓ CI / ✓ audit]

*CI-geguardet: Modelle, Thinking-Stufe, `run_batch`-Vererbung, Prompt-Verdrahtung. Audit-Stand (18.06., nicht CI-geguardet): Lesestufen-Altersbänder, Wortziel-Formel, Eignungs-Rubrik-Details, Temperatur.*

- **Inhaltsquelle:** deutsche Wikipedia (API). Kein Fremd-/Trainingswissen. Vor-Schritt holt den Artikel und injiziert ihn als `WIKIPEDIA_TEXT`.
- **Generator:** `gemini-3.5-flash`, Thinking **MEDIUM** (`GEMINI_MODEL` in `generate_grounded.py`; `run_batch.py` importiert ihn als `GEN_MODEL` — kein eigener Model-Owner). Belegt durch den Lauf-Stempel `generation_method = "gemini-3.5-flash/batch/v5.2"`.
- **Lektorat:** separater Pass mit `claude-sonnet-4-6` (Sprache, Quiz-Fairness, Wikipedia-Grounding, Box-Regeln, Wortzahl-Caps). Tiers: SILENT (kleine Korrekturen), KORRIGIERT (größere klare Korrekturen direkt eingebaut), PRÜFEN (Ausnahmefall).
- **Aktiver Prompt:** `wissensfreund_generator_prompt_v5_2.md` (v5.2 — Produktion; seit 30.06. aktiv, siehe Entscheidungs-Log 30.06. / Kap. 9). Die älteren `…_v4_production.md` und `…_v3.23_production.md` bleiben unreferenziert als Historie liegen.
- **Lesestufen:**

| Stufe | Alter | Richtwort |
|---|---|---|
| S1 | 4–6 | kurz, direkte Ansprache, Alltagsvergleiche, viel Staunen |
| S2 | 7–9 | Einleitungssatz, erste Fachbegriffe mit Erklärung |
| S3 | 10–12 | fachlich korrekt, lockerer Ton, kritische/ethische Abschnitte |

- **Wortziele (Ergiebigkeit):** `target_S = round(Wlo + clamp((Erg−2)/6, 0, 1) × (Whi−Wlo))`; Bänder S1 [88, 250] / S2 [100, 400] / S3 [150, 650] (S1-Untergrenze 22.06. mit der v4-Adoption 75→88 angehoben; S2/S3 unverändert — Cap-Spielraum für die S1-Szene). **Obergrenzen sind harte Limits** (S3 max **650**, nicht 700). Verdrahtet über `wortziel_for` + `ergiebigkeit_scores.json` (4.375 Einträge). Bei dünner Quelle: kürzer schreiben statt aufblähen.
- **Eignungs-Gate:** 12-Kategorien-Rubrik, Schalter `EIGNUNG_STRICT`, Loader `eignung_for()`, Exclude-Filter vor Phase 1, `age_floor`-Stufen-Skipping (Mechanismus vorhanden; per Entscheidung 20.06. NICHT genutzt, um wichtige abstrakte Themen aus S1 zu kippen — siehe Kap. 9).
- **Temperatur:** Sync-Pfad 0.6 (`gemini_client.py`); Batch-Pfad **1.0** (belegt `run_batch.py:1123` + `meta.generation_temperature`; Stand 02.07.).

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
- **Schlüsselstein:** `verify_project_facts.py` deklariert **16 Fakten** (14 hart geprüft, 2 KNOWN_OPEN) und prüft sie gegen den Code. Die CI-Action `verify_facts.yml` bricht den Build bei jedem Drift (push auf main + PR). Aktueller Lauf: 14/14 PASS. *[✓ CI — das ist die CI selbst]*
- **Quell-Snapshot-Konsistenz:** Das Sync-Lektorat prüft gegen den Phase-1-Snapshot (`primary_text`/`companion_texts`, gereicht als `sources_block`); **kein eigener Fetch/`resolve_lemma` im Lektorat-Pfad** — also kein Phantom-Beanstandungs-Risiko durch Quell-Drift seit der Generierung. Guarded in `verify_project_facts.py` (`regex_absent` auf `scripts/lektorat_common.py`). *[✓ CI]*
- **Prinzip:** Doku wird aus dem Manifest abgeleitet, nicht von Hand gepflegt. Memory ist ein verlustbehafteter Cache und nie die Quelle — jede Konfig-Behauptung wird mit einem gelesenen Artefakt belegt. Rangfolge: Lauf-Artefakt > Code-Default > Prosa-Zusammenfassung.

---

## 6. Speicher & Auslieferung  [✓ audit / PO]

- **Cloudflare R2** (Bucket `wissensfreund-articles`).
- **Bild-Tiers:** Standard liefert Hero + weitere Bilder mit 300 px (Hero konfigurierbar über `STANDARD_HERO_RES`); Plus/Premium erhalten alle Bilder mit 800 px offline.

---

## 7. Produkt & App  [PO / ? zu prüfen]

- **Plattform:** Flutter, Android-first; Testgerät Samsung S23. **[PO]**
- **Inhaltsquelle — Ziel:** nur generierte R2-Artikel. **Ist-Zustand:** die ausgelieferte App liefert noch Klexikon-Artikel; Umstellung steht aus (Klexikon raus, sobald finale Artikel vorliegen). Klexikon nur noch informelle Orientierung (Register/Themenauswahl), nie Quelle. **[PO]**
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
| 20.06.2026 | **S1-Strategie / v3.24:** age_floor-Skipping für schwere/abstrakte Themen verworfen — wichtige Themen (Demokratie, Sklaverei) müssen auch S1 erreichen. Stattdessen den Kern durch EINE durchgehende konkrete Szene erzählen statt per Definition (Zwei-Fälle-Logik: leichte Begriffe = Alltagsszene; schwere = dem Kind bekanntes Gefühl, keine niedliche Analogie). ERG_BANDS-Untergrenzen 50/80/100 → 75/100/150 (Cap-Spielraum, kein erzwungenes Soll; „kürzer statt aufblähen" bleibt dominant). Neue Regeln R48–R52, R46 geschärft. |
| 22.06.2026 | **v4 als Produktions-Generator-Prompt übernommen** (`wissensfreund_generator_prompt_v4_production.md`; alte v3.23-Datei bleibt unreferenziert als Historie). Gekoppelt: **S1-ERG_BANDS-Untergrenze 75→88** (nur S1-lo; S2/S3 unverändert). Begründung: A/B-Lauf (v3.24 vs v4) + Belegtreue-Verifikation (3 Themen × S3, Grounding mitgesichert) zeigen reichere, **quellentreue** Ausschöpfung; v3.24 schöpfte unter (frühere Dünn-/Trockenheitsprobleme = Unter-Ausschöpfung, nicht fehlender Stoff). |
| 22.06.2026 | **Kompass-Anker übernommen** (+2 Kriterien in `COMPANION_PROMPT_TMPL`: höchstens ein konkreter, kindgerechter, belegbarer Anker je Thema; drastische Tod-/Gewalt-/Katastrophe-Anker meiden). **Eignungs-geprüft** (companion-only, 5 Themen × 2 Läufe): Anker-Leitplanke hält auf heiklen Themen — Zweiter Weltkrieg → Enigma/Luftschutzbunker/Kindertransport statt Tod/Gewalt; Titanic → Robert Ballard/Olympic, „Wrack der Titanic" verworfen; unkritische Themen erhalten sinnvolle Anker (Saturn V, Sphinx/Cheops, Megachile pluto). |
| 22.06.2026 | **Lektorat-Box-Apply-Bug behoben** (Marker-Strip + Granularitäts-Guard Option A in `_apply_auto_correction`; aufgedeckt durch die E2E-Validierung, Titanic-S3-wow-Box). Interne `BOX[...]:`-Render-Marker werden aus claim/korrektur gestrippt (kein Leak in `box["text"]`); Ganzbox-Korrekturen ersetzen die Box als Ganzes, Ein-Satz-Korrekturen nur den Satz. **Fail-safe:** mehrdeutiger Mehr-Satz-Match → PRÜFEN statt Spleiß. Plus Display-Strip vor `_diff_excerpt` (kein Label-Fragment im Prüfbericht). |
| 22.06.2026 | **findings[] + Abnehmer-Umstellung abgeschlossen:** strukturiertes findings[] im V2-pruefbericht (fec90f5); Shape-A-Abnehmer auf Shape B umgestellt (20bec3f). FP/FN-Messung jetzt technisch möglich. |
| 25.06.2026 | **Weg B — Grundsatzentscheidung:** Generierungs-Pipeline von Gemini auf Claude umgestellt (Anlass: gemini-3.5-flash ~30 h unzuverlässig/503, kein produktionsreifer Gemini-Fallback). Provider-Routing zentral über `stage_models.py`. **TTS bleibt Gemini** (keine gleichwertige Anthropic-Alternative). |
| 25.06.2026 | **Weg B — Lemma + Kompass auf Haiku 4.5** via `stage_models`-Routing (forced tool-use). In Praxis bewiesen: Stage 1 läuft ohne gemini-3.5-flash, Erde bekommt Companions. |
| 25.06.2026 | **Weg B — Generator auf Sonnet 4.6 gewählt** (Stil-Vorsprung im Test; Haiku zu kurz/abstrakt, gemini-2.5-flash 44 % JSON-Defekte). Hinweis: `stage_models["generator"]=Sonnet` bleibt **uncommitted** bis der Sonnet-Generator-Testlauf gelingt (derzeit durch Anthropic-Batch-502 blockiert). |
| 25.06.2026 | **Weg B — Trim + Box-Repair auf Sonnet** (Modell-Eignungsbefund: Haiku kürzt nicht — reduziert die Wortzahl bei Overshoot kaum). |
| 25.06.2026 | **Weg B — Quote-Repair typografie-erhaltend** in `parse_article_json` (transport-agnostisch; behebt den ASCII-Schluss-Anführungszeichen-Defekt `„…"`, der das JSON-Parsing brach). |
| 25.06.2026 | **Weg B — Companion-Robustheit:** Such-Fallback via `resolve_lemma` (Verlustrate 35 %→~0), 429-Härtung des WP-Lookups via `_wp_get`, kulturelle Verortung im Kompass-Prompt (greifbar vor abstrakt, Nähe zum Kind im deutschsprachigen Raum — Wirkung noch unverifiziert wegen WP-Rate-Limit). |
| 26.06.2026 | **Weg B (Gemini→Claude für Generierung) VERWORFEN.** Sonnet 4.6 als Generator stilistisch nicht ausreichend: faktentreu, aber nicht kindgerecht-flüssig erzählend (Product-Owner-Urteil). Getestet an Erde S1/S2/S3 über `sonnet_v1` (pro-narrativ), `sonnet_v2` (Erzählbogen+Brücken), `sonnet_v3` (Bogen vor Fakten-Quote) und `gemini_v1` (Geminis eigener Prompt auf Sonnet). Zwei externe Stilgutachten (Gemini 3.1 Pro) + Claude-Code-Prompt-Analyse: konvergierender Befund = Sonnets gewissenhaft-sachliches Temperament erreicht Flashs Erzählfluss per Prompt nur teilweise; formale Fehler (Moderatorenfragen, Klammer-Prozente) behebbar, aber Kern-Erzählfluss bleibt zurück. Flash bleibt das überlegene Erzähl- UND Companion-Auswahl-Modell. **Konsequenz:** Pipeline-Generierung eingefroren auf Vor-Weg-B (Gemini Flash + v4). Reaktivierung sobald Gemini Flash wieder zuverlässig (503 behoben). Details: Abschnitt „Eingefrorener Stand & Reaktivierung (26.06.2026)". |
| 27.06.2026 | Generator-Prompt v4: Narrativer Fluss und Selektion geschärft. Diagnose-Anlass: Erde S3 aus branch_fullrun_erde_vulkan_6von9 (Faktenreihung ohne Klammer, unvermittelte Themensprünge, falsch platzierte Boxen). Fünf Prompt-Eingriffe: ERZÄHLFADEN-Planungsfeld, explizites Weglassrecht (Selektion vor Vollständigkeit), Brückenpflicht ohne Ausnahme, Box-Anker = unmittelbar umgebender Fließtext, Selbst-Check aktualisiert. Commit 376de8a auf Branch companion-faszination-vielfalt-2026-06; noch nicht in main gemergt. |
| 29.06.2026 | Generierung bleibt ausschließlich auf gemini-3.5-flash — kein Modell-Fallback für Phase 2. Entschied bewusst gegen Fallback auf 2.5-flash (auch bei 503-Erschöpfung). Konsequenz: Läufe bei anhaltender 503-Welle warten auf Flash-Stabilität. |
| 30.06.2026 | v5.2 als Produktions-Generator-Prompt aktiviert (v4 abgelöst). Grundlage: Vergleichsläufe Erde/Vulkan/Zweiter Weltkrieg/Wal — v5.2 deutlich lebendiger geschrieben, ERZÄHLFADEN trägt durchgehend, Box-Anker sitzen korrekter (Product-Owner-Urteil nach Lektüre). SYSTEM_PROMPT_PATH in generate_grounded.py auf v5.2 umgestellt. Gleichzeitig appeal-Parameter in run_batch.py:522 nachgezogen (data["appeal"] → select_companions_raw) — schließt die Divergenz zu generate_grounded.py:1127; vorher lief der Batch-Kompass immer mit Default "medium". |
| 01.07.2026 | Generator-Prompt v5.2: drei Register-/Wahrheitstreue-Regeln ergänzt (Commit 0c045c6), aus PO-Review der c-Läufe (Vulkan/Wal/WWII S1 zu blumig, inhaltlich ungedeckte Ausschmückungen). (1) Abschnitt A: Grenzlinie gegen weiche Erfindung — Vergleiche dürfen färben, aber keine Gefühle/Motivationen/intensivierenden Verstärker über die Quelle hinaus hinzufügen (fängt "singt für seine Familie", "viel größer als"). Gilt alle Stufen. (2) S1-Matrix: Register-Drossel gegen stimmungsmalende Adjektive, die Klarheit ersetzen oder Bedeutung verfälschen. (3) S3-Matrix: Drastik-Schranke — Tötungs-/Hinrichtungsmethoden benennen, nicht ausmalen. Lektorat NICHT geändert: Minimal-Eingriff-Prinzip existiert bereits, arbeitete im Blauwal-Fall korrekt (Quelle nennt einige Dinosaurier als evtl. länger, Korrektur war quellenkonform). NOCH NICHT empirisch validiert. Kontext: Validierungslauf v5.2c bestätigte davor die ersten drei Fixes (Companion-Ausschöpfung/Trim/Box-Schema) technisch. |
| 01.07.2026 | Bild-Pipeline: zwei zusammenhängende Fixes. (1) Bildmenge abschnittsbezogen (Commit 8bb6a53): geerbter v4-Widerspruch aufgelöst — die 80%-Pool-Regel zog gegen die Ein-Bild-pro-Abschnitt-Logik. Jetzt maßgeblich: ein Bild pro Abschnitt, zweites nur bei >5 Sätzen (alle Stufen), harte Obergrenze 15/Artikel; Leitprinzip von "Default VERWENDEN" auf textstruktur-bezogen umgedreht. (2) Raster-Diagramme nicht mehr vorgefiltert (Commit 9752a97): "diagram"/"schema"/"chart" aus _IMG_SKIP_LOWER entfernt — didaktische Grafiken (Vulkan-Querschnitt etc.) gelangen jetzt in den Vision-Filter, der ihre Kindgerechtigkeit bewertet, statt sie blind am Dateinamen zu verwerfen. SVG bleibt vorerst übersprungen (_IMG_SKIP_EXT unberührt). Beide noch nicht empirisch validiert. |
| 01.07.2026 | Stage-Entkopplung als 503-Gegenmaßnahme verifiziert (kein Fix nötig): Die Gemini-Stages (1 Sourcing/Companion, Vision, 2 Generierung) und das Sonnet-Lektorat (Stage 3) sind zeitlich trennbar. Belegt: Quelltext-Snapshot (primary_text + companion_texts) liegt nach Stage 1 in stage1_checkpoint.json persistiert; stage3_lektorat liest diesen Snapshot (run_batch.py:1441–1443), ruft KEIN fetch_wikipedia_text (nur in Stage 1) → kein Snapshot-Drift, auch Stunden später. --stage 3 startet eigenständig aus den Stage-1/2-Checkpoints (run_batch.py:1850–1897). Konsequenz: Gemini-Arbeit ins 503-arme Frühfenster (--stage 1 → vision_retry → --stage 2), Lektorat später nachziehen (--stage 3). Anlass: wiederholte 503-/Queue-Stalls im Vormittagsfenster (Vulkan v5.2d abgebrochen). |
| 31.07.2026 | **GPT als Generator getestet und VERWORFEN — final bei Flash.** Bakeoff `gpt-5.6-terra` vs. `gemini-3.5-flash` (Dino-Hörspiel, identische Pipeline + identischer Prompt, nur der Generator getauscht). Objektiver Rubrik-Score (Claude-Sonnet-5-Judge, verankert 1–5, story-first gewichtet): **Flash 3.64 vs. GPT 3.18**. Befund: GPT erzählt enzyklopädisch/„Museumsführung" (lange, fast lexikonartige Erklärblöcke, unerklärte Fachbegriffe wie *theropod*/*Gabelbein*), weniger Story-Sog; Flash hat den stärkeren Hook (Hühnerknochen-Rahmen) + mehr „show, don't tell". Deckt sich mit dem früheren ChatGPT-Sitzungsbefund (GPT tendiert zum Aufzählen). **Modelltausch = kein Qualitätsgewinn** — der Flash-Prompt + die Pipeline sind gut getuned. **Konsequenz:** GPT-Scaffolding restlos entfernt (`scripts/openai_client.py` gelöscht, GPT-Zweige in `generate_grounded.py` per `git restore` zurückgerollt, GPT-Preiszeilen aus `cost_tracker.py` entfernt); Produktion unverändert Gemini Flash. **Nebenbefund (mit dem Rückbau ebenfalls weg):** Der Test deckte 2 latente Bugs im Nicht-Gemini-Generatorpfad auf — Kompass-Auswahl und mechanische Post-Pässe riefen mit dem Fremd-Modellnamen den **Gemini-Endpoint** auf (→ 404). Betraf nie die Produktion; der bestehende Claude-A/B-Pfad ist davon nicht berührt. |

### gemini-3.1-flash-lite (getestet 2026-06-25, abgelehnt)
- JSON-Zuverlässigkeit: 9/9 ✅ (besser als 2.5-flash)
- Wortzahlen: 34–50 % unter Ziel (wal_l3: 325 statt 650 W)
- Bildnutzung: 2–6 Bilder/Artikel trotz 21–27 kuratierter Bilder im Pool
- Stil: nachweislich schlechter als gemini-3.5-flash (Product-Owner-Urteil)
- Entscheidung: ABGELEHNT als Stage-2-Ersatz
- Grund: Qualitätsrückgang bei Länge, Bildnutzung und Stil nicht
  durch Prompt-Optimierung behebbar (struktureller Fähigkeitsunterschied)
- Konsequenz: Produktion wartet auf Rückkehr von gemini-3.5-flash;
  kein weiterer Optimierungsaufwand für 3.1-flash-lite

---

## Eingefrorener Stand & Reaktivierung (26.06.2026)

> Für ein künftiges Ich / eine neue Chat-Instanz: das hier ist der maßgebliche Zustand.

**STATUS (Snapshot 26.06.; Prompt-Nennung 02.07. nachgezogen):** Die Generierung wurde nach dem Weg-B-Rückbau auf **gemini-3.5-flash** zurückgesetzt (damals `…v4_production.md`; **seit 30.06. `wissensfreund_generator_prompt_v5_2.md`** produktiv). Auf diesem Stand war das Projekt **produktionsbereit**, damals aber bewusst pausiert wegen zeitweiser gemini-3.5-flash-503. *(Reaktiviert am 30.06. — siehe STATUS.md / Entscheidungs-Log; der übrige Abschnitt bleibt als datierter 26.06.-Snapshot stehen.)* Es ist KEIN Code-Defekt offen — es ist ein Warten auf die Modell-Verfügbarkeit.

**WAS WEG B WAR:** Versuch, die Generierung von Gemini auf Claude zu migrieren (Motiv: die 503-Ausfälle). Verworfen, weil Sonnet 4.6 als Generator stilistisch nicht kindgerecht genug erzählt (faktentreu, aber faktenlastig statt flüssig). Begründung im Detail: Entscheidungs-Log 26.06.2026.

**WAS BLEIBT (providerunabhängige Härtungen — NICHT zurückgebaut, verbessern auch den Flash-Betrieb):**
- typografie-erhaltender Quote-Repair `_repair_article_quotes` / `parse_article_json` (`abb7505`, geschärft `c8e49a5`)
- PHASE-A per-Artikel-Fehlerbehandlung — ein defekter Artikel killt nicht den Batch (`75cbfd1`)
- Companion-Such-Fallback via `resolve_lemma`, Verlustrate 35 %→~0 (`d9d8775`)
- Wikipedia-429-Härtung `_wp_get` + `_companion_target_ok` (`bae2f8e`)
- verify `regex`-Dispatch (`b1f83d8`)

**WAS DORMANT IM REPO LIEGT (ungenutzt, solange keine Stage außer `vision_recheck`/`lektorat` auf anthropic steht):**
- `scripts/claude_client.py` — anbieter-neutraler JSON-Wrapper (forced tool-use). Wird vom **Opus-Vision-Recheck** weiter gebraucht (der ist **pre-Weg-B** und providerunabhängig — bleibt).
- `scripts/test_sonnet_batch.py` — Weg-B-Test.
- `scripts/stage_models.py` — bleibt als zentraler Provider/Modell-Single-Point; alle Generierungs-Stufen stehen auf `gemini` (nur `vision_recheck`=Opus, `lektorat`=Sonnet, beide pre-Weg-B). Der Mechanismus, eine Stufe wieder auf `anthropic` zu schalten, bleibt erhalten.

**WAS ARCHIVIERT IST:** `archiv/weg_b_2026-06/` — `sonnet_v1`/`v2`/`v3` + `gemini_v1` Generator-Prompts, `refetch_sonnet_batch.py`, plus `README.md` mit dem vollständigen Befund. Aufbewahrt für einen etwaigen künftigen Anlauf mit einem stärkeren Modell.

**REAKTIVIERUNGS-CHECKLISTE (wenn Gemini Flash wieder zuverlässig ist):**
1. Gemini-503-Lage prüfen — kleiner Testlauf über einige Themen.
2. Die Generierung läuft **bereits** auf Gemini — **kein Umschalten nötig**, nur die Verfügbarkeit verifizieren, dann Produktion fortsetzen.
3. Optional: `stage_models.py` erlaubt jederzeit ein erneutes Provider-Experiment (Mechanismus bleibt) — die verify-Checks „Generierung eingefroren: … = Gemini" schützen bis dahin vor unbeabsichtigtem Drift.
4. Prompt-Änderungen validieren (Commit 376de8a): Mind. einen Artikel — idealerweise Erde S3 als Direktvergleich — mit den geschärften Narrativen-Fluss-Regeln generieren und gegen die Diagnose (Faktenreihung, Themensprünge, Box-Platzierung) prüfen. Branch-Merge erst nach positivem Befund.

**REAKTIVIERUNG EINES CLAUDE-GENERATOR-VERSUCHS (falls je ein stärkeres Sonnet-Nachfolgemodell verfügbar ist):** `archiv/weg_b_2026-06/` enthält die ausgereiften Prompt-Iterationen **und** den Befund, woran Sonnet 4.6 scheiterte (Erzählfluss-Temperament, nicht formale Regeln). Dort ansetzen, nicht bei Null.

---

## 10. Bekannte offene Punkte (KNOWN_OPEN)

- **(02.07.) NÄCHSTER SCHRITT — Vulkan-v5.2d-Layout-Befunde diagnostizieren (aus Artikel-JSON, nicht Docx):** Der Vulkan-v5.2d-Lauf (`articles/vulkan_v5_2d/`, run_id 20260702T091952) lief technisch sauber durch (Stage 2 3/3 OK), aber das PO-Leseurteil der Artikel-Texte zeigt DREI noch nicht diagnostizierte Layout-Befunde: (1) **Box→Abschnitt-Fehlzuordnung** (Box sitzt im falschen Abschnitt), (2) **Box wiederholt den Fließtext** (redundanter Inhalt statt Mehrwert), (3) **falsche Bildzuordnung** (semantisch unpassendes Bild, obwohl img_index-Zählung 1–2/Abschnitt regelkonform ist). Diagnose direkt an den Artikel-JSONs: Box→Abschnitt-Zuordnung (boxes je section), Box-Text vs. section sentences (Überlappung), img_index→section→Bildmotiv (passt das Bild zum Abschnittsinhalt?). NICHT über die Docx (überträgt leer). Kennzahlen-Ebene war unauffällig — die Befunde sind inhaltlich/semantisch.
- **(01.07./02.07.) Sammel-Validierungslauf für die unvalidierten Prompt-/Pipeline-Änderungen** (Vulkan/Wal/WWII, S1/S2/S3): (a) Register-/Drastik-Regeln 0c045c6 — S1 nüchterner, keine intensivierenden Verstärker ("viel größer") schon vom Generator, keine drastischen S3-Methodendetails; (b) Bildmenge abschnittsbezogen 8bb6a53 — ein Bild/Abschnitt, zweites bei >5 Sätzen, keine 80%-Überfüllung; (c) Raster-Diagramm-Fix 9752a97 — kommen didaktische Grafiken jetzt durch den Vision-Filter und landen im Artikel? Zusätzlich beobachten: kehrt die Vulkan-S2-Box-Fehlplatzierung wieder (Generator-Kohärenz, Einzelfall)? **STAND 02.07.: Vulkan durchgelaufen** — Bildmenge 8bb6a53 bestätigt (1–2/Abschnitt), Trim 0/3, S3 640 im oberen Drittel, Lektorat sauber; Register/Drastik 0c045c6 am Text noch zu beurteilen; **Raster-Diagramm-Fix 9752a97 an Vulkan UNVALIDIERT** (Pool nur Fotos, Vulkans Diagramme sind SVG → braucht Fix B ODER ein raster-diagramm-lastiges Thema). **Wal + WWII stehen noch aus** (gleiche Staffelung: Stage 1 → vision_retry → Stage 2 → Stage 3).
- **(01.07.) SVG-Diagramme nutzbar machen (Fix B, zweiteilig):** Didaktische Grafiken liegen auf Wikipedia oft als .svg vor. Aktuell werden SVGs bereits beim Sammeln ausgefiltert (_IMG_SKIP_EXT in image_vision_filter.py) — sie fehlen also schon im Stage-1-Pool, nicht erst im Vision-Schritt. Fix B umfasst daher ZWEI Teile: (1) Sammel-Logik SVGs zulassen, (2) SVG→PNG-Rasterung vor Pillow-Skalierung/Vision (neue Dependency, z.B. cairosvg/rsvg — Cairo unter Windows installations-heikel). Aufwand/Nutzen erst nach dem Sammel-Validierungslauf entscheiden: zeigt der Lauf, dass Raster-Diagramme (Fix A) den Bedarf schon weitgehend decken, ist Fix B nachrangig. Bislang keine Zählung, wie viele didaktisch wertvolle SVGs die Themen liefern — das erfordert einen eigenen MediaWiki-Diagnoseabruf (SVGs testweise zulassen).
- **(01.07.) Entkoppelter Lauf-Workflow gegen 503 (verifiziert, nutzbar ohne Fix):** Produktionsläufe künftig gesplittet — Phase A (Gemini, 503-kritisch) geballt im Frühfenster: --stage 1 → vision_retry → --stage 2 für alle Themen; Phase B (Sonnet-Lektorat, kein 503-Risiko) später: --stage 3 gegen den persistierten Stage-1-Snapshot. Relevant auch für den späteren Bulk-Lauf (503-Vermeidung skaliert). Nächster konkreter Einsatz: Sammel-Validierungslauf Vulkan/Wal/WWII v5.2d (die vier unvalidierten Fixes 0c045c6/8bb6a53/9752a97 prüfen), sobald Frühfenster.
- **(01.07.) Per-Paket-Batch-Isolation (Härtung B, aufgeschoben):** Stage 2 reicht aktuell einen Monolith-Batch für alle Themen×Stufen ein (run_batch.py) — ein Stall/Fehler trifft alle. Echte Isolation (fehlgeschlagenes Paket resumebar, erfolgreiche persistiert) erfordert, dass die Pro-Artikel-JSONs pro Paket geschrieben werden → Step-4-Post-Processing muss in die Paket-Schleife wandern, gen_reqs nach Thema gruppiert werden. Kein additiver Fix, sondern Umbau des Batch-/Checkpoint-Flusses → eigener Schritt mit vorheriger Checkpoint-Diagnose. Bis dahin Blast-Radius auf Scheduler-Ebene reduzierbar (run_batch je Kleingruppe mit eigenem --output-dir). Neuer CLI-Parameter --themen-pro-batch (Default 3–5) vorgesehen.
- **(01.07.) run_status.jsonl — kleine Lücke (retry_exhausted_503):** 503-Erschöpfung beim Gemini-Batch-Submit tritt als geworfene Exception im create-Retry auf (max 4 Versuche), BEVOR poll_gemini_batch läuft → erzeugt aktuell Exit≠0, aber keinen run_status-FAILED-Eintrag mit grund=retry_exhausted_503. Nachrüstbar durch _run_status-Aufruf im Erschöpfungspfad des Batch-Create-Retry. Niedrige Priorität (Exit≠0 ist maschinell erkennbar), aber für saubere unbeaufsichtigte Auswertung wünschenswert.
- **(30.06.) S3-Wortziel zieht bei v5.2 nicht ganz ins obere Drittel** — Abschnitt-D-Regel (high Appeal + ≥4 Companions → oberes Drittel) greift bei S1/S2 sichtbar, aber Wal S3 landete bei 559 statt ≥585 W (mittleres Band, über Untergrenze). Über weitere Läufe beobachten; ggf. S3-Wortziel-Formulierung im Prompt nachschärfen.
- **(30.06.) Wal-Companions wurden mit `appeal="medium"` selektiert** (Stage-1-Lauf vor dem run_batch:522-appeal-Fix). Ein appeal-korrekter Neulauf wäre der erste echte Beleg, dass die gestaffelte Companion-Auswahl im Batch-Pfad wirkt (bisher nur in `generate_grounded.py:1127` aktiv gewesen).
- **CI-Migration:** `artikel_pipeline.yml` ist dispatch-only, ruft den Claude-Legacy-Generator (`generate_articles.py`) und würde mangels Prompt-Datei scheitern → auf `run_batch.py` migrieren; `generate_articles.py` stilllegen; YAML fixen/löschen.
- **Lektorat-Fehlerquote messen** (False-Positive/Negative gegen Ground-Truth) vor dem Skalieren. Ziel: ≥ 50–70 % ohne Korrektur durch.
- ~~**Strukturiertes, maschinenlesbares `findings[]` im V2-`pruefbericht`**~~ →
  **ERLEDIGT (22.06.):** findings[] additiv in Shape B eingebaut
  (fec90f5); Shape-A-Abnehmer (render_review_html.py, generate_grounded.py)
  auf V2 umgestellt (20bec3f). Alle vier Verdikte (SILENT/KORRIGIERT/PRÜFEN/
  EINBAU_FEHLGESCHLAGEN) maschinenlesbar; kein Abnehmer mehr an Shape A.
  Voraussetzung für FP/FN-Messung erfüllt.
- **Grounding v3.17/v2.8** committen und im Pipeline-Lauf validieren (in Dateien gebaut, nicht getestet).
- **v3.24-Validierung (vor Skalierung):** S1-Szenen-Strategie auf Demokratie/Sklaverei prüfen (feuert die durchgehende Szene? Budget tragfähig, ohne dünne Themen aufzublähen?); R47/R52 mit einem Größenvergleich-Thema (Blauwal/Pyramide) testen; R46 generator-seitig (Gladiator) erneut prüfen.
- **~~Generator-Prompt-Konsolidierung / A-B (v3.24 vs v4)~~ → ERLEDIGT (22.06.):** v4 als Produktion übernommen, S1-Untergrenze 75→88 (Kap. 9). Daraus neu offen:
  - **~~Kompass-Companion-Erweiterung~~ → ERLEDIGT (22.06.):** Anker-Kriterien in `COMPANION_PROMPT_TMPL` übernommen + eignungs-geprüft (Kap. 9). Aktiv in Produktion.
  - **BKS-Über-Verwerfung (nice-to-have, kein Blocker — Priorität gesenkt):** Der BKS-Plausibilitäts-Guard verwirft teils zu viel („Knappe"/„Rüstung" bei Ritter, „Sonnenbarke des Cheops"/„Kufu-Schiff" bei Cheops). Folge: dünneres Grounding/teils nur 2 Companions. **Aber:** die E2E-Validierung zeigt, dass Ritter auch mit dünnem Grounding gut wird → keine Dringlichkeit; bei Gelegenheit bessere BKS-Auflösung/Alternativ-Kandidaten.
  - **Spätere Verfeinerung (PRÄZISIERT 25.06., Priorität gesenkt):** Die Companion-Auswahl ist **stufen-blind** (Kompass sieht nur thema+lead, 1× pro Thema, kein S1/S2/S3, kein `sensibel`-Flag). **Das ist KEIN Defekt:** Die Auswahl liefert nur Quellmaterial; die Stufen-Differenzierung macht der **Generator** (kennt `AGE_LEVEL`). Eine explizite Stufen-Steuerung (z. B. „Holocaust erst ab S3") wäre daher eher eine **Generator-Prompt-Sache**, nicht Sache des Kompass. Nur falls je explizit nötig umzusetzen.
- **~~Lektorat-Box-Apply-Bug~~ → ERLEDIGT (22.06.):** Marker-Strip + Granularitäts-Guard Option A in `_apply_auto_correction` (Kap. 9); fail-safe (mehrdeutig → PRÜFEN).
- **~~E2E-Validierung (v4 + Kompass + Lektorat kombiniert)~~ → ERLEDIGT (22.06., Meilenstein):** voller Pfad auf 4 Themen × S1/S2/S3 + Lektorat sauber durchgelaufen; **S1-Floor-88 verhält sich korrekt** (Elektron S1: word_target 62–88, Modell schreibt kürzer statt aufzublähen).
- **~~Quell-Snapshot-Konsistenz (Lektorat)~~ → ERLEDIGT (22.06.):** Diagnose sauber (gleicher Phase-1-Snapshot, kein Re-Fetch); jetzt CI-geguardet (`regex_absent` in `verify_project_facts.py`, Kap. 5).
- **Primärtext-Trunkierung beim Fetch prüfen (niedrige Priorität):** klären, ob `fetch_wikipedia_text` den Primärartikel beim Abruf kürzt (Inhalts-**Vollständigkeit** für den Generator — getrennt von der gelösten Snapshot-Frage, hier geht es nur um den Generator-Input). Niedrige Priorität, da v4 reiche Artikel liefert.
- **Lektorat-Fehlflag-Qualitätspass:** beobachtete Fehl-/Über-Korrekturen aus der E2E gezielt prüfen — Aristoteles-S3 „Selbstrückzug"-Flag (Lektorat flaggt eine eigene/korrekte Aussage), Ritter-S1 „Helm"-Überkorrektur, Titanic-S2 Überlebendenzahl. Input für die geplante FP/FN-Messung.
- **Dosierungs-Nuance (v4-Mikro-Tuning erwägen):** Titanic S2 nennt eine große Opferzahl, die der Prompt eigentlich erst für S3 vorsieht → Stufen-Dosierung sensibler Zahlen im v4-Prompt nachschärfen.
- **Strukturiertes Box-Korrektur-Protokoll (Härtung, später):** statt Freitext-`claim_original` ein maschinenlesbares Ziel (Box-ID + Satz-Index) vom Lektorat anfordern — eliminiert das Matching-/Granularitäts-Risiko an der Wurzel.
  - **Wachposten „lebendig ≠ ausschmücken":** v4 streut gelegentlich kleine **unbelegte** Tupfer ein (z. B. „Zahnräder" statt des belegten Sperrklinken-Mechanismus; „maßgeschneiderte Stahlplatten") — bei Lektorat/Feintuning beobachten, ggf. R45-Backstop im Lektorat schärfen.
  - **Ungetestet:** S1-Wortziel-Effekt (88) an **erg-schwachen** Themen (die vier A/B-Themen sind erg-stark, der Lever bewegt sie kaum); Lektorat×v4-Zusammenspiel (A/B war Roh-Output ohne Lektorat).
  - **Kosmetisch:** v4-Wortziel-Tabelle „Appeal" → „Ergiebigkeit" relabeln (Wortbudget hängt an Ergiebigkeit, nicht am Appeal).
- **~~Batch-Pfad-Temperatur bestätigen.~~ → ERLEDIGT (02.07.):** Batch-Pfad = 1.0 (`run_batch.py:1123` + `meta.generation_temperature`), Sync-Pfad 0.6. CI-geguardet ist die Temperatur weiterhin nicht.
- **Source-Cache vor Bulk-Run** (spart Re-Fetches, hält Lektorat auf dem Generator-Snapshot).
- **Gemini-Cache-Hygiene** (per-Topic-Löschung nach 3 Stufen, TTL ~15 min).
- **Aufräumen:** Audit-/Probe-Skripte, Spare-Clone, `scrape_out`, ZIM-Zweig einfrieren; ~~Modell-Konstanten zentralisieren~~ → **teil-erledigt (25.06.):** zentrales Provider/Modell-Routing in `stage_models.py` (`STAGE_MODELS` + `get_stage_config`); Alt-Konstanten (`GEMINI_MODEL`, `VISION_MODEL`, `LEKTORAT_MODEL`) bleiben als Default/Fallback bestehen — vollständige Ablösung offen.
- **PRÜFEN → konkrete Vorschläge:** Lektorat soll bei PRÜFEN-Flags fertige Korrektur-Optionen (A/B) liefern, nicht nur flaggen (Beleg: Zugvögel S3 PRÜFEN ohne Vorschlag).
- **Lektorat-Backstops für die neuen Generator-Regeln (zweite Schicht):** R52 (Quantoren-/Geltungsbereich-Inflation — korrektheitsrelevant, höchste Priorität), R50 (STIMMT_DAS-Leckage — sicher auto-korrigierbar), R49 (Schlüsselbegriff-Konsistenz — sicher auto-korrigierbar).
- **R48 ↔ Companion-Auswahl:** Kompass soll für zentrale Fachbegriffe den definierenden Companion mitliefern, damit eine belegte Erklärung möglich ist (sonst Begriff vereinfachen/vermeiden).
- **Box-Platzierung (R51):** Code/Schema-Untersuchung — werden Boxen mechanisch ans Abschnittsende gerendert, oder steuert das Modell die Position? Ggf. Positions-/Ankerfeld pro Box. [TEIL-GEKLÄRT 01.07.: Diagnose ergab — Box-JSON enthält nur {type, text(, reveal_text)}, KEIN Anchor-/Positionsfeld. Der Renderer folgt der Section-Verschachtelung; die Box sitzt dort, wo der Generator sie im JSON platziert. Die Vulkan-S2-Fehlplatzierung (fachfremder Seismometer-Satz an Geysir-Passage) ist damit ein GENERATOR-Kohärenzfehler, kein Renderer-Problem. Offen bleibt, ob ein explizites Anchor-Feld sinnvoll wäre — bislang Einzelfall (n=1), daher als Beobachtungspunkt im Validierungslauf, nicht als Fix.]
- **~~Anführungszeichen-Normalisierung~~ → ERLEDIGT (25.06.):** deterministischer, typografie-erhaltender Regex-Post-Process `_repair_article_quotes` in `parse_article_json` (abb7505) — behebt den ASCII-Schluss-Defekt `„…"` transport-agnostisch (Freitext + stringifizierte Tool-Use-Felder). (Im Generator-Parser statt als separater Lektorat-Schritt.)
- **Lektorat-Regression verifizieren:** Sklaverei S3 „Harriet Greens Mutter" widerspricht der zitierten Quelle (Harriet Green IST die Mutter) — gegen Volltext prüfen; konkrete Evidenz für die Fehlerquoten-Messung.
- **~~generation_method-Versionsstring nachziehen~~ → ERLEDIGT (22.06.):** Beide Pfade leiten den Versionsstring jetzt aus `SYSTEM_PROMPT_PATH.stem` ab (Sync ohnehin; Batch-Hardcode `v3.23b` in `run_batch.py:1051` ersetzt) → stempeln `…/v4`.
- **verify-Check gegen hartcodierte Versionsstempel erwägen** (damit diese Drift nicht wiederkehrt): ein `verify_project_facts.py`-Check, der sicherstellt, dass `generation_method` aus dem Prompt-Pfad abgeleitet und nicht erneut hartcodiert wird.
- **Optional-Polish:** ZWK-Beispiel und Edit-2-Beispiel („das Land war einmal geteilt") als konkrete Szene schärfen (demonstrieren noch die alte „eindampfen"-Idee).

### Weg B — Provider-Neutralität (Gemini → Claude) — ❌ VERWORFEN/ABGESCHLOSSEN (26.06.2026)

> **Strang abgeschlossen und verworfen** (Sonnet-Generator stilistisch unzureichend — siehe
> Entscheidungs-Log 26.06.2026 + Abschnitt „Eingefrorener Stand & Reaktivierung"). Generierung
> ist auf Vor-Weg-B (Gemini Flash + v4) zurückgebaut. Historie erhalten, NICHT gelöscht.
> Die früheren OFFEN-Punkte dieses Strangs sind damit **obsolet durch Rückbau**.

Architektur-Strang (begonnen 25.06.2026, verworfen 26.06.2026). Ziel war: die Generierungs-Pipeline unabhängig
von gemini-3.5-flash betreiben (Anlass: ~30 h 503-Unzuverlässigkeit, kein produktionsreifer
Gemini-Fallback). TTS blieb bewusst Gemini.

- **Was gebaut wurde (committet, providerunabhängige Teile BLEIBEN aktiv):**
  - `stage_models.py` — zentrale Provider/Modell-Konfig (`STAGE_MODELS` + `get_stage_config` + `ARTICLE_SCHEMA`). **Bleibt** (Stufen jetzt auf Gemini).
  - `claude_client.py` — Anthropic-Aufruf mit forced tool-use. **Bleibt dormant** (Opus-Vision-Recheck nutzt es weiter).
  - Quote-Repair, PHASE-A-Fehlerbehandlung, Companion-Such-Fallback, 429-Härtung — **bleiben** (providerunabhängig).
- **Obsolet durch Rückbau (waren OFFEN, jetzt gegenstandslos):**
  1. ~~Sonnet-Generator-Testlauf~~ → durchgeführt (Erde S1/S2/S3 über v1/v2/v3 + gemini_v1); Ergebnis = Verwerfung.
  2. ~~Companion-Verortung unverifiziert~~ → Companion-Prompt auf die sachliche Vor-Weg-B-Fassung (a10a6db) zurückgesetzt; Verortungs-/Faszinations-Varianten verworfen.
  3. ~~Trim-Schärfe bei Anthropic-Overshoot~~ → gegenstandslos (Trim wieder Gemini).
  4. ~~Vision-Migration auf Haiku~~ → nicht weiterverfolgt; Vision bleibt gemini-2.5-flash, Opus-Recheck (pre-Weg-B) bleibt.

### Artikelqualität hängt primär an Companion-Auswahl, nicht am Generator (Befund 26.06.2026)

Diagnose-Anlass: Ein voller Erde-Lauf (gemini-3.5-flash/v4, Companions Vulkan/Polarlicht/Erdbeben/Pangaea) war inhaltlich deutlich schwächer als ein früherer guter Erde-Lauf (25.06., Companions Vulkan/Wasserkreislauf/Regenbogen/Dinosaurier/Mond): schmälere Themen, unpassender Schwerpunkt auf der fernen Zukunft der Sonne (düster/kindfern).

**Sauberer Vergleich (verifiziert):** Beide Läufe identisch in Modell (gemini-3.5-flash), Prompt (v4), Temperatur (1.0), Thinking (MEDIUM), Primärquelle (WP „Erde"). EINZIGER Unterschied = die Companions. → Qualitätsunterschied ist auf Companions + Sampling zurückführbar, NICHT auf Prompt-Drift oder Generator-Defekt.

**Mechanismus (belegt über `source_passages`-Verteilung):** Guter Lauf stützte sich auf 4 Erde-Passagen + reichlich Companion-Stoff (Dino 3×, Vulkan 2×, Wasserkreislauf, Regenbogen, Mond). Schwacher Lauf stützte sich 17× auf den Primärartikel Erde, weil lebendige Companions fehlten — und griff für die Schluss-Sektion zum dramatischsten Primärtext-Block (Sonnen-Apokalypse, sauber grounded, aber kindfern).

**Schlussfolgerung:** Der Companion-Hebel (Faszinations + Vielfalt, Branch `companion-faszination-vielfalt-2026-06`) adressiert die WURZEL — gute Companions hätten die Schluss-Sektion mit lebendigem Stoff gefüllt und den Sonnen-Schwerpunkt vermieden.

**NÄCHSTER SCHRITT (offen):** Mehrere (2–3) volle Erde-Läufe MIT den verbesserten Companions generieren und lesen. Prüffrage: Liefert Flash mit guten Companions KONSTANT den lebendigen, breit gestreuten Artikel — oder bleibt trotz guter Companions zu viel Lauf-zu-Lauf-Varianz (Temperatur 1.0 ist hoch)? Erst das zeigt, ob der eingefrorene Stand produktionstauglich ist. Falls zu viel Varianz: Hebel Temperatur senken oder Mehrfach-Generierung-mit-Auswahl erwägen. Dabei auch Commit 376de8a (Selektion + narrativer Fluss, Branch companion-faszination-vielfalt-2026-06) mitvalidieren: Zeigt der Artikel einen durchgehenden Erzählfaden statt Faktenreihung?

**SEKUNDÄRER, COMPANION-UNABHÄNGIGER PUNKT (optional, prompt-steuerbar):** v4 sagt nichts gegen düster-ferne Zukunfts-Schwerpunkte in Kinderartikeln. Eine Generator-Prompt-Regel („kein apokalyptischer Fern-Zukunfts-Fokus für Kinder") könnte als zusätzliche Absicherung erwogen werden — Wurzel bleibt aber die Companion-Auswahl, nicht ein v4-Defekt.

### Companion-Auswahl: Faszinations-Kriterien + Vielfalt (offen, 26.06.2026)

**Stand: in main gemergt am 30.06.2026 (Commit-Merge companion-faszination-vielfalt). Companion-Prompt auf v5.1-Stil mit appeal-gestaffelter Anzahl überarbeitet; aktiv in Produktion.** Betrifft die Companion-Auswahl (Kompass), NICHT die verworfene Sonnet-Generierung — läuft auf dem eingefrorenen Gemini-3.5-flash-Kompass.

**(a) Faszinations-Companion-Kriterien — bewährt, uncommitted.**
Zwei Steuer-Bullets in `COMPANION_PROMPT_TMPL` (`generate_grounded.py`), eingehängt als erste Auswahlkriterien:
- „Faszinations-Test" (Staunen/Drama/Bewegung/Geheimnis vor ordnenden Oberbegriffen; Beispiel Erde: Vulkan/Dinosaurier/Regenbogen statt Sonnensystem/Kontinente/Erdatmosphäre)
- „Dynamisch vor statisch" (Vorgang/Ereignis vor Eigenschaft/Kategorie)

Beleg: 9 Stage-1-Läufe (Vulkan/Wal/Dinosaurier je 3×) → KONSTANT lebendige Companions, 0 trockene Großbegriffe. Restvarianz nur zwischen lebendigen Optionen. Gegenstück: der reine a10a6db-Prompt (aktuell COMMITTETER Einfrier-Stand) ist schwach steuernd und würfelt (Erde mal Vulkan/Wasserkreislauf, mal Pangaea/Erdkern).

⚠️ **STAND:** Die Bullets sind auf dem Branch gesichert (nicht verlustgefährdet). main ist bewusst OHNE diese Bullets eingefroren. Reaktivierung: entweder den Branch nach main mergen (erzeugt erwartbaren Merge-Konflikt in diesem Kapitel, bewusst auflösen) ODER die Companion-Auswahl im Folge-Chat neu konzipieren und den Branch ggf. verwerfen. Product-Owner-Entscheidung zum Mergen steht aus. (Beim Mergen zusätzlich nötig: verify-Check-Anpassung, da Companion-Prompt nicht mehr byte-identisch a10a6db.)

**(b) Vielfalt der Blickwinkel — getestet, beide Kriterien erfüllt (26.06.).**
Beobachtung (Product Owner): Companion-Wahl teils einseitig — Dino lieferte je 3 Dino-Arten (Tyrannosaurus/Argentinosaurus/Archaeopteryx), Wal 4 Arten; der volle Erde-Lauf (Teil B) nur 4 statt 5 Companions, mit Pangaea im Graubereich. Lebendig ja, aber nicht bunt/breit genug.
Lösungsansatz: drittes Steuer-Bullet „Vielfalt der Blickwinkel (lebendig bleibt Vorrang)" — wähle verschiedene Blickwinkel-Typen (Art/Ereignis/Schauplatz/Phänomen/Person/Erforschung/Größen-Lebensraum-Bezug), nicht mehrfach dieselbe Sorte; NIE lebendigen Anker durch trockenen Großbegriff ersetzen, nur um Vielfalt zu erhöhen; 5 Plätze ausschöpfen wo lebendige Anker existieren.
Test (Dino/Vulkan/Wal/Erde je 3× = 12 Stage-1-Läufe, alle sauber, kein 503/Bug). Prüfkriterium zweigeteilt — beide erfüllt: (1) **Vielfalt gestiegen** (deutlich bei Erde: 4→5 Slots, Pangaea verschwunden, breite Typen [Marianengraben/Chicxulub/Meteorit]; deutlich bei Wal: 4 Arten → 3 Arten + benanntes Einzeltier „Keiko (Orca)" + Phänomen „Walgesang"; leicht bei Vulkan [neu Person/Mythos „Vulcanus", Größen-Bezug]; neutral bei Dino — nirgends gesunken). (2) **Lebendigkeit gehalten** (0 klar trockene Companions über 59, ein einziger Graubereich: „Erdkern"). Damit Commit-Gate (Vielfalt ↑ UND Lebendigkeit gehalten) erfüllt → auf diesem Branch gesichert.
