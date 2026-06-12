# Wissensfreund — STATUS
<!-- updated: 2026-06-12T12:19:20Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Lauf 3 (pilot_output3): WORTZIEL-Wording auskonvergiert — Deckel hält (Vulkan S3 644/650, Kühlschrank punktgenau), Dino-Kontrolle ok. Rest: Vulkan S2 461/400 → gehört in Wortzahl-Guard. Hund nachgeholt nach Connection-Reset.** ← AKTUELL

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

### Finalisierte Formel (wc=0, noch NICHT in generate_grounded.py verdrahtet)
```
fasc_norm_S  = (flash_S − 1) / 9
importance_S = fasc_norm_S              ← wc=0 optimal

Klexikon-Abwesenheits-Deckel, NUR S2/S3, NUR wenn KlexW fehlt:
  importance_S = min(importance_S, 0.25 + 0.5·importance_S)

target_S = Wlo + importance_S · (Whi−Wlo)
  S1[50,250] / S2[80,400] / S3[100,650]
```

---

## 🔴 Nächster Schritt (höchste Priorität)

**Vulkan S2 Wortzahl-Guard**: Δ+61 (461/400) trotz Lauf-3-Deckel — Vesuv-Companion 42 kB dominiert bei kleinem WP (20.9 kB). Optionen: (a) Companion-Char-Cap proportional zu wmax, (b) große Companions kürzen wenn wmax<300, (c) post-hoc Wortcount-Check mit Retry.
Dann: WORTZIEL_TABLE → dynamisch (imp_S aus importance_cache_33.json).

---

## 🔴 Offene Punkte (nach Priorität)

1. **Vulkan S2 Wortzahl-Guard** (Companion-Cap bei kleinen Zielen)
2. **WORTZIEL_TABLE → dynamisch** (imp_S aus importance_cache_33.json verdrahten)
3. **resolve_lemma in generate_grounded.py** einbauen (vor fetch_wikipedia_text, Z. 746)
4. **Pilotartikel reviewen** → pilot_output3/*.md
5. **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
6. Flutter-App testen: WfArticleListScreen mit R2-Artikeln
