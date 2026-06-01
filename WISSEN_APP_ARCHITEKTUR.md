# WISSEN: App-Architektur
<!-- Thematisches Wissensdokument — wird nicht täglich gelesen, nur bei App-Themen -->
<!-- Letztes Update: 2026-06-01 -->

## Repos

| Repo | Pfad | Inhalt |
|---|---|---|
| App | `C:\Users\Andreas\Wissensfreund\wissensfreund_app` | Flutter/Dart, primär |
| CI/Pipeline | `C:\Users\Andreas\wissensfreund_repo` | Python-Skripte + GitHub Actions Workflows |
| Testbed | `C:\Users\Andreas\Vorlesefreund\vorlesefreund_testbed` | TTS-Latenz-Tests |

---

## State & Services

- **State:** Provider-Pattern → `lib/providers/wissensfreund_provider.dart`
- **Key Services:**
  - `ZimUpdateService` — ZIM-Download und Versionsprüfung
  - `ImageLibraryService` — offline ZIP, Progress-Tracking, Staging-Dir-Pattern
  - `HiResImageService` — on-demand Fetch von Wikimedia Commons
  - `JsonArticleService` — R2-Download, lokaler Cache für JSON-Artikel
  - `AudioPackageService` — Audio-Pipeline (noch nicht aktiv)
  - `ProfileService` — Multi-User, SQLite, CRUD, Verlauf, Favoriten
  - `ParentalLockService` — BiometricPrompt, Kiosk-Modus
  - `DataLimitOverlayService` — Datenlimit-Overlay, Vollbild
  - `NetworkSettingsService` — WLAN/Mobilfunk, Tageslimit, Monatslimit
  - `SubscriptionService` — Free / Plus / Premium, Google Play Billing 6.2.1

---

## Artikel-Darstellung

**3 Ansichtsmodi:**
- A — Volltext + Satz-Highlighting (TTS-Cursor sichtbar)
- B — kompakt
- C — Vollbild-Galerie

**TTS-Chunking:**
- `_speechChunks` / `_chunkOffsets` / `_currentChunk` — interne Puffer
- `_ttsCursor` — aktuelle Position im Text
- Satz-IDs (`s001`, `s002`…) im JSON-Format erleichtern Highlighting
- Jeder Satz hat einen `img_index` (0-basiert) — welches Bild beim Vorlesen dieses Satzes zu sehen ist
- Bildwechsel findet an thematischen Grenzen statt, nicht an Abschnittsgrenzen
- Mehrere aufeinanderfolgende Sätze können denselben `img_index` haben

**Nav-Stack:**
- Max. 2 Einträge
- Speichert Artikel + Satzstart-Offset für Zurück-Navigation
- Nach Artikel-Ende: Mikrofon öffnet sich automatisch nach 2 Sek
- Mit Stack: Professor fragt "Soll ich mit [Artikel] weitermachen?"

---

## Frage-Typ-Erkennung (5 Typen)

| Typ | Erkennung | Reaktion | Verfügbar |
|---|---|---|---|
| 1 Themen-Frage | "Was ist", "Erzähl mir", "Wer ist" | Artikel vorlesen | Free + Plus |
| 2 Warum/Wie | "Warum", "Wie", "Wann", "Wo" | Gemini extrahiert Stelle | nur Plus |
| 3 Vergleich | 2 Artikel-Begriffe + Vergleichswort | Beide Artikel laden, Gemini | nur Plus |
| 4 Folgefrage | Artikel bereits geladen + neue Frage | Gemini aus Kontext | nur Plus |
| 5 Fallback | alles andere | Gemini versucht mit Kontext | nur Plus |

`_detectQueryType()` ist implementiert. Gemini-Integration selbst steht noch aus.

**Eiserne Regel:** Gemini antwortet NIE aus Trainingswissen. Immer nur aus geladenem Artikeltext. Kein Artikel + zu komplex = Eltern-Verweis.

---

## Freemium-Modell

| Feature | Free | Plus | Premium |
|---|---|---|---|
| Artikel lesen/hören | ✅ | ✅ | ✅ |
| Bilder 300px offline | ✅ | ✅ | ✅ |
| Bilder 800px offline (images_standard.zip) | ❌ | ✅ | ✅ |
| Bilder 1600px offline (images_pro.zip) | ❌ | ❌ | ✅ |
| Bilder on-demand von Wikimedia (bis ~2048px) | ❌ | ✅ (WLAN) | ✅ (WLAN) |
| Fragen stellen (Typen 2–5) | ❌ | ✅ | ✅ |
| Produkte | — | `wissensfreund_plus` (INAPP) | `wissensfreund_premium` (SUBS) |

Upgrade-Trigger: nicht beim Onboarding, sondern wenn Nutzer erlebt was fehlt 
(z.B. unscharfes Bild → "Besser mit Plus"-Badge).

---

## Nutzer-Profil & Onboarding

- **ProfileService** — SQLite Schema v7, Tabellen: `profiles`, `article_history`, `favorites`
- **Profil-Wizard** — 5 Schritte: Name → Geburtsjahr → Avatar (20 Tiere) → Sprachniveau → Fertig+Konfetti
- **Onboarding-Flow:** FirstRunScreen → Internet & Daten → Bildqualität → Kinderschutz → ProfileCreation → HomeScreen
- `onboarding_complete` SharedPref verhindert Wiederholung
- `ProfileService.activeAgeLevel` — Altersstufe (1/2/3) für Artikel-Filterung

