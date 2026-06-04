# Wissensfreund — STATUS
<!-- updated: 2026-06-04T12:48:05Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 5. Teil)

**Vollbild-Viewer — Doppeltipp-Erkennung auf Listener umgestellt**
Branch `spike/photo-view-plus`, auf S23 installiert.

### Root Cause (Diagnose)
PVs `onTapDown`-Callback feuert im Pan-Modus (gezoomt) NICHT zuverlässig.
Im Ruhezustand klappt es (Basis→Stufe1 funktioniert), nach Zoom-in wird `onTapDown`
von PVs Gesture-Routing nicht mehr durchgeleitet.

### Fix
`Listener` (Raw-Pointer-Events) außen um `PhotoViewGallery`:
- `onPointerDown`: feuert IMMER, zustandsunabhängig (Basis, Stufe1, Max, Pinch)
- `_activePointers`-Zähler: 2. Finger invalidiert Doppeltipp-Tracking → kein Pinch-Fehlalarm
- `_onPointerUp` / `_onPointerCancel`: dekrementieren Zähler
- `_onPageChanged`: `_lastTapDownTime = null` → kein Fehlschlag beim Blättern
- `onTapDown` aus pageOptions entfernt (nicht mehr gebraucht)

### Logging (zum Verifizieren, bleibt bis Test bestätigt)
```
adb logcat | grep WISS
```
Zeigt: `WISS ptr↓ idx=0 scale=0.204 zoomed=false`
Dann: `WISS DT fired idx=0 scale=0.204 min=0.204 →Stufe1`

---

## 🔴 Gerätetest — S23

```
[ ] 1. Basis → Stufe1 → Max → Basis → Stufe1 → … (beliebig oft, kein Hängen)
[ ] 2. Fokalpunkt: Bildbereich unter Finger bleibt beim Zoom-in stehen
[ ] 3. Pinch zoomen → dann Doppeltipp → sinnvolle Stufe (kein Einfrieren)
[ ] 4. Wischen direkt nach Zoom-out (Basis) funktioniert
[ ] 5. Panning frei, Seitennavigation zuverlässig
[ ] Logging bestätigt: ptr↓ UND DT fired auch wenn zoomed=true
```

---

## 🔴 Nach bestandenem Test
- debugPrint-Zeilen entfernen, neu committen
- `spike/photo-view-plus` → `main` mergen, Branch löschen

---

## 🟡 Zum Testen (niedrigere Prio)
- Mode B Lupe: Bold entfernen + `_ttsCursor` erst im progressHandler updaten

---

## 🔴 Offene To-Dos (nach Priorität)

### Mittel
- **Selbst produzierte Artikel**, **Quiz-Checkpoint + Run neu**
- **Bilder-Patch** (patch_article_images_v1.py) nach Quiz-Fertigstellung

### Niedrig
- Epoch-Guard TTS-Seek | Mode-B-ZIM-\n-Loch
- Links/Gemini-Integration/Topic-Tree
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
