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
- **`_userScrolling = true` VOR dem `ageLevel < 2`-Check setzen** — sonst greift der Guard bei
  Level 0/1 nie, und Auto-Scroll springt Text zurück (Bug 2026-06-01, beide _onScroll-Methoden)
- **`_seekToChunkForOffset`: `startSpeaking`-Parameter auch im ZIM-Pfad beachten** — der else-Zweig
  (`_chunkImgIndices` leer) muss `startSpeaking: false` respektieren, sonst startet TTS bei Pause+Scroll
- **Links in JSON-Artikeln fehlen im Datenmodell** — `WfSentence` hat kein Link-Feld; `WfArticleConverter`
  setzt `links: const []`. Lösung erfordert Python-Pipeline-Änderung (Link-Positionen aus HTML extrahieren),
  dann `WfSentence.links`, `WfArticleConverter`-Update, Provider-Befüllung. Backlog nach Quiz-Run.
- **Mode B Bottom-Padding = `_kProfZone` (220 dp)**, nicht `_kMicClear` (80 dp) — Professor
  ist 218 dp hoch; Mic ist 52+14+14 = 80 dp; beide Konstanten vorhanden, die richtige verwenden

---

## Modus C — Slider-Navigation (ab 2026-06-01)

### UI-Layout

```
[oben] 🔊 (top: 90, right: 14) — Bildunterschrift vorlesen
[Bild]
[unten] ⏮ | ────Slider──── | ⏭  (height: 48, bottom: imageClearance - 24)
[Thumbnails]
```

### Slider-State-Pattern (`_sliderDragValue`)
```dart
double? _sliderDragValue;   // null = Provider-Wert; non-null = Drag-Position

Slider(
  value: _sliderDragValue ?? _chunkFraction(provider),
  onChanged: (v) => setState(() => _sliderDragValue = v),
  onChangeEnd: (v) {
    setState(() => _sliderDragValue = null);
    // → jumpToSection(...)
  },
)
```
**Warum:** Consumer-Rebuilds während Drag würden Slider auf Provider-Position snappen ohne lokalen State.

### Navigation: Chunk-Level (nicht Sektion)
- `totalChunks` = `_speechChunks.length` (Provider Getter)
- `_prevChunk`/`_nextChunk` springen zum nächsten Satz (`chunkCharOffset(cur ± 1)`)
- `_chunkFraction = currentChunkIndex / (totalChunks - 1)` → Slider-Position

### `jumpToSection(int charOffset)` — sofortiger TTS-Interrupt
```dart
Future<void> jumpToSection(int charOffset) async {
  _pendingSeekOffset = null;
  final wasPlaying = _state == AppState.speaking && !_isPaused;
  if (wasPlaying) {
    _isPaused = true;   // GUARD: verhindert onComplete → auto-advance
    _state = AppState.idle;
    notifyListeners();
    await _tts.stop();
    _isPaused = false;
  }
  _seekToChunkForOffset(charOffset, startSpeaking: !_isPaused);
}
```
`_isPaused = true` MUSS vor `await _tts.stop()` gesetzt werden — `onComplete` prüft `_isPaused`
und würde sonst zum nächsten Chunk weiter springen.

Gegensatz: `seekAfterCurrentChunk` queued `_pendingSeekOffset` → wirkt erst nach aktuellem Satz.

### `seekNow(int charOffset)` — sofortiger Interrupt für Scroll-Navigation
```dart
void seekNow(int charOffset) {
  _pendingSeekOffset = null;
  _stimmtPauseTimer?.cancel();
  if (_state == AppState.speaking && !_isPaused) {
    _ttsStopPending = true;     // onComplete-Guard: unterdrückt Stop-Event
    unawaited(_tts.stop());
    _seekToChunkForOffset(charOffset);  // synchron, vor dem Dart-Event-Loop-Tick
  } else {
    _seekToChunkForOffset(charOffset, startSpeaking: !_isPaused);
  }
}
```
Gegenüber `jumpToSection` kein async/await nötig, weil `_ttsStopPending` den Completion-Handler abblockt.
Wird von `_jumpToTopSentence` (Mode A+B) gerufen, nicht für Section-Pfeile.

### Heading-Gap Bug in _jumpToTopSentence (behoben 2026-06-02)
`WfArticleConverter` schreibt `"Heading\n"` in `plainText`. `_splitSentences` merged Überschriften ohne Satzzeichen mit dem ersten Satz der Section → `sentences[k]` = `"Heading\nErster Satz."`.

