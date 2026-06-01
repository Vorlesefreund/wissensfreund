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

## Wichtige Designentscheidungen (nicht rückgängig machen)

- **Kein Doppel-Renderer** — ZIM-Artikel werden per `convert_zim_to_json.py` konvertiert, dann identisch behandelt
- **Kein `viewPadding.bottom` manuell berechnen** — immer `SafeArea()` verwenden
- **Staging-Dir-Pattern** für Downloads — `.new/` Verzeichnis, atomarer Austausch am Ende
- **Plausibilitätsprüfung manuell** — Claude Code/Chat macht Fehler bei großen Zahlen, Andreas prüft selbst
