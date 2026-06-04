# Claude Chat — Übergabe-Notizen

<!-- Von Claude Code geschrieben; Claude Chat liest diese Datei beim Session-Start -->
<!-- Zuletzt aktualisiert: 2026-06-04 -->

---

## Session-Abschluss 2026-06-04 — Claude Code

### Was wurde erledigt

**1. quiz_and_upload.yml — Auto-Trigger entfernt (commit 2cc9779)**
- `workflow_run:`-Trigger komplett entfernt; Workflow startet nur noch manuell (`workflow_dispatch`).
- Grund: Quizze sind ein Hedge auf Eis (~95–145 € für ~2.935 Artikel, Kosten-Schutz).
- Warnhinweis im YAML eingebaut: Vor Aktivierung R2-Checkpoint
  `staging/checkpoints/quiz_checkpoint.json` löschen — sonst 609 Artikel übersprungen
  und mit Platzhalter-Quizzen ausgeliefert (Checkpoint-Falle).
- Job-Level `if:` vereinfacht auf `if: github.event_name == 'workflow_dispatch'`.

**2. Erster Doku-Checkpoint (commit 4c33e72)**
Auftrag aus CLAUDE_CODE_DOKU_CHECKPOINT.md:
- WISSEN_ARTIKEL_PIPELINE.md: Viele Abschnitte neu/ergänzt — Content-Sicherheit Text/Bilder,
  Qualitäts-Methodik, Stimmt-das-Regel, living_being-Pflichtmuster, CONTENT_DEPTH +
  TOPIC_INTEREST als implementiert bestätigt, System-Prompt-Versionslinie v3.2→v3.3→v3.4,
  R2-Koexistenz-Konflikt, Mengenziele, Quiz-Strategie.
- WISSEN_BILDER.md: Content-Sicherheit (Bilder/Kinderschutz) + Lizenz/Attribution ergänzt.
- System-Prompt v3.4 auditiert (nur gelesen, NICHT geändert). 3 Lücken gefunden.
- STATUS.md aktualisiert.

**3. Zweiter Doku-Checkpoint — Wortgrenzen-Fix (commit 655c86d)**
Auftrag aus CLAUDE_CODE_DOKU_CHECKPOINT(1).md — KORRIGIERT den ersten Checkpoint:
- WISSEN_ARTIKEL_PIPELINE.md: Wortgrenzen-Tabelle ersetzt.
  - ALT (falsch): Fließtext-only, ~200/~500/~900 Wörter
  - NEU (korrekt, MASSGEBLICHER STAND, Entscheidung 02.06.):
    Zählregel: **Fließtext + Boxen zusammen, OHNE Quiz**
    Interest-gestaffelt (low / medium / high über TOPIC_INTEREST):
    - Stufe 1 (4–6 J.): 50–100 / 100–150 / 150–250 Wörter
    - Stufe 2 (7–9 J.): 80–150 / 150–250 / 250–400 Wörter
    - Stufe 3 (10–12 J.): 100–200 / 200–350 / 350–650 Wörter
    low-interest bewusst niedrig — für wenig ergiebige Themen.
- STATUS.md: Timestamp + Beschreibung des Wortgrenzen-Fixes korrigiert.

---

### System-Prompt v3.4 — Audit-Ergebnis (nur lesen, NICHT ändern)

| Regel | Vorhanden? | Stelle |
|---|---|---|
| Eiserne Regel (nur Wikipedia-Text) | ✅ | Abschnitt 1 |
| Alterseignung: Ungeeignetes weglassen | ❌ fehlt | — |
| Interessantheits-Methodik + Alters→Filter-Raster | ❌ fehlt | — |
| Wortgrenzen interest-gestaffelt, inkl. Boxen ohne Quiz | ⚠️ Tabelle vorhanden (Z.56–73), genaue Werte gegen 02.06.-Stand prüfen | Z.56–73 |
| Stimmt-das-Klischee-Regel + Titel-Doppelverbot + Brückensatz-Regel | ✅ | Abschnitt 5 |
| living_being Stufe-3-Rollen | ⚠️ Basis vorhanden, Stufe-3-Erweiterung unklar | Abschnitt 4 |
| CONTENT_DEPTH steuert Abschnittszahl | ✅ | Abschnitt 3 |
| categories[] Array | ✅ | Schema-Abschnitt |
| Quiz: 3/4 Fragen, A/B/C, correct_key gleichverteilt | ✅ | Quiz-Abschnitt |
| related_terms core/discover | ✅ | Schema-Abschnitt |
| Stufe-1-Perspektivregel (kein Kleiner-Machen) | ✅ | Stufe-1-Abschnitt |
| Sound-Objekt in images[] | ⚠️ nicht explizit | — |

**Prompt NICHT anfassen bis Code↔Prompt-Abgleich abgeschlossen** (generate_articles.py
sendet noch v3.2-Felder: TOPIC_INTEREST statt TOPIC_APPEAL/TOPIC_FAMILIARITY;
WIKIPEDIA_LINKS, ARTICLE_INDEX, IMAGE_METADATA fehlen).

---

### Offene Aufgaben (Priorität wie in STATUS.md)

**Hoch — Kinderschutz:**
- Content-Sicherheitsfilter Bilder entscheiden: Reicht dateiname-basierter Claude-Filter,
  oder braucht es Wikipedia-Kategorienabruf (prop=categories auf Commons) + Vision-API?
  Stufen 2 + 3 der dreistufigen Filterung existieren nicht als aktiver Code.
  Vor erstem produktiven Bilder-Patch-Run klären.

**Hoch — Pipeline unlauffähig:**
- `generate_articles.py` sendet v3.2-Felder; v3.4 erwartet andere Felder → Code anpassen.
- `wissensfreund_system_prompt.md` (kanonischer Name ohne Version) existiert nicht im Repo;
  Workflow `artikel_pipeline.yml` zeigt darauf → Pipeline würde sofort scheitern.

**Mittel:**
- R2-Koexistenz: `upload_articles.py` nutzt `rclone sync` auf gemeinsamen `articles/`-Pfad
  → ZIM und Wikipedia-Artikel würden sich gegenseitig überschreiben.
  Entscheidung steht: getrennte Präfixe. Implementierung noch offen.
- Bilder-Patch (`patch_article_images_v1.py`) — erst nach Kinderschutz-Entscheidung.
- Spare-Klon `C:\Users\Andreas\Wissensfreund\wissensfreund_app` entfernen (~2026-06-18).

**Niedrig / Klärungsbedarf:**
- Box-Key: `myth` vs. `stimmt` vs. `stimmt_das` — kanonischer Key im Schema festklopfen.
- Primärkategorie-Konvention: erste in Liste vs. `primary: true`.

---

### Letzte Commits (diese Session)

| Commit | Beschreibung |
|---|---|
| 2cc9779 | quiz_and_upload.yml: Auto-Trigger entfernt, nur manuell (Hedge-Schutz) |
| 4c33e72 | WISSEN_ARTIKEL_PIPELINE.md + WISSEN_BILDER.md + STATUS.md (erster Checkpoint) |
| 655c86d | Wortgrenzen-Fix: interest-gestaffelt, inkl. Boxen ohne Quiz (zweiter Checkpoint) |
