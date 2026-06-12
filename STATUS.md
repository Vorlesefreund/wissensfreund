# Wissensfreund — STATUS
<!-- updated: 2026-06-12T16:04:05Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Wortzahl-Guard: Post-Gen >Cap (wmax·1.05) → bis zu 2 Trim-Pässe (eigenes Lektor-Prompt), danach review_flag. Sichert harte Stufen-Obergrenze deterministisch. py_compile + import PASS.** ← AKTUELL

**BKS-Fix: resolve_lemma erkennt Selbst-Begriffsklärungen (pageprops.disambiguation) und löst via _resolve_bks auf substanziellsten Link auf, geflaggt BITTE PRUEFEN: BKS … (→ Review-Flag). Verifiziert: Schmetterling → Schmetterlinge, Apfel → Kulturapfel; Hund-Kontrolle ohne BKS-Flag.**

**Doppelbedeutungs-Direktive wirksam: v3.23-Prompt dokumentiert DOPPELBEDEUTUNG-Feld + build_grounded_user_message injiziert die Zeile in den stabilen Prefix. Plumbing-Test PASS.**

**resolve_lemma im Hauptloop verdrahtet (Part B): primaer_wikipedia wird jetzt aufgelöst (Redirect/BKS/Listen/Lemma-Wechsel); Lemma-Flags → review_flag; Doppelbedeutungs-Direktive diagnostisch am Job (nicht injiziert). py_compile + import PASS.**

**Ergiebigkeit verdrahtet (Part A+A.2): Wortbudget + Appeal-Tier (Companion/Bild) beide aus ergiebigkeit_scores.json; Klexikon-Appeal entfernt. Verifikation Wörter+Appeal gegen xlsx-Ground-Truth PASS.**

**Lauf 3 (pilot_output3): WORTZIEL-Wording auskonvergiert — Deckel hält (Vulkan S3 644/650, Kühlschrank punktgenau), Dino-Kontrolle ok. Rest: Vulkan S2 461/400 → gehört in Wortzahl-Guard. Hund nachgeholt nach Connection-Reset.**

`temp/_pilot_gen3_hund.py` → `pilot_output3/Hund_S{1,2,3}.md`. Netzwerk-Retry (3 Versuche, 2s/5s/10s) um prepare_topic_sources ergänzt.

```
Thema           S   Ziel    Ist       Δ     kB  Comp
-------------------------------------------------------
Dinosaurier     1    250    209     -41   66.4     5  ✓
Dinosaurier     2    400    347     -53   66.4     5  ✓
Dinosaurier     3    650    636     -14   66.4     5  ✓  ← Dino-Kontrolle ok
Hund            1    250    188     -62   78.1     4  ✓
Hund            2    400    363     -37   78.1     4  ✓
Hund            3    650    667     +17   78.1     4  ✓  ← nah an 650, leicht drüber
Vulkan          1    217    197     -20   20.9     4  ✓
Vulkan          2    400    461     +61   20.9     4  ⚠  → Wortzahl-Guard
Vulkan          3    650    644      -6   20.9     4  ✓
Kühlschrank     1     83     79      -4   41.1     4  ✓
Kühlschrank     2    240    234      -6   41.1     4  ✓
Kühlschrank     3    375    371      -4   41.1     4  ✓
```

**WORTZIEL-Fix verdrahtet + Verifikations-Re-Run 7×3 → pilot_output2/ (2026-06-12)**

WORTZIEL-Wording in `generate_grounded.py` geändert: Obergrenze → angestrebte Länge.
`temp/_pilot_gen2.py` → `pilot_output2/` (21 Artikel). Overshoot bei Vulkan S3 +198 und Kühlschrank S1 +40.

**Wortbudget-Kalibrierung abgeschlossen (2026-06-11/12)**

33 Themen re-scored mit content_richness_v2 (wc=0 optimal).

