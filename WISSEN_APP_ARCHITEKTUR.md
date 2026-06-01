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

### Scroll-Navigation Modus A + B (Stufe 2/3)
- **800 ms Debounce** nach Scroll-Stop (`_scrollDebounce`).
- `_userScrolling = true` während User scrollt → blockiert `_smartScrollTo` (kein Auto-Scroll zurück).
- `_programmaticScroll = true` (600 ms) während TTS-Auto-Scroll → blockiert `_onScroll` (kein falsches _userScrolling).
- Nach Debounce: `_jumpToTopSentence()` ermittelt obersten sichtbaren Satz → `seekAfterCurrentChunk(offset)`.

**Mode A** (`_ModeAContentState`): nutzt `_sentenceTopCache` (gebaut einmalig bei initState).
- `_userScrolling = false` sofort in `_jumpToTopSentence` — funktioniert weil `_sentenceTopCache` stabil ist
  (Mode A ändert keine Font-Sizes, Positionen bleiben korrekt).
- **Bug 2026-06-01**: `_jumpToTopSentence` hatte `_userScrolling = false` an KEINEM Return-Pfad.
  → Nach erstem manuellen Scroll: `_userScrolling = true` für immer → `_smartScrollTo` dauerhaft geblockt.
  Fix: `_userScrolling = false` an allen 5 Early-Returns + unmittelbar nach `seekAfterCurrentChunk`.

**Mode B** (`_ModeBContentState`): nutzt **live** `findRenderObject()` in `_jumpToTopSentence`.
- Stale-Cache-Problem: aktiver Satz fontSize 19, inaktiv 15 → Positionen verschieben sich mit jedem TTS-Advance.
  Ein staler Cache liefert falsches `topIdx` → `topIdx == activeIdx` → kein Seek.
- Fix: `_jumpToTopSentence` iteriert alle `_sentenceKeys`, fragt jedes Mal live `globalToLocal()` ab.
- `_seekResumeTimer` (3000 ms): `_userScrolling` bleibt nach Seek-Aufruf `true` bis Timer feuert.
  Verhindert, dass `_smartScrollTo` für alte TTS-Sätze sofort zurückscrollt, bevor Seek greift.
  Neuer Scroll von User → `_seekResumeTimer?.cancel()` (State-Machine Reset).
- **Professor-Zone-Bug 2026-06-01**: Professor-Widget (218 dp) deckt untere ~220 dp des Viewports ab.
  - Scroll-Schwelle `viewportH * 0.5` zu spät: Safe-Zone endet bei ~306 dp, 50% = ~262 dp, nächster
    Satz bei ~312 dp → bereits unter Professor. Fix: Schwelle auf `viewportH * 0.35` (≈184 dp).
  - Bottom-Padding `_kMicClear` (80 dp) → letzter Artikel-Satz unter Professor sichtbar.
    Fix: Padding auf `_kProfZone = _kProfH + _kProfBottom - 4 = 220 dp` erhöht.

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

## JSON-Artikel: Bundled-Asset-Fallback (ab 2026-06-01)

`JsonArticleService.loadArticle(id)` hat drei Stufen:
1. Lokaler Datei-Cache (`getApplicationDocumentsDirectory()/wf_articles/articles/$id.json`)
2. R2-CDN-Fetch (`AssetConfig.r2ArticlesBaseUrl/articles/$id.json`)
3. **Bundled Asset** (`assets/test/$id.json`) — Fallback wenn R2 nicht erreichbar oder 404

`pubspec.yaml` enthält `- assets/test/` damit Flutter die Dateien einbettet.
Aktuell bundled: `elefant_l2.json` (5 Abschnitte, 5 Bilder, 4 Quiz-Fragen).

**Test-Button** (`home_screen.dart`): immer `'elefant_l2'` laden — NICHT dynamisch nach Altersstufe.
Grund: Nur `elefant_l2.json` existiert. Dynamisches `'elefant_l$level'` mit Stufe 1 oder 3 → 404 →
leerer Artikel → keine Bilder, keine Kapitel-Pfeile in Modus C.

## Bild-Fetch: JSON vs. ZIM

| Quelle | Weg | Netzwerk nötig? |
|---|---|---|
| JSON-Artikel | `_fetchFromThumbUrl` → `NetworkService.canUseNetwork` → `HiResImageService` (Wikimedia CDN) | Ja — WiFi (default: `mobileAllowed=false`) |
| ZIM-Artikel | `ImageLibraryService._zimBytes` → lokal aus ZIM-Datei gelesen | Nein |

Auf Mobilfunk ohne explizites Freischalten → JSON-Bilder werden geblockt → `_articleImages = []` → keine Bilder sichtbar.

---

## Wichtige Designentscheidungen (nicht rückgängig machen)

- **Kein Doppel-Renderer** — ZIM-Artikel werden per `convert_zim_to_json.py` konvertiert, dann identisch behandelt
- **Kein `viewPadding.bottom` manuell berechnen** — immer `SafeArea()` verwenden
- **Staging-Dir-Pattern** für Downloads — `.new/` Verzeichnis, atomarer Austausch am Ende
- **Plausibilitätsprüfung manuell** — Claude Code/Chat macht Fehler bei großen Zahlen, Andreas prüft selbst
- **Test-Button hardcoded auf `elefant_l2`** — nie wieder dynamisch nach Altersstufe bauen
- **`_userScrolling` an ALLEN Return-Pfaden zurücksetzen** — gilt für Mode A und B; vergessene
  Resets führen zu dauerhaft blockiertem Auto-Scroll ohne offensichtlichen Fehler
- **Mode B Bottom-Padding = `_kProfZone` (220 dp)**, nicht `_kMicClear` (80 dp) — Professor
  ist 218 dp hoch; Mic ist 52+14+14 = 80 dp; beide Konstanten vorhanden, die richtige verwenden
