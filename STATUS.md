# Wissensfreund — STATUS
<!-- updated: 2026-06-02T14:21:26Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-02 — TTS-Hang + Zentrierung Root Cause Fix)

### Bugfixes dieser Session

- **TTS "hängt" nach Scrollen / Zentrierung funktioniert nicht** (Root Cause: `_lastActiveIdx` premature update):
  - `_lastActiveIdx = scrollIdx` wurde im Consumer-Builder gesetzt, BEVOR `_smartScrollTo` die Guards (`_userScrolling`) prüfte
  - → Wenn blockiert: `_lastActiveIdx` schon auf neuen Wert gesetzt → nächster Rebuild sieht keine Änderung → Scroll feuert nie
  - → User sieht TTS "hängt": TTS läuft, aber Screen scrollt nicht mit → Satz off-screen
  - → Re-Read: User scrollt um TTS zu finden → neuer Seek → springt zurück
  - **Fix**: `_lastActiveIdx = idx` erst INNERHALB von `_smartScrollTo()` setzen (nach Guard-Check)
  - **Fix**: `_lastBoxKey = boxKey` / `_lastActiveIdx = rawIdx` erst INNERHALB von `_smartScrollToBox()` setzen
  - `_smartScrollToBox` Signatur geändert: jetzt `(GlobalKey key, String? boxKey, int rawIdx)`
  - Consumer-Builder: Redundante Updates entfernt, Consumer retried nun korrekt bis Scroll tatsächlich feuert
  - Gilt für Mode A und Mode B

Geänderte Dateien:
- `lib/screens/article_screen.dart`:
  - Mode A `_smartScrollTo`: `_lastActiveIdx = idx` vor `_scrollPending = true`
  - Mode A Consumer: `_lastActiveIdx = activeIdx` entfernt
  - Mode B `_smartScrollTo`: `_lastActiveIdx = idx` vor `_scrollPending = true`
  - Mode B `_smartScrollToBox`: neue Parameter `boxKey, rawIdx`; Updates darin
  - Mode B Consumer: `_lastActiveIdx`/`_lastBoxKey` Updates entfernt, Aufruf angepasst

APK gebaut + installiert ✅ (Commit noch ausstehend)

---

## 🟡 Zum Testen (in dieser Reihenfolge)

1. Artikel öffnen, TTS starten → vorherige Sätze/Boxen in Modus B scrollen
2. Aktiver Satz soll sich automatisch zentrieren, wenn TTS weiterschreitet
3. Nach Scroll: Satz soll nach 3s wieder zentriert werden (kein TTS-Hang)
4. Box nach Satz: TTS liest weiter (kein Hänger)
5. Gleicher Absatz darf nicht doppelt vorgelesen werden

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** (alle Bugfixes aus letzten zwei Sessions)
- **Selbst produzierte Artikel** (neue JSON-Artikel mit echten Inhalten)

### Mittel (zurückgestellt)
- **Quiz-Checkpoint löschen + Run neu starten**
- **Bilder-Patch** (`patch_article_images_v1.py`)
- **Links in JSON-Artikeln**
- **Gemini-Integration**
- **Topic-Tree Kachel-Navigation**

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1

- Gallery-Artikel (111 Artikel, 540 Bilder)
- Audio-Pipeline
