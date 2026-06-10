# Lektorat Catch-Test Ergebnisse

Goldset: 4 Slips (L1–L4) × 6 Kontrollen (K1–K6)

## Übersicht

| Verifizierer | Catch-Rate | FP-Rate | Verpasste Slips | Falsch-Positive |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 4/4 | 2/6 | — | K5, K6 |

---

## Claude Sonnet 4.6

Modell-ID: `claude-sonnet-4-6`

### Slips

- ✓ **L1 GEFANGEN** (NICHT_BELEGT) gold=ÜBERZOGEN
  > Eine berühmte Vermittlerin zwischen den Völkern war Pocahontas, die Tochter eine
- ✓ **L2 GEFANGEN** (NICHT_BELEGT) gold=NICHT_BELEGT
  > Die Maya entwickelten eine eigene Schrift und tiefes Wissen über die Sterne.
- ✓ **L3 GEFANGEN** (NICHT_BELEGT) gold=ÜBERZOGEN
  > Die Pocken töteten neun von zehn Ureinwohnern — das entspricht etwa 90 Prozent d
- ✓ **L4 GEFANGEN** (WIDERSPRUCH) gold=WIDERSPRUCH
  > Marterpfähle gab es gar nicht — das ist nur ein Vorurteil aus alten Filmen.

### Kontrollen

- ✓ K1 korrekt (BELEGT)
- ✓ K2 korrekt (BELEGT)
- ✓ K3 korrekt (BELEGT)
- ✓ K4 korrekt (BELEGT)
- ✗ **K5 FALSCH-POSITIV** (NICHT_BELEGT) gold=BELEGT
  > 2024 bat US-Präsident Biden die indigenen Völker Amerikas wegen der Internate of
  > Begründung: Die Quelle nennt als Anlass «Misshandlungen an von der US-Regierung betriebenen Internaten», nicht «
- ✗ **K6 FALSCH-POSITIV** (NICHT_BELEGT) gold=BELEGT
  > Die ersten Menschen kamen vor mindestens 16.000 Jahren über die Landbrücke Berin
  > Begründung: Die Quelle sagt nicht, dass die ersten Menschen »vor mindestens 16.000 Jahren« ankamen. Sie sagt: »D
