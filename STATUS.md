# Wissensfreund — STATUS
<!-- updated: 2026-06-04T14:04:13Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen (Session 2026-06-04, 8. Teil)

**Vollbild-Viewer — Erratischer Doppeltipp: Root Cause aus WISS-Logs diagnostiziert & gefixt**
Branch `spike/photo-view-plus`, APK gebaut & auf S23 installiert.

### Erfasste WISS-Logs (Beweis des Bugs)
```
base=0.3750, max=4.3333, outer=360.0×780.0, img=960×720

06-04 15:52:57.513 DT s0=2.2655 →Basis   (Animation 2.27→0.375 startet, 220ms)
06-04 15:52:58.111 ptr↓ s0=1.2317        ← Scale eingefroren MID-ANIMATION!
06-04 15:52:58.279 DT s0=1.2317 →Basis   (2. Versuch, ebenfalls abgebrochen)
06-04 15:52:59.243 ptr↓ s0=0.8460
06-04 15:52:59.417 DT s0=0.8460 →Max     (0.846 ≤ 0.9844 = Stufe1*1.05 → falsche Stufe!)
06-04 15:52:59.649 anim done 4.3333=4.3333 ✓  (Max OK: User hielt 822ms > 220ms Anim)
```

### Root Cause
`_onScaleEnd` rief `_zoomAnimCtrl.stop()` bedingungslos.
PV feuert `onScaleEnd` beim Finger-Heben nach JEDEM Tap, nicht nur nach Pinch/Pan.
→ 2. Tap der Doppeltipp-Sequenz hebt Finger → `onScaleEnd` → `.stop()` → Animation stirbt
→ `_onZoomAnimStatus(completed)` nie erreicht → exaktes Reset nie angewandt → Scale eingefroren.

### Fix
`_zoomAnimCtrl.stop()` aus `_onScaleEnd` entfernt.
Pinch wird bereits in `_onPointerDown` (multi-touch branch) gestoppt — kein Konflikt.

---

## 🔴 Gerätetest — S23 (APK installiert, Test ausstehend)

```
[ ] 1. Basis → Stufe1 → Max → Basis → … mehrfach: deterministisch
[ ] 2. Nach Pinch → Doppeltipp funktioniert korrekt
[ ] 3. Max → Basis: exakt Ausgangsgröße, Wischen danach OK
[ ] 4. Log: WISS anim done scale=X target=X → beide gleich
```
Logging: `adb logcat | grep WISS`

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
