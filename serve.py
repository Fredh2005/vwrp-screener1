#!/usr/bin/env python3
"""
Run the VWRP screener as a local web app with live-updating prices.

    python serve.py                 # http://localhost:8765, opens your browser
    python serve.py --lan           # also reachable from your phone on the same wifi
    python serve.py --port 9000
    python serve.py --no-open

Serves output/dashboard.html and adds two things a plain file:// page cannot do:

  * live quotes  -- GET /quotes proxies Yahoo, cached 60s server-side
  * refresh      -- POST /refresh re-runs the whole screen

Quotes come from Yahoo Finance, which is a delayed feed (typically up to 15
minutes, varying by exchange). It is not a licensed real-time market feed.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "output")
SCREENER = os.path.join(BASE, "screener.py")

QUOTE_TTL = 60           # seconds; Yahoo is delayed anyway, so don't hammer it
_refresh_lock = threading.Lock()
_quote_lock = threading.Lock()
_quote_cache = {"asof": 0, "quotes": {}}
OPTS = {"top": 150, "full": False}


# --------------------------------------------------------------------------
# Live quotes
# --------------------------------------------------------------------------

def dashboard_tickers():
    """Read the tickers straight out of the page we're serving."""
    path = os.path.join(OUTDIR, "dashboard.html")
    try:
        with open(path) as fh:
            html = fh.read()
        start = html.index("const DATA = ") + len("const DATA = ")
        end = html.index("\n", start)
        data = json.loads(html[start:end].rstrip(";"))
        return [r["Ticker"] for r in data["rows"] if r.get("Ticker")]
    except Exception as exc:
        print(f"! could not read tickers from dashboard: {exc}", file=sys.stderr)
        return []


def fetch_quotes(tickers):
    """Latest intraday price and change vs the previous close."""
    import yfinance as yf

    out = {}
    if not tickers:
        return out

    # Previous close, from daily bars.
    prev = {}
    try:
        daily = yf.download(tickers, period="5d", interval="1d",
                            progress=False, threads=True, auto_adjust=False)
        if daily is not None and not daily.empty:
            close = daily["Close"]
            for tk in close.columns:
                col = close[tk].dropna()
                if len(col) >= 2:
                    prev[tk] = float(col.iloc[-2])
                elif len(col) == 1:
                    prev[tk] = float(col.iloc[-1])
    except Exception as exc:
        print(f"! daily bars failed: {exc}", file=sys.stderr)

    # Latest price, from 1-minute bars.
    try:
        intraday = yf.download(tickers, period="2d", interval="1m",
                               progress=False, threads=True, auto_adjust=False)
        if intraday is not None and not intraday.empty:
            close = intraday["Close"].ffill()
            last = close.iloc[-1]
            for tk in close.columns:
                px = last.get(tk)
                if px is None or px != px:      # NaN check
                    continue
                px = float(px)
                p = prev.get(tk)
                out[tk] = {
                    "price": round(px, 2),
                    "day_pct": round((px / p - 1) * 100, 2) if p else None,
                }
    except Exception as exc:
        print(f"! intraday bars failed: {exc}", file=sys.stderr)

    return out


def cached_quotes():
    with _quote_lock:
        age = time.time() - _quote_cache["asof"]
        if _quote_cache["quotes"] and age < QUOTE_TTL:
            return _quote_cache
        quotes = fetch_quotes(dashboard_tickers())
        if quotes:
            _quote_cache["quotes"] = quotes
            _quote_cache["asof"] = time.time()
            print(f"> quotes refreshed ({len(quotes)} tickers)", flush=True)
        return _quote_cache


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

# The same page carries two identities: "Screener" is the live one on this
# machine, "Daily update" is the published snapshot people are sent. The built
# HTML names the published one, so rewrite it on the way out.
LOCAL_NAME = "Screener"

MANIFEST = {
    "name": "VWRP Screener (live)",
    "short_name": LOCAL_NAME,
    "id": "/",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#0D1524",
    "theme_color": "#8A6A2F",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any maskable"},
    ],
}

# Served under the plain names but taken from the local-* variants, so the
# home-screen icon here reads SCREENER while the published one reads DAILY UPDATE.
ICON_FILES = {
    "apple-touch-icon.png": "local-apple-touch-icon.png",
    "icon-192.png": "local-icon-192.png",
    "icon-512.png": "local-icon-512.png",
}

ICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<rect width="192" height="192" rx="34" fill="#181B22"/>
<path d="M34 130 L74 92 L104 116 L158 58" fill="none" stroke="#C9A45C"
      stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="158" cy="58" r="13" fill="#C9A45C"/>
</svg>'''


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=OUTDIR, **kw)

    def _send(self, code, body, ctype="application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "", "/dashboard.html"):
            return self._send(200, self._local_page(), "text/html; charset=utf-8")
        elif self.path == "/quotes":
            cache = cached_quotes()
            return self._send(200, json.dumps({
                "quotes": cache["quotes"],
                "asof": (cache["asof"] or time.time()) * 1000,
            }))
        elif self.path in ("/manifest.webmanifest", "/manifest.json"):
            return self._send(200, json.dumps(MANIFEST), "application/manifest+json")
        elif self.path.lstrip("/") in ICON_FILES:
            src = os.path.join(BASE, ICON_FILES[self.path.lstrip("/")])
            if not os.path.exists(src):
                src = os.path.join(BASE, self.path.lstrip("/"))
            if os.path.exists(src):
                with open(src, "rb") as fh:
                    return self._send(200, fh.read(), "image/png")
            return self.send_error(404)
        elif self.path == "/icon.svg":
            return self._send(200, ICON, "image/svg+xml")
        return super().do_GET()

    def _local_page(self):
        """The built page, renamed for this machine."""
        with open(os.path.join(OUTDIR, "dashboard.html")) as fh:
            html = fh.read()
        return html.replace(
            '<meta name="apple-mobile-web-app-title" content="Daily update">',
            f'<meta name="apple-mobile-web-app-title" content="{LOCAL_NAME}">'
        ).replace("<title>VWRP Screener</title>",
                  "<title>VWRP Screener (live)</title>")

    def do_POST(self):
        if self.path != "/refresh":
            return self.send_error(404)

        # One refresh at a time -- concurrent runs would fight over the cache.
        if not _refresh_lock.acquire(blocking=False):
            return self._send(429, "A refresh is already running", "text/plain")
        try:
            cmd = [sys.executable, "-W", "ignore", SCREENER, "--top", str(OPTS["top"])]
            if OPTS["full"]:
                cmd.append("--refresh")
            print(f"\n> refreshing: {' '.join(cmd)}", flush=True)
            proc = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
            if proc.returncode == 0:
                _quote_cache["asof"] = 0          # tickers may have changed
                print("> refresh complete", flush=True)
                return self._send(200, "ok", "text/plain")
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            print("> refresh FAILED:\n" + tail, flush=True)
            return self._send(500, tail or "refresh failed", "text/plain")
        finally:
            _refresh_lock.release()

    def end_headers(self):
        # Always re-read the freshly written dashboard rather than a cached copy.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # keep the console for refresh/quote progress only


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Serve the VWRP screener locally.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--top", type=int, default=150,
                    help="how many holdings the refresh button screens")
    ap.add_argument("--refresh-full", action="store_true",
                    help="refresh button ignores the 24h cache (much slower)")
    ap.add_argument("--lan", action="store_true",
                    help="listen on all interfaces so your phone can reach it")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    OPTS["top"], OPTS["full"] = args.top, args.refresh_full

    if not os.path.exists(os.path.join(OUTDIR, "dashboard.html")):
        print("No dashboard yet - generating one first...", file=sys.stderr)
        subprocess.run([sys.executable, "-W", "ignore", SCREENER,
                        "--top", str(args.top)], cwd=BASE, check=False)

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    try:
        server = ThreadingHTTPServer((host, args.port), Handler)
    except OSError as exc:
        if exc.errno == 48:
            print(f"Port {args.port} is already in use - the screener may already "
                  f"be running.\nCheck with:  lsof -nP -iTCP:{args.port} -sTCP:LISTEN"
                  f"\nOr pick another port:  python serve.py --port {args.port + 1}",
                  file=sys.stderr)
            sys.exit(1)
        raise

    print(f"VWRP screener running at http://localhost:{args.port}/")
    if args.lan:
        ip = lan_ip()
        if ip:
            print(f"On your phone (same wifi):  http://{ip}:{args.port}/")
        print("Note: --lan exposes it to your local network, not the internet.")
    print("Live prices refresh every 60s (Yahoo delayed feed).")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(
            f"http://localhost:{args.port}/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
