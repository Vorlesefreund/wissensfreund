# Wissensfreund — STATUS
<!-- updated: 2026-06-18T13:34:54Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Abgeschlossen (2026-06-18) — Daten-Konsistenz-Audit + Exclude-Backstop

**Wortziel-Bug behoben.** ergiebigkeit_scores.json aus catalog_full.json neu gebaut:
134 → 4375 Einträge. XLSX == catalog_full für erg verifiziert (1 trivialer Diff: 9/11
erg_s1). Alte Datei in _alt/. Pipeline nutzt jetzt echte Scores statt Fallback-6.
Builder: build_ergiebigkeit_scores.py (Format aus Altdatei gespiegelt, bricht bei
unbekanntem Format ab).

**Exclude-Gate geprüft + gehärtet.** Befund: 58 XLSX-Excludes sind NICHT in
catalog_full (0 vorhanden) → per Omission unerreichbar (unbekanntes Thema → Skip).
Gate war damit einschichtig; zwei gedachte Backstops waren inert (Job-Builder prüfte
falsches Feld; eignung_verdicts.json hat kein exclude-Feld, nur age_floor+framing).
Fix: eignung_exclude.json (58 normalisierte Lemmata, aus XLSX) als Positiv-Liste;
eignung_for() und _build_catalog_jobs() prüfen sie jetzt → Laufzeit-Gate (Z.1515)
feuert wieder auf JEDEM Pfad. Verifiziert: napoleon→exclude, biene→include.
Builder: build_eignung_exclude.py.

**Schema-Drift bestätigt + entschärft.** Excludes waren in 3 Dateien unterschiedlich
markiert (XLSX eignung="exclude" / catalog_full droppt sie / eignung_verdicts.json
neues Schema exclude:true, Feld fehlt). Positiv-Liste vereinheitlicht den Check.

## Derived-File-Disziplin (NEU — einhalten)

catalog_review_master.xlsx = EINZIGE Wahrheitsquelle. Bei jeder XLSX-Änderung neu bauen:
- build_ergiebigkeit_scores.py → ergiebigkeit_scores.json
- build_eignung_exclude.py     → eignung_exclude.json
catalog_full.json ist abgeleitet (Excludes weggelassen, age_floor enthalten).

## Restlücken (niedrigprior)

- ~249 erg_s1-Lücken in XLSX UND catalog_full (gleicher Stand, kein Sync-Problem) → S1-Fallback.
- eignung_verdicts.json: 738 Einträge, nur age_floor+framing_note. exclude jetzt über
  _EXCLUDE_SET abgefangen; age_floor via catalog_full im Job-Builder verdrahtet.
- EIGNUNG_STRICT=False (Bulk-Default); "True vor Bulk" unrealistisch (3813 ohne Verdict).
- audit_*.py (Einmal-Diagnosen) im Repo-Root → im Aufräumschritt entfernen.

## Nächste Schritte (Reihenfolge)

1. Enge Datenfluss-Karte: welches Skript erzeugt welche Datei aus welcher Quelle;
   jede abgeleitete Datei aus XLSX reproduzierbar? (Fortsetzung des Audits)
2. Aufräumen: Spare-Clone, scrape_out, verwaiste _alt-Stände, audit_*-Einmalskripte.
3. PROJEKTDOKUMENT.md NACH dem Aufräumen neu generieren (nicht vorher — sonst Drift festgeschrieben).
4. KERN: Generierung + Lektorat (eigentlicher Engpass, Qualität noch nicht gut genug).
5. Danach Bilder, dann TTS.

## Offen aus Artikel-Review (nach dem Audit)

1. PRÜFEN braucht immer Korrekturvorschlag (A/B) — nicht umgesetzt.
2. Lektorat soll mehr auto-korrigieren statt PRÜFEN (Pest "goldene Säule Wien").
3. Innerartikel-Konsistenz: Fließtext vs. Box (Blauwal "größtes Tier je" vs Box).
4. Sprachliche Fehlbezüge ("dankbare Denkmäler", "Wärmestrahlung" als Licht).
5. Roter Faden / Wesentliches zuerst, bes. S1 (Photosynthese, Wikinger-Einstieg).
6. Lektorat-Gründlichkeit ungleich über Stufen (Drachenkopf nur in S3 gefangen).
7. EINBAU-BUG: Korrekturen zerstören manchmal Satzgrammatik (Wikinger S3) — technisch.
- Nächster Generierungstest: wieder 3 NEUE Themen (Overfitting-Check).

## Weiter offen (unverändert)

age_floor-Gate Stage 2 · Stage 4 TTS (tts_produce.py fehlt) · Bildbaustelle · Stage-3-Idempotenz
· Box-Sentiment-Feinschliff · Quiz/stimmt_das schema mismatch (Flutter)

---

Catalog: 4346 primary · 213 Leuchtturm · 563 sensibel · 58 exclude (XLSX)
