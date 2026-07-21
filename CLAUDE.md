# Wissensfreund App — Claude Code Anweisungen

## GRUNDREGEL QUELLENPRÜFUNG (nicht verhandelbar)
Vor jedem Faktencheck den vollständigen echten Wikipedia-Quelltext beschaffen und ausschließlich daran prüfen. Kein Faktenurteil ohne wörtliches Belegzitat. "Nicht gefunden" ≠ "falsch". Lange Artikel schneiden beim Abruf ab — den GANZEN Text sichern. Immer gegen den Quelltext-Snapshot der Generierungszeit prüfen, nie gegen ein später nachgeladenes Exemplar. Ohne Volltext keinen Check vortäuschen. Details: QUELLEN_GRUNDREGEL.md.

## EISERNE REGEL (App-Kernprinzip)
KI darf NIEMALS aus Trainingswissen antworten.
Nur aus geladenem Wikipedia-Artikeltext. Kein Ausnahmefall. Kein Fallback.

## ARTIKEL-LOGIK
Relevanz: Titel +3P | Erster Absatz +2P | Fließtext +1P | mehrere Begriffe → multiplizieren

"Was ist/sind/Erzähl/Wer ist" → ganzen Artikel vorlesen (~70 %)
"Warum/Wie/Wann/Wo/Stimmt es" → nur relevante Stelle per KI aus Artikeltext
Folgefrage → direkt aus bereits geladenem Artikeltext antworten
Vergleich ("größer als") → beide Artikel laden, KI antwortet nur daraus
Kein Treffer → "Das können Mama oder Papa erklären!" — kein KI-Fallback

## BUILD & DEPLOY (Bash, nicht PowerShell)
flutter build apk --debug
adb install -r build/app/outputs/flutter-apk/app-debug.apk

## Arbeitsverzeichnis
Zu Session-Beginn das aktuelle Arbeitsverzeichnis ausgeben. Es MUSS
C:\Users\Andreas\wissensfreund_repo sein — falls nicht, dorthin wechseln und bestätigen.

## SESSION-START (Reihenfolge einhalten)
1. CLAUDE.md lesen
2. STATUS.md lesen — aktuellen Stand kennen
   Pfad (einzige Quelle der Wahrheit): ./STATUS.md

## SESSION-ENDE (Pflicht, keine Ausnahme)
1. STATUS.md neu schreiben — aktueller Stand, max. 60 Zeilen
   Format: Zuletzt abgeschlossen / Gerade in Arbeit / Offen nach Priorität
   Zeile 2: <!-- updated: YYYY-MM-DDTHH:MM:SSZ --> aktualisieren
   Bash: date -u +"%Y-%m-%dT%H:%M:%SZ"
2. Bei neuen Erkenntnissen: WISSEN_*.md ergänzen (nicht überschreiben)
   - App/Flutter → WISSEN_APP_ARCHITEKTUR.md
   - Artikel/Pipeline → WISSEN_ARTIKEL_PIPELINE.md
   - Bilder → WISSEN_BILDER.md
3. Committen + pushen:
   git add STATUS.md WISSEN_*.md [geänderte Dateien]
   git commit -m "STATUS.md [Datum] [Beschreibung]"
   git push origin main

## BRANCHES
Standardbranch: main. Branch nur für riskante Experimente, sofort nach Test zurück nach main.

## STATUS.md TIMESTAMP
Zeile 2: <!-- updated: 2026-06-01T00:00:00Z --> — bei JEDEM Schreiben aktualisieren.
Bash: date -u +"%Y-%m-%dT%H:%M:%SZ"

## Diff-/Text-Review über Datei (Terminal-Truncation vermeiden)

Die Terminal-Ausgabe wird zu "(+N lines, ctrl+o to expand)" gekürzt, bevor
sie Claude Chat (über Andreas' Copy-Paste) erreicht. Lange Diffs oder Texte
kommen dadurch abgeschnitten an. Deshalb gilt:

- Immer wenn Claude Chat einen vollständigen Diff oder einen langen Text
  (Prompt-Block, Datei-Ausschnitt >~20 Zeilen, ganzer geänderter Abschnitt)
  zur Prüfung sehen soll: NICHT in die Terminal-Antwort schreiben und NICHT
  in sed/fold-Häppchen zerlegen, sondern in eine Datei schreiben:
      git diff > /c/Users/Andreas/Desktop/_review_diff.txt
  (bzw. git diff --staged, oder für Datei-Ausschnitte den Text direkt in
  diese Datei schreiben). Danach den Pfad nennen bzw. present_files nutzen.
- Andreas lädt diese eine Datei hoch; Claude Chat liest den ungekürzten
  Inhalt und gibt frei. Eine Datei, ein Upload, kein Hin-und-Her.
- Die Datei _review_diff.txt ist ein Wegwerf-Reviewartefakt: vor jedem neuen
  Review überschreiben, nicht committen (liegt auf dem Desktop, außerhalb des
  Repos — kein .gitignore nötig).
- Kurze Bestätigungen (Commit-Hash, "nur Datei X gestaged", PASS/FAIL-Bilanz)
  dürfen weiterhin direkt in die Terminal-Antwort — die Datei-Methode gilt nur
  für lange Diffs/Texte, die sonst getrunct würden.

## TOKEN OPTIMIZATION RULES
- Niemals ganzen Code ungefragt ausgeben — nur relevante Diffs/Zeilen
- Aufgaben bündeln: Code + Tests + Error-Handling in einer Nachricht
- Read-Tool nur gezielt einsetzen (offset + limit nutzen)
- Keine Wiederholung bekannter Codeblöcke im Output

## COMPACTION & HANDOVER RULES
Summary bewahrt NUR:
1. Aktuelle Architekturlogik
2. Exakter Zustand offener To-Dos
3. Globale Schnittstellen / Typdefinitionen
