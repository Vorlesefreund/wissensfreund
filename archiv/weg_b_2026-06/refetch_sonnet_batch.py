#!/usr/bin/env python3
"""refetch_sonnet_batch.py — verarbeitet einen BESTEHENDEN Anthropic-Generierungs-Batch
ohne einen neuen zu erstellen (spart Generierungskosten).

Hintergrund: Ein Stage-2-Sonnet-Batch lief erfolgreich (✓9), das Post-Processing
crashte aber an einem Quote-Defekt → 0 Artikel gespeichert. Der Batch ist serverseitig
~29 Tage abrufbar. Dieses Skript nutzt die ECHTE PHASE-B-Logik aus run_batch.stage2_generierung
(kein Duplikat) und biegt nur den Batch-CREATE-Schritt per Monkeypatch auf den bestehenden
Batch um: batches.create(...) → batches.retrieve(EXISTING_ID).

Damit laufen poll → results → destringify (mit gefixtem Quote-Repair) → Trim/Box/validate/
Bilder → speichern exakt wie im Produktionspfad.

Aufruf: python -X utf8 scripts/refetch_sonnet_batch.py
"""
import sys
from anthropic.resources.messages.batches import Batches

EXISTING_BATCH_ID = "msgbatch_012B94cyKe3Gi8j2P19S1RU5"

# ── Monkeypatch: create() gibt den bestehenden Batch zurück, statt neu zu erstellen ──
_orig_create = Batches.create
def _create_returns_existing(self, *args, **kwargs):
    print(f"[refetch] batches.create abgefangen → nutze bestehenden Batch {EXISTING_BATCH_ID}",
          flush=True)
    return self.retrieve(EXISTING_BATCH_ID)
Batches.create = _create_returns_existing

# ── argv auf den ursprünglichen Stage-2-Lauf setzen, dann run_batch.main() ──
sys.argv = [
    "run_batch.py",
    "--themen", "Erde", "Regenwald", "Wal",
    "--stufen", "1", "2", "3",
    "--output-dir", "articles/wegb_stage1_20260625",
    "--run-id", "wegb_stage1_20260625",
    "--stage", "2",
]

import run_batch  # load_dotenv läuft beim Import (run_batch.py:44)

if __name__ == "__main__":
    try:
        run_batch.main()
    finally:
        Batches.create = _orig_create  # Patch zurücknehmen
