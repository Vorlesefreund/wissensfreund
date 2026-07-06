# Wissensfreund — STATUS
<!-- updated: 2026-07-06T11:45:38Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

> **06.07.2026 — NEUARCHITEKTUR GENERATOR: PHASE 0 + 1 (FUNDAMENT) VALIDIERT & COMMITTET.**
> Modulare Pass-Pipeline neben dem alten Monolithen aufgebaut, Fallback-Garantie durchgehend gewahrt.
> **Phase 0 (Commit d640407):** Schalter `--pipeline old|new` in run_batch.py (argparse choices,
> Env-Fallback `WF_PIPELINE`, Priorität CLI>Env>'old'), an stage2_generierung(pipeline=) durchgereicht;
> Routing-Branch vorn in stage2_generierung; alter Pfad zeichengenau unberührt. (eignung_exclude.json
> 58→59 nachgezogen → verify grün.)
> **Phase 1 (Commit 670bbdf):** neues Modul `scripts/pipeline_new.py` — Pass 1 (PLAN, JSON) →
> Pass 2 (PROSA, reines Markdown, code-gesteuerte Wortziel-Schleife max 3 Versuche, bandnächste
> Fassung+Flag statt Abbruch, gemini-3.5-flash) → Pass 6 (deterministischer dt. Satz-Splitter,
> offset-basiert + Abkürzungsliste; HARTE Rejoin-Invariante NUR auf Absatz-Ebene, Überschriften aus;
> source_passages via Minimal-KI mit Substring-Verifikation). Stubs: boxes=[], images=[], Quiz-Stub,
> review_flag=True. run_batch `_stage2_pipeline_new` (synchron, Resume via Datei-Existenz, age_floor-Gate,
> validate_article mit word_floor). **JSON-Ausgabeschema unverändert.**
> **Validierung WWII S1/S2/S3 (articles/wwii_new_mvp, untracked):** über die echte
> stage2_generierung(new), exit 0; alle Stufen im Wortband auf Anschlag 1; Rejoin-Invariante hielt
> (keine Textmutation); JSON app-valide; Belege wörtlich+verifiziert (10/10/25). Schatten-Vergleich
> vs. v5.2g: ebenbürtige Prosa, S2 besser gegroundet (10 vs 6), S3 worttreuer (428 im Band vs 620 über).
> Register/Thema-Primat/nüchterne Ernst-Themen sitzen. Alter Pfad unberührt, verify 0 Hart-FAIL.
> Desktop: `_wwii_shadow_alt_vs_neu.txt`.
> **Phase 2 (Commit 1c13143) — BOX-PASS (Pass 3) + QUELLTEXT-CACHE.** Boxen entkoppelt vom
> Prosa-Pass: `pass3_boxes` erzeugt 1–2 (S3 bis 3) gegroundete Boxen aus im Artikel FEHLENDEN
> Fakten, je einem Abschnitt zugeordnet (`[]` erlaubt). Deterministische Guards `_apply_boxes`:
> Anker-Match, `stimmt_das`-Disziplin (reveal_text+auto), leichter Anti-Redundanz-Guard,
> Budget-Cap; `_box_lint`-Verteilung → review_flag. **Cache (Nutzerwunsch):** `create_source_cache`
> = ein Gemini-Cache je Thema, NUR Quelltext, OHNE System-Prompt → von allen Pässen geteilt +
> Lektorat-fähig (stabiler `_source_block` als reuse-Kern; `_call_pass` faltet den System-Prompt
> bei Cache in die User-Message). Validierung WWII S1/S2/S3 (gecacht): Boxen gegroundet/verankert/
> nicht-redundant, validate OK, l2 box-lint-geflaggt; **Cache-Hit 99,7 %** der Input-Tokens,
> Laufzeit ~5 min statt ~9–15. Alter Pfad unberührt, verify 0 Hart-FAIL. (articles/wwii_new_cache, untracked)
> **OFFEN — Box-Länge:** Boxen sind noch zu wortreich (S3 ~59 W/Box vs. v5.2 knapper) → Längen-
> Vorgabe im Pass-3-Prompt (in Arbeit). **Danach:** Phase 3 (Bild/Quiz), Phase 4 (Lektorat A+B,
> nutzt den Quelltext-Cache), Phase 5 (Umschalten). Modellwahl Pass 2 später empirisch schärfen.
>
> **05.07.2026 — THEMENGEBIETE-MEHRFACHZUORDNUNG + PRIMÄR-UMSCHICHTUNG (additiv).**
> Jedes der 4346 Katalog-Themen hat jetzt eine Liste ALLER zutreffenden Themengebiete (aus den festen 20).
> Klassifikation: `claude-sonnet-5` via Anthropic Message Batches (0 Fehler), strenger Prompt (Primär immer
> enthalten, Zusatz nur bei Kernthema, max 3) + deterministische notiz-Hint-Harvestung (114 Hints, regelbasiert).
> Verteilung #Gebiete: 1→3224 · 2→1084 · 3→38.
> **Mechanismus (rebuild-fest, KEINE XLSX angefasst):** neue committbare Datei `themengebiete_annotations.json`
> (key=thema: themengebiet-Override + themengebiete-Liste). `catalog_merge.py` wendet sie in `main()` VOR
> `assign_ranks()` an (neue Funktion `apply_themengebiete_annotations`) → landet automatisch in catalog_full.json,
> übersteht jeden Merge. Neue XLSX-Spalte `themengebiete` (Pipe-getrennt) in catalog_merge + build_master.
> **build_master.py NUR editiert, NICHT ausgeführt** (schreibt die verbotene catalog_review_master.xlsx).
> **419 Primär umgeschichtet** (Sonnet-Primär-Review `primaer_alternative`; altes Primär bleibt in der Liste;
> 28× fehlendes Gebiet ergänzt, 0× getrimmt) → `production_rank` für 3758 Themen neu (Round-Robin nach Primär).
> Reproduzierbarkeit: catalog_merge.py reproduzierte catalog_full.json VOR Ergänzung byte-identisch (kein Drift);
> Diff danach NUR themengebiete/themengebiet/production_rank; verify_project_facts.py 0 Hart-FAIL.
> Nicht committet: catalog_review.xlsx (regenerierbares Binär-Derivat).
>
> **05.07.2026 (Nachtrag) — MASTER-XLSX-REBUILD + 2 DUBLETTEN AUSGESCHLOSSEN.**
> Master-XLSX freigegeben + neu gebaut (`scripts/build_master.py`) → Spalte `themengebiete` + Primär-
> Umschichtungen jetzt sichtbar. Schutzprotokoll eingehalten: BACKUP/BACKUP2/BACKUP3 vor Build, wertgenaue
> Verifikation gegen Backup — 16 Kommentare + Shakespeare/Terror erhalten, 0 unerwartete Diffs,
> audit/kommentiert unangetastet (MD5 vor=nach). Zwei echte Dubletten am ROH-Layer ausgeschlossen
> (catalog_manual.json, eignung:exclude): 'Elisabeth die Zweite'→'Königin Elisabeth II.',
> 'Neuschwanstein Castle (Bayern)'→'Schloss Neuschwanstein'; tote Keys aus themengebiete_annotations.json
> (4346→4344), catalog_full.json neu (4343 primary, 59 exclude). Bugfix cffb907: `load_existing_annotations`
> las die Kommentar-Spalte nicht → build_master hätte alle manuellen Kommentare geleert (vor Ausführung
> gefangen). Commits: cffb907 (Kommentar-Fix) + f4eae85 (Dubletten). Master-XLSX NICHT committet
> (nicht-deterministisches Binär-Derivat); Backups liegen bis zu Andreas' Bestätigung.

