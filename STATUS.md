# Wissensfreund — STATUS
<!-- updated: 2026-06-12T18:06:32Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Katalog-Rater-Instruktion wissensfreund_rater_kuratierung_v1.md (Modell Opus; ~5000 Themen, 19 Gebiete; Ergiebigkeit gegen 134er-Anker; Eignungs-Rubrik; Kleinstädte vorerst ausgenommen).** ← AKTUELL

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

**Katalog-Lauf** (neuer Chat): Opus-Calls je Themengebiet + ~20 Anker aus
wortziele_ergiebigkeit_134_v2.xlsx → JSON-Arrays → Merge-Skript →
Excel-Freigabe → eignung_verdicts.json + Katalog ≈ 5000 Themen.

---

## 🔴 Offene Punkte (nach Priorität)

Katalog-Lauf (Gebiets-Calls → Merge → Excel-Freigabe → eignung_verdicts.json) — nächster Chat
Dedup (Hai=Haie, Deutschland 3×, Zigarette=Zigaretten; eigenständige Dino-Arten) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); test_modelcompare2 Sichtung; Flutter WfArticleListScreen
