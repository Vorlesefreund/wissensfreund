# Wissensfreund — STATUS
<!-- updated: 2026-06-03T07:46:50Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — Phase 2: ImageFullscreenOverlay)

### Neues Widget: ImageFullscreenOverlay
- `lib/widgets/image_fullscreen_overlay.dart` (neu)
- PageView mit Bildwechsel per Wischen (gesperrt wenn gezoomt)
- InteractiveViewer: Pinch-to-Zoom 1×–4×, Doppeltipp-Toggle 1×↔2.5×
- TransformationController → _isZoomed-Flag → PageView-Physics umschalten
- Bildschirm-Rotation (portraitUp + landscape) beim Öffnen, Restore beim Schließen
- SystemUiMode.immersiveSticky beim Öffnen, restoreSystemUI() beim Dispose
- TTS pausiert (pauseSpeaking) beim Öffnen, bleibt pausiert beim Schließen
- Orientierungs-Hinweis: decodeImageFromList → Seitenverhältnis → "Handy drehen" bei imgRatio > 1.3 + Portrait, 3s auto-fade
- Bildunterschrift: Gradient 80dp + weißer Text 13px maxLines 2
- 🔊 Speaker-Button (oben rechts, nur wenn caption vorhanden, einmal pro Bild → ausgegraut)
- Bild-Zähler "1 / 3" (oben mitte, ab 2 Bildern)
- Zurück-Button (oben links)

### Trigger in article_screen.dart
- `_pushImageFullscreen(ctx, images, index)` — Top-Level-Helper: Plus/Premium → Overlay, Free → SnackBar
- `_FullscreenGallery`: onTap auf äußerem GestureDetector → 2. Tipp öffnet Overlay (Mode A/B Zwei-Schritt-Flow)
- Modus C: `_MainArticleImage(onTap: ...)` → direktes Overlay (da Mode C bereits Vollbild)

### Build
- APK gebaut ✅ — Gerät nicht verbunden, Installation ausstehend
- `flutter analyze lib/widgets/image_fullscreen_overlay.dart` → No issues found

---

## 🟡 Zum Testen (manuelle Checkliste aus CLAUDE_CODE_PHASE2_VOLLBILD_v3.md)

- Modus A/B: Bild tippen → _FullscreenGallery → dort nochmal tippen → Overlay
- Modus C: Bild tippen → direkt Overlay
- Overlay füllt Bildschirm (Statusbar versteckt)
- Gerät drehen → Bild dreht mit
- Querformat-Bild: "Handy drehen" erscheint 3s
- Zurück-Button, Wischen, Pinch, Doppeltipp, Rand-Swipe
- TTS pausiert beim Öffnen, bleibt pausiert
- Free-Nutzer → Upgrade-SnackBar

---

## 🟡 Offen — nächste Schritte (nach Priorität)

### Hoch
- **Manuell testen** — seekWithDelay + Zentrierung (aus letzter Session)
- **Manuell testen** — ImageFullscreenOverlay (diese Session)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche in Mode A)
- Mode B Lupe: `_ttsCursor` erst im progressHandler updaten (zu früh springendes Highlight)

### Mittel (zurückgestellt)
- **Selbst produzierte Artikel** (neue JSON-Artikel mit echten Inhalten)
- **Quiz-Checkpoint löschen + Run neu starten**
- **Bilder-Patch** (`patch_article_images_v1.py`)
- **Links in JSON-Artikeln**, **Gemini-Integration**, **Topic-Tree**

### Niedrig
- Upgrade-Dialog, Plus/Premium-Design, Sound-Thumbnails

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline
