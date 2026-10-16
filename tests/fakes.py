"""Test doubles: a fake HTTP model server and an in-memory backend."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from szlif_core.backends import Backend


class FakeServer:
    """routes: {(method, path): (status, body, delay_s[, headers])}. A dict body is sent
    as JSON, bytes as they are. Unknown routes answer 404."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                path = self.path.split("?", 1)[0]
                fake.requests.append((self.command, path, dict(self.headers), body))
                status, payload, delay, *extra = fake.routes.get(
                    (self.command, path), (404, {"error": "not found"}, 0))
                if delay:
                    time.sleep(delay)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for name, value in (extra[0] if extra else {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.server.handle_error = lambda *args: None
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class FakeBackend(Backend):
    """Returns the given replies in order; a BackendError in the list is raised."""

    def __init__(self, replies=None, models=None, list_error=None, cloud=True, kind="ollama",
                 url="http://127.0.0.1:11434"):
        super().__init__(url)
        self.kind = kind
        self.replies = list(replies or [])
        self.models = list(models or [])
        self.list_error = list_error
        self.cloud = cloud
        self.calls = []

    def list_models(self):
        if self.list_error:
            raise self.list_error
        return self.models

    def chat(self, model, system, user):
        self.calls.append((model, system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def cloud_disabled(self):
        return self.cloud