Berechneter `charOffset` für diesen "merged Satz" = start of Heading in `plainText`. Aber `_chunkOffsets[s3_0]` = start of Heading + len(Heading) + 1. Dadurch fand `_seekToChunkForOffset` den letzten Satz VOR der Überschrift statt des richtigen Satzes.

**Fix in `_jumpToTopSentence`**:
```dart
final nl = sentences[topIdx].indexOf('\n');
if (nl >= 0) charOffset += nl + 1;  // spring past "Heading\n" zum echten Satz
```

---

## _lastActiveIdx Premature-Update Bug (2026-06-02)

### Symptome
- Aktiver Satz zentriert sich nicht automatisch nach Scrollen
- TTS "hängt" (läuft weiter, aber Screen scrollt nicht mit → Satz off-screen)
- Gleicher Absatz wird wiederholt vorgelesen (User scrollt TTS hinterher → neuer Seek → springt zurück)

### Root Cause
In beiden Modes (A + B) wurde `_lastActiveIdx = scrollIdx` im **Consumer-Builder** gesetzt, BEVOR
`_smartScrollTo()` die Guards `_scrollPending` / `_userScrolling` prüfte. Wenn `_smartScrollTo`
wegen `_userScrolling = true` blockiert wurde:
- `_lastActiveIdx` war bereits auf den neuen Wert gesetzt
- Nächster Consumer-Rebuild sah `scrollIdx == _lastActiveIdx` → kein Aufruf → Scroll feuert nie

### Fix
`_lastActiveIdx = idx` wird nur innerhalb `_smartScrollTo()` gesetzt, NACH den Guards (wenn Scroll
tatsächlich ausgeführt wird). Gleiches gilt für `_lastBoxKey = boxKey` in `_smartScrollToBox()`.

Consumer-Builder ruft `_smartScrollTo()` / `_smartScrollToBox()` auf solange `scrollIdx != _lastActiveIdx`
→ retried automatisch bei jedem Rebuild bis Guards passierbar sind.

`_smartScrollToBox` Signatur: `(GlobalKey key, String? boxKey, int rawIdx)` — boxKey + rawIdx werden
intern gesetzt.

### Kapitelüberschriften mitvorlesen
Beim Aufbau von `_speechChunks` in `loadAndSpeakJsonArticle`:
```dart
final text = (i == 0 && heading.isNotEmpty)
    ? '$heading. ${s.text}'
    : s.text;
_speechChunks.add(text);
_chunkOffsets.add(s.startChar);   // Offset bleibt s.startChar, nicht vom Heading verschoben
_chunkImgIndices.add(s.imageIndex);
```
Heading wird laut gelesen, taucht aber nicht im Artikeltext auf → kein Offset-Fehler.

---

## Zone-Padding Feedback-Loop & Live-Scan-Entscheidung (2026-06-03)

### Das Problem: Zone-Padding Feedback-Loop in Mode A

Mode A blendet den Professor-Bereich am unteren Viewport-Rand ein. Sätze, die in diesen
Bereich fallen, bekommen `extraRightPad = _kProfPad` → schmalere Textbreite → mehr Zeilen
→ Satz wird höher → alle Sätze darunter verschieben sich nach unten.

Würde `_computeProfessorZone` live messen (statt Cache), entsteht ein Feedback-Loop:
1. Messe Position Satz N → in Zone → Padding → Satz N höher
2. Satz N höher → Satz N+1 rutscht in Zone → N+1 bekommt Padding → wird höher
3. N+1 höher → N+1 rutscht aus Zone → kein Padding → kürzer → rutscht rein → …
→ Endlose Oszillation zwischen zwei Layout-Zuständen.

**Fix:** `_sentenceTopCache` / `_sentenceHeightCache` — Snapshot einmalig vor dem ersten
Padding-Auftrag (`_buildCache()` im `initState`-PostFrameCallback). Cache ändert sich nie
→ `_computeProfessorZone` liefert immer dasselbe Ergebnis → keine Oszillation.

### Warum Live-Scan in `_jumpToTopSentence` trotzdem sicher ist

`_jumpToTopSentence` ist **rein lesend** — es ruft nur `seekWithDelay`/`seekToChunk` auf
und schreibt keine Padding-Werte zurück. Deshalb kann ein Live-Scan dort keinen Feedback-
Loop in `_computeProfessorZone` auslösen. `_computeProfessorZone` bleibt cache-basiert und
ist von `_jumpToTopSentence` vollständig entkoppelt.

