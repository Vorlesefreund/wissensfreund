# Archiv: Katalog-Audit-Snapshots (07.07.2026)

Einmalige Analyse-Outputs aus der Katalog-Aufräumphase. Zweck erfüllt (die daraus
abgeleiteten echten Lücken sind als Audit-Gap-Themen in den Master eingepflegt), daher
archiviert statt im Root liegen zu lassen. Alle **regenerierbar** durch erneuten Lauf
des jeweiligen Erzeuger-Skripts.

| Datei | Erzeuger | Inhalt |
|---|---|---|
| `coverage_gaps_klexikon.json` | `coverage_audit.py` | Themen mit Klexikon-Deckungslücke |
| `coverage_gaps_llm.json` | `coverage_audit.py` | LLM-vorgeschlagene Themenlücken |
| `coverage_gaps_pflichtliste.json` | `coverage_audit.py` | Pflichtlisten-Abgleich |
| `catalog_review_delta_r2.xlsx` | `catalog_delta_r2.py` | nur die R2-Neuzugänge zur separaten Review |

**Nicht archiviert (aktiv in Produktion):** `eignung_verdicts.json` wird von
`generate_grounded.py` als Eignungs-Gate gelesen und bleibt im Root.

Reaktivieren: bei Bedarf zurück in den Repo-Root kopieren oder Erzeuger-Skript neu laufen
lassen (regeneriert aus dem aktuellen Katalog-/Master-Stand).
