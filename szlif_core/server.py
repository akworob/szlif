"""The local web server: serves the page and computes everything it shows.

It listens on 127.0.0.1 only. A request must name this server in its Host
header (against DNS rebinding), and a POST must come from this page's origin
and carry JSON, so another web page cannot send text through Szlif or use the
user's API key. Nothing the user pastes is logged or written to disk."""

import json
import os
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from . import COMMAND
from .backends import Backend, BackendError
from .blocks import split_blocks
from .cleaner import clean, summary
from .guard import check
from .rewrite import MAX_CHARS, MODES, run_round
from .verify import build_prompt
from .view import build_view

PAGE = Path(__file__).with_name("strona.html")
MAX_BODY = 1024 * 1024
PAGE_HEADERS = {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                               "connect-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class Invalid(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _grouped(n: int) -> str:
    return format(n, ",").replace(",", " ")


def _text(body: Dict, name: str, required: bool = True) -> Optional[str]:
    """A text field with its line breaks made \\n; checked when required."""
    value = body.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise Invalid(400, "Nieprawidłowe zapytanie.")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if required and not value.strip():
        raise Invalid(400, "Wklej tekst.")
    if required and len(value) > MAX_CHARS:
        raise Invalid(413, "Tekst ma %s znaków, limit to %s. Podziel go na części."
                      % (_grouped(len(value)), _grouped(MAX_CHARS)))
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "Szlif"

    def log_message(self, *args: Any) -> None:  # no logs: they would carry what the user pasted
        pass

    def _send(self, status: int, data: bytes, headers: Dict[str, str]) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"})

    def _ours(self) -> set:
        port = self.server.server_address[1]
        return {"127.0.0.1:%d" % port, "localhost:%d" % port}

    def do_GET(self) -> None:
        if self.headers.get("Host", "") not in self._ours():
            return self._json(403, {"blad": "Nieprawidłowy nagłówek Host."})
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, PAGE.read_bytes(), PAGE_HEADERS)
        if path == "/api/stan":
            return self._json(200, self._stan())
        if path == "/favicon.ico":  # no icon; answering keeps the browser console clean
            return self._send(204, b"", {})
        self._json(404, {"blad": "Nie ma takiej strony."})

    def do_POST(self) -> None:
        if self.headers.get("Host", "") not in self._ours():
            return self._json(403, {"blad": "Nieprawidłowy nagłówek Host."})
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {"http://" + h for h in self._ours()}:
            return self._json(403, {"blad": "Zapytanie z obcej strony."})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(415, {"blad": "Oczekiwano JSON."})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"blad": "Zapytanie jest za duże."})
        try:
            body = json.loads(self.rfile.read(length) or b"null")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"blad": "Nieprawidłowe zapytanie."})
        routes = {"/api/bloki": self._bloki, "/api/runda": self._runda, "/api/widok": self._widok,
                  "/api/weryfikacja": self._weryfikacja}
        route = routes.get(self.path.split("?", 1)[0])
        if route is None:
            return self._json(404, {"blad": "Nie ma takiej strony."})
        try:
            self._json(200, route(body))
        except Invalid as e:
            self._json(e.status, {"blad": str(e)})
        except BackendError as e:
            self._json(502, {"blad": str(e)})

    def _stan(self) -> Dict:
        backend: Backend = self.server.backend
        models, error = [], None
        try:
            models = backend.list_models()
        except BackendError as e:
            error = str(e)
        model = self.server.default_model or next((m for m in models if "bielik" in m.lower()), None) \
            or (models[0] if models else None)
        if model is None and error is None:
            error = "Brak modelu. Uruchom: %s instaluj" % COMMAND
        cloud = backend.cloud_disabled() if backend.kind == "ollama" and backend.is_local and models else None
        return {"rodzaj": backend.kind, "serwer": backend.url, "lokalny": backend.is_local,
                "chmura_wylaczona": cloud, "modele": models, "model": model, "limit": MAX_CHARS,
                "tryby": MODES, "blad": error, "polecenie": COMMAND}

    def _bloki(self, body: Dict) -> Dict:
        """The cleaned text in blocks; the page rewrites the paragraphs one at a time."""
        tekst = _text(body, "tekst")
        cleaned = clean(tekst, bool(body.get("ukryte", True)), bool(body.get("myslniki", False))).text
        return {"bloki": split_blocks(cleaned)}

    def _weryfikacja(self, body: Dict) -> Dict:
        """The prompt for a second model that checks the meaning of every rewritten paragraph."""
        pairs, warnings = body.get("pary"), body.get("uwagi", [])
        try:
            pairs = [(int(p["numer"]), str(p["przed"]), str(p["po"])) for p in pairs]
            if not isinstance(warnings, list):
                raise TypeError
        except (TypeError, KeyError, ValueError, OverflowError):
            raise Invalid(400, "Nieprawidłowe zapytanie.")
        return {"prompt": build_prompt(pairs, [str(w) for w in warnings])}

    def _runda(self, body: Dict) -> Dict:
        tekst = _text(body, "tekst")
        current = _text(body, "biezacy", required=False)
        model = body.get("model") or self.server.default_model
        if not isinstance(model, str) or not model:
            raise Invalid(400, "Brak modelu. Uruchom: %s instaluj" % COMMAND)
        hidden, dashes = bool(body.get("ukryte", True)), bool(body.get("myslniki", False))
        original = clean(tekst, hidden, dashes).text
        try:
            return run_round(self.server.backend, model, original, current or original,
                             int(body.get("runda", 1)), hidden, dashes)
        except (TypeError, ValueError):
            raise Invalid(400, "Nieprawidłowe zapytanie.")

    def _widok(self, body: Dict) -> Dict:
        tekst = _text(body, "tekst")
        result = _text(body, "wynik", required=False)
        cleaned = clean(tekst, bool(body.get("ukryte", True)), bool(body.get("myslniki", False)))
        if result is None:
            after, problems = cleaned.text, []
        else:
            after, problems = result, check(cleaned.text, result, bool(body.get("uciete", False)))
        spans = [span for p in problems for span in p.missing_spans]
        view = build_view(cleaned.text, cleaned.changes, after, spans)
        return {"przed": view["przed"], "po": view["po"], "czyszczenie": summary(cleaned.changes),
                "problemy": [asdict(p) for p in problems]}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR would let a second Szlif bind the same port silently.
    allow_reuse_address = os.name != "nt"

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # a closed browser tab is not an error worth printing


def make_server(backend: Backend, default_model: Optional[str], port: int = 8765) -> Server:
    try:
        server = Server(("127.0.0.1", port), Handler)
    except OSError:
        server = Server(("127.0.0.1", 0), Handler)
    server.backend = backend
    server.default_model = default_model
    return server
