#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
from pathlib import Path
import socketserver


class SpaRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        self._spa_root = Path(directory or ".").resolve()
        super().__init__(*args, directory=str(self._spa_root), **kwargs)

    def do_GET(self):
        requested = self.path.split("?", 1)[0].split("#", 1)[0]
        target = self._spa_root / requested.lstrip("/")
        if requested not in {"/", ""} and not target.exists():
            self.path = "/index.html"
        return super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Serve a static SPA build with index fallback.")
    parser.add_argument("--root", required=True, help="Path to the built frontend directory.")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind.")
    parser.add_argument("--port", type=int, default=5159, help="Port to bind.")
    args = parser.parse_args()

    frontend_root = Path(args.root).resolve()
    if not frontend_root.exists():
        raise SystemExit(f"Frontend root does not exist: {frontend_root}")

    handler = lambda *handler_args, **handler_kwargs: SpaRequestHandler(
        *handler_args,
        directory=str(frontend_root),
        **handler_kwargs,
    )

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((args.host, args.port), handler) as httpd:
        print(f"Serving {frontend_root} on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
