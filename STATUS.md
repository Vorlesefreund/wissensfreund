# Wissensfreund — STATUS
<!-- updated: 2026-06-04T13:39:04Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 7. Teil)

**Vollbild-Viewer — Endwerte Doppeltipp-Animation exakt**
Branch `spike/photo-view-plus`, auf S23 installiert.

### P1: Basis-Schritt ohne Endsprung

**Root Cause**: `ssCtrl.reset()` in `_onZoomAnimStatus` setzte scaleState = initial via
normalen Setter → notifyListeners() → `_blindScaleStateListener` (ignorable) → 
`animateOnScaleStateUpdate(unserEndwert, PVsMinScale)` → sichtbarer Endsprung.

**Fix**: `ssCtrl.setInvisibly(PhotoViewScaleState.initial)` statt `reset()` →
nur regular listeners → `_blindScaleStateListener` NOT triggered → kein Endsprung.
Plus: `ctrl.updateMultiple(minScale, Offset.zero)` vor setInvisibly → exakter Finalwert.

### P2: Max exakt erreichen

**Fix**: In `_onZoomAnimStatus` (non-toBase): `ctrl.updateMultiple(scale: _zoomAnimToScale, ...)`
→ Floating-Point-sicherer finaler Snap auf exakten Zielwert.
Erweitertes Logging: `WISS DT` zeigt jetzt outer×img×base×max; `WISS anim done` zeigt
scale vs. target nach Abschluss.

### Logging (zum Verifizieren, bis Test bestätigt)
```
adb logcat | grep WISS
```

---

## 🔴 Gerätetest — S23

```
[ ] 1. Basis → Stufe1 → Max → Basis → … mehrfach: VOLLE Stufen, kein "fast"
[ ] 2. Max → Basis: EXAKT Ausgangsgröße, Wischen direkt danach OK
[ ] 3. Log: WISS anim done scale=X.XXXX target=X.XXXX → beide gleich
[ ] 4. Pinch → Doppeltipp → sinnvolle Reaktion
[ ] 5. Fokalpunkt: Bildbereich unter Finger bleibt stehen
```

---

## 🔴 Nach bestandenem Test
- `debugPrint`-Zeilen entfernen
- `spike/photo-view-plus` → `main` mergen, Branch löschen

---

## 🟡 Ausstehend (niedrigere Prio)
- Mode B Lupe: Bold entfernen + `_ttsCursor` erst im progressHandler updaten

---

## 🔴 Offene To-Dos

### Mittel
- Selbst produzierte Artikel, Quiz-Checkpoint + Run neu
- Bilder-Patch (patch_article_images_v1.py) nach Quiz-Fertigstellung

### Niedrig
- Epoch-Guard TTS-Seek | Mode-B-ZIM-\n-Loch | Links/Gemini/Topic-Tree
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
