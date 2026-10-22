"""Loopback-only read-only HTTP explorer."""

from __future__ import annotations

import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from types import FrameType
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from .explorer_data import BadRequest, Explorer
from .queries import NotFound

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
ALLOWED = {
    "/api/meta": set(),
    "/api/files": {"prefix", "limit", "cursor"},
    "/api/file": {"path", "limit", "cursor"},
    "/api/symbols": {"q", "file", "limit", "cursor"},
    "/api/symbol": {"id"},
    "/api/neighborhood": {"id", "direction", "relations", "limit"},
    "/api/query": {
        "command",
        "target",
        "file",
        "scope",
        "depth",
        "ancestors",
        "kind",
        "confidence",
        "limit",
        "cursor",
    },
    "/api/source": {"path", "start", "end"},
}


def make_server(db_path: str, port: int = 8765) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise BadRequest("Port out of range")
    viewer = Explorer(db_path)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def answer(
            self, code: int, data: Any, content_type: str = "application/json; charset=utf-8"
        ) -> None:
            raw = (
                json.dumps(data, ensure_ascii=False).encode()
                if not isinstance(data, bytes)
                else data
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            host = self.headers.get("Host", "")
            port = cast(ThreadingHTTPServer, self.server).server_port
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return self.answer(403, {"error": "Invalid host"})
            parsed = urlsplit(self.path)
            if parsed.path in ASSETS:
                name, mime = ASSETS[parsed.path]
                return self.answer(
                    200, resources.files("codegraph").joinpath("web", name).read_bytes(), mime
                )
            if parsed.path not in ALLOWED:
                return self.answer(404, {"error": "Unknown route"})
            try:
                params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=15)
                if any(
                    len(v) != 1 or k not in ALLOWED[parsed.path] or len(v[0]) > 1024
                    for k, v in params.items()
                ):
                    raise BadRequest("Invalid parameters")
                p: dict[str, Any] = {k: v[0] for k, v in params.items()}
                route = parsed.path
                if route == "/api/meta":
                    data = viewer.status()
                elif route == "/api/files":
                    data = viewer.files(**p)
                elif route == "/api/file":
                    data = viewer.file(**p)
                elif route == "/api/symbols":
                    data = viewer.symbols(**p)
                elif route == "/api/symbol":
                    data = viewer.symbol(p["id"])
                elif route == "/api/neighborhood":
                    data = viewer.neighborhood(p.pop("id"), **p)
                elif route == "/api/source":
                    data = viewer.source(**p)
                else:
                    if "ancestors" in p:
                        if p["ancestors"] not in ("true", "false"):
                            raise BadRequest("Invalid ancestors")
                        p["ancestors"] = p["ancestors"] == "true"
                    data = viewer.query(**p)
                    if data["results"]["next"] is not None:
                        nxt = dict(p, cursor=data["results"]["next"])
                        data["results"]["next_url"] = route + "?" + urlencode(nxt)
                    else:
                        data["results"]["next_url"] = None
                self.answer(200, data)
            except (BadRequest, KeyError, TypeError) as exc:
                self.answer(400, {"error": str(exc)})
            except NotFound as exc:
                self.answer(404, {"error": f"Not found: {exc}"})
            except OSError:
                self.answer(404, {"error": "Source unavailable"})

        def do_POST(self) -> None:
            self.answer(405, {"error": "Read-only viewer"})

        do_PUT = do_DELETE = do_PATCH = do_POST

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(db_path: str, port: int = 8765) -> None:
    server = make_server(db_path, port)
    server.timeout = 0.1
    print(
        f"codegraph explorer: http://127.0.0.1:{server.server_port}/ (Ctrl-C to stop)", flush=True
    )
    previous = signal.getsignal(signal.SIGTERM)

    def stop(signum: int, frame: FrameType | None) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    finally:
        signal.signal(signal.SIGTERM, previous)
        server.server_close()
