# Wissensfreund — Artikel-Pipeline Briefing
## Für neue Chat-Session: JSON-Datenmodell + System-Prompt

---

## 1. KONTEXT

Wissensfreund ist eine Flutter-App (Android) als Kinderlexikon, basierend auf der Klexikon-ZIM-Datei.
Wir erweitern das Artikelrepertoire durch **eigene, KI-generierte Artikel auf Wikipedia-Basis**.

**Ziel dieser Session:** JSON-Datenmodell + System-Prompt für die automatische Artikel-Generierung.

---

## 2. ARTIKEL-GRUNDMUSTER (4 Typen)

| Muster | Themengebiete | Struktur |
|--------|--------------|----------|
| **Lebewesen** | Tiere, Pflanzen | Körperbau → Verhalten → Lebensraum → Mensch & Natur |
| **Orte & Geografie** | Länder, Städte, Landschaften | Lage → Natur → Menschen & Kultur → Wirtschaft & Probleme |
| **Geschichte & Personen** | Epochen, Persönlichkeiten | Wer/Wann → Leben/Alltag → Werk/Bedeutung → Mythos vs. Realität |
| **Technik & Wissenschaft** | Erfindungen, Naturphänomene | Was ist es → Wie funktioniert es → Geschichte → Zukunft & Ethik |

---

## 3. ALTERSGRUPPEN (3 Stufen)

### Stufe 1 — 4–6 Jahre
- Sehr kurze Sätze, direkte Ansprache ("Stell dir vor...")
- Alltagsvergleiche aus der Kinderwelt
- Keine Tabellen, keine komplexen Fachbegriffe
- Emotional, spielerisch, viel Staunen
- Richtwert: ~200 Wörter Fließtext

### Stufe 2 — 7–9 Jahre
- Einleitungssatz der das Thema einordnet (z.B. "Elefanten sind die größten Landtiere der Welt")
- Erste Fachbegriffe mit sofortiger Erklärung
- Tabellen erlaubt (einfach)
- Erste kritische Abschnitte möglich
- Etwas verspielter Ton, direkte Ansprache
- Richtwert: ~400 Wörter Fließtext

### Stufe 3 — 10–12 Jahre
- Fachlich korrekt, aber mit Alltagsvergleichen und lockerem Ton
- Kurze Sätze, kein Lehrbuch-Stil
- Tabellen mit mehr Spalten erlaubt
- Kritische Abschnitte, Kontroversen, ethische Fragen
- "Stimmt das?"-Boxen, Fakt-Boxen, Warn-Boxen
- Richtwert: ~700 Wörter Fließtext

---

## 4. ARTIKEL-ELEMENTE (alle Stufen)

### Pflicht-Elemente
- **Titel** + Emoji + Untertitel
- **Abschnitte** mit Überschrift + Fließtext (Sätze einzeln markiert für TTS)
- **Bilder** pro Abschnitt zugeordnet (Index 0–5, bis zu 6 Bilder)
- **Quiz** am Ende (3 Fragen Stufe 1–2, 4–5 Fragen Stufe 3)
- **Themenfarbe** (CSS-Farbwert passend zum Thema)

### Optionale Elemente (je nach Stufe und Thema)
- **Wow-Box** — zentriert, animiert einblendend, für alle Stufen
- **Fakt-Box** — blau, ab Stufe 2
- **Stimmt das?-Box** — lila, ab Stufe 2 (auto-reveal nach 3,5s), Stufe 3 (manuell)
- **Warn-Box** — orange, für kritische Inhalte
- **Tabelle** — ab Stufe 2
- **Sound-Marker** — Platzhalter für Audio-Einbindung (z.B. Musikbeispiele)

---

## 5. QUIZ-REGELN

- Immer **A / B / C** voranstellen (für Spracheingabe/-ausgabe)
- 3 Antwortoptionen pro Frage
- Stufe 1: bildbasiert möglich (im JSON: `image_quiz: true`)
- Stufe 2–3: Textantworten
- Fragen testen Textverständnis, nicht Auswendiglernen

---

## 6. "STIMMT DAS?"-REGELN (wichtig!)

- Greift ein **Thema des Artikels** auf
- Ist **nicht direkt aus dem Text beantwortbar** — erfordert kritisches Denken
- Die Antwort ist differenziert, nicht simpel Ja/Nein
- Stufe 2: vereinfacht, kürzere Auflösung, auto-reveal nach 3,5s beim Vorlesen
- Stufe 3: anspruchsvoller, manuell aufklappbar
- **Kein Thema darf nur in der "Stimmt das?"-Frage auftauchen** — es muss im Artikel behandelt sein

