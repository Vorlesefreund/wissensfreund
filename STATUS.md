# Wissensfreund — STATUS
<!-- updated: 2026-06-14T14:51:35Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Round-2 + Merge (2026-06-14): 11/11 R2-Calls, 3542 eindeutige Themen (760 Dubletten), 3427 primary / 96 reserve / 30 exclude, 431 sensibel, 177 Leuchtturm. Dry-Run Avoid-List korrekt (Tiere: 313). Plural-Fix + 5 neue Geschichte-Einträge.** ← AKTUELL

**Katalog-Merge v1 (2026-06-13): 2761 eindeutige Themen, 2681 primary / 66 reserve / 25 exclude, 376 sensibel.**

**Katalog-Batch-Lauf abgeschlossen: 24/24 Gebiete, 3274 Themen roh, 3170 primary / 104 reserve, 447 sensibel, 179 Leuchtturm.**

**Essen & Alltag: 174 Themen (alle primary), 4 sensibel, 5 Leuchtturm. Harness: Extended-Output-Beta (output-128k) für >32k tokens; MAX_TOKENS Default 48k.**

**Religion, Feste & Bräuche: 102 Themen, 100 primary / 2 reserve, 64 sensibel (Gebiet naturgemäß sensibel), 5 Leuchtturm.**

**Märchen, Mythologie & Fabelwesen: 137 Themen (110 primary / 27 reserve), 11 sensibel, 13 Leuchtturm. Harness: Streaming + 32k + dotenv + primary/reserve-Split.**

**Katalog-Phase gestartet (2026-06-13): wissensfreund_rater_kuratierung_v2.md + catalog_rater_harness.py committed. Dry-Run bestanden: 134 Anker geladen, User-Message korrekt. --list zeigt 24 Calls, Budget-Summe 3980.**

**Katalog-Rater-Instruktion wissensfreund_rater_kuratierung_v1.md → v2 (Modell Opus; ~5000 Themen, 24 Calls; Ergiebigkeit gegen 134er-Anker; Eignungs-Rubrik; Kleinstädte vorerst ausgenommen).**

**Eignungs-Gate Runtime: exclude/age_floor/framing_note; EIGNUNG_STRICT-Schalter; eignung_verdicts.json-Loader (Fallback bis Excel). v3.23b: FRAMING-Direktive. Verifikation PASS.**

**Box-Verteilungs-Guard: Lint (Clusterung / kein Mitteldrittel) + Modell-Reparatur-Pass mit Inhalts-Integritätscheck; sonst review_flag. stimmt_das-Pflicht bewusst NICHT eingebaut.**

**Wortzahl-Guard: wmax·1.05-Cap → bis zu 2 Trim-Pässe (Lektor-Prompt) → review_flag. Verifiziert: 238→18W.**

**BKS-Fix: resolve_lemma erkennt Selbst-BKS (pageprops.disambiguation) → _resolve_bks() → BITTE PRUEFEN-Flag.**

### Pipeline-Zustand (generate_grounded.py, Stand 2026-06-12)
Ergiebigkeit verdrahtet ✅ | resolve_lemma im Hauptloop ✅ | Doppelbedeutungs-Direktive ✅
Wortzahl-Guard ✅ | Box-Verteilungs-Guard ✅ | Eignungs-Gate ✅
System-Prompt: v3.23b-production | Modell: gemini-3.5-flash

### Ergiebigkeits-Modell (Detail → WISSEN_ARTIKEL_PIPELINE.md)
`target_S = Wlo + frac·(Whi−Wlo), frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250] S2[80,400] S3[100,650]. Rater = Opus per API, Anker: 134 Themen.

---

## 🔴 Nächster Schritt

**Nächster Schritt:** catalog_review.xlsx öffnen → FREIGABE-Spalte befüllen (431 sensibel + 30 exclude prüfen) → eignung_verdicts.json generieren.
Tiere jetzt 628 primary (größtes Gebiet). Geschichte 197, Länder 212, Technik 237, Naturwiss 230.

---

## 🔴 Offene Punkte (nach Priorität)

Katalog-Lauf (Gebiets-Calls → Merge → Excel-Freigabe → eignung_verdicts.json) — nächster Chat
Dedup (Hai=Haie, Deutschland 3×, Zigarette=Zigaretten; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); test_modelcompare2 Sichtung; Flutter WfArticleListScreen
