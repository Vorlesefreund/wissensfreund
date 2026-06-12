# Wissensfreund — STATUS
<!-- updated: 2026-06-12T12:09:19Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**WORTZIEL Lauf 3 (pilot_output3): harter Deckel + Auswahlregel — Overshoot bei Kühlschrank gefixt, Vulkan S2 noch leicht drüber (2026-06-12)** ← AKTUELL

`temp/_pilot_gen3.py` → `pilot_output3/` (9/12 Artikel, Hund ausgefallen wegen Connection-Reset).

```
Thema           S   Ziel    Ist       Δ     kB  Comp
-------------------------------------------------------
Dinosaurier     1    250    209     -41   66.4     5  ✓
Dinosaurier     2    400    347     -53   66.4     5  ✓
Dinosaurier     3    650    636     -14   66.4     5  ✓  ← Dino trifft noch ✓
Hund            1    250      —       —      0     0  ✗  (Connection Reset)
Hund            2    400      —       —      0     0  ✗
Hund            3    650      —       —      0     0  ✗
Vulkan          1    217    197     -20   20.9     4  ✓
Vulkan          2    400    461     +61   20.9     4  ⚠  leicht drüber
Vulkan          3    650    644      -6   20.9     4  ✓
Kühlschrank     1     83     79      -4   41.1     4  ✓  (war +40 in Lauf 2)
Kühlschrank     2    240    234      -6   41.1     4  ✓
Kühlschrank     3    375    371      -4   41.1     4  ✓
```

Fazit: Lauf-3-Wording ("Strebe X Wörter an … X ist zugleich die harte Obergrenze") funktioniert gut.
Kühlschrank-Overshoot aus Lauf 2 (+40) vollständig gefixt (jetzt -4).
Vulkan S2 bleibt mit +61 leicht drüber — kleines WP-Primärtext (20.9 kB) + großer Vesuv-Companion (42 kB).
Hund ausgefallen (Netzwerk-Reset während Phase 1 — kein Inhaltsproblem).

**WORTZIEL-Fix verdrahtet + Verifikations-Re-Run 7×3 → pilot_output2/ (2026-06-12)**

WORTZIEL-Wording in `generate_grounded.py` geändert: Obergrenze → angestrebte Länge.
`temp/_pilot_gen2.py` → `pilot_output2/` (21 Artikel). Ergebnis: starke Verbesserung bei
inhaltsreichen Themen; Overshoot bei Vulkan S3 +198 und Kühlschrank S1 +40.

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

**Vulkan S2-Overshoot analysieren** (Δ+61 trotz Lauf-3-Deckel) — vermutlich Vesuv-Companion-Übergewicht.
Ggf. Companion-Char-Cap bei kleinen Zielen reduzieren, oder Vesuv aus Kompass ausschließen wenn Wmax<300.
Dann: WORTZIEL_TABLE durch dynamische imp_S-Berechnung aus importance_cache_33.json ersetzen.
Hund mit neuem Lauf nachziehen (3 fehlende Artikel).

---

## 🔴 Offene Punkte (nach Priorität)

1. **Vulkan S2 Overshoot** untersuchen (Companion-Cap oder Kompass-Filter für große Companions)
2. **Hund-Nachziehen** (3 fehlende Artikel aus Lauf 3 — Netzwerk-Retry genügt)
3. **WORTZIEL_TABLE → dynamisch** (imp_S aus importance_cache_33.json verdrahten)
4. **resolve_lemma in generate_grounded.py** einbauen (vor fetch_wikipedia_text, Z. 746)
5. **Pilotartikel reviewen** → pilot_output3/*.md
6. **Sichtung** test_modelcompare2 — Qualitätsvergleich 3 Modelle
7. Flutter-App testen: WfArticleListScreen mit R2-Artikeln
