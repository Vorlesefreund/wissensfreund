#!/usr/bin/env python3
"""
dashboard_server.py
Minimal-Webserver für Live-Log-Anzeige während Generierungsläufen.
Usage: py scripts/dashboard_server.py --log <pfad-zur-logdatei> [--port 8765]
"""

import argparse
import http.server
import json
import os
import re
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wissensfreund — Generierung</title>
<style>
  body { background:#0d1117; color:#e6edf3; font-family:monospace; margin:0; padding:16px; }
  h1 { font-size:1rem; color:#58a6ff; margin:0 0 12px; }
  #status { font-size:.8rem; color:#8b949e; margin-bottom:8px; }
  #log {
    background:#161b22; border:1px solid #30363d; border-radius:6px;
    padding:12px; height:75vh; overflow-y:auto;
    font-size:.78rem; line-height:1.5; white-space:pre-wrap; word-break:break-all;
  }
  .INFO    { color:#e6edf3; }
  .WARNING { color:#d29922; }
  .ERROR   { color:#f85149; }
  .phase1  { color:#58a6ff; font-weight:bold; }
  .phase2  { color:#3fb950; font-weight:bold; }
  .done    { color:#3fb950; font-weight:bold; }
  #badges { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  .badge {
    background:#21262d; border:1px solid #30363d; border-radius:12px;
    padding:2px 10px; font-size:.72rem; color:#8b949e;
  }
  .badge.active { border-color:#58a6ff; color:#58a6ff; }
  .badge.ok     { border-color:#3fb950; color:#3fb950; }
</style>
</head>
<body>
<h1>Wissensfreund — Generierungs-Dashboard</h1>
<div id="status">Lade...</div>
<div id="badges"></div>
<div id="log"></div>
<script>
const LOG_RE = /^(\\d{2}:\\d{2}:\\d{2})\\s+(INFO|WARNING|ERROR)\\s+(.*)$/;

function colorLine(line) {
  const m = line.match(LOG_RE);
  if (!m) return '<span>' + esc(line) + '</span>';
  const [, ts, level, msg] = m;
  let cls = level;
  if (msg.includes('Phase 1') || msg.includes('Kompass') || msg.includes('Validiert'))
    cls = 'phase1';
  else if (msg.includes('Phase 2') || msg.includes('Artikel generieren'))
    cls = 'phase2';
  else if (msg.includes('Gespeichert') || msg.includes('gespeichert') || msg.includes('DONE'))
    cls = 'done';
  return `<span class="${cls}">${esc(ts)} <b>${level}</b> ${esc(msg)}</span>`;
}
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function extractBadges(lines) {
  const badges = [];
  for (const l of lines) {
    if (l.includes('Kompass-Vorschlag:')) {
      const m = l.match(/Kompass-Vorschlag: \\[(.*)\\]/);
      if (m) badges.push({label: 'Vorschlag', val: m[1], cls: ''});
    }
    if (l.includes('Validiert (final):')) {
      const m = l.match(/Validiert \\(final\\): \\[(.*)\\]/);
      if (m) badges.push({label: 'Companions', val: m[1], cls: 'ok'});
    }
    if (l.includes('Phase 2') && l.includes('Stufe')) {
      const m = l.match(/Stufe (\\d)/);
      if (m) badges.push({label: 'L' + m[1], val: 'generiert', cls: 'active'});
    }
    if (l.includes('HTTP/1.1 200 OK') && badges.some(b => b.val === 'generiert')) {
      const last = [...badges].reverse().find(b => b.val === 'generiert');
      if (last) last.cls = 'ok', last.val = 'fertig';
    }
  }
  // deduplicate last-wins
  const seen = new Map();
  for (const b of badges) seen.set(b.label, b);
  return [...seen.values()];
}

async function refresh() {
  try {
    const r = await fetch('/api/log');
    const data = await r.json();
    const lines = data.lines || [];
    const el = document.getElementById('log');
    const atBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 5;
    el.innerHTML = lines.map(colorLine).join('\\n');
    if (atBottom) el.scrollTop = el.scrollHeight;

    document.getElementById('status').textContent =
      `${lines.length} Zeilen | ${data.done ? 'Fertig' : 'Laeuft...'} | ${new Date().toLocaleTimeString()}`;

    const bdg = document.getElementById('badges');
    bdg.innerHTML = extractBadges(lines)
      .map(b => `<span class="badge ${b.cls}">${b.label}: ${b.val}</span>`).join('');
  } catch(e) {
    document.getElementById('status').textContent = 'Verbindungsfehler: ' + e;
  }
}

refresh();
setInterval(refresh, 2500);
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    log_path: Path = Path("/dev/null")
    done_flag: list[bool] = [False]

    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard.html":
            self._serve_text(HTML_TEMPLATE.encode(), "text/html")
        elif self.path == "/api/log":
            try:
                text = self.log_path.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
            except FileNotFoundError:
                lines = ["(Log-Datei noch nicht vorhanden)"]
            payload = json.dumps({"lines": lines, "done": self.done_flag[0]}).encode()
            self._serve_text(payload, "application/json")
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_text(self, data: bytes, ct: str):
        self.send_response(200)
        self.send_header("Content-Type", ct + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass  # HTTP-Anfragen nicht in die Konsole loggen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, help="Pfad zur Log-Datei")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    Handler.log_path  = Path(args.log)
    Handler.done_flag = [False]

    server = http.server.HTTPServer(("localhost", args.port), Handler)
    print(f"Dashboard: http://localhost:{args.port}/")
    print(f"Log-Quelle: {args.log}")
    print("Ctrl+C zum Beenden")

    def _watch():
        import time
        while True:
            time.sleep(3)
            try:
                text = Handler.log_path.read_text(encoding="utf-8", errors="replace")
                if "=== DONE ===" in text or "THEMA:" in text and text.count("fertig") >= 3:
                    Handler.done_flag[0] = True
            except FileNotFoundError:
                pass

    threading.Thread(target=_watch, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
