# Archiv: Weg B (Gemini → Claude-Generierung) — verworfen, Juni 2026

## Was Weg B war
Migration der **Artikel-Generierung** von Gemini Flash auf Anthropic-Claude-Modelle.
Motiv: `gemini-3.5-flash` war über längere Zeit instabil (503 / Service-Erschöpfung,
zeitweise ~30 h nicht zuverlässig nutzbar). Um die Pipeline davon unabhängig zu machen,
wurden die Generierungs-Stufen (Generator, Lemma, Kompass, Trim, Box-Repair) versuchsweise
auf Claude umgeroutet — Generator zuletzt auf `claude-sonnet-4-6`, gesteuert über
`scripts/stage_models.py` und `scripts/claude_client.py` (forced tool-use JSON-Wrapper).

## Warum verworfen
Sonnet als **Generator** war stilistisch **nicht kindgerecht / nicht flüssig genug**:
faktenlastig statt erzählend, Erzählbögen zerfielen in Aufzählungen, Brüche an
Abschnitts- und Box-Grenzen. Getestet an **Erde S1/S2/S3** über mehrere kuratierte
Prompt-Iterationen:

- `sonnet_v1` — pro-narrativ (Leitsatz „erzählen statt definieren")
- `sonnet_v2` — Erzählbogen + Brückensätze + Box-Platzierungsregel
- `sonnet_v3` — „Bogen vor Fakten-Quote" (Fakten weglassen erlaubt, Moderatorenfragen/
  Klammer-Prozente verboten)
- `gemini_v1` — Geminis eigener Prompt (1:1) auf Sonnet, zum Stil-Gegentest

Ergebnis (Product-Owner-Urteil): keine Fassung erreichte das Flash-Niveau bei
Lebendigkeit **und** Zusammenhang. Einzelne Befunde wurden behoben (Moderatorenfragen,
Klammer-Prozente), das Kernproblem (faktenlastiger, weniger flüssiger Erzählstil)
blieb. Entscheidung: **Projekt eingefroren, Generierung zurück auf Gemini Flash + v4**,
bis Gemini Flash wieder zuverlässig ist.

## Inhalt dieses Archivs
- `wissensfreund_generator_prompt_sonnet_v1.md` / `_v2.md` / `_v3.md` — die Sonnet-Generator-Prompts
- `wissensfreund_generator_prompt_gemini_v1.md` — Geminis Prompt (Stil-Gegentest auf Sonnet)
- `refetch_sonnet_batch.py` — Helfer zum kostenfreien Re-Fetch eines bestehenden Anthropic-Batch

## Was im Repo bleibt (dormant)
- `scripts/claude_client.py` — anbieter-neutraler JSON-Wrapper (forced tool-use). Bleibt am Ort,
  wird vom **Vision-Recheck (Opus)** weiterhin gebraucht (der ist pre-Weg-B und providerunabhängig).
- `scripts/test_sonnet_batch.py` — Weg-B-Test, bleibt am Ort (dormant).
- `scripts/stage_models.py` — bleibt als zentraler Provider/Modell-Single-Point; alle
  Generierungs-Stufen stehen wieder auf `gemini` (Vision-Recheck/Lektorat weiterhin Claude,
  da pre-Weg-B). Reaktivierung von Weg B = Stufen dort zurück auf `anthropic` schalten.

## Reaktivierungsbedingung
Siehe `PROJEKTDOKUMENT.md` (Weg-B-Kapitel) — Weg B wird erst wieder erwogen, wenn ein
Claude-Generator den kindgerechten Erzählstil erreicht ODER Gemini Flash dauerhaft ausfällt.
