# Wissensfreund — STATUS
<!-- updated: 2026-06-19T06:25:53Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## Abgeschlossen (2026-06-18)

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
