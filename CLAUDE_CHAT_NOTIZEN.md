# CLAUDE_CHAT_NOTIZEN.md

Kommunikationskanal: Claude Chat → Claude Code

Claude Code liest diese Datei **am Session-Start vor allem anderen** (nach CLAUDE.md).
Offene Aufträge sofort umsetzen. Erledigte Einträge mit [x] markieren + Datum ergänzen, nicht löschen.

---

## Format

```
---
## [Datum] [Thema]

**Entscheidung / Auftrag:**
Was Claude Code wissen oder umsetzen soll.

**Priorität:** hoch / mittel / niedrig

**Erledigt:** [ ] — oder: [x] Umgesetzt am [Datum]
---
```

---

---
## 2026-05-21 Offene Aufgaben aus Claude Chat Session

**Entscheidung / Auftrag:**
Folgende Punkte wurden heute besprochen und sind noch offen:

1. Sound-Thumbnails & Wiedergabe (🎵)
   - Sound-Dateien in Thumbnail-Leiste neben Bildern anzeigen
   - Notenschlüssel-Icon als Erkennungszeichen
   - Pulsier-Animation beim Abspielen
   - Erklärtext als Overlay, identisches Unterbrechungsverhalten wie bei Bildern
   - Kein Vollbild für Audio

2. Immersive Mode + neues Button-Layout
   - Immersive Mode nur im Artikel-Screen und Vollbild
   - Neues Button-Layout: [←] [🎤] [⏸] während Vorlesen
   - Mikrofon unterbricht Professor, merkt Position, öffnet STT
   - Zurück-Button kehrt zu Home zurück
   - Pause/Play rechts

3. Missing images für Thumbnails 5+ (URL-decode-Problem in getImageBytes)
   - Aus CHANGES.md: "vermutlich URL-decode-Problem"
   - Bitte fixen

**Priorität:** 3 = hoch, 1+2 = mittel

**Erledigt:**
- [x] Punkt 3: Fehlende Thumbnails 5+ — umgesetzt am 2026-05-22 (commit 94da0d1: robust multi-variant findByFilename)
- [ ] Punkt 1: Sound-Thumbnails — Audio-Infrastruktur fertig; wartet auf Ergebnis des Audio-Pipeline-Runs (GH Actions, 1. Juni)
- [x] Punkt 2: Immersive Mode + Button-Layout — umgesetzt am 2026-05-22 (StatefulWidget ArticleScreen, _ArticleControls, interruptAndStartListening())
---

---
## 2026-05-25 Frage-Typ-Erkennung & Gemini-Logik

**Entscheidung / Auftrag:**
Für die spätere Gemini-Integration folgende Logik
implementieren — das ist eine zentrale Design-Entscheidung:

FRAGE-TYP-ERKENNUNG (5 Typen):

1. Themen-Frage
   Erkennung: beginnt mit "Was ist", "Was sind",
   "Erzähl mir", "Wer ist", "Was macht"
   Reaktion: Artikel vorlesen — KEIN Gemini
   Verfügbar: Free + Premium

2. Warum/Wie-Frage
   Erkennung: beginnt mit "Warum", "Wie", "Wann",
   "Wo", "Wieso", "Weshalb"
   Reaktion: Artikel laden, Gemini extrahiert
   relevante Textstelle, Professor spricht Antwort
   Verfügbar: nur Premium

3. Vergleichsfrage ← WICHTIG, kommt sehr oft!
   Erkennung: zwei erkannte Artikel-Begriffe +
   Vergleichswort (größer, kleiner, schneller,
   schwerer, stärker, älter, länger, gefährlicher etc.)
   ODER "oder", "versus", "verglichen mit"
   Beispiel: "Was ist größer, ein Elefant oder ein Wal?"
   Reaktion: BEIDE Artikel laden, Gemini vergleicht
   aus beiden Artikeltexten, Professor spricht Antwort
   Verfügbar: nur Premium

