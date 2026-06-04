# Wissensfreund — STATUS
<!-- updated: 2026-06-04T13:06:17Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 6. Teil)

**Vollbild-Viewer — Doppeltipp Scale-Werte + onScaleStart-Bug gefixt**
Branch `spike/photo-view-plus`, auf S23 installiert.

### Root Causes (beide gefixt)

**Bug 1: onScaleStart stoppte Animation beim zweiten Tap**
`onScaleStart: _zoomAnimCtrl.stop()` feuert für JEDEN Pointer-Down (auch einfachen Tap).
Zweiter Tap der Doppel-Geste → Animation startet → onScaleStart stoppt sie sofort.
Fix: `if (_activePointers > 1) _zoomAnimCtrl.stop()` — nur bei echtem Pinch stoppen.
`_onPointerDown` (Multi-Touch-Branch) stoppt ebenfalls.

**Bug 2: Skalenwerte rechneten mit falschen Bezugswerten**
`_initialScaleFor` und `_computeMaxScale` nutzten `MediaQuery.sizeOf(context)` statt der
echten Layout-Größe, die PV intern verwendet. Fix: `LayoutBuilder` um `Listener`+Gallery →
`_outerSize = constraints.biggest` (identisch mit PVs scaleBoundaries.outerSize).
Alle Scale-Berechnungen (baseScale, maxScale, Focal-Point-Clamp) verwenden nun `_outerSize`.

### Logging noch aktiv
```
adb logcat | grep WISS
```
Erwartet: `scale≈0.2xx` bei Basis, `scale≈0.5xx` bei Stufe1, `scale≈3.xx` bei Max.
Branch immer korrekt (`→Stufe1`, `→Max`, `→Basis`).

---

## 🔴 Gerätetest — S23

```
[ ] 1. Basis → Stufe1 → Max → Basis → Stufe1 → … (beliebig oft, deutliche Stufen)
[ ] 2. Fokalpunkt: Bildbereich unter Finger bleibt beim Zoom-in stehen
[ ] 3. Pinch zoomen → dann Doppeltipp → sinnvolle Stufe, kein Einfrieren
[ ] 4. Wischen direkt nach Zoom-out (Basis) funktioniert
[ ] 5. Panning frei, Seitennavigation zuverlässig
```

---

## 🔴 Nach bestandenem Test
- `debugPrint`-Zeilen entfernen, neu committen
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