### Ergiebigkeits-Modell (aktuell — Detail in WISSEN_ARTIKEL_PIPELINE.md)
Länge = Claude-bewertete ERGIEBIGKEIT (spannend+unterhaltsam+wissenswert, Kind-Neugier),
NICHT Flash, NICHT Wichtigkeit. Claude 0,74 vs Flash 0,53 ggü. Andreas' Noten.
`target_S = Wlo + frac·(Whi−Wlo),  frac = clamp((score−2)/6, 0, 1)`
Bänder: S1[50,250]  S2[80,400]  S3[100,650]   (Score 8 = Limit, 9–10 sättigen)
Boost (nur nach oben): Lebens-Zentralität/Strategie/Heimat → Wirtschaft, Gemüse, Markt,
  Lexikon, Düsseldorf; Sockel für dt. Orte + Herkunftssprachen.
Füllbarkeit = Generator-Prompt-Regel (Wortziel ausschöpfen, nie aufblähen), kein Modul.
Rater = Opus-Klasse-Claude per API, verankert an die 134 (wortziele_ergiebigkeit_134_v2.xlsx).
WORTZIEL-Wording auskonvergiert (Lauf 1–3): Deckel hält weitgehend selbst; Rest (Vulkan S2 +61,
Hund S3 +17) → Wortzahl-Guard.

### Rang-Tabelle 33 (Pilot-Themen fett)

Hinweis: f-Spalten sind Flash-Importance (alt). Werden beim Voll-Rating durch Ergiebigkeits-Scores ersetzt. W-Spalten (Bänder) bleiben gültig.

| # | Thema | f:S1/S2/S3 | **W1/W2/W3** |
|---|---|---|---|
| 1 | Dinosaurier | 10/10/9 | **250/400/650** |
| 2 | Vulkan | 7/10/10 | **217/400/650** |
| 3 | Indianer | 6/9/8 | **183/400/650** |
| 4 | Elefant | 9/8/6 | **250/400/650** |
| 5 | Hund | 10/8/6 | **250/400/650** |
| 9 | Fußball | 6/8/8 | **183/400/650** |
| 11 | Schmetterling | 8/7/5 | **217/347/467** |
| 18 | Pangolin | 3/6/7 | **117/293/467** |
| 24 | Düsseldorf | 1/2/3 | **217/400/650** |
| 28 | Kühlschrank | 2/4/5 | **83/240/375** |
| 29 | Wirtschaft (test) | — | **117/347/650** |
| 33 | Viereck | 2/2/2 | **117/187/283** |

---

## 🔴 Nächster Schritt (höchste Priorität)

Ergiebigkeits-Formel verdrahten in generate_grounded.py: WORTZIEL_TABLE durch dynamische
target_S-Berechnung (Kurve + Boost) ersetzen; Ergiebigkeits-Scores aus Rater-Lauf einlesen.
Parallel: resolve_lemma vor prepare_topic_sources() einbauen.

---

## 🔴 Offene Punkte (nach Priorität)

Ergiebigkeits-Formel verdrahten (Kurve+Boost ersetzt WORTZIEL_TABLE) ✅ — resolve_lemma einbauen ✅
Wortzahl-Guard (Post-Gen >Cap → Trim-Pass) ✅
Box-Regeln im Generator-Systemprompt: stimmt_das-Pflicht (S2/S3) + Verteilung (keine End-Clusterung)
Katalog: Claude kuratiert+bewertet+kategorisiert ~5000 Themen (verankert an die 134), Round-Robin-Reihenfolge
Eignungs-/Framing-Gate (Nazis, Erotik, Negerkuss→Schaumkuss, Homosexualität/Geschlechtsorgane altersgerecht, politisch neutral) — Vor-Bulk
Dedup (Hai=Haie, Deutschland 3×, Zigarette=Zigaretten; bekannte Dino-Arten eigenständig, obskure als Companion) — Vor-Bulk
3-flash-preview L3 Fix (max_output_tokens explizit); test_modelcompare2 Sichtung; Flutter WfArticleListScreen mit R2-Artikeln
