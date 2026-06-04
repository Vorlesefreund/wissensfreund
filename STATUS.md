# Wissensfreund — STATUS
<!-- updated: 2026-06-04T19:47:29Z -->
<!-- Älteres Wissen → WISSEN_BILDER.md / WISSEN_ARTIKEL_PIPELINE.md / WISSEN_APP_ARCHITEKTUR.md -->

---

## ✅ Zuletzt abgeschlossen

**Dokumentations-Checkpoint (2026-06-04)**
- WISSEN_ARTIKEL_PIPELINE.md reconciled: Wortgrenzen-Fix (interest-gestaffelt, inkl.
  Boxen ohne Quiz, MASSGEBLICHER STAND Entscheidung 02.06.), Content-Safety dokumentiert,
  Stimmt-Regel, living_being-Pflichtmuster, CONTENT_DEPTH/TOPIC_INTEREST als implementiert
  bestätigt, R2-Koexistenz-Entscheidung, Mengenziele, Quiz-Strategie,
  System-Prompt-Versionslinie v3.2→v3.3→v3.4
- WISSEN_BILDER.md: Content-Sicherheit (Bilder) + Lizenz/Attribution ergänzt
- System-Prompt v3.4 auditiert — 3 Lücken: Alterseignungs-Weglass-Regel,
  Interessantheits-Methodik, Wortgrenzen interest-gestaffelt (inkl. Boxen, ohne Quiz)
  gegen genaue Werte S1 50-100/100-150/150-250 etc. prüfen
- quiz_and_upload.yml: Auto-Trigger entfernt, nur noch manuell (commit 2cc9779, Hedge)

**Vollbild-Viewer — komplett, auf main gemergt (e0906eb → merge)**
- PhotoViewGallery (photo_view_plus 1.1.1) ersetzt InteractiveViewer — Pinch-Arena gelöst
- 3-Stufen-Doppeltipp: Basis → Stufe1 (minScale×2.5) → Max (covered×4) → Basis, deterministisch
- Caption an Bildunterkante verankert; Pinch-Fix via Future.microtask
- Getestet auf S23 ✅; Branch spike/photo-view-plus gelöscht

**Repo-Hygiene — beide Klone auf main vereint (2026-06-04)**
- Uncommitted work aus wissensfreund_app gesichert + nach main gemergt
- Arbeitsverzeichnis/Keeper: **C:\Users\Andreas\wissensfreund_repo**

---

## ⏰ Offen: Spare-Klon entfernen (~2026-06-18)

**C:\Users\Andreas\Wissensfreund\wissensfreund_app** — Spare-Klon, vorher:
1. Prüfen ob `scrape_out/` (1,6 GB) noch gebraucht wird
2. 30-Sek-Check: `git status` + `git status --ignored` in wissensfreund_app
3. Dann Ordner löschen

**C:\Users\Andreas\Wissensfreund\CLAUDE.md + STATUS.md** — verwaiste Nicht-Git-Kopien,
können nach Entfernung von wissensfreund_app ebenfalls gelöscht werden.

---

## 🔴 Offene Punkte (nach Priorität)

### Hoch
- **Content-Sicherheitsfilter Bilder entscheiden (Kinderschutz):**
  Vor Bilder-Patch-Run klären: Reicht dateiname-basierter Claude-Filter, oder braucht es
  Wikipedia-Kategorienabruf (prop=categories auf Commons) + Vision-API?
  Stufe 2 + 3 der dreistufigen Filterung fehlen als aktiver Code-Filter.
  Details: WISSEN_BILDER.md § Content-Sicherheit, WISSEN_ARTIKEL_PIPELINE.md § Content-Sicherheit (Bilder)
- **Bilder-Patch** (`patch_article_images_v1.py`): Artikel von R2 laden, Patch laufen lassen,
  zurück nach R2. (ANTHROPIC_API_KEY in GitHub Secrets) — erst nach Kinderschutz-Entscheidung
- **Selbst produzierte Artikel** — Pipeline starten (Skripte fertig, Code↔Prompt-Abgleich
  erst beenden)

### Mittel
- **Code↔v3.4-Prompt-Abgleich:** `generate_articles.py` sendet v3.2-Felder; v3.4 erwartet
  TOPIC_APPEAL, TOPIC_FAMILIARITY, WIKIPEDIA_LINKS, ARTICLE_INDEX, IMAGE_METADATA.
  Details: WISSEN_ARTIKEL_PIPELINE.md § System-Prompt-Versionslinie
- **Fehlende kanonische Prompt-Datei:** `wissensfreund_system_prompt.md` (ohne Versionssuffix)
  existiert nicht im Repo; Workflow-Variable zeigt darauf → Pipeline würde scheitern.
- **R2-Koexistenz:** upload_articles.py nutzt rclone sync → ZIM + Wikipedia-Artikel
  würden sich überschreiben. Entscheidung: getrennte Präfixe implementieren, vor Pilot.
- **Epoch-Guard TTS-Callbacks**: Generations-Zähler statt `_ttsStopPending` (~5 Stellen)
- **Mode B Lupe**: Bold entfernen + `_ttsCursor` erst im progressHandler updaten
- **Sound-Thumbnails**: wartet auf Audio-Pipeline-Run-Ergebnis

### Niedrig / Klärungsbedarf
- **Primärkategorie-Konvention + Hierarchie-Ebenen:** erste in Liste vs. primary:true;
  alle Hierarchieebenen explizit speichern? (Konzeptchat nie final entschieden)
- **Box-Key Klärung:** myth vs. stimmt vs. stimmt_das — kanonischer Key noch nicht festgeklopft
- **ZIM→JSON Decode-Auflösungs-Cap**, **Kiosk → Screen Pinning**, **STT-Routing**,
  **Fire-OS-Entscheidung**, **Bild-Tier-Werte vereinheitlichen**

---

## 🧊 Reserve / auf Eis

- **Klexikon-Quiz-Run** (`generate_quizzes.py`): Hedge, falls selbst produzierte Artikel
  zu teuer/langsam. Auto-Trigger entfernt (commit 2cc9779). Checkpoint (609 Einträge)
  auf R2 — vor Aktivierung löschen.

---

## 🔵 Verschoben auf Version 1.1
- Gallery-Artikel (111 Artikel, 540 Bilder), Audio-Pipeline, Gemini-TTS-Idee
- Links/Topic-Tree, Upgrade-Dialog, Plus/Premium-Design
