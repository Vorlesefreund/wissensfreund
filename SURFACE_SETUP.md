# Surface einrichten — Gedächtnis-Sync (von Claude auf dem Desktop vorbereitet, 2026-09-03)

Dieses Dokument ist ein Auftrag für eine **Claude-Sitzung auf dem Surface**.
Andreas muss nichts abtippen — die Sitzung liest und erledigt die Schritte.

## 0. Erst absichern
Führe `hostname` aus. Steht dort **Andreas-PC**, dann läuft diese Sitzung in
Wahrheit auf dem Desktop (ferngesteuert) — STOPP und sag Andreas Bescheid.
Bei jedem anderen Namen (Surface) weiter.

## 1. Gedächtnis-Repo in den richtigen Pfad klonen
Zielpfad (auf beiden Rechnern identisch):
`$HOME/.claude/projects/C--Users-Andreas-wissensfreund-repo/memory`

- Liegt dort schon etwas: in `memory_alt_<Zeitstempel>` **umbenennen, nicht löschen**.
- Dann klonen:
  `git clone https://github.com/Vorlesefreund/claude-memory-wissensfreund.git "<Zielpfad>"`
- Zur Kontrolle die `.md`-Dateien zählen (erwartet: ~73).

## 2. Dieselben Hooks in die Surface-`~/.claude/settings.json` eintragen
Merge in den vorhandenen `hooks`-Block (nicht ersetzen). Genau diese drei Hooks —
identisch zum Desktop:

**SessionStart**, Hook 1 (Projekt-Repo im aktuellen Ordner holen):
```
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git pull --ff-only --quiet 2>/dev/null || true
```

**SessionStart**, Hook 2 UND **Stop**, Hook 1 (identischer Befehl, Gedächtnis abgleichen):
```
M="$HOME/.claude/projects/C--Users-Andreas-wissensfreund-repo/memory"; git -C "$M" rev-parse --is-inside-work-tree >/dev/null 2>&1 && { [ -n "$(git -C "$M" status --porcelain)" ] && git -C "$M" add -A && git -C "$M" -c user.name=Andreas -c user.email=az@expansionssupport.de commit -qm "auto: Gedaechtnis-Notizen"; git -C "$M" pull --ff-only --quiet; git -C "$M" push -q; } 2>/dev/null; true
```
Jeder Hook: `"type":"command"`, `"shell":"bash"`, `"timeout":30`. Am sichersten
mit Python mergen (JSON laden, ergänzen, zurückschreiben), damit die Datei gültig bleibt.
Ist ein Gedächtnis-Hook schon vorhanden, nicht doppeln.

## 3. Prüfen
- `python -c "import json,os;json.load(open(os.path.expanduser('~/.claude/settings.json')))"` → gültig?
- Melde Andreas: hostname, Zahl der Notizen, dass die Hooks stehen.

## Was danach automatisch läuft
Beim Start jeder Sitzung wird das Gedächtnis geholt; sobald Claude eine Notiz
schreibt, wird sie beim nächsten Stopp still hochgeladen. Desktop und Surface
bleiben so auf gleichem Wissensstand — ohne dass jemand daran denken muss.

*(Diese Datei darf nach der Einrichtung gelöscht werden — sie ist nur der Bote.)*
