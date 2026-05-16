#!/usr/bin/env python3
"""Local-only HTTP server for the x-control dashboard.

Listens on 127.0.0.1 only — never exposed off-machine. No auth needed because
nothing leaves localhost.

Routes
------
GET  /                      → latest pulse dashboard (auto-finds newest .html)
GET  /YYYY-MM-DD            → that day's dashboard
GET  /YYYY-MM-DD.md         → that day's markdown pulse (plain text)
GET  /archive               → JSON list of available pulse dates
GET  /healthz               → "ok"
POST /regenerate            → run monitor.py and redirect to /
GET  /static/<file>         → any other file under PULSE_DIR (escape-safe)

Run
---
  python scripts/serve.py             # port 8787
  python scripts/serve.py 9000        # custom port
  python scripts/serve.py --no-open   # don't open browser on start
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PULSE_DIR = Path.home() / "Documents" / "Last30Days"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
MONITOR = ROOT / "scripts" / "monitor.py"

DEFAULT_PORT = 8787
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

INDEX_BANNER_JS = """\
<script>
(function(){
  // When served via x-control serve.py (host has port :8787), enable refresh button.
  if (location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') return;
  const btn = document.createElement('button');
  btn.textContent = '↻ Regenerate now';
  btn.setAttribute('style', [
    'position:fixed', 'top:16px', 'right:16px', 'z-index:99',
    'padding:8px 14px', 'border-radius:9999px', 'border:1px solid rgba(255,255,255,.2)',
    'background:rgba(255,255,255,.06)', 'color:#fff', 'cursor:pointer',
    'font-family:"JetBrains Mono",monospace', 'font-size:12px',
    'backdrop-filter:blur(8px)', '-webkit-backdrop-filter:blur(8px)',
    'transition:all .18s cubic-bezier(.16,1,.3,1)',
  ].join(';'));
  btn.onmouseenter = () => btn.style.background = 'rgba(255,255,255,.12)';
  btn.onmouseleave = () => btn.style.background = 'rgba(255,255,255,.06)';
  btn.onclick = async () => {
    btn.textContent = '⋯ regenerating';
    btn.disabled = true;
    try {
      const r = await fetch('/regenerate', {method: 'POST'});
      if (r.ok) location.reload();
      else { btn.textContent = '✗ ' + r.status; setTimeout(() => location.reload(), 1500); }
    } catch (e) { btn.textContent = '✗ ' + e.message; }
  };
  document.body.appendChild(btn);
})();
</script>
"""


def _latest_dashboard() -> Path | None:
    files = sorted(PULSE_DIR.glob("x-pulse-*.html"), reverse=True)
    return files[0] if files else None


def _by_date(day: str) -> Path | None:
    if not DATE_RE.match(day):
        return None
    p = PULSE_DIR / f"x-pulse-{day}.html"
    return p if p.exists() else None


def _md_by_date(day: str) -> Path | None:
    if not DATE_RE.match(day):
        return None
    p = PULSE_DIR / f"x-pulse-{day}.md"
    return p if p.exists() else None


def _archive() -> list[dict]:
    out = []
    for p in sorted(PULSE_DIR.glob("x-pulse-*.html"), reverse=True):
        m = re.match(r"x-pulse-(\d{4}-\d{2}-\d{2})\.html", p.name)
        if not m:
            continue
        st = p.stat()
        out.append({
            "date": m.group(1),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "url": f"/{m.group(1)}",
        })
    return out


def _inject_refresh(html: str) -> str:
    # Insert just before </body> for least conflict
    if "</body>" in html:
        return html.replace("</body>", INDEX_BANNER_JS + "</body>", 1)
    return html + INDEX_BANNER_JS


class Handler(BaseHTTPRequestHandler):
    server_version = "x-control-serve/1.0"

    def _send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8", headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, msg: str) -> None:
        self._send(status, msg.encode(), "text/plain; charset=utf-8")

    def _file(self, p: Path, ctype: str = "text/html; charset=utf-8", inject: bool = False) -> None:
        try:
            body = p.read_text()
        except OSError as e:
            self._text(HTTPStatus.NOT_FOUND, f"not found: {e}")
            return
        if inject:
            body = _inject_refresh(body)
        self._send(HTTPStatus.OK, body.encode(), ctype)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            p = _latest_dashboard()
            if not p:
                self._text(HTTPStatus.NOT_FOUND, "No dashboards yet. Run `python scripts/monitor.py` first.")
                return
            self._file(p, inject=True)
            return

        if path == "/healthz":
            self._text(HTTPStatus.OK, "ok")
            return

        if path == "/archive":
            self._send(HTTPStatus.OK, json.dumps(_archive(), indent=2).encode(), "application/json")
            return

        # /YYYY-MM-DD.md
        m = re.match(r"^/(\d{4}-\d{2}-\d{2})\.md$", path)
        if m:
            p = _md_by_date(m.group(1))
            if not p:
                self._text(HTTPStatus.NOT_FOUND, f"no markdown pulse for {m.group(1)}")
                return
            self._file(p, ctype="text/markdown; charset=utf-8")
            return

        # /YYYY-MM-DD
        m = re.match(r"^/(\d{4}-\d{2}-\d{2})$", path)
        if m:
            p = _by_date(m.group(1))
            if not p:
                self._text(HTTPStatus.NOT_FOUND, f"no dashboard for {m.group(1)}")
                return
            self._file(p, inject=True)
            return

        # /static/<filename>  — read-only, only under PULSE_DIR, only safe names
        m = re.match(r"^/static/([A-Za-z0-9_.-]+)$", path)
        if m and SAFE_NAME_RE.match(m.group(1)):
            p = PULSE_DIR / m.group(1)
            if p.exists() and p.is_file() and p.resolve().is_relative_to(PULSE_DIR.resolve()):
                ctype = "text/plain; charset=utf-8"
                if p.suffix == ".html":
                    ctype = "text/html; charset=utf-8"
                elif p.suffix == ".md":
                    ctype = "text/markdown; charset=utf-8"
                elif p.suffix == ".json":
                    ctype = "application/json"
                self._file(p, ctype=ctype)
                return

        self._text(HTTPStatus.NOT_FOUND, f"no route: {self.path}")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/regenerate":
            self._run_monitor()
            return
        self._text(HTTPStatus.NOT_FOUND, f"no route: {self.path}")

    def _run_monitor(self) -> None:
        if not VENV_PYTHON.exists() or not MONITOR.exists():
            self._text(HTTPStatus.INTERNAL_SERVER_ERROR, "monitor.py or venv not found")
            return
        try:
            proc = subprocess.run(
                [str(VENV_PYTHON), str(MONITOR)],
                capture_output=True, text=True, timeout=90,
            )
        except subprocess.TimeoutExpired:
            self._text(HTTPStatus.GATEWAY_TIMEOUT, "monitor.py timed out after 90s")
            return
        if proc.returncode != 0:
            self._text(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"monitor.py exit {proc.returncode}\n\nstdout:\n{proc.stdout[:2000]}\n\nstderr:\n{proc.stderr[:2000]}",
            )
            return
        self._send(HTTPStatus.OK, b'{"ok":true}', "application/json")

    def log_message(self, fmt: str, *args) -> None:
        # Quieter access log: only print non-noise
        msg = fmt % args
        if any(s in msg for s in (" 200 ", " 304 ")) and "/healthz" in msg:
            return
        sys.stderr.write(f"[{self.log_date_time_string()}] {msg}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Local x-control dashboard server")
    ap.add_argument("port", nargs="?", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true", help="don't open the browser on start")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1 — localhost only)")
    args = ap.parse_args()

    PULSE_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    sys.stderr.write(f"x-control dashboard at {url}  (Ctrl-C to stop)\n")

    if not args.no_open:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nstopping\n")
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
