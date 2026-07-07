# Archiv: catalog_review.xlsx + catalog_review_audit.xlsx (07.07.2026)

Beide Dateien sind **generierte Review-Artefakte** aus einer früheren Katalog-Phase
und wurden von der Wahrheitsquelle **`catalog_review_master.xlsx`** (im Repo-Root)
abgelöst. Hier archiviert statt gelöscht, weil Teile davon unikat sind.

## Warum abgelöst
- `catalog_review.xlsx` (Sheet *Review*, 4550×18) → vollständig in der Master
  aufgegangen (Master hat dieselben 4550 Zeilen + zusätzliche Spalte `Kommentar`).
- Produktions-Skripte lesen ausschließlich `catalog_review_master.xlsx`
  (`build_eignung_exclude.py`, `build_ergiebigkeit_scores.py`, `catalog_merge.py`,
  `audit_*.py` u.a.). Diese beiden Dateien wurden **nur geschrieben**, nie als Input
  gelesen — und sind jederzeit regenerierbar:
  - `catalog_review.xlsx` ← `catalog_merge.py`
  - `catalog_review_audit.xlsx` ← `coverage_audit.py`

## Was hier NICHT in der Master steckt (Archivierungsgrund)
- `catalog_review.xlsx` › Sheet **Dubletten** (1097 Zeilen) — kein Master-Sheet.
- `catalog_review_audit.xlsx` › Sheet **Review** (4707×22) mit den Audit-Spalten
  `STATUS_NEU`, `QUELLE_AUDIT`, `MUTMASSLICHE_DUBLETTE`, `AEHNLICH_VORHANDEN`
  und 157 Zeilen mehr als die Master — die komplette Audit-Analyse ist unikat.

## Reaktivieren
Bei Bedarf einfach zurück in den Repo-Root kopieren, oder das jeweilige
Erzeuger-Skript erneut laufen lassen (regeneriert aus der aktuellen Master).
