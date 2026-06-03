# Wissensfreund — STATUS
<!-- updated: 2026-06-03T18:22:24Z -->
<!-- Dieser File wird von Claude Code bei jeder Session aktualisiert. -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## 🟢 Zuletzt abgeschlossen (Session 2026-06-03 — photo_view_plus Migration)

**Branch:** `spike/photo-view-plus` — APK auf S23 installiert.
- InteractiveViewer → photo_view_plus 1.1.1 (PhotoViewGestureDetectorScope fix)
- _LimitedCoverScale: resolve() = min(sk, sc*1.18) | strictScale | maxScale=covered*4
- Double-tap: disableDoubleTap+onTapUp-Debounce+AnimController+_clampPosition()
- bottomInset für alle Bottom-Elemente | filterQuality.high | Flutter 3.44.0 / Dart 3.12.0

---

## 🔴 Muss am S23 verifiziert werden (Regressions-Checkliste)

```
[ ] PageView Mehrbild-Wisch
[ ] Pinch sofort nach Öffnen — KERN-BUG, explizit testen!
[ ] Bild lässt sich im Zoom NICHT aus Viewport schieben
[ ] Doppeltipp 1x↔2.5x zentriert auf Tippposition
[ ] Zurück- / Speaker- / ⓘ-Lizenz-Button funktionsgleich
[ ] Bildunterschrift + "1 / 3"-Zähler korrekt
[ ] Limited cover max ~15% Crop, kein Letterbox
[ ] Schwarzer Hintergrund | Seitenverhältnis-Randfälle
```

**Nach Geräte-Parität:** `spike/photo-view-plus` → `main` mergen, Branch löschen.

---

## Kompatibilitäts-Audit 2026-06-03

Zielboden: Android 10 (API 29), 3 GB RAM, ~2016-Hardware.

**1. Build**
compileSdk=36 | targetSdk=flutter.targetSdkVersion (Flutter 3.44.0 → 35) | minSdk=29
NDK 28.2.13676358 | KEIN abiFilters/splits.abi → universelles APK (arm64-v8a + armeabi-v7a)

**2. ZIM-Reader**
Eigener Kotlin-Parser (RandomAccessFile) — KEINE libzim. Zstd-Cluster: native JNI
libzim_zstd.so (C-zstd 1.5.6 via CMake). XZ: org.tukaani:xz pure Java.
ABIs: Flutter-Default (arm64-v8a + armeabi-v7a) — 32-Bit dabei, kein Problem.

**3. On-Device-LLM**
Nicht implementiert — _handleGeminiPlaceholder() ist Stub mit TODO-Kommentar (Z. 1389).
Kein mediapipe/tflite/llama/gemma-Package in pubspec.

**4. 3D-Charakter**
Nicht vorhanden — professor_widget.dart ist 2D Flutter-Widget (AnimationController).
Kein filament/WebView/OpenGL-ES. Kein Fallback nötig.

**5. Google-Play-Services-Kopplung**
HART: BillingService (billing:6.2.1) → Play Store required. Bricht auf Fire OS/AOSP.
  Graceful Degradation: bei Verbindungsfehler → "free" (kein Crash).
STT: Android SpeechRecognizer (kein ML Kit) — funktioniert ohne Google-Services wenn
  Gerät eigene Erkennungs-Engine hat; fällt auf Cloud-Recognizer zurück (Retry-Logik).
TTS: flutter_tts → Android TTS (gerätenativ, Manifest fragt com.google.android.tts).
Firebase/Firestore/FCM/ML Kit: NICHT vorhanden.
→ Einzige harte Play-Kopplung: Billing.

**6. TTS**
flutter_tts → Android TTS-Engine (gerätenativ). Sprache: de-DE.
Wenn de-DE fehlt: flutter_tts fällt auf Gerätestandard zurück; kein App-seitiger Fallback.
Keine vorproduzierten Dateien für Professor-Sprache (ZIM-Audio ist separat).

**7. Eltern-Kiosk**
3 Mechanismen: Overlay (SYSTEM_ALERT_WINDOW + ForegroundService + onStop()),
DeviceAdmin (force-lock only), BiometricPrompt (ParentalUnlockActivity).
Blockiert: Home, Recents, Wischgesten, Notification-Tap.
NICHT blockiert: ADB, Accessibility-Service-Umweg (bekannte Einschränkung, doc. in Memory).
Screen Pinning (startLockTask) NICHT verwendet.

**8. Bild-Tier-Diskrepanz (nur vermerkt — nicht aufgelöst)**
App (asset_config.dart): thumb=300px | standard=800px | pro=1200px
Pipeline (download_images.py / CLAUDE_CHAT_NOTIZEN): thumb=300px | standard=800px | pro=1600px
→ pro-Tier Diff: App erwartet 1200px, Pipeline erzeugt 1600px. Auflösung ausstehend.

---

## 🟡 Zum Testen (ausstehend)
- Mode B Lupe: Bold entfernen (wechselnde Zeilenumbrüche)
- Mode B Lupe: _ttsCursor erst im progressHandler updaten (zu frühes Highlight)

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
