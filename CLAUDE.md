# Wissensfreund — CI/Scripts-Repo

## ZWECK
Python-Skripte (scripts/) + GitHub Actions (.github/workflows/) für die monatliche
Medien-Pipeline: ZIM → Bilder (3 Tiers, Pillow-Resize) + Audio → Cloudflare R2.

## EISERNE REGEL (App-Kernprinzip)
KI darf NIEMALS aus Trainingswissen antworten.
Nur aus geladenem Klexikon-Artikeltext. Kein Ausnahmefall. Kein Fallback.

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
gh workflow run update_image_licenses.yml

## SESSION-START (Reihenfolge einhalten)
1. CLAUDE.md lesen
2. CLAUDE_CHAT_NOTIZEN.md lesen — offene Aufträge prüfen und umsetzen
3. STATUS.md lesen — aktuellen Stand kennen

## STATUS.md TIMESTAMP
Zeile 2: <!-- updated: 2026-06-01T00:00:00Z --> — bei JEDEM Schreiben aktualisieren.
Bash: date -u +"%Y-%m-%dT%H:%M:%SZ"
STATUS.md ist Kommunikationskanal zu Claude Chat (nicht CHANGES.md — wird gecacht).

## TOKEN OPTIMIZATION RULES (Claude Code & Claude Chat)
- Niemals ganzen Code ungefragt ausgeben — nur relevante Diffs/Zeilen ändern
- Aufgaben bündeln: Code + Tests + Error-Handling in einer Nachricht fordern
- Read-Tool nur gezielt einsetzen (offset + limit nutzen)
- Keine Wiederholung bekannter Codeblöcke im Output

## COMPACTION & HANDOVER RULES
- Bei /compact (Claude Code) oder Handover-Briefing (Claude Chat):
  Alte Terminal-Logs und gelöschten Code herausfiltern
- Summary bewahrt NUR:
  1. Aktuelle Architekturlogik
  2. Exakter Zustand offener To-Dos
  3. Globale Schnittstellen / Typdefinitionen

## WISSENSDOKUMENTE & SESSION-ABSCHLUSS

Am Ende JEDER Session (Pflicht, keine Ausnahme):
1. STATUS.md vollständig neu schreiben — nur aktueller Stand, max. 60 Zeilen
   Format: Zuletzt abgeschlossen / Gerade in Arbeit / Offen nach Priorität
2. Wenn neue Erkenntnisse, Entscheidungen oder verworfene Ansätze entstanden:
   entsprechende WISSEN_*.md ergänzen (nicht überschreiben, nur ergänzen)
   - Bild-Themen → WISSEN_BILDER.md
   - Artikel/Pipeline-Themen → WISSEN_ARTIKEL_PIPELINE.md
   - App/Flutter-Themen → WISSEN_APP_ARCHITEKTUR.md
3. Alle 4 Dateien committen:
   git add STATUS.md WISSEN_*.md CLAUDE_CHAT_NOTIZEN.md [geänderte Dart/Python-Dateien]
   git commit -m "STATUS.md [Datum] [Beschreibung]"
   git push origin main

BEIM SESSION-START (nach CLAUDE.md):
- STATUS.md lesen (Pflicht)
- Relevante WISSEN_*.md nur lesen wenn das Thema der Session es erfordert
- CLAUDE_CHAT_NOTIZEN.md lesen (offene Aufträge prüfen)