Mode B hat das Problem nie gehabt: Mode B hat kein `extraRightPad` und kein
`_computeProfessorZone` — der Professor-Bereich ist dort nicht in das Text-Layout integriert.

### Entscheidung (2026-06-03)

`_jumpToTopSentence` in Mode A auf Live-Scan umgestellt (identisch Mode B):
- Satz-Loop: `Scrollable.maybeOf(ctx)` → `vpBox.globalToLocal` → `localY >= 0`
- Box-Loop: identisch, über `_boxKeys`
- `_computeProfessorZone` bleibt unverändert cache-basiert

Gemischter Zustand (live in `_jumpToTopSentence`, cached in `_computeProfessorZone`) ist
stabil: eine minimale Positions-Diskrepanz durch aktives Padding ist möglich (wenige Pixel),
aber kein Stabilitätsproblem.

---

## Vollbild-Zoom: InteractiveViewer → photo_view_plus (2026-06-03)

### Warum InteractiveViewer aufgegeben wurde

Drei überlappende Probleme — alle architekturell unlösbar:

1. **Gesture Arena** (Hauptursache): PageView (HorizontalDragRecognizer) vs. InteractiveViewer
   (ScaleGestureRecognizer). Erster Pointer wird als Drag eingeordnet → PageView gewinnt →
   Pinch wird nie registriert. Nicht fixbar ohne PageView zu ersetzen.

2. **boundaryMargin-Paradox**: `constrained: false` + `boundaryMargin: EdgeInsets.zero` ist
   strukturell unlösbar wenn `displayH < screenH`. Workaround `EdgeInsets.all(double.infinity)`
   + eigenes `_clampedMatrix` in `onInteractionUpdate` kämpft gegen IVs Focal-Point-Mathematik.

3. **Animation-Gesture-Konflikt**: onInteractionEnd-Animation vs. neu beginnender Pinch.

### photo_view_plus Evaluation — Phase 1 Spike (2026-06-03)

Package: `photo_view_plus: ^1.1.1`

**1. Gesture Arena — ✅ GELÖST**
`PhotoViewGestureRecognizer._decideIfWeAcceptEvent`:
- 2 Pointer → always accept → Pinch gewinnt immer
- 1 Pointer → nur accept wenn nicht am Rand (`hitDetector.shouldMove`) → PageView bekommt Edge-Swipes
- `PhotoViewGallery` wraps `PageView.builder` in `PhotoViewGestureDetectorScope` → out-of-box

**2. InteractionPolicy Clamp-Hook — ✅ VORHANDEN**
```dart
PhotoViewInteractionPolicy(
  clampPosition: (metrics, nextPos) => metrics.clampPosition(nextPos),  // Standard reicht
  onGestureEnd: (ctx) => defaultGestureEndPolicy(ctx),  // Spring-Back + Fling
)
```

**3. Limited Cover max 15% Crop — ✅ IMPLEMENTIERBAR**
```dart
class LimitedCoverScale extends PhotoViewScale {
  const LimitedCoverScale();
  @override
  double resolve(Size outerSize, Size childSize) {
    final sc = math.min(outerSize.width / childSize.width, outerSize.height / childSize.height);
    final sk = math.max(outerSize.width / childSize.width, outerSize.height / childSize.height);
    return math.min(sk, sc * 1.18);
  }
}
```
`initialScale: const LimitedCoverScale()`, `minScale: const LimitedCoverScale()`, `strictScale: true`
PV berechnet childSize intern aus `MemoryImage` — kein manuelles imgRatio-Decode nötig!

**4. Doppeltipp 1x↔2.5x an Tippposition — ⚠️ IMPLEMENTIERBAR (~30 Zeilen)**
`disableDoubleTap: true` + `onTapUp` mit Zeit/Distanz-Debounce + eigener AnimController.
Positionsformel (PhotoView-Koordinaten, basePosition=center):
```
outerCenter = Offset(outerSize.width/2, outerSize.height/2)
r = targetScale / currentScale
newPosition = (tapPos - outerCenter) * (1 - r) + currentPosition * r
newPosition = metrics.clampPosition(newPosition)
```
Dann `controller.updateMultiple(position, scale)` in AnimationController-Listener aufrufen.

**Gesamtbewertung: Phase 2 Migration empfohlen.**
Alle 4 Kriterien erfüllt. `MemoryImage(bytes)` funktioniert out-of-box als imageProvider.