4. Folgefrage (während oder nach Vorlesen)
   Erkennung: Artikeltext bereits geladen +
   neue Frage des Kindes
   Reaktion: Gemini antwortet aus bereits geladenem
   Artikelkontext — kein neuer Download nötig
   Verfügbar: nur Premium

5. Alles andere / unklar → IM ZWEIFEL KI
   Reaktion: Gemini versucht mit verfügbarem
   Artikelkontext zu helfen
   Wenn kein Artikel gefunden: Eltern-Verweis
   Verfügbar: nur Premium

EISERNE REGEL (nie brechen):
Gemini antwortet NIE aus eigenem Trainingswissen.
Immer nur aus geladenem Klexikon-Artikeltext.
Kein Artikel + zu komplex = Eltern-Verweis,
auch bei Premium.

FREE vs. PREMIUM:
- Free: nur Typ 1 (Artikel vorlesen)
- Premium: alle 5 Typen

_detectQueryType() ist bereits vorhanden aber nicht
verdrahtet — bei Gemini-Integration aktivieren und
um Typ 3 (Vergleichsfrage) und Typ 5 (Fallback)
erweitern.

**Priorität:** hoch — vor Gemini-Integration umsetzen

**Erledigt:** [x] Umgesetzt am 2026-05-25 (nacht) — _detectQueryType auf 5 Typen erweitert, _processQuery verdrahtet, _handleGeminiPlaceholder implementiert, Weiterhören-Feature komplett
---

---
## 2026-05-26 Offene Prompts — bereit zur Umsetzung

**Auftrag 1 — Interne Links + Navigation (KOMPLETT)**
Folgende Punkte implementieren:

1. Links aus Klexikon-HTML extrahieren (ZimReader)
   Nur interne Links, keine externen URLs
   In SQLite cachen: article_links Tabelle

2. Tippbare Links nur in Modus A (nicht B/C,
   nicht Mini-Klexikon)
   RichText mit Akzentfarbe + unterstrichen

3. Link-Tap-Logik:
   Professor liest Satz zu Ende → fragt
   "Soll ich mehr über [Begriff] erzählen?"
   → Ja: Artikel wechseln, Position in Stack
   → Nein/nichts: nach 5 Sek weiterlesen

4. Zwei-Ebenen Zurück-Stack (max. 2 Einträge)
   Stack speichert Artikel + Position

5. Nach Artikel-Ende — je nach Stack:
   Stack leer:
   "Was möchtest du als nächstes hören?"
   → Mikrofon nach 2 Sek automatisch

   Stack 1 Eintrag (z.B. Savanne):
   "Soll ich mit der Savanne weitermachen
    oder möchtest du etwas anderes hören?"
   → Kind nennt Artikel oder neues Thema
   → nichts: nach 5 Sek Mikrofon öffnet sich

   Stack 2 Einträge (z.B. Savanne + Afrika):
   "Soll ich mit der Savanne, mit Afrika
    weitermachen oder etwas anderes erzählen?"
   → Kind nennt Artikel oder neues Thema
   → nichts: nach 5 Sek Mikrofon öffnet sich

6. Quellübergreifende Link-Auflösung:
   Zuerst eigene Artikel suchen, dann ZIM

7. Mini-Klexikon (3-5 Jahre): KEINE Links

**Auftrag 2 — Bildqualität je Stufe (Flutter-App)**
Flutter-App Bildanzeige je nach Freemium-Stufe:
- Free: 300px (thumb) aus ZIM/image_thumb.zip
- Plus+Premium ohne Download: 300px lokal,
  1200px on-demand bei WLAN (Cache 500 MB LRU)
- Plus+Premium mit Download: 600px lokal,
  1200px on-demand bei WLAN (Cache 500 MB LRU)
Upgrade-Hinweis im Vollbild für Free-Nutzer:
"Schärfere Bilder mit Wissensfreund Plus"

**Priorität:** Auftrag 1 zuerst, dann Auftrag 2

**Erledigt:** [ ]
---
