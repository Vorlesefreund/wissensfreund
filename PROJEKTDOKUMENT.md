# Wissensfreund — Projektdokument v21

**Stand:** 22. Juni 2026 · ersetzt v20 (1. Juni 2026)

**Pipeline-Fakten zuletzt gegen Code geprüft:** 22.06.2026, via `verify_project_facts.py` (14/14 PASS · 2 KNOWN_OPEN · 0 FAIL)

> **Wichtigste Änderung gegenüber v20:** Die Klexikon-/ZIM-Architektur als Inhaltsquelle ist entfallen — das Inhaltsmodell sind ausschließlich selbst generierte, Wikipedia-basierte Artikel. (Übergang: die ausgelieferte App liefert noch Klexikon-Inhalt, siehe Kap. 1/7.) Die alte Doku war an mehreren Stellen veraltet (u. a. „Claude generiert Artikel" — tatsächlich Gemini; feste Wortziele; 3-stufiger Bildfilter).

**Verifikations-Stempel** (vor jedem Abschnitt):
- **[✓ CI]** — unter den Fakten, die `verify_project_facts.py` + CI **automatisch** prüfen; Drift bricht den Build.
- **[✓ audit]** — am 18.06.2026 durch Lesen von Code, Daten und Lauf-Artefakten verifiziert, aber **(noch) nicht CI-geguardet** — kann unbemerkt driften.
- **[PO]** — Stand laut Product Owner (Andreas), nicht code-verifiziert.
- **[? zu prüfen]** — aus v20 übernommen, wartet auf den Review-Durchgang des PO.

> **Was die CI heute automatisch prüft (16 Fakten, 14 hart + 2 KNOWN_OPEN):** Produktions-Generator `gemini-3.5-flash`; Thinking-Stufe MEDIUM; `run_batch.py` erbt das Generator-Modell (kein eigener Owner); Lektorat `claude-sonnet-4-6`; Vision-Modell `gemini-2.5-flash`; Bild-Recheck Opus 4.8; aktiver Generator-Prompt verdrahtet (`wissensfreund_generator_prompt_v4_production.md`); Prompt-Datei existiert; S1-Wortziel-Untergrenze `ERG_BANDS[1]=(88,250)`; Exclude-Backstop verdrahtet; `catalog_review_master.xlsx` existiert; `ergiebigkeit_scores` deckt den Katalog (nicht der 134-Stub); `eignung_exclude.json` == XLSX-Excludes (reproduzierbar); Lektorat prüft den Phase-1-Snapshot (kein eigener Quell-Fetch im Lektorat-Pfad). **KNOWN_OPEN** (brechen den Build nicht): CI ruft `run_batch.py` / CI ruft *nicht* den Legacy-Claude-Generator. — Alles andere in den [✓ audit]-Abschnitten ist von Hand verifiziert, aber nicht in diesem Satz enthalten.

---

## 1. Kurzfassung — was Wissensfreund heute ist  [PO]

Wissensfreund ist ein deutschsprachiges, KI-gestütztes Kinderlexikon als Flutter-App (Android-first, Testgerät Samsung S23). Das Inhaltsmodell sind **ausschließlich selbst generierte, kindgerechte Artikel auf Wikipedia-Basis**; Klexikon ist als Inhalts-/Faktenquelle abgelöst und dient nur noch als informelle Orientierung (Register, Themenauswahl), nie als Quelle. **Übergang:** Die aktuell ausgelieferte App liefert noch Klexikon-Artikel; sie werden ersetzt, sobald genügend finale generierte Artikel vorliegen. Jeder Artikel existiert in drei Lesestufen (S1/S2/S3) mit Vorlesefunktion (TTS), Quiz, lizenzgeprüften Bildern und Freemium-Modell. Ein animierter Erklär-Charakter („Professor") ist als Figur vorgesehen, aber **noch zu erstellen**.

---

## 2. Inhalts-Generierungs-Pipeline  [✓ CI / ✓ audit]

*CI-geguardet: Modelle, Thinking-Stufe, `run_batch`-Vererbung, Prompt-Verdrahtung. Audit-Stand (18.06., nicht CI-geguardet): Lesestufen-Altersbänder, Wortziel-Formel, Eignungs-Rubrik-Details, Temperatur.*

- **Inhaltsquelle:** deutsche Wikipedia (API). Kein Fremd-/Trainingswissen. Vor-Schritt holt den Artikel und injiziert ihn als `WIKIPEDIA_TEXT`.
- **Generator:** `gemini-3.5-flash`, Thinking **MEDIUM** (`GEMINI_MODEL` in `generate_grounded.py`; `run_batch.py` importiert ihn als `GEN_MODEL` — kein eigener Model-Owner). Belegt durch den Lauf-Stempel `generation_method = "gemini-3.5-flash/batch/v4"`.
- **Lektorat:** separater Pass mit `claude-sonnet-4-6` (Sprache, Quiz-Fairness, Wikipedia-Grounding, Box-Regeln, Wortzahl-Caps). Tiers: SILENT (kleine Korrekturen), KORRIGIERT (größere klare Korrekturen direkt eingebaut), PRÜFEN (Ausnahmefall).
- **Aktiver Prompt:** `wissensfreund_generator_prompt_v4_production.md` (v4.0 — Produktion; seit 22.06. übernommen, siehe Kap. 9). Die alte `…_v3.23_production.md` bleibt unreferenziert als Historie liegen.
- **Lesestufen:**

| Stufe | Alter | Richtwort |
|---|---|---|
| S1 | 4–6 | kurz, direkte Ansprache, Alltagsvergleiche, viel Staunen |
| S2 | 7–9 | Einleitungssatz, erste Fachbegriffe mit Erklärung |
| S3 | 10–12 | fachlich korrekt, lockerer Ton, kritische/ethische Abschnitte |

- **Wortziele (Ergiebigkeit):** `target_S = round(Wlo + clamp((Erg−2)/6, 0, 1) × (Whi−Wlo))`; Bänder S1 [88, 250] / S2 [100, 400] / S3 [150, 650] (S1-Untergrenze 22.06. mit der v4-Adoption 75→88 angehoben; S2/S3 unverändert — Cap-Spielraum für die S1-Szene). **Obergrenzen sind harte Limits** (S3 max **650**, nicht 700). Verdrahtet über `wortziel_for` + `ergiebigkeit_scores.json` (4.375 Einträge). Bei dünner Quelle: kürzer schreiben statt aufblähen.
- **Eignungs-Gate:** 12-Kategorien-Rubrik, Schalter `EIGNUNG_STRICT`, Loader `eignung_for()`, Exclude-Filter vor Phase 1, `age_floor`-Stufen-Skipping (Mechanismus vorhanden; per Entscheidung 20.06. NICHT genutzt, um wichtige abstrakte Themen aus S1 zu kippen — siehe Kap. 9).
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

---

## 10. Bekannte offene Punkte (KNOWN_OPEN)

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
  - **Spätere Verfeinerung:** Companion-Auswahl **stufen-/sensibel-bewusst** machen (Lesestufe S1/S2/S3 und `sensibel`-Flag fließen bisher nicht in den Kompass ein — z. B. bei sensiblen Themen die Anker-Kriterien noch konservativer, bei S1 einfachere Anker).
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
- **Batch-Pfad-Temperatur** bestätigen.
- **Source-Cache vor Bulk-Run** (spart Re-Fetches, hält Lektorat auf dem Generator-Snapshot).
- **Gemini-Cache-Hygiene** (per-Topic-Löschung nach 3 Stufen, TTL ~15 min).
- **Aufräumen:** Audit-/Probe-Skripte, Spare-Clone, `scrape_out`, ZIM-Zweig einfrieren; Modell-Konstanten zentralisieren.
- **PRÜFEN → konkrete Vorschläge:** Lektorat soll bei PRÜFEN-Flags fertige Korrektur-Optionen (A/B) liefern, nicht nur flaggen (Beleg: Zugvögel S3 PRÜFEN ohne Vorschlag).
- **Lektorat-Backstops für die neuen Generator-Regeln (zweite Schicht):** R52 (Quantoren-/Geltungsbereich-Inflation — korrektheitsrelevant, höchste Priorität), R50 (STIMMT_DAS-Leckage — sicher auto-korrigierbar), R49 (Schlüsselbegriff-Konsistenz — sicher auto-korrigierbar).
- **R48 ↔ Companion-Auswahl:** Kompass soll für zentrale Fachbegriffe den definierenden Companion mitliefern, damit eine belegte Erklärung möglich ist (sonst Begriff vereinfachen/vermeiden).
- **Box-Platzierung (R51):** Code/Schema-Untersuchung — werden Boxen mechanisch ans Abschnittsende gerendert, oder steuert das Modell die Position? Ggf. Positions-/Ankerfeld pro Box.
- **Anführungszeichen-Normalisierung:** deterministischer Post-Process (Regex) auf Hausnorm („…"), statt LLM-Lektorat.
- **Lektorat-Regression verifizieren:** Sklaverei S3 „Harriet Greens Mutter" widerspricht der zitierten Quelle (Harriet Green IST die Mutter) — gegen Volltext prüfen; konkrete Evidenz für die Fehlerquoten-Messung.
- **~~generation_method-Versionsstring nachziehen~~ → ERLEDIGT (22.06.):** Beide Pfade leiten den Versionsstring jetzt aus `SYSTEM_PROMPT_PATH.stem` ab (Sync ohnehin; Batch-Hardcode `v3.23b` in `run_batch.py:1051` ersetzt) → stempeln `…/v4`.
- **verify-Check gegen hartcodierte Versionsstempel erwägen** (damit diese Drift nicht wiederkehrt): ein `verify_project_facts.py`-Check, der sicherstellt, dass `generation_method` aus dem Prompt-Pfad abgeleitet und nicht erneut hartcodiert wird.
- **Optional-Polish:** ZWK-Beispiel und Edit-2-Beispiel („das Land war einmal geteilt") als konkrete Szene schärfen (demonstrieren noch die alte „eindampfen"-Idee).
