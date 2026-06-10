# Lektorat Catch-Test Ergebnisse

Goldset: 4 Slips (L1–L4) × 6 Kontrollen (K1–K6)

## Übersicht

| Verifizierer | Catch-Rate | FP-Rate | Verpasste Slips | Falsch-Positive |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 4/4 | 1/6 | — | K6 |
| Claude Haiku 4.5 | 2/4 | 0/6 | L1, L2 | — |
| Gemini 3.1 Pro | 3/3 (+1 Fehler) | 0/6 (+1 Fehler) | — | — |

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
- ✓ K5 korrekt (BELEGT)
- ✗ **K6 FALSCH-POSITIV** (ÜBERZOGEN) gold=BELEGT
  > Die ersten Menschen kamen vor mindestens 16.000 Jahren über die Landbrücke Berin
  > Begründung: Die Quelle belegt zwar, dass die Besiedlung Amerikas 'mehrere Einwanderungswellen umfasst, die minde

## Claude Haiku 4.5

Modell-ID: `claude-haiku-4-5-20251001`

### Slips

- ✓ **L3 GEFANGEN** (NICHT_BELEGT) gold=ÜBERZOGEN
  > Die Pocken töteten neun von zehn Ureinwohnern — das entspricht etwa 90 Prozent d
- ✓ **L4 GEFANGEN** (WIDERSPRUCH) gold=WIDERSPRUCH
  > Marterpfähle gab es gar nicht — das ist nur ein Vorurteil aus alten Filmen.
- ✗ **L1 VERPASST** (BELEGT) gold=ÜBERZOGEN
  > Eine berühmte Vermittlerin zwischen den Völkern war Pocahontas, die Tochter eine
- ✗ **L2 VERPASST** (BELEGT) gold=NICHT_BELEGT
  > Die Maya entwickelten eine eigene Schrift und tiefes Wissen über die Sterne.

### Kontrollen

- ✓ K1 korrekt (BELEGT)
- ✓ K2 korrekt (BELEGT)
- ✓ K3 korrekt (BELEGT)
- ✓ K4 korrekt (BELEGT)
- ✓ K5 korrekt (BELEGT)
- ✓ K6 korrekt (BELEGT)

## Gemini 3.1 Pro

Modell-ID: `gemini-2.5-pro`

### Slips

- ✓ **L2 GEFANGEN** (ÜBERZOGEN) gold=NICHT_BELEGT
  > Die Maya entwickelten eine eigene Schrift und tiefes Wissen über die Sterne.
- ✓ **L3 GEFANGEN** (NICHT_BELEGT) gold=ÜBERZOGEN
  > Die Pocken töteten neun von zehn Ureinwohnern — das entspricht etwa 90 Prozent d
- ✓ **L4 GEFANGEN** (WIDERSPRUCH) gold=WIDERSPRUCH
  > Marterpfähle gab es gar nicht — das ist nur ein Vorurteil aus alten Filmen.
- ⚠ L1 FEHLER: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand 

### Kontrollen

- ✓ K1 korrekt (BELEGT)
- ✓ K2 korrekt (BELEGT)
- ✓ K3 korrekt (BELEGT)
- ✓ K4 korrekt (BELEGT)
- ✓ K5 korrekt (BELEGT)
- ✓ K6 korrekt (BELEGT)
