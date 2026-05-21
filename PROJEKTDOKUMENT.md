# Wissensfreund — Projekt-Referenz

> Kompakte Architektur-Referenz für Claude Code und Claude Chat.
> Vollständiges Projektdokument (45 Seiten): nur bei Andreas lokal verfügbar.
> Diese Datei bei Versions-Updates bitte aktualisieren und pushen.

**Stand:** 2026-05-21 | **App-Version:** 1.0.0 (Entwicklungsphase)

---

## App-Konzept

Wissensfreund ist eine kindersichere Wissens-App für Kinder von 4–12 Jahren.
Der animierte Charakter "Wissensfreund" beantwortet Kinderfragen per Spracheingabe (STT)
und Sprachausgabe (TTS) — ausschließlich aus verifizierten Klexikon-Artikeln, vollständig offline.
Kein Internet, keine Werbung, kein Social Media, keine KI-Halluzinationen.

---

## Zielgruppe und Altersgruppen

| Gruppe | Alter | Verhalten |
|--------|-------|-----------|
| Kleine Kinder | 4–8 Jahre | Einfache Fragen, vollständiges Vorlesen des Artikels |
| Größere Kinder | 8–12 Jahre | Komplexere Fragen, gezielte Antworten aus Artikeltext |
| Eltern | — | Kinderschutz einrichten, Einstellungen verwalten |

**Gerät:** Primär ein dediziertes Android-Gerät (Galaxy S23), nicht das eigene Elterngerät.
Kinder haben das Gerät alleine — Eltern müssen sich authentifizieren um es freizugeben.

---

## Tech-Stack

| Komponente | Technologie | Warum |
|------------|-------------|-------|
| App-Framework | Flutter (Dart) | Cross-platform, gute Android-Integration |
| Android-Nativ | Kotlin | Overlay, Foreground Service, Biometrie — nur nativ möglich |
| Wissensquelle | Klexikon-ZIM (offline, ~156 MB mit Bildern) | Kindgerecht, lizenziert (CC BY-SA 3.0), vollständig offline |
| Artikel-Suche | Dart-ZIM-Parser + Relevanz-Punkte-System | Schnell, offline, keine Server-Abhängigkeit |
| KI-Verarbeitung | Google Gemini API | Nur für Textextraktion aus geladenen Artikeln — kein eigenes Wissen |
| TTS | Android `TextToSpeech` (offline) | Latenz <200 ms, keine Internetverbindung nötig |
| STT | Android `SpeechRecognizer` | Plattform-nativ, beste Genauigkeit auf Android |
| Kinderschutz | Android `SYSTEM_ALERT_WINDOW` + Foreground Service | Overlay über alle Apps, nicht bypassbar via Home/Recents |
| Eltern-Auth | `androidx.biometric` — `BIOMETRIC_STRONG`, `BIOMETRIC_WEAK`, `DEVICE_CREDENTIAL` | Alle vom Gerät unterstützten Methoden |

---

## Kern-Architektur-Entscheidungen

### Offline-First
Die gesamte Wissensbasis (Klexikon-ZIM) ist lokal auf dem Gerät.
Gemini-API-Aufrufe sind die einzige Internet-Abhängigkeit.
Alle anderen Funktionen (TTS, STT, Suche, Artikel) funktionieren ohne Internet.

### ZIM-Datei
- Format: OpenZIM (Kiwix-Standard)
- Inhalt: Alle Klexikon-Artikel auf Deutsch, mit Bildern
- Dateigröße: ~156 MB (maxi), ~80 MB (nopic)
- Pfad auf Gerät: `/sdcard/Android/data/de.wissensfreund.wissensfreund_app/files/klexikon.zim`
- Lizenz: CC BY-SA 3.0 — Pflichtangabe: Artikel-Footer + Impressum + `source_url` in DB

### Relevanz-Punkte-System (Suche)
- Schlagwort im Titel: +3 Punkte
- Schlagwort im ersten Absatz: +2 Punkte
- Schlagwort nur im Fließtext: +1 Punkt
- Mehrere Suchbegriffe im selben Artikel: Punkte multiplizieren
- Zwei gleichwertige Treffer → Charakter fragt: max. 1 Rückfrage

### KI-Einsatz (Eiserne Regel)
Gemini darf **ausschließlich** aus dem geladenen Artikeltext antworten.
**Kein Fallback auf Trainingswissen** — ohne Ausnahme.
Kein passender Artikel → Eltern-Verweis: "Das können Mama oder Papa besser erklären."

### Frage-Typ-Erkennung (Keyword-Matching, keine KI)
- "Was ist / Was sind / Erzähl mir / Wer ist" → kompletten Artikel vorlesen (~70 %)
- "Warum / Wie / Wann / Wo / Ist es wahr / Stimmt es" → gezielte Antwort aus Artikeltext
- Folgefragen während/nach Vorlesen → Artikeltext bereits geladen, direkte KI-Antwort

### TTS / STT — Audio Driver Bug (gelöst)
Nach TTS bleibt Android-Treiber im Music-Modus → STT leer/NO_MATCH.
Fix: `AudioRecord`-Warmup 150 ms vor `SpeechRecognizer`-Start.

### Kinderschutz-Architektur
```
Kind drückt Home/Recents
        ↓
onStop() in MainActivity
        ↓
WissensfreundForegroundService zeigt nativen Overlay (TYPE_APPLICATION_OVERLAY)
        ↓
Overlay: "Entsperren" (Eltern) | "Zurück zu Wissensfreund" (Kind)
        ↓ Entsperren
ParentalUnlockActivity (transparent, kein Recents-Eintrag)
BiometricPrompt: Fingerabdruck / Gesicht / PIN / Muster / Passwort
        ↓ Erfolg           ↓ Abbruch
released = true        Overlay wieder einblenden
Activity schließt sich → Nutzer auf Recents/Home
```

**Authenticators (API-abhängig):**
- API 30+ (Android 11+): `BIOMETRIC_STRONG | BIOMETRIC_WEAK | DEVICE_CREDENTIAL`
- API 29 (Android 10): `BIOMETRIC_STRONG | DEVICE_CREDENTIAL`

---

## Responsive UI — Pflicht-Regeln

- Niemals hardcodierte Pixel — immer `MediaQuery` + relative Werte
- Widget-Dimensionen als benannte Konstanten, abhängige Werte ableiten
- Bildhöhen per `MediaQuery + clamp`
- Zielgeräte: Android 10+, ab 3 GB RAM (nicht nur Galaxy S23)

---

## Lizenz-Pflichtangaben (Klexikon)

CC BY-SA 3.0 — rechtlich verpflichtend bei jeder Nutzung:
1. Artikel-Footer mit Quellenangabe und Link
2. Impressum-Abschnitt in der App
3. `source_url`-Feld in der Datenbank

---

## Bekannte Besonderheiten / Fallstricke

- `flutter install` löscht die ZIM-Datei → nach jedem Reinstall `adb push` nötig
- Flutter-Build und `flutter run` **immer über Bash-Tool** ausführen (Symlink-Problem auf Windows ohne Developer Mode)
- Overlay benötigt `SYSTEM_ALERT_WINDOW`-Berechtigung (einmalige manuelle Einrichtung)
- `ParentalUnlockActivity` muss `FragmentActivity` sein (nicht `AppCompatActivity`) — sonst Crash mit transparentem Theme