---

## Vollbild-Viewer: Implementierung abgeschlossen (2026-06-04, Branch spike/photo-view-plus)

Letzter Commit: `3ce0359`. Nicht gemergt — 3 offene Punkte (siehe STATUS.md).

### Endarchitektur `image_fullscreen_overlay.dart`

**Package:** `photo_view_plus: 1.1.1` (exakter Pin, kein `^`).
`PhotoViewGallery` ersetzt `InteractiveViewer` vollständig.

**Scale-Konfiguration:**
```dart
initialScale: PhotoViewComputedScale.contained
minScale:     PhotoViewComputedScale.contained
maxScale:     PhotoViewComputedScale.covered * 4.0
strictScale:  true
```
`LimitedCoverScale` aus Phase-1-Evaluation NICHT verbaut — `covered * 4.0` reicht für Praxis.

**outerSize — korrekte Quelle:**
`LayoutBuilder` um Gallery → `constraints.biggest` → `_outerSize`.
NICHT `MediaQuery.sizeOf(context)` (stimmt nicht mit PVs internem `scaleBoundaries` überein).

**Doppeltipp — 3-Stufen-Zyklus:**
- Basis = `min(outerW/imgW, outerH/imgH)` (= `PhotoViewComputedScale.contained`)
- Stufe1 = `base * 2.5`
- Max = `max(outerW/imgW, outerH/imgH) * 4.0` (= `covered * 4.0`)
- Zyklus: Basis → Stufe1 → Max → Basis → …
- Entscheidung per `ctrl.scale` (absoluter Wert) gegen `base * 1.05` und `stufe1 * 1.05`

**Tap-Erkennung — raw Listener (nicht PV-onTapDown):**
PVs `onTapDown` feuert nicht im Zoom/Pan-Modus (Gesture-Arena-Problem).
Lösung: `Listener(onPointerDown/Up/Cancel)` um die Gallery.
`_activePointers`-Counter: bei ≥2 Pointern Tap-State sofort verwerfen + Animation stoppen.

**Animation:**
`AnimationController` 220ms easeOut, treibt `ctrl.updateMultiple(scale, position)`.
`_animateTo()` setzt From/To-Felder und ruft `.forward()`.

**Kritischer Bug (onScaleEnd) — Root Cause + Fix:**
PV feuert `onScaleEnd` beim Finger-Heben nach JEDEM Tap, nicht nur nach Pan/Pinch.
`_zoomAnimCtrl.stop()` in `onScaleEnd` → Animation nach 2. Tap-Lift abgebrochen →
`AnimationStatus.completed` nie gefeuert → Scale eingefroren (Beweis aus WISS-Logs).
Fix: `_zoomAnimCtrl.stop()` aus `onScaleEnd` entfernt. Pinch-Stop: in `_onPointerDown`
multi-touch branch (`_activePointers > 1`).

**Basis-Animation ohne Endsprung (setInvisibly):**
`ssCtrl.reset()` notifiziert IGNORABLE Listener → `_blindScaleStateListener` →
`animateOnScaleStateUpdate` → sichtbarer Endsprung.
Fix: `ssCtrl.setInvisibly(PhotoViewScaleState.initial)` + `ctrl.updateMultiple(minScale, Offset.zero)`.

**Focal-Point-Formel:**
```
center = Offset(outerW/2, outerH/2)
p1 = tapPos - center - (tapPos - center - p0) * (s1/s0)
halfX = max(0, (imgW*s1 - outerW)/2)
p1 = Offset(p1.dx.clamp(-halfX,halfX), p1.dy.clamp(-halfY,halfY))
```

**Weitere Features:**
- Weichgezeichneter Hintergrund-Füller (`_kBlurredBackdrop`, `ImageFilter.blur sigma=18`)
- Lautsprecher-Icon gebunden an `provider.isCaptionPlaying` (kein Flackern bei TTS)
- Reset auf Basis + Position-Zero bei Orientierungswechsel (`_onOrientationChanged`)

### Offene Punkte (nächste Session)
(a) Caption-Platzierung: unter dem Bild bei Letterbox, Overlay wenn Bild Höhe füllt.
(b) Pinch-Zoom gelegentlich nicht erkannt — Verdacht: 2-Finger fälschlicherweise als Doppeltipp;
    bei `_activePointers >= 2` Tap-State sofort löschen (bereits in Code, Timing prüfen).
(c) Regressionslauf S23, dann merge `spike/photo-view-plus → main`.
