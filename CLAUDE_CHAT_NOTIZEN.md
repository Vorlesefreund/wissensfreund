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