---

## Datenlimit-System

- 80%/90%/100% Warnungen eingebettet zwischen TTS-Chunks
- Bei 100%: Professor beendet graceful, spricht Übergabe-Phrase
- Eltern entsperren mit BiometricPrompt → Limit erhöhen → Retry automatisch
- `DataLimitOverlayService` — Singleton, 4 Phasen (gesperrt → entsperrt → anpassen → speichern)

---

## Interne Links zwischen Artikeln

- `ZimReader.getLinkRefs()` — extrahiert interne Links aus ZIM
- SQLite-Cache: `article_links` Tabelle
- Links nur in Modus A tippbar (nicht B/C, nicht Mini-Klexikon Stufe 1)
- Link-Tap: Professor liest Satz zu Ende → fragt "Soll ich mehr über [Begriff] erzählen?"
- Quellübergreifend: erst eigene JSON-Artikel, dann ZIM

---

## Build & Deploy

```bash
flutter build apk --debug
adb install -r build/app/outputs/flutter-apk/app-debug.apk
# Nach ZIM-Reinstall:
adb push klexikon.zim /sdcard/Android/data/.../files/
```

---

## Technische Schulden (niedrige Priorität)

- `kMonthlyQuestionLimit` + `addSessionMinutes()` vorhanden aber inaktiv → aktivieren wenn Gemini läuft
- `RadioListTile` deprecated in Flutter 3.32+ (nur Info-Warnung, kein Fehler)
- Download-Größe wird statisch "~2 GB" angezeigt, nicht aus Manifest gelesen
- Gallery-Artikel (111) ohne eigene UI-Komponente → Version 1.1

---

## Navigation & Bild-Sync nach Altersstufe

Implementiert in `article_screen.dart` + `wissensfreund_provider.dart` (Session 2026-06-01).

### Mode-Toggle nach Altersstufe
- Stufe 1 (ageLevel==1): Toggle zeigt nur B und C (2 Icons). Modus A ausgeblendet.
- Stufe 2/3: Toggle zeigt A, B, C (3 Icons).
- Automatischer Wechsel: Wenn Stufe 1 aktiv und Modus A gespeichert → postFrameCallback setzt Modus B.
- Implementiert als `_buildModeToggle()` in `_ArticleHeader`; nutzt `provider.setViewMode(mode)`.

### Bild-Sync (`_doImageSwipe` — top-level Hilfsfunktion)
- Stufe 1: freies Wischen, kein TTS-Sync.
- Stufe 2/3 vorwärts (next > ttsImg): `provider.pauseImageSync()` → Sync pausiert bis TTS aufholt.
- Stufe 2/3 rückwärts (next < ttsImg): 10 s Timer → danach Bild auf TTS-img_index zurück.
- Provider-Felder: `_chunkImgIndices`, `_imageSyncPaused`, `currentTtsImageIndex`.
- Sync wird im Chunk-Advance-Handler automatisch weitergeschalten.
- Nur für JSON-Artikel (img_index pro Satz). ZIM-Artikel: `_chunkImgIndices` leer → kein Sync.

### Scroll-Navigation Modus A (Stufe 2/3)
- 1500 ms Debounce nach Scroll-Stop (`_scrollDebounce` in `_ModeAContentState`).
- Kein Sprung wenn aktueller TTS-Satz bereits sichtbar (`_sentenceTopCache`).
- Sonst: oberster vollständig sichtbarer Satz ermittelt → `provider.seekAfterCurrentChunk(offset)`.

### Kapitel-Navigation Modus C (Stufe 2/3)
- Zwei Pfeil-Buttons `‹`/`›` (36 px, halbtransparent) neben Thumbnails.
- Nur sichtbar wenn `sectionChunkStarts.length > 1` und `ageLevel >= 2`.
- `_prevSection` / `_nextSection` in `_ModeCContentState` (jetzt StatefulWidget).
- Provider-Felder: `_sectionChunkStarts`, `_sectionHeadings`, `chunkCharOffset(idx)`.

### Provider: `seekAfterCurrentChunk(charOffset)`
- Wenn Professor spricht: deferred via `_pendingSeekOffset`, Sprung nach aktuellem Chunk.
- JSON-Artikel (img_index vorhanden): Chunk-Index per Offset-Lookup, `_chunkImgIndices` bleibt erhalten.
- ZIM-Artikel: `_startSpeakingFrom(offset)` (Heuristik-Chunking, keine img-Daten).

---

## Wichtige Designentscheidungen (nicht rückgängig machen)

- **Kein Doppel-Renderer** — ZIM-Artikel werden per `convert_zim_to_json.py` konvertiert, dann identisch behandelt
- **Kein `viewPadding.bottom` manuell berechnen** — immer `SafeArea()` verwenden
- **Staging-Dir-Pattern** für Downloads — `.new/` Verzeichnis, atomarer Austausch am Ende
- **Plausibilitätsprüfung manuell** — Claude Code/Chat macht Fehler bei großen Zahlen, Andreas prüft selbst
