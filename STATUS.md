# Wissensfreund Status
<!-- updated: 2026-05-25T09:15:01Z -->

## Zuletzt erledigt (Session 2026-05-25)

### Freemium-Modell
- `SubscriptionService` (Free / Plus / Premium) mit SharedPreferences-Cache
- `BillingService.kt` — Google Play Billing 6.2.1, Produkte: `wissensfreund_plus` (INAPP), `wissensfreund_premium` (SUBS)
- Feature-Gates: `canAskQuestions`, `canDownloadMediumQuality`, `canUseHighResOnDemand`
- `_SubscriptionDialog` im Menü mit Upgrade-Cards, Statistiken, Restore-Button
- `question_usage` + `usage_stats` Tabellen in SQLite (Schema v6)

### Menü & Kinderschutz
- Menü-Zugang durch BiometricPrompt gesichert wenn Kiosk aktiv
- Einmalige Auth für alle Menüpunkte (`parentalUnlocked`-Flag — kein zweiter Prompt)

### Onboarding-Kette (Bugfix)
- `StorageManager.initialize()` fehlte vor der Kette → `AssertionError` → Bildqualitäts- und Netzwerk-Dialog wurden nie gezeigt. Gefixt.
- `evictOldCache()` wird jetzt beim App-Start im Hintergrund aufgerufen (war toter Code)

### Bildqualitäts-Dialog
- Speicher-Prüfung via `StatFs` (neuer `getFreeStorageBytes()`-Channel in MainActivity.kt)
- Bei < 2 GB frei: Standard empfohlen, Orange-Warnung, Download-Button deaktiviert
- Fehlermeldungen jetzt sprechend: HTTP 404 → "Bildpaket noch nicht verfügbar" statt "Bitte WLAN prüfen"

### Sonstiges
- `AnimatedSwitcher` Crossfade 200 ms → 300 ms
- `_StorageDialog` Endlos-Spinner gefixt (StorageManager-Init fehlte)
- CHANGES.md + STATUS.md: `<!-- updated: ... -->` Timestamp-System

---

## Offen / Nächste Schritte

### Dringend
- **images_medium.zip**: GitHub Actions Workflow läuft gerade (gestartet 2026-05-25 ~09:10 UTC).
  Fertig in ca. 1h 20 min. Danach ist "Gut"-Bildqualität in der App downloadbar.

### Fehlende Features (aus Prompt-Checkliste)
- **100% Datenlimit-Overlay mit BiometricPrompt**: Limit-reached → aktuell nur stiller Fehler.
  Sperre + Eltern-Authentifizierung zum Entsperren fehlt noch.
- **Upgrade-Flow bei Rückfrage (Free-User)**: `canAskQuestions`-Gate vorhanden,
  aber kein Prompt / kein Dialog wenn Free-User fragt. Wartet auf Gemini-Integration.
- **Speicher-Prüfung im Onboarding**: Empfehlung basiert auf freiem Speicher — ✅ erledigt heute.
  Download-Größe wird noch statisch ("~2 GB") angezeigt, nicht aus Manifest gelesen.

### Design-Ausstände
- **Plus & Premium Dialog**: Neue Designvorgaben vom User angekündigt, noch nicht geliefert.
- **Sound-Thumbnails**: Audio-Infrastruktur fertig; wartet auf Ergebnis des GH-Actions-Runs
  (Audio-Pipeline, läuft parallel zum Images-Job heute).

### Technische Schulden
- `kMonthlyQuestionLimit = 5000` und `addSessionMinutes()` vorhanden aber inaktiv
  (aktivieren wenn Gemini läuft).
- Bottom-Navigation-Bar-Abstand: Fix installiert, aber vom User noch nicht final bestätigt.
