# Wissensfreund — STATUS
<!-- updated: 2026-06-10T19:46:31Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**BKS-Guard in fetch_wikipedia_text (2026-06-10)** ← AKTUELL

### BKS-Guard: Begriffsklärungsseiten erkennen + auflösen
- `generate_articles.py`: `fetch_wikipedia_text` prüft jetzt `pageprops=disambiguation`.
  Bei BKS: Wikitext holen, Links in Erscheinungsreihenfolge extrahieren (nicht prop=links,
  das alphabetisch sortiert), erste 5 NS-0-Kandidaten per prop=info größenmäßig vergleichen,
  größten Artikel neu fetchen.
- Logging: Redirect immer sichtbar (INFO), BKS-Auflösung als WARNING + "BITTE PRÜFEN".
- Guard-Tiefe: _bks_depth=1 verhindert verkettete BKS-Rekursion.
- Verifiziert: Apfel→Kulturapfel (49K), Schmetterling→Schmetterlinge (81K).
  Nicht-BKS-Themen (Vulkan, Hund, Dinosaurier) unverändert.
  Redirect-Log "Hund -> Haushund" sichtbar.

**503-Härtung + Robuste Phase-2-Generierung (2026-06-10)**

### 503-Härtung: Phase 2 sequenziell
- `generate_grounded.py`: Phase-2-Loop von ThreadPoolExecutor auf sequenziell umgestellt.
  Sequenziell verhindert den 503-Burst (3 gleichzeitige Calls → Free-Tier-Rate-Limit).
  Verifiziert: 0 × 503 in Phase 2 (war: 1-3 × pro Lauf mit parallelen Calls).

### Robuste Generierung: finish_reason + outer retry
- `gemini_client.py`: finish_reason-Check nach Response — wenn nicht STOP (MAX_TOKENS/SAFETY),
  RuntimeError → wird als retryable erkannt. `_retry_wait`: 30/60/120/240s (war 60/120/240/300).
  `RETRY_ATTEMPTS`: 4 (war 6).
- `generate_grounded.py` `generate_one_level`: outer retry loop (4 Versuche, 30/60/120/240s).
  Jeder Versuch: call_gemini → JSON-Parse → Plausibilitätsprüfung (Sections ≥ 1, Sätze ≥ 3).
  Bei Fehler: Retry. Nach 4 Fehlschlägen: return None, FEHLGESCHLAGEN — NIE partiellen Artikel
  schreiben. Fehlgeschlagene Stufen loggen + zusammenfassen, Rest-Lauf läuft weiter.
  user_msg lazy gebaut (auch für Wortzahl-Retry korrekt).
- Verifiziert: L3 JSON-Parse-Fehler bei Versuch 1 → Retry-Wait 30s → Versuch 2 erfolgreich.
  Alle 3 Stufen vollständig gespeichert. Cache-Hit L2/L3 ✓. DELETE 200 OK ✓.

### Phase-2-Timing nach Umbau
- Sequenziell (inkl. 1 × Retry 30s): ~215s — war ~96s parallel (aber 1-2 Truncations/Lauf).
- Tradeoff: Zuverlässigkeit > Rohgeschwindigkeit auf Free-Tier gemini-3.5-flash.

### Vorgänger: Cache-Hygiene + Phase-2-Parallel (2026-06-10)
- Cache TTL 15 Min + finally-Delete. Parallelisierung (ThreadPoolExecutor).

### Gemini-Cache-Hygiene
- `generate_grounded.py`: Phase-2 + Lektorat + Artikel-Schreiben in `try/finally` eingewickelt.
  `finally`: `client.caches.delete(name=gemini_cache)` — löscht Cache nach Themenlauf auch bei Fehler.
  TTL von 3600s auf **900s (15 Min)** gesenkt — Backstop für harte Abstürze vor finally.
- Verifikation: `DELETE .../cachedContents/... HTTP/1.1 200 OK` im Log ✓.
  Nach Lauf: `client.caches.list()` → 0 verbleibende Caches ✓.
  (API-Signatur-Fix: `client.caches.delete(name=...)` statt positivem Argument.)



### Phase 2 parallel (concurrent.futures)
- `generate_grounded.py`: `ThreadPoolExecutor(max_workers=len(topic_jobs))` — alle Stufen gleichzeitig.
  Reihenfolge nach age_level sortiert vor Lektorat. Wandzeit L1-L3: ~96s (war ~131s sequenziell).

### Lektorat Sync als Default (--lektorat-batch für Batch-API)
- `lektorat_common.py`: `run_lektorat_sync` — sequenziell, direkte API-Calls (kein Polling).
  Sequenziell BEWUSST: L1 schreibt Anthropic-KV-Cache (create=60765), L2+L3 lesen ihn (read=60765).
- `generate_grounded.py`: Default = `run_lektorat_sync`; `--lektorat-batch` → `run_lektorat_batch`.
  Lektorat-Wandzeit: ~212s sequenziell (Batch war ~134s, aber dort kein garantierter Cache-Hit).

### Gemini-Cache Fix: system_instruction-Konflikt
- `gemini_client.py`: Bei `cached_content` wird `system_instruction` NICHT in GenerateContentConfig
  gesetzt (API 400 sonst — system_instruction muss im Cache stehen, nicht doppelt im Request).

### Cache-Verifikation (Lauf Indianer L1-L3, --skip-images)
- Gemini: `prompt=54905, cached=54858` → **99,9 % Cache-Hit** | nur 128 Zeichen Suffix gesendet.
- Anthropic: L1 `create=60765 read=0` → L2 `create=0 read=60765` → L3 `create=0 read=60765` ✓.

### Vorgänger: Prompt-Caching Grundaufbau + Catch-Test-Fix (2026-06-10)
- Caching: build_lektorat_parts, run_lektorat_batch mit cache_control, _split_grounded_user_message,
  try_create_gemini_cache, generate_one_level(gemini_cache=...). Catch-Test: 4/4 ✓.
- Stufe-2-Prompt: BELEGT-BEDINGUNG, VERBUND-REGEL. Catch-Test-Fix: box.text-Bug, ["Schrift"].

---

## 🔴 Nächster Schritt (Hoch)

**Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
- **3-flash-preview L3 Fix**: max_output_tokens explizit setzen (Thinking frisst Budget)
- **Sichtung** test_v323 — WORTZIEL-Erstlauf
- **generate_grounded.py Re-Run** biene_l3 + demokratie_l1

### Mittel
- **Flutter-App testen**: WfArticleListScreen mit R2-Artikeln
- **Related Terms**: prepare_articles.py befüllt sie noch nicht

### Niedrig
- Primärkategorie-Konvention, Box-Key, ZIM→JSON Decode-Cap
- artikel_pipeline.yml Pfad-Bug (python scripts/ statt python root)

---

## Pipeline-Architektur (Referenz)

| Skript | Rolle | Status |
|---|---|---|
| `prepare_articles.py` | Batch-Vorbereitung (Job-JSONs) | Produktion |
| `generate_articles.py` | Artikel-Generierung (Claude/Gemini) | Produktion |
| `upload_articles.py` | Index + R2-Upload | Produktion |
| `generate_grounded.py` | Lokaler Test: Kompass-Grounding + Lektorat | Aktiv (Entwicklung) |

Produktions-Workflow: `.github/workflows/artikel_pipeline.yml` (manuell, kein Schedule)

---

## 🧊 Reserve / auf Eis
- **Klexikon-Quiz-Run**: Checkpoint (609 Einträge) auf R2

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel, Audio-Pipeline, Links/Topic-Tree, Upgrade-Dialog