---

## 7. BILD-KONZEPT

- **1 Bild oben** (Hero-Bild, wechselt mit Abschnitt)
- **Thumbnail-Strip unten** (6 Bilder, wischbar)
- Bilder kommen aus Wikipedia/Wikimedia Commons
- Lizenz: CC BY, CC BY-SA, CC0 oder Public Domain
- Jeder Satz hat einen `img_index` (0–5) → zugehöriges Bild
- Bild-Beschreibung + Lizenzangabe im JSON

---

## 8. THEMENFARBEN

Jeder Artikel hat eine eigene Primärfarbe passend zum Thema:
- Tiere/Natur → Grün (`#4caf50`)
- Brasilien/Tropen → Tropengrün/Gelb (`#7cb342` / `#f9a825`)
- Raumfahrt → Blau/Dunkel (`#5c9eff`)
- Geschichte/Personen → Goldbraun (`#d4a017`)
- Weitere nach Bedarf definieren

---

## 9. TEXTREGEL FÜR DIE GENERIERUNG (System-Prompt Grundlagen)

### Inhalt
- Ausschließlich aus Wikipedia-Input — kein Fremdwissen, keine Halluzinationen
- Wenn eine Information nicht im Wikipedia-Text steht, wird sie weggelassen
- Vergleiche und Metaphern müssen aus dem Wikipedia-Text ableitbar oder offensichtlich korrekt sein

### Sprache & Grammatik
- Korrekte deutsche Grammatik und Deklination (Artikel, Kasus)
- Keine Schachtelsätze
- Kurze, klare Sätze — auch in Stufe 3
- Mehr Alltagsvergleiche, weniger Fachsprache (besonders Stufe 3)
- Positiv formulieren, aktive Verben bevorzugen

### Häufige Fehler vermeiden
- Artikel-Fehler: "die Schwerkraft" nicht "den Schwerkraft", "der Karneval" nicht "das Karneval"
- Verben: "brannten" nicht "brennten", "sie saßen" nicht "sie sitzten"
- Satzstruktur: Kein Infinitiv ohne Subjekt ("Menschen auf dem Mars zu besiedeln" → umformulieren)

---

## 10. 3 ANSICHTSMODI

Jeder Artikel erscheint in 3 Modi, die der Nutzer umschalten kann:

| Modus | Beschreibung |
|-------|-------------|
| **A — Lesen** | Fließtext mit Satz-Highlighting beim Vorlesen |
| **B — Satz** | Ein Satz groß im Fokus, Fortschrittsanzeige |
| **C — Galerie** | Bilder im Vordergrund, Text darunter |

---

## 11. NAVIGATION & THEMENBAUM (noch zu entwickeln)

Geplante Hierarchie für App-Kachel-Navigation:
- Ebene 1: Themengebiet (z.B. "Tiere")
- Ebene 2: Unterthema (z.B. "Landtiere")
- Ebene 3: Artikel (z.B. "Elefanten")

Die Kategorien-Whitelist für die Wikipedia-Pipeline ist noch zu definieren.

---

## 12. PRODUKTIONS-ZIEL

- ~10.000 Artikel Stufe 3
- ~5.000–7.000 Artikel Stufe 1 und 2
- 100–200 Artikel pro Woche
- Vollautomatische Pipeline (GitHub Actions → Claude API → R2)
- Review nur für auffällige Artikel

---

## 13. REFERENZ-ARTIKEL (bereits erstellt als HTML)

Fertige Beispiel-Artikel für alle Muster:
- **Elefanten** (Lebewesen) — `elefanten_final.html`
- **Ritter im Mittelalter** (Geschichte) — `ritter_artikel.html`
- **Raketen & Raumfahrt** (Technik) — `raketen_artikel.html`
- **Brasilien** (Geografie) — `brasilien_artikel.html`
- **Ludwig van Beethoven** (Personen) — `beethoven_artikel.html`

---

## 14. OFFENE AUFGABEN FÜR DIESE SESSION

1. **JSON-Datenmodell** definieren (alle Felder eines Artikels)
2. **System-Prompt** für Claude-API-Generierung entwickeln
3. **Kategorien-Whitelist** für Wikipedia-Pipeline skizzieren
4. **Themenbaum** für App-Navigation entwerfen

