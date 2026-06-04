# Wissensfreund — STATUS
<!-- updated: 2026-06-04T12:28:55Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 4. Teil)

**Vollbild-Viewer — 3-Stufen-Doppeltipp-Zoom implementiert**
Branch `spike/photo-view-plus`, APK gebaut, Gerät-Install ausstehend (USB nicht verbunden).

### 3-Stufen-Zyklus
Basis → Stufe 1 (2.5×) → Max (covered×4) → Basis → …
- Liest `ctrl.scale` direkt → zustandslos, funktioniert nach jedem Pinch
- `_handleDoubleTap(index, tapLocalPos)`: 3 Schwellen (`minScale*1.05`, `minScale*2.625`)
- Zoom-in: animiert zur Tippposition (Fokalpunkt bleibt unter dem Finger)
- Zoom-out: animiert zu Basis, dann `ssCtrl.reset()` → scaleState=initial

### Animation
- `AnimationController _zoomAnimCtrl` (220ms, easeOut, Vsync via TickerProviderStateMixin)
- `_onZoomAnimTick()`: drives `ctrl.updateMultiple(scale, position)` auf jedem Frame
- PVs `_blindScaleListener` klemmt Position auto. auf gültige Range (kein extra Clamp nötig)
- `onScaleStart`: `_zoomAnimCtrl.stop()` → kein Konflikt mit Pinch
- `_onScaleEnd`: ebenfalls `_zoomAnimCtrl.stop()` vor Reset-Logik
- `_onPageChanged`: `_zoomAnimCtrl.stop()` beim Blättern

### Fokalpunkt-Formel
`p1 = tapLocalPos - center - (tapLocalPos - center - p0) * (s1/s0)`
Clamp: `halfX = max(0, (imgWidth * s1 - outerWidth) / 2)` — gleiche Formel wie PV cornersX.

---

## 🔴 Gerätetest erforderlich — S23 verbinden + APK installieren

```
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

Testmatrix:
```
[ ] 1. Doppeltipp: Basis → Stufe1 → Max → Basis → Stufe1 → … (beliebig oft)
[ ] 2. Fokalpunkt: Bild-Bereich unter Finger bleibt beim Zoom-in stehen
[ ] 3. Zoom-out (Stufe3→Basis): sauber auf Ausgangsgröße + Wischen direkt danach OK
[ ] 4. Erst Pinch zoomen, dann Doppeltipp → kein Einfrieren, sinnvolle Stufe
[ ] 5. Pinch greift beim ERSTEN Touch
[ ] 6. Panning frei, Seitennavigation zuverlässig
[ ] Hintergrund-Blur, Lautsprecher — keine Regressionen
```

---

## 🔴 Nach bestandenem Test
`spike/photo-view-plus` → `main` mergen, Branch löschen.

---

## 🟡 Zum Testen (ausstehend, niedrigere Prio)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu frühes Highlight)

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