> **03.07.2026 — GIT-HYGIENE + COWORK-BEFUND.**
> (a) `.gitattributes` neu (7e200b4): `* text=auto` + binary/eol-Regeln → CRLF-Phantom-Drift behoben (vorher ~550 Phantom-„Änderungen" → nur echte). CI-robust (verify nutzt splitlines).
> (b) Aufräum-Commits (84ba5e7 + d771883): `wissensfreund_system_prompt_v3_7.md` gelöscht; zwei fehlgeschlagene Test-Artikel `test_5topics/_errors/{biene,dschungel}_l3.json` gelöscht; `articles/generalize_test/` untracked (32 Dateien, bleiben lokal) + `.gitignore`. Unangetastet: `test_5topics/` (Skript-Ziel `_images/`), die drei Katalog-XLSX.
> (c) Cowork-Befund: Push aus Cowork geht (PAT in `.git/config`). ABER Datei-Edits + Commits aus Cowork sind unsicher — der Git-Index korrumpiert wiederholt (Reparatur `rm .git/index && git reset`) UND große Datei-Schreibvorgänge können abschneiden (STATUS.md wurde beim Cowork-Edit auf 639 statt 654 Zeilen verstümmelt, aus HEAD wiederhergestellt). ENTSCHEIDUNG: Datei-Änderungen/Commits laufen über Windows/Claude Code; Cowork = Lesen/Analyse/Planung + Push.

> **03.07.2026 — GENERATOR-FIXES + VALIDIERUNGSLAUF (Wal/WWII v5.2e).**
> Vier Commits: (1bdb2d3) Prompt v5.2 — Bild-Satz-Passung (gemischte Abschnitte) + Box-Anti-Redundanz + erweiterter Selbst-Check; (3acfa58) run_batch `_limit_images_per_section` behält die semantische img_index-Zuordnung in Zwei-Bild-Abschnitten (vorher positionsbasiert verdreht, reproduzierbar in wwii_l3); (51f3347) Zwei-Bild-Schranke `n > 5` an die Prompt-Regel angeglichen (vorher `n >= 4` — stille Prompt/Code-Drift). Beide Code-Fixes mit deterministischem Unit-Test grün.
> Validierungslauf `wal_wwii_v5_2e_20260703` (run_id val_wal_wwii_20260703, Stages 1-3, 6/6 Artikel, kein 503): Box-Anti-Redundanz ✅, S1-Ton/Register ✅ (bestätigt am sensiblen WWII-Artikel mit Opus-Recheck), Bildmenge/Abschnitt ✅. Bild-Satz-Passung war ⚠️ → als Code-Bug diagnostiziert (3acfa58) und die Schwellen-Drift geschlossen (51f3347). Alle Fixes greifen ab dem nächsten Lauf.
> **OFFEN — SVG-Diagramme (Fix B, einziger offener Prüfpunkt aus dem Lauf):** Raster-Diagramme erreichen den Pool ✅, aber didaktische SVG-Grafiken werden beim Sammeln weiter übersprungen (`_IMG_SKIP_EXT`). Braucht SVG→PNG-Rasterung (neue Dependency) + ein Test-Thema mit SVG-Diagrammen. Aufwand/Nutzen erst nach einem Sammel-Lauf entscheiden.

> **v5.2 PRODUKTIV + BRANCH GEMERGT (30.06.2026)** — Branch `companion-faszination-vielfalt-2026-06`
> nach main gemergt (Merge aba4122). Produktions-Generator-Prompt jetzt **v5.2** (v4 abgelöst;
> `SYSTEM_PROMPT_PATH` in generate_grounded.py). Companion-Prompt v5.1-Stil mit Faszinations-/
> Vielfalts-Kriterien + appeal-gestaffelter Anzahl. **appeal-Fix in run_batch.py:522 aktiv**
> (`data["appeal"]` → select_companions_raw) — Batch-Kompass lief vorher immer mit Default "medium".
> **Gemini-503-Welle vom 28.06. abgeklungen**, Generierung wieder lauffähig: Wal-Lauf 30.06.
> (S1/S2/S3 + Bilder + Lektorat) 503-frei durchgelaufen, 4 Companions (Moby-Dick/Echoortung/
> Walfang/Tiefsee), Docx wal_v5_2. Details: PROJEKTDOKUMENT Entscheidungs-Log 30.06.

> **v5.2-FEINSCHLIFF (01.07.2026): 3 FIXES VALIDIERT + 4 NEUE UNVALIDIERT.**
> (a) **Validierungslauf v5.2c durchgelaufen** (Vulkan Stage-2-Resume l1+l3 + Wal + WWII frisch,
> je S1/S2/S3, Queue gesund) — die ersten drei Fixes technisch bestätigt:
> - 3df8c2c Companion-Ausschöpfung: greift jetzt auch bei Wal S3 (Blauwal/Schwertwal/Moby-Dick
>   tragen bei; b-Lauf war nur Primär+Moby-Dick). Vulkan/WWII S3 breit.
> - c17d559 Trim (wmax×1.25): 0 von 9 Artikeln getrimmt; S3 landet im oberen Band statt unter min
>   (Vulkan l3 650, Wal l3 676, WWII l3 540 — alle unter Schwelle 812/812/709).
> - 9dc1842 Box-Schema: reveal_text-Missbrauch = 0 über alle 9 Artikel.
> Docx vulkan/wal/wwii_v5_2c auf Desktop.
>
> (b) **VIER NEUE Fixes — NOCH NICHT VALIDIERT** (aus PO-Leseurteil der c-Docx: S1 zu blumig,
> ungedeckte Ausschmückungen; + Bild-Pipeline-Befunde):
> - 0c045c6 Register-/Wahrheitstreue (drei Regeln): Abschnitt A Anti-Ausschmückung (alle Stufen) —
>   keine erfundenen Gefühle/Motivationen/Verstärker ("singt für seine Familie", "viel größer als");
>   S1-Matrix Register-Drossel ("sanfte Riesen", "schlaue Töne"); S3-Matrix Drastik-Schranke.
> - 8bb6a53 Bildmenge abschnittsbezogen: 80%-Pool-Regel (geerbter v4-Widerspruch) raus; jetzt ein Bild/
>   Abschnitt, zweites nur bei >5 Sätzen (alle Stufen), harte Obergrenze 15.
> - 9752a97 Raster-Diagramme durchlassen: "diagram/schema/chart" aus _IMG_SKIP_LOWER raus — didaktische
>   Grafiken erreichen jetzt den Vision-Filter statt am Dateinamen verworfen zu werden.
> Der nächste (Sammel-)Lauf muss zeigen, ob sie greifen: S1 nüchterner, keine "viel größer"-Verstärker
> schon vom Generator, ein Bild/Abschnitt statt Überfüllung, Diagramme im Artikel. Lektorat unverändert.
>
> **OFFENER PIPELINE-PUNKT — SVG (Fix B):** Didaktische Grafiken sind auf Wikipedia oft .svg; die werden
> weiter beim Sammeln übersprungen (_IMG_SKIP_EXT). Fix B = Sammel-Logik + SVG→PNG-Rasterung (neue
> Dependency). Aufwand/Nutzen erst nach dem Sammel-Lauf entscheiden. Details: PROJEKTDOKUMENT Roadmap.

> **02.07.2026 — BATCH-HÄRTUNG + FLASH-MONITOR PRODUKTIV; VULKAN-v5.2d-LAUF UNGEPRÜFT.**
> (a) **Unbeaufsichtigt-Härtung run_batch.py** (de2b5b1): Gemini-Batch-Stall-Timeout jetzt
>   `GEMINI_BATCH_TIMEOUT_MIN` (Default 30, env-überschreibbar) statt 48h; bei Timeout Auto-Cancel
>   (`client.batches.cancel`) VOR TimeoutError. Zentrale append-only **run_status.jsonl** (Repo-Root;
>   ts/run_id/thema/stufe/status/grund/detail) an allen Degradationspunkten + Summary-Logzeile.
>   Anthropic-Poll (Lektorat/Phase B) bewusst unberührt. Paketierung (B) aufgeschoben (Checkpoint-Umbau).
> (b) **Flash-Verfügbarkeits-Monitor** (3a11719 + Fix bedd81c + .gitignore 689b6d8): `scripts/flash_monitor.py`
>   misst tageszeitliche `gemini-3.5-flash`-Queue-Lage (4 Wegwerf-Requests an GEMINI_MODEL, 20-min-Timeout +
>   Auto-Cancel, append **flash_monitor.jsonl**, garantiert genau 1 Zeile/Aufruf). Windows-Task
>   `WissensfreundFlashMonitor` läuft **19×/Tag** (00:05–09:05, alle 30 min, „nur wenn angemeldet"; Wrapper
>   `flash_monitor_run.bat` → `flash_monitor_task.log`, beide lokal/gitignored). Manuell + im Task-Kontext
>   verifiziert (succeeded, Key aus .env). Auswertung nach einigen Tagen → 503-armes Frühfenster + realistische
>   Timeout-/Paketgrößen.
> (c) **Vulkan-v5.2d-Lauf durch, NICHT freigegeben** (`articles/vulkan_v5_2d/`, run_id 20260702T091952):
>   Stage 2 **3/3 OK** (Batch ~11 min, kein Stall — 30-min-Timeout musste nicht greifen), Companions 4
>   (Pompeji/Vulcanus/Geysir/Raucher), appeal high, **kein Trim** (S1 250 / S2 381 / S3 640).
>   **Bildmenge-Fix 8bb6a53 eingehalten** (1–2 Bilder/Abschnitt via img_index, zweites nur bei >5 Sätzen).
>   **Raster-Diagramm-Fix 9752a97 UNVALIDIERT** (Pool 28 = nur Fotos; Vulkan-Diagramme sind SVG → Fix B nötig).
>   Lektorat 9 Findings, kein PRÜFEN/EINBAU_FEHLGESCHLAGEN. **DREI OFFENE LAYOUT-BEFUNDE (PO-Leseurteil,
>   noch NICHT diagnostiziert): Box→Abschnitt-Fehlzuordnung, Box wiederholt Fließtext, falsche Bildzuordnung
>   — aus Artikel-JSON zu diagnostizieren (nicht Docx).** Register/Drastik-Fix 0c045c6 am Text noch zu
>   beurteilen. Wal/WWII-v5.2d stehen noch aus. Kein STATUS-/Katalog-Eingriff; Docx + S1/S2/S3-Txt auf Desktop.
> (d) **FIX 1 committet + verifiziert** (8b3740d): Der „Doppelsatz"-Befund war ein **Lektorat-Apply-Bug** in
>   `_apply_auto_correction` (`lektorat_common.py`) — bei einem Mehr-Satz-`claim_original` wurde nur der Best-Match-
>   Satz ersetzt, die weiteren vom Claim abgedeckten Original-Sätze blieben als Waisen stehen. Fix (sec-Zweig):
>   neuer Helfer `_claim_covers_run` prüft einen zusammenhängenden Satz-Lauf ab Best-Match; bei sauberem Lauf wird
>   der erste Satz durch den Korrektur-Block ersetzt und die Folge-Sätze entfernt, sonst kein Eingriff (→ flaggen).
>   Ein-Satz-Claims + Box-Zweige unverändert (regressionsfrei). Am realen Pompeji-Fall verifiziert (9→8 Sätze,
>   s027-Waise entfernt, alle anderen intakt). **Noch offen:** img_index-Fehlzuordnung + Box-Redundanz (Generator-
>   Prompt), Photosynthese-Recall-Miss (Lektorat) — Diagnosen in `diagnose_fixes.txt` (lokal, ungetrackt).

> **WEG B VERWORFEN + RÜCKBAU ABGESCHLOSSEN (26.06.2026)** — Generierung zurück auf
> Gemini-3.5-flash + v4_production (Sonnet-Generator stilistisch nicht kindgerecht genug,
> an Erde S1/S2/S3 über sonnet_v1/v2/v3 + gemini_v1 getestet). `stage_models` alle
> Generierungs-Stufen auf gemini; Companion-Prompt auf sachliche a10a6db-Fassung; run_batch
> lädt fix v4. Providerunabhängige Härtungen behalten (Quote-Repair, PHASE-A-Fehlerbehandlung,
> Companion-Fallback, 429-Härtung, verify). Weg-B-Prompts → `archiv/weg_b_2026-06/`;
> claude_client.py + test_sonnet_batch.py dormant im Repo. verify: 0 Hart-FAIL (5 Einfrier-Checks).
> Details: PROJEKTDOKUMENT „Eingefrorener Stand & Reaktivierung".
>
> **Stage-1/2/3-Resilienz-Thema GESCHLOSSEN** — alle drei Stages konsistent resume-fähig, real verifiziert
> (Degradation + Resume unter 503). Vulkan-Verifikation grün: 9-Artikel-A–G-Vergleich vollständig (verify_20260623b),
> Companion-Fix (Vesuv/Pompeji) + Bildausnutzung + Box-Konkretheit sichtbar wirksam. Der finale Resume am
> 2026-06-24 lief selektiv: Stage 1 komplett übersprungen, Stage 2/3 nur die 3 fehlenden Vulkan-Artikel/-Lektorate
> neu, Titanic+WW2 per Datei-Existenz unberührt (Zeitstempel unverändert). Alle 9 Artikel + 9 Lektorate vorhanden.
>
> **~~PROJEKT PAUSIERT (26.06.2026)~~ → REAKTIVIERT (30.06.2026):** 503-Welle vom 28.06.
> abgeklungen, Generierung wieder lauffähig. Produktion jetzt Gemini Flash + **v5.2** (nicht
> mehr v4). Details: PROJEKTDOKUMENT Entscheidungs-Log 30.06. + „Eingefrorener Stand & Reaktivierung".
>
> **COMPANION-VERBESSERUNG + GENERATOR-ÜBERARBEITUNG (27.06.2026 — am 30.06. nach main gemergt):**
> Branch companion-faszination-vielfalt-2026-06 brachte gegenüber main folgende Änderungen
> (alle committet; Merge aba4122 am 30.06.):
>
> Companion-Prompt (Variante E):
> - Kinderalltag/Kinderfantasie als oberstes Kriterium
> - Autorframing: Flash wählt als zukünftiger Autor
> - Vielfalt der Blickwinkel mit Selbst-Probe-Frage
> - Zwei neue Kriterien: Kulturelle Ankerpunkte (Moby Dick, Mythen) + Wie sieht es dort aus?
>   (Klimazonen, Biotope)
> - Harte Ausschlussgründe (Pangaea, Blue Marble etc.)
> - Companion-Limit: 3 (Testlauf; soll dynamisch 3–5 nach Appeal werden)
> - 9+12 Stage-1-Läufe auf A/B/C/D/E getestet; E Sieger
>
> Generator-Prompt v4 (Branch-Stand):
> - NARRATIVER FLUSS: Tiefe vor Breite
> - Wortziel durch Erzähltiefe, nicht neue Fakten
> - MIKRO-FLUSS: Bindewörter + Vorher-Nachher-Beispiel
> - S1: Ø <12 Wörter, Bindewörter erwünscht
> - S2/S3: Konjunktionen, Lese-Sog, Überleitungen
> - JSON-Mindset: Denke in Absätzen, gib in Sätzen aus
> - Docx-Caption-Fix: beschreibung + Originaltitel + Lizenz
> - Selektion + narrativer Fluss geschärft (committet+gepusht 376de8a): ERZÄHLFADEN-Feld
>   in PLANUNG, "Selektion vor Vollständigkeit", Brückenpflicht ohne Ausnahme, Box-Anker =
>   unmittelbar umgebender Fließtext (sonst streichen)
>
> Testlauf-Stand:
> - v1 (vor Wortziel-Regel): gut, zu kurz
> - v2 (mit Wortziel-Regel): Faktenflut; Regel angepasst
> - v3/v3b: Gemini-503-Zähschleife, abgebrochen (Crash-Guard hielt)
> - Generator v5.2 (= v5.1-Stil + v4-Schemablock): läuft schema-konform durch Pipeline;
>   Erde-Vergleichslauf grün (erde_v5_2_test.docx); planung als Text-Prefix (nicht 100% deterministisch),
>   ERZÄHLFADEN befüllt. Datei: wissensfreund_generator_prompt_v5_2.md (lokal, nicht committet) [überholt 30.06.: committet + als Produktions-Prompt gemergt]
>
> Companion-Prompt v5.1 + appeal-Injektion (commit ec76efa, Branch):
> - COMPANION_PROMPT_TMPL ersetzt: Appeal-gestufte Anzahl (low=2-3, medium/high=3-5),
>   3-Säulen-Kriterien, härtere Ausschlussgründe; .format() bekommt appeal durchgereicht
>   (select_companions_raw(appeal=...) ← prepare_topic_sources ← job["resolved_appeal"])
> - Dreifach-Lauf (v5.2-Generator, neuer Kompass, mit Bildern+Lektorat):
>   - Vulkan (appeal high): 4 Comp (Pompeji/Vulcanus/Geysir/Schwarzer Raucher), S1-3 im Ziel, Docx vulkan_v5_2
>   - Zweiter Weltkrieg (appeal low): 3 Comp (Anne Frank/Enigma/Weiße Rose), S1-3 ok (wenig Bilder=sensibel-Filter), Docx wwii_v5_2
>   - Wal (appeal high): Companion-Test grün. 29.06.-Nachzug: Kompass lieferte 4 Comp
>     (Delfin/Moby Dick/Blauwal/Meeresschutz) erst über Fallback 3.5-flash→2.5-flash. ABER
>     Phase-2-Generierung hat KEINEN Modell-Fallback → alle Stufen an 503 erschöpft/übersprungen
>     (None-Guard griff sauber, kein Crash), 0 Artikel. Wal-Artikel+Docx zurückgestellt.
> - BEFUND: Appeal-Staffelung wirkt (high→4, low→3 statt fixem "bis zu 3"); kulturelle/vielfältige Anker
> - Folgecommits (Branch): docx-Header zeigt jetzt Companions (09bce25); v5.2 erstmals committet
>   (0b1427e) inkl. neuem Abschnitt "D. Artikelumfang" (high Appeal + ≥4 Comp → oberes Spannendrittel)
> - FALLBACK-ASYMMETRIE (29.06., dokumentiert): Kompass hat Modell-Fallback (3.5→2.5-flash),
>   Phase-2-Generierung NICHT. ENTSCHEIDUNG: bewusst KEIN Generierungs-Fallback auf 2.5-flash
>   (auch bei 503-Erschöpfung) — Läufe warten auf 3.5-flash-Stabilität (Entscheidungs-Log 29.06.).
> - Nächster Schritt: Wal-Lauf nachziehen wenn Flash stabil; Docx-Vergleich v4 vs v5.2 lesen; dann Merge-Entscheidung [erledigt 30.06.: gemergt]
>
> Bugfix auf Branch:
> - None-Guard nach Retry-Erschöpfung (Cache-403-Crash)
>
> **OFFENE Punkte nach Priorität:**
> - **Companion-Auswahl ist stufen-blind (diagnostiziert): KEIN Defekt** — Auswahl liefert
>   nur Quellmaterial, Stufen-Differenzierung macht der Generator (kennt AGE_LEVEL).
>   "Holocaust ab S3" wäre ggf. Generator-Prompt-Sache, nicht Kompass.
> - **Trim-Schärfe (offen, nicht dringend):** bei Overshoot >200W zu zahm
>   (2 Pässe je ~27W). Auf echten Produktions-Wortzahlen messen ob Nachschärfung
>   nötig — NICHT auf 904W-Extremfall (Sonnet-Freitext-Test) tunen.
> - **gemini-3.5-flash down** (~30h 503). Fallback-Optionen getestet:
>   - gemini-2.5-flash: 44% JSON-Fehler → abgelehnt
>   - gemini-3.1-flash-lite: 9/9 JSON ok, aber −34–50% Wortzahl,
>     2–6 Bilder statt 10–15, Stil schlechter → abgelehnt
>   Produktion pausiert bis 3.5-flash stabil. Nächster Check: manuell.
> - **Lektorat: Stand 3 = bester Stand** (Recall 100 %, Precision 53 % auf GT_v1+v2).
>   Precision-Fix via Prompt-Tuning gescheitert (Rollback nach Stand 4). Precision-Lösung
>   erfordert claim-weise Architektur — deferred. FPs sind Stil-Tausche/Additionen,
>   keine Faktenfehler; mit Baustein 2 im Review handhabbar.
> - **erde_l3 nachtrimmen** — 839 > 682 W, wenn gemini-3.5-flash stabil.
> - **Review erw_20260624 Erde** — erde_l2 (1 KORR) + erde_l3 (3 SILENT + 1 PRÜFEN)
>   via review_tool.py.
> - **TTS-Stimme entschieden** (separater Chat) — einsatzbereit.
> - **[NÄCHSTER SCHRITT] Leuchtturm-Themen** — Sonne, Mond, Flugzeug, Eisenbahn,
>   Dinosaurier (staged wenn 3.5-flash stabil).
> - **Staged-Lauf-Workflow** jetzt Standard — nie wieder Voll-Lauf wenn Vision-Retry
>   nötig ist (dokumentiert in CLAUDE_CHAT_NOTIZEN.md).
> - **vulkan_l3 review_flag** (685 > 682 W) — 3 Wörter kürzen bei redaktioneller
>   Durchsicht. Unkritisch.
> - **Hygiene:** untracked Test-Ordner verify_pruefen_test{,2,3a,3b} + Probe-Skripte
>   aufräumen/gitignoren (unkritisch).
> - **TTS-Parameter festgelegt** (Stimme Iapetus, Modell gemini-3.1-flash-tts-preview,
>   Scene-Instructions S1–S3, tts_compose.py) → in CLAUDE_CHAT_NOTIZEN.md dokumentiert.
> - **TTS-Orchestrator `tts_produce.py` (v2)** + `tts_compose.py` erweitert. Artikel-Audio (1 WAV,
>   Iapetus) + Quiz-Audio (--quiz). NEU: **Stimmungs-Scene** (neutral/ernst/staunend, auto aus
>   title+category_top/sub — Vulkan→staunend, WW2/Spartacus→ernst, Dino→staunend); **5 Richtig/
>   Falsch-Varianten** (per Frage-Index%5); **5 Abschluss-Clips** je Ergebnis (alle_richtig…alle_falsch);
>   **Stil-Tags** [excited]/[thoughtful]/[serious] vor wow/stimmt_das/warnung-Boxen.
>   **PAUSEN-BEFUND:** gemini-3.1-flash-tts cappt [pause=N] bei ~1.9 s → `synth_with_pauses` splittet
>   den Text an großen Pausen (>=1.5 s) und fügt ECHTE Stille ein (Kapitel 2.0 s, stimmt_das 4.0 s;
>   kleine 0.3/0.5 s bleiben inline). Verifiziert: Vulkan l1–l3 + WW2_l2 → 63 valide WAVs; gemessene
>   Artikel-Pausen 1×~5.6 s + 4×~2.5 s exakt wie gesetzt.
> - **Stage-4-Wiring FERTIG** — `stage4_tts()` in run_batch.py ruft `tts_produce.produce_article(quiz=True,
>   run_id=_RUN_ID)` je Artikel, Output → `out_dir/audio/`. Quelle: **Lektorat bevorzugt** (korrigierter
>   Text), Fallback articles/. **Naming-Fix:** stage4_tts strippt den `lektorat_`-Präfix → WAVs heißen
>   `vulkan_l1_artikel.wav` (== article_id). **Encoding-Fix:** produce_article wrappt stdout auf UTF-8
>   (io.TextIOWrapper) → Lauf braucht KEIN `PYTHONIOENCODING` mehr. Verifiziert: Vulkan l1–l3 ohne
>   Env-Var, 3 OK / 0 Fehler, 48 WAVs mit sauberen Namen.
> - **Audio→R2-Verdrahtung FERTIG** — (1) `upload_articles.py` um `--audio-dir` erweitert (lädt WAVs nach
>   `r2:{bucket}/audio/`, `upload_audio_to_r2()`, gleiche rclone-Flags); `--topic-tree` jetzt optional.
>   (2) `stage5_upload()` in run_batch.py ruft upload_articles.py mit articles+audio. `--stage 5` (NICHT in
>   run_all — explizit). Verifiziert: Vulkan-Upload → 18 Artikel-JSON + **48 WAVs in r2/audio/** (sauberes
>   Naming). ⚠️ Indizes werden aus --articles-dir neu gebaut → global.json zeigt nur die hochgeladene Menge
>   (Bucket noch nicht live, App auf klexikon.zim — unkritisch; bei Voll-Katalog-Upload beachten).
> - **TTS-Pipeline end-to-end FERTIG** (Stage 1→2→3→4→5). Entscheidung: **nur Vulkan als TTS-Pilot**
>   (l1–l3, 48 WAVs in R2) — keine weiteren Themen vertonen/hochladen vor dem echten Produktionslauf.
> - **Review-Workflow (Standard ab jetzt):**
>   1. Claude Code → Docx auf Desktop
>   2. Andreas prüft in Word, tippt Kommentare in rechte Spalte
>   3. Speichern in wissensfreund_approved/ oder wissensfreund_changes/
>   4. watch_review_folders.py erkennt Datei automatisch (oder manuell:
>      python scripts/process_review_docx.py <pfad> --run-dir <dir>)
>   5. Approved → editorial_approved.json → TTS → App
> - **Produktions-Übersicht:** `python scripts/generate_production_status.py` → production_status.json
>   (Stadium je Thema+Stufe). Stand 2026-06-25: 125 Artikel, 97 reviewed, 3 vertont, 54 review_flag.
>   Word-Review je Lauf: `python scripts/generate_review_docx.py <run_dir>` (*.docx ist gitignored).

---

## Abgeschlossen (2026-06-25)

**Weg B (Gemini → Claude) Fortschritt:**
- Schritt 1 ✅ Lemma + Kompass auf Haiku 4.5 (committed, in Praxis bewiesen: Stage 1 ohne 3.5-flash, Erde bekommt Companions)
- Quote-Repair ✅ typografie-erhaltend in parse_article_json (transport-agnostisch)
- Schritt 2c ✅ Trim + Box-Repair provider-fähig (Sonnet), ARTICLE_SCHEMA zentral
- claude_client.py: forced tool-use (thinking_budget=0) + auto+thinking-Pfad + Streaming
- Anthropic Batch + tool-use + thinking verifiziert (test_sonnet_batch: emit-Block kommt, große Felder werden stringifiziert → _destringify_article löst das)
- Schritt 2b ✅ Stage-2-Generator-Batch provider-fähig (Sonnet-Zweig, 3ce6991)
- Batch-Create-Retry-Härtung Anthropic-Zweig (b75de83)
- Companion-Such-Fallback via resolve_lemma — Verlustrate 35%→~0 (d9d8775)
- 429-Härtung Companion-Lookup + _companion_target_ok via _wp_get (bae2f8e)
- Companion-Kompass kulturelle Verortung + greifbar-vor-abstrakt (3d4430a, unverifiziert)
- Vision sensibler Gegentest: WW2/Titanic/Gladiator gesourct, Kontaktbogen-Docx erstellt
  (Bildauswahl von Andreas als unzureichend bewertet → Companion-Fixes oben adressieren die Ursache)

**Modell-Vergleichstest** (test_25flash + test_31flashlite):
- gemini-2.5-flash: 44 % JSON-Fehlerrate im Batch (nicht produktionsreif für Stage 2)
- gemini-3.1-flash-lite: 9/9 JSON sauber, aber Artikel zu kurz + zu wenig Bilder
  (2-6 statt 6-14; Wortunterschreitung in 7/9 Artikeln)
- Fazit: kein Fallback-Modell produktionsreif; gemini-3.5-flash bleibt Zielmodell
- Werkzeug: --gen-model Override in run_batch.py (Commit 7dd21ac).

**Review-Round-Trip-Workflow** (Commit 6831344) — process_review_docx.py +
watch_review_folders.py. Kommentare aus rechter Docx-Spalte (w:w=1701)
auslesen, Satz-Zuordnung via exact/substring/fuzzy, Änderungen in
lektorat_*.json schreiben, neues Docx regenerieren. Approved-Ordner →
editorial_approved.json setzen. E2E-Test bestanden.

**Produktions-Übersicht `generate_production_status.py` + production_status.json** (Commit folgt).
Scannt alle articles/<run_dir>/articles/ + /lektorat/, baut je Thema+Stufe ein Stadium
(produziert < lektoriert < reviewed < vertont < auf_app) mit review_complete/word_count/
review_flag/tts_wav/generated_at. Output JSON-Array (Repo-Root), sortiert nach Thema/Stufe,
plus stdout-Summary + Stadium-Verteilung. Erstlauf: 125 Artikel total, 97 reviewed, 3 vertont,
54 review_flag; Verteilung lektoriert 25 / reviewed 97 / vertont 3. „reviewed" gilt auch
vacuously bei 0 Findings (alle Findings entschieden → True) — bewusst nach Spec.

**Word-Review-Generator versioniert** — `scripts/generate_review_docx.py` (python-docx) erstmals
getrackt: durchgehend 2-spaltiges A4-Review (Text links, Kommentarspalte rechts), Tracked-Changes
(KORR: rot durchgestrichen + grün), PRÜFEN mit Quelle/Beleg, Inline-Bilder + Hero, Quiz mit
markierter richtiger Antwort. Aufruf je Lauf: `python scripts/generate_review_docx.py <run_dir>`.

**.gitignore: Word-Dokumente** (Commit 0f0ee2c) — `*.docx` + Word-Lock-Dateien (`~$*.docx`,
`~$*.xlsx`) ignoriert. Review-Docs sind regenerierbare Artefakte, gehören nicht ins Repo.

**erw_20260624 komplett (9/9)** — Erde via Kompass-Fallback durchgebracht (Commit b29f44e).
erde_l3 review_flag (839 > 682 W, Trim-503-Ausfall — nachtrimmen wenn 3.5-flash stabil).
Regenwald/Wal/Erde Artikel + Lektorate auf main.

## Abgeschlossen (2026-06-24)

**TTS-Diagnose + Vergleich** — gemini-2.5-flash-preview-tts + gemini-3.1-flash-tts-preview
beide verfügbar und stabil. PCM→WAV-Fix dokumentiert. Stimme in separatem Chat
abschließend gewählt und getestet.

**Circuit Breaker Stage-1-Kompass** — run_batch.py: CB_THRESHOLD=3 / CB_WAIT_MIN=15.
Nach 3 aufeinanderfolgenden API-Ausfällen (companions_raw==[] AND usage=={}) pausiert
Stage 1 automatisch 15 Min und macht danach weiter. Kein Abbruch — companions_failed-Topics
bleiben für Resume markiert. Echte 0-Companions (usage gefüllt) lösen Breaker nicht aus
und resetten ihn. Wirkt erst bei ≥3 Topics im Lauf (Solo-Lauf: kein Effekt).

**Produktionslauf erw_20260624** (Regenwald + Wal, 6/9 Artikel) — Commit 6130b7e.
Erde ausgefallen: Kompass-503-Erschöpfung (6 Versuche), nicht Logikfehler — Retry ausstehend.
18 Bilder ohne Vision-Verdict (503-Welle): Vision-Retry-Fix greift ab nächstem Lauf.
Review vollständig: 8/8 Findings (3 KORR angenommen, 4 SILENT auto, 1 PRÜFEN angenommen).
BOX-Präfix-Bug in review_tool.py behoben. Staged-Lauf-Workflow dokumentiert.

**Review verify_20260623b abgeschlossen** (Commit a1db022) — review_tool.py auf 9 Artikel
angewendet. 16/16 Findings reviewed: 8 KORRIGIERT angenommen, 2 PRÜFEN abgelehnt
(vulkan_l3 Pompeji/Herculaneum + ww2_l1 Kausalität Code-Knacker → kein Eingriff),
6 SILENT auto. Lektorat-Verzeichnis erstmals versioniert. Review-Workflow end-to-end
verifiziert.

**Baustein 2: HTML-Review-Tool** (Commit 4f3b2d2) — review_tool.py, Python stdlib,
kein Flask. GET / zeigt interaktive Review-Seite (PRÜFEN mit Radio-Buttons annehmen/ablehnen,
KORRIGIERT mit Revert-Checkbox, SILENT eingeklappt). POST /submit schreibt Entscheidungen
in lektorat_*.json (review_decision + reviewed_at), Lektorat-Body wird in-place aktualisiert,
Pre-Lektorat-Artikel bleiben unangetastet. Atomare Writes, konservative Defaults, idempotenter
Re-Run. Option A: lektorat_*.json als Edit-Ziel (enthält korrigierten Body + pruefbericht).

**Lektorat reproduzierbar (temp=0) + Eingriffsgrenze geschärft** (Commit 0a39bf8, feature/lektorat-temp0-eingriffsgrenze
→ main FF). (1) **Reproduzierbarkeit:** Lektorat lief ohne gesetzte Temperatur → Anthropic-Default 1.0 →
nicht-deterministische Faktenprüfung (empirisch belegt: gleicher Artikel, vulkan_l3, kippte zwischen Läufen,
KORRIGIERT↔SILENT). `temperature=0` an allen 4 Aufrufstellen (run_batch Stage-3-Batch, lektorat_common
run_lektorat_sync + run_lektorat_batch, run_lektorat_catchtest). (2) **Eingriffsgrenze geschärft** (LEKTORAT_SYSTEM):
Z.55-Widerspruch aufgelöst (von „direkt/nicht impliziert" → „sinngemäße Deckung genügt"); neue EINGRIFFSGRENZE-Kernregel
(Eingriff NUR bei Widerspruch zur Quelle ODER ungedecktem Zusatz); „Unvollständigkeit ≠ Fehler"-Schutz mit Beispielen
(Landhaus/Erdspalte/drei Rotoren) — schließt die Lücke, durch die das Modell quellengetreue Verkürzungen als
„einseitig" flaggte; Grenzwert-Ausnahme (falsche Obergrenze „bis zu 20 km" bei Quelle 30 km = Widerspruch → korrigieren),
scharf vom erlaubten Weglassen abgegrenzt. py_compile + verify_project_facts 14/14 PASS (regex_absent hält).
**Diagnose-Befund dahinter:** Reproduzierbarkeit (temp) und Vollständigkeit (Recall) sind UNABHÄNGIG — temp=0 fixiert nur,
macht nicht vollständiger; Recall braucht den claim-weisen Prompt-Umbau (s. OFFEN).

**Lektorat PRÜFEN liefert jetzt Korrekturvorschläge** (Commit 616c19f, feature/lektorat-pruefen-vorschlag → main FF)
— Baustein 1 von 2 des Review-Workflows. Bisher gab PRÜFEN nur Problem+Begründung aus („Artikel NICHT ändern") →
im Review nicht zustimmungsfähig. Jetzt liefert jedes PRÜFEN-Finding mindestens einen konkreten, ankreuzbaren
Vorschlag. Drei Eingriffe in lektorat_common.py: (1) Prompt — PRÜFEN-Schwelle als Qualitätskriterium statt hartem
Zähllimit (Ziel 0–1, aber ALLE echten Zweifelsfälle melden, kein Umdeklarieren zu KORRIGIERT); fallabhängige
Vorschlagsvorgabe (Fall 1 zwei Varianten/Schnittbereich, Fall 2 Kern bewahren, Fall 3 zurücknehmen ohne ungedeckte
Weichmacher); verbindliche Maxime „im Zweifel zurückschneiden, nie hinzudichten". (2) Output-Schema — pruefen-Block
um `korrektur_vorschlag` (Pflicht) + `korrektur_alt` (optional, nur Fall-1) erweitert. (3) Builder — PRÜFEN-Zweig
liest die neuen Felder statt `korrektur_neu=None`; `korrektur_alt` konsistent in allen findings[]-Zweigen.
parse_lektorat_v2 unverändert (reicht generisch durch), Renderer/HTML bewusst nicht angefasst (Baustein 2).
py_compile + verify_project_facts (14/14 PASS, regex_absent grün) + Inline-Funktionstest grün. **OFFEN: Test an
echten Daten (9 Verify-Artikel) + Baustein 2 (HTML-Review-Tool).**

**Stage-1/2/3-Resilienz-Thema geschlossen + Vulkan-Verifikation grün.** Finaler Resume in verify_20260623b
selektiv gelaufen: Stage 1 kompletter Skip (alle Topics sauber), Stage 2 „unvollständig (3/9 fehlen:
vulkan_l1–l3) → fehlende neu, vorhandene überspringen", Stage 3 analog; Titanic+WW2 per Datei-Existenz
unberührt (Zeitstempel unverändert, Log „bereits vorhanden"/„bereits lektoriert — übersprungen"). Alle 9
Artikel + 9 Lektorate vorhanden, beide Checkpoints vollständig. Damit sind alle drei Stages konsistent
resume-fähig und unter realer 503-Degradation verifiziert (Flash-Check + l3-Trim fielen sauber per Fallback ab,
kein Abbruch). A–G-Analyse Vulkan grün: Grounding lückenlos belegt (source_passages), Primärinhalt ≥50 %,
Box-Konkretheit (WOW Tamu-Massiv/Surtsey-Perlen, Warnung pyroklastische Ströme), Bildausnutzung deutlich ↑
(l3 8/12 inkl. freigegebenem Vesuv-Historiengemälde), Stufenstaffelung 210/346/685 W sauber, Lektorat treffsicher
(l1 0, l2 3 KORR, l3 3 SIL/1 KORR/1 PRÜFEN). Companion-Fix (Vesuv/Pompeji erstmals präsent) + v4-Edits + Vision/
Diagramm-Fixes sichtbar wirksam. Zwei kleine offene Punkte oben im Banner.

**Checkpoint-Resume-Lücke in Stage 2+3 geschlossen** (Commit 0b447b6, feature/stage23-resume-fix → main FF) —
systemischer Fix, alle drei Stages konsistent resume-fähig. Diagnose über den Vulkan-Resume: Stage 1 reparierte
Vulkan (companions_failed→False), aber Stage 2+3 übersprangen sich pauschal (status=done) ohne Pro-Artikel-
Prüfung → die in Stage 1 reparierten Topics erreichten die Folgestages nie (Vulkan-Artikel nie generiert/
lektoriert). Fix in run_batch.py: Stage-2/3-Full-Skip auf `_load_cp_raw` + Vollständigkeitsprüfung umgebaut
(alle themen×stufen-Dateien vorhanden → skip; sonst Fall-through). Stage 2: vorhandener Disk-Vorscan +
Pro-Artikel-Skip selektieren das Fehlende; Empty-Batch-Pfad returnt vorgeladene `articles` statt `{}`. Stage 3:
NEU Datei-Vorscan befüllt `lektorat_results` aus existierenden `lektorat_*.json` VOR dem Batch-Bau (sonst fielen
saubere Topics aus dem Checkpoint), alte `={}`-Re-Init entfernt, Empty-Pfad returnt Vorgeladenes. Wahrheitsquelle
bewusst Datei-Existenz (robuster als companions_failed-Filter; Asymmetrie zu Stage 1 gewollt). py_compile OK.
**Macht den finalen Vulkan-Resume (Stage 2+3 ziehen die 3 fehlenden Artikel) jetzt möglich** — steht als Nächstes an.

## Abgeschlossen (2026-06-23)

**Checkpoint-Resume-Lücke geschlossen** (Commit 8acc43e, feature/stage1-resume-fix → main FF). Diagnose
bestätigte: Nach einem Exit-0-Lauf mit Degradation übersprang der Stage-Level-Checkpoint (status=done) die
GANZE Stage 1 (`if cp: return cp["topics"]`) und zementierte companions_failed-Topics — die Fix-2-Partial-
Resume-Logik kam nie zur Ausführung (Partial in Phase C gelöscht). Fix in run_batch.py: neuer `_load_cp_raw`
(Checkpoint ohne Skip-Log); Checkpoint-Resume jetzt mit Pro-Topic-Prüfung — alle Topics sauber → ganze Stage
skip (kein Regress); ≥1 companions_failed → Checkpoint wird Resume-Quelle, Fall-through in Phase A. Eine
Resume-Quelle (Partial > Checkpoint), EIN `done_topics`-Filter für beide Pfade (identische Option-1-Semantik).
Selbstheilend: scheitert ein Resume erneut, bleibt der Topic companions_failed im bedingungslos geschriebenen
Phase-C-Checkpoint, nächster Re-Run greift ihn wieder. py_compile OK. **Macht den 2. Resilienz-Test-Teil
(Vulkan-Resume in verify_20260623b) jetzt möglich** — steht als Nächstes an.

**Stage-1-Resilienz: Pro-Topic-Checkpoint + 503-Sichtbarkeit** (Commit 331773f, feature/stage1-resilience →
main FF). Fix 1: 0-Companion-Topics werden mit `companions_failed=True` markiert (statt still als done) →
`failed_topics` + `log.error` am Stage-1-Ende; Stage 2 überspringt solche Topics. Fix 2 (Ansatz B/Variante b):
Stage 1 zu Pro-Topic-Außenschleife umgebaut, schreibt nach jedem Topic atomar `stage1_partial.json`
(tmp+os.replace); Opus-Recheck als cross-topic Nachlauf (Phase B, resume-fest via deterministischem
`_img_key`); Resume übernimmt nur sauber verarbeitete Topics (`companions_failed != True`), gescheiterte
werden neu durchlaufen; Phase C schreibt finalen Checkpoint + löscht Partial. Neue Helfer `_partial_path/
_save_partial/_load_partial/_img_key/_opus_recheck`; tote `_img_candidates`/`defaultdict` entfernt.
py_compile + Helfer-Inline-Test grün. **Verifikationslauf steht weiterhin aus** — wartet auf stabilen
Gemini-Zustand; die Resilienz-Fixes machen einen erneuten Lauf nun abbruch-/degradations-robust.

**Kompass-Auswahl Batch→Sync** (Commit f6135be, feature/kompass-sync → main FF). In run_batch.py Step 2 den
Kompass-Batch-Block (client.batches.create + poll_gemini_batch + _get_inlined_responses) durch synchrone
Schleife mit `select_companions_raw` (aus generate_grounded.py) ersetzt — bringt Retry (6×, exp. Backoff),
Structured Output (response_schema) und Usage-Tracking mit. Tote Imports COMPANION_PROMPT_TMPL/
COMPANION_SYSTEM_PROMPT entfernt; Dry-Run-Print + Stage-1-Docstring auf Sync-Terminologie. Anlass:
verify_20260623b hing >2h im Kompass-BATCH (JOB_STATE_RUNNING) — derselbe Gemini-Batch-Queue-Stau wie zuvor In run_batch.py Step 2 den
Kompass-Batch-Block (client.batches.create + poll_gemini_batch + _get_inlined_responses) durch synchrone
Schleife mit `select_companions_raw` (aus generate_grounded.py) ersetzt — bringt Retry (6×, exp. Backoff),
Structured Output (response_schema) und Usage-Tracking mit. Tote Imports COMPANION_PROMPT_TMPL/
COMPANION_SYSTEM_PROMPT entfernt; Dry-Run-Print + Stage-1-Docstring auf Sync-Terminologie. Anlass:
verify_20260623b hing >2h im Kompass-BATCH (JOB_STATE_RUNNING) — derselbe Gemini-Batch-Queue-Stau wie zuvor
bei Vision, NICHT modell-/schritt-spezifisch sondern batch-spezifisch. Jetzt sind Kompass + Vision sync;
nur noch Stage-2-Generierung + Opus-Recheck + Lektorat laufen über Batch. py_compile OK. Lauf wird neu gestartet.

**Vision: Companion-Bildkontext + Diagramme freigeben** (Commit 177ca72, feature/vision-context → main FF).
run_batch.py: vor `analyze_with_vision` wird `thema_vision` gebildet — Companion-Bilder (img["_source"] ≠
resolved_title) erhalten präzisen Kontext „Thema (Bild aus Begleitartikel: X)", Primär-/quellenlose Bilder
bleiben beim reinen thema. Keine Signatur-Änderung. image_vision_filter.py: pauschale ab_stufe=0-Regel für
Diagramme im VISION_PROMPT_TEMPLATE ersetzt — nur noch rein dekorative/leere Grafiken → 0; thematisch relevante
Diagramme/Karten/Querschnitte/Skizzen (Vulkanquerschnitt, Enigma-Schema, Stadtplan Pompeji) → ab_stufe 2/3.
Anlass: Vision bewertete Companion-Bilder (Enigma, Pompeji) gegen das falsche Thema; Skizzen wurden pauschal
gesperrt (verify_20260623: kein einziges Diagramm im Pool akzeptiert). py_compile + Inline-Check (inkl. BKS) grün.
**OFFEN: Wirkung noch nicht durch Lauf verifiziert** — bei nächstem Lauf prüfen: relevanz der Companion-Bilder↑,
Diagramme/Karten erscheinen im Pool.

**Generator-Prompt v4: Box-Qualität + Primärinhalt-Pflicht + Bildnutzung** (Commit 26fd462,
feature/generator-box-primary → main FF). 5 rein additive Edits in `wissensfreund_generator_prompt_v4_production.md`:
(1) Qualitätspflicht WOW (konkrete Tatsache + Kind-Vergleich, keine rohen Zahlen), (2) Qualitätspflicht Warnung
(themenspezifisch, kein Allgemeinplatz/Moralisieren), (3) Primärinhalt-Pflicht (≥50 % der Sätze = Kernthema;
Companions reichern an, ersetzen nicht) in grounding_rules, (4) Skizzen & Diagramme für S2/S3 explizit einladen,
(5) Bildnutzung maximieren + thematisches Matching (Pompeji-Abschnitt → Pompeji-Bild) — beide bei img_index.
Anlass: Verifikationslauf verify_20260623 — Generator nutzte nur 20–50 % des kuratierten Bild-Pools
(Vulkan 10/22, WW2 4/13), Boxen mit Qualitätslücken, WW2 zu nebenschauplatz-lastig. **OFFEN: Wirkung noch nicht
durch neuen Lauf verifiziert** — bei nächstem Lauf prüfen: Bild-Ausnutzung↑, Box-Konkretheit↑, Kern-Anteil↑.

**Vision-Check von Batch auf Sync umgestellt** (Commit fad46a3, feature/vision-sync → main FF).
`analyze_with_vision()` um optionalen `model=`-Parameter erweitert (image_vision_filter.py; `None`→Default
`GEMINI_MODEL`, sonst übergebener Name — kein Breaking Change für batch_run.py/generate_grounded.py). In
run_batch.py den gesamten Vision-Batch-Block (Step 5: `client.batches.create` + `poll_gemini_batch` +
Chunk-Loop, ~48 Z.) durch synchronen Einzelaufruf direkt im Download-Loop ersetzt (`model=VISION_MODEL`,
cost_tracker wie zuvor, None-Guard). Schnittstelle zu Step 6 (`all_vision_results[key]`) unverändert;
`img_meta_by_key`/`topic_img_keys` bleiben (von Step 6 + Opus-Lookup gebraucht). Tote Imports
(VISION_SYSTEM_PROMPT, VISION_PROMPT_TEMPLATE) entfernt; VISION_CHUNK_SIZE als toter Code kommentiert.
**VISION_MODEL bleibt gemini-2.5-flash** (günstig). Anlass: Vision-Batch klemmte modellspezifisch >3 h in
der Gemini-Batch-Queue (Kompass-Batch auf gemini-3.5-flash in 1 Min durch) — Queue-Problem ist
batch-spezifisch, nicht modellspezifisch; Sync eliminiert es ohne Modellwechsel. py_compile + Mock-Test grün.
**OFFEN: noch nicht durch echten Batch-Lauf verifiziert** — Mini-Verifikationslauf (3 Themen × S1-3) folgt.

**Companion-Auswahl auf „Würze & Tiefe" umgestellt** (Commit a953031, feature/companion-anchors → main FF).
`COMPANION_PROMPT_TMPL` überarbeitet (kanonische Quelle generate_grounded.py; run_batch.py importiert sie).
(1) Trainingswissen bei der AUSWAHL erlaubt — auch Begleitartikel die im Primärartikel fehlen, aber als
prägend bekannt sind (Vesuv-Beispiel); eiserne Grounding-Regel unberührt (Inhalt weiter nur aus geholten
Quelltexten). (2) Anker-Obergrenze entfernt (mehrere Anker, max 5 Slots). (3) Tod/Katastrophe-Regel
differenziert: ernste Themen erlaubt wenn kindgerecht erschließbar; nur reine Gräuel ohne Sachkern gemieden.
COMPANION_SYSTEM_PROMPT unverändert. Anlass: Vulkan-Lauf zog 5 Sachbegriffe, keinen Anker → kein Vesuv/Pompeji.
**OFFEN: Companion-only-Verifikationslauf** (inkl. Gegencheck heikler Themen — hält die differenzierte Regel?).
Kompass ist weiterhin stufen-/sensibel-BLIND (nur thema+lead, 1× pro Thema) — Verfeinerung bleibt offen.

**Bildwechsel pro Section begrenzt** (Commit e0c5348, feature/img-per-section → main FF). Neuer Post-Process
`_limit_images_per_section` in run_batch.py, greift nach `_set_is_hero`, vor dem Speichern. S1: genau 1 Bild
pro Section; S2/S3: 1 Bild bei <4 Sätzen, bis 2 ab >=4 Sätzen (erste floor(n/2) Sätze Bild A, Rest B).
Bild-Wahl: häufigster img_index (Generator-Mehrheit) + Tiebreaker Vision-relevanz aus Stage-1-Pool (imgs_s,
fehlt→0) + kleinerer Index. -1-Sätze erben das Section-Bild (kein Flackern); bildlose Sections unverändert;
images[] nicht beschnitten (Galerie bleibt). Diagnose-Basis: img_index kommt vom Generator-LLM (Code
normalisiert nur None→-1); relevanz (0-10, Vision) liegt nur im Stage-1-Pool, nicht im finalen JSON. 6 Inline-
Tests grün. **OFFEN: noch nicht durch echten Batch-Lauf verifiziert** — Verifikationslauf (3 Themen × S1-3) folgt.

**1600px-Phantom-Tier entfernt** (Commit 18172dc, feature/fix-tiers → main FF). `tiers`-Dict in
`_set_hero_and_tiers` (run_batch.py) trägt jetzt nur noch 300 + 800. Diagnose ergab: der „1600"-Pfad
(`bilder/{thema}/{stem}_1600.jpg`) war deklariert, aber nie befüllt — kein Code schreibt nach `bilder/`,
das Verzeichnis existiert nicht. 1600px-Bytes existieren nur im Vision-Cache (`.cache/downloads/{md5}_1600.jpg`,
image_vision_filter.py) und bleiben unangetastet. Rest-Drift dokumentiert: 600er-Tier wird nur gemessen
(Speicher-Tabelle), weder gecacht noch deklariert; kein 2048 irgendwo. Bild-Publishing nach `bilder/`/R2 bleibt offen.

**Batch-Pfad-Temperatur explizit + meta-Audit** (Commit 8230d6d, feature/batch-temperature → main FF).
Diagnose: Stage-2-`GenerateContentConfig` (gecacht + Fallback) trug keine `temperature` → stiller Gemini-
API-Default 1.0 griff (Stage-1: Kompass 0.3, Vision 0.1; Sync-Pfad gemini_client 0.6 — im Batch nicht
genutzt). Jetzt `temperature=1.0` in beiden Stage-2-Configs explizit (kein inhaltlicher Wechsel; die mit
1.0 erzeugten fp_measurement-Artikel wurden für gut befunden). Zusätzlich `generation_temperature=1.0`
und `generation_thinking="MEDIUM"` ins `article.meta` (bisher dokumentierte nur `generation_method` Modell/
Pfad/Prompt-Version) → Lauf-Parameter auditierbar. Greift ab nächstem Batch-Lauf. py_compile OK.

**LEKTORAT_SYSTEM: zwei Beispiel-Ergänzungen** (Commit 7523785, feature/lektorat-grounding-examples → main FF).
Rein additiv in der Prompt-Konstante, kein Bestandstext geändert. (1) GROUNDING-REGEL: neuer Bullet
„Domänen-/Fächerlisten" — sinngemäße Deckung durch Quelllisten explizit (z. B. „Sprachen" als Lehrfach
deckt „sprachen mehrere Sprachen"). (2) SELBSTKONSISTENZ-PFLICHT: zweites Beispiel — Begründung mit
„sachgerecht"/„kein Handlungsbedarf"/„nicht falsch" erzwingt Silence, niemals PRÜFEN. Adressiert zwei
FPs aus dem fp_measurement-Lauf (Ritter S2 / Vulkan S3). py_compile OK. **Kontext:** FP/FN-Mess-Lauf
(3 Themen × S1–S3, 9 Artikel, 21 findings) gelaufen → `articles/fp_measurement/` + annotierbare
`findings_annotation.xlsx`; HTML-Viewer rendert V2-findings[] korrekt (verifiziert).

**Shape-A-Abnehmer auf V2-`findings[]` umgestellt** (Commit 20bec3f, feature/orphan-consumers → main FF).
`render_review_html.py:render_lektorat` und `generate_grounded.py:1843` lasen noch Shape A
(findings/summary mit status/auto_angewandt/vorschlag_offen/eskaliert) und lieferten seit der
findings[]-Einführung (fec90f5) Fehlausgaben (alles als ESKALATION, leere Belege bzw. `[…0A/0V/0E]`).
Beide auf verdikt-Branching + Felder beleg/problem/begruendung umgestellt: SILENT→v-AUTO,
KORRIGIERT→v-VORSCHLAG, PRÜFEN/EINBAU_FEHLGESCHLAGEN→v-ESKALATION; Zähler aus findings[]; lekt_note
neu `[LEKTORAT N:NS/NK/NP/NE]`. Rückwärtskompatibel (leeres findings[] → ""). py_compile beide OK.
Damit hängt kein Konsument mehr an Shape A.

**Strukturiertes `findings[]` im V2-pruefbericht** (Commit fec90f5, feature/findings-v2 → main FF).
`annotate_article_lektorat_v2` schreibt additiv eine `findings`-Liste (verdikt/claim_original/
korrektur_neu/beleg/problem/begruendung) parallel zu `text`/`n_silent`/`n_korrigiert`/`n_pruefen` —
Verdikte SILENT | KORRIGIERT | EINBAU_FEHLGESCHLAGEN | PRÜFEN. claim/korrektur als Display-Variante
(`_strip_render_markers`), leere Strings → null. Inline-Unittest (4-Fälle) grün; keine bestehenden
Konsumenten geändert. Erledigt den offenen Folgepunkt aus 2026-06-21 (Commit 5989ee6). Hinweis:
`n_pruefen` zählt weiterhin auch EINBAU_FEHLGESCHLAGEN-Zeilen (Bestandsverhalten); `findings[]` trennt sauber.

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
- **batch_run.py Legacy stilllegen**: ruft `COMPANION_PROMPT_TMPL.format(...)` mit veralteter Signatur
  (age_level/ages/appeal/excerpt/n_links/link_list, KEIN `lead`) → würde `KeyError: 'lead'` werfen.
  Produktion läuft über run_batch.py (thema+lead). batch_run.py ist toter Pfad — entfernen/archivieren.

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

age_floor-Gate Stage 2 · Bildbaustelle · Stage-3-Idempotenz
· Box-Sentiment-Feinschliff · Quiz/stimmt_das schema mismatch (Flutter)

---

Catalog: 4346 primary · 213 Leuchtturm · 563 sensibel · 58 exclude (XLSX) ·
App-Inhalt aktuell: klexikon.zim (Umstellung auf generierte Artikel ausstehend)
