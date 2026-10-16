import contextlib
import http.client
import io
import json
import threading
import unittest

from szlif_core.backends import BackendError, Reply
from szlif_core.server import make_server
from tests.fakes import FakeBackend

BIELIK = "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q6_K"


class Running:
    """A Szlif server on a free port, in a thread."""

    def __init__(self, backend, default_model="m", port=0):
        self.server = make_server(backend, default_model, port)
        self.port = self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest(method, path, skip_host=host is not None)
        if host is not None:
            conn.putheader("Host", host)
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else (body or b"")
        all_headers = {"Content-Type": "application/json"} if body is not None else {}
        all_headers.update(headers or {})
        for name, value in all_headers.items():
            conn.putheader(name, value)
        conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        is_json = resp.getheader("Content-Type", "").startswith("application/json")
        return resp.status, (json.loads(raw) if is_json else raw.decode()), resp


def texts(segments, kinds=("eq", "del", "ins")):
    return "".join(s["text"] for s in segments if s["t"] in kinds)


def widok(**body):
    return dict({"tekst": "", "wynik": None, "ukryte": True, "myslniki": False}, **body)


def runda(**body):
    return dict({"tekst": "", "biezacy": None, "runda": 1, "model": "m", "ukryte": True, "myslniki": False}, **body)


class Security(unittest.TestCase):
    def test_page_served(self):
        with Running(FakeBackend()) as s:
            status, body, resp = s.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Szlif", body)
        self.assertIn("default-src 'self'", resp.getheader("Content-Security-Policy"))

    def test_favicon_no_content(self):
        with Running(FakeBackend()) as s:
            self.assertEqual(s.call("GET", "/favicon.ico")[0], 204)

    def test_bad_host_rejected(self):
        with Running(FakeBackend()) as s:
            self.assertEqual(s.call("GET", "/", host="evil.example:80")[0], 403)

    def test_foreign_origin_rejected(self):
        with Running(FakeBackend()) as s:
            status = s.call("POST", "/api/widok", widok(tekst="a"), {"Origin": "http://evil.example"})[0]
        self.assertEqual(status, 403)

    def test_wrong_content_type(self):
        with Running(FakeBackend()) as s:
            status = s.call("POST", "/api/widok", widok(tekst="a"), {"Content-Type": "text/plain"})[0]
        self.assertEqual(status, 415)

    def test_no_request_logging(self):
        err = io.StringIO()
        with Running(FakeBackend()) as s, contextlib.redirect_stderr(err):
            s.call("GET", "/")
            s.call("GET", "/nie-ma")
        self.assertEqual(err.getvalue(), "")

    def test_busy_port_falls_back(self):
        with Running(FakeBackend()) as first:
            second = make_server(FakeBackend(), None, first.port)
            try:
                self.assertNotEqual(second.server_address[1], first.port)
            finally:
                second.server_close()


class Widok(unittest.TestCase):
    def test_widok_clean_only(self):
        with Running(FakeBackend()) as s:
            status, v, _ = s.call("POST", "/api/widok", widok(tekst="a​b"))
        self.assertEqual(status, 200)
        self.assertIn({"t": "pill", "text": "", "label": "ZWSP"}, v["przed"])
        self.assertEqual(texts(v["po"]), "ab")
        self.assertEqual(v["czyszczenie"], {"ZWSP": 1})

    def test_widok_normalizes_newlines(self):
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst="a\r\nb", wynik="a\nb"))[1]
        self.assertEqual([seg for seg in v["przed"] + v["po"] if seg["t"] in ("del", "ins")], [])

    def test_widok_reports_problems(self):
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst="Koszt 15 zł.", wynik="Koszt 10 zł."))[1]
        self.assertEqual(v["problemy"][0]["missing"], ["15 zł"])
        self.assertTrue(any(seg.get("warn") for seg in v["przed"]))

    def test_widok_cut_flag(self):
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst="Ala ma kota.", wynik="Ala ma", uciete=True))[1]
        self.assertEqual([p["kind"] for p in v["problemy"]], ["cut"])


class Runda(unittest.TestCase):
    def test_runda_ok(self):
        with Running(FakeBackend([Reply("Kot jest Ali.", False)])) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota."))
        self.assertEqual(status, 200)
        self.assertEqual((r["tekst"], r["przyjeta"], r["stop"]), ("Kot jest Ali.", True, False))

    def test_runda_rejects_empty(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="  \n"))
        self.assertEqual((status, r["blad"]), (400, "Wklej tekst."))

    def test_runda_rejects_too_long(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="a" * 12001))
        self.assertEqual(status, 413)
        self.assertIn("12 000", r["blad"])
        self.assertIn("12 001", r["blad"])

    def test_runda_bad_json(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/runda", b"{nie json", {"Content-Type": "application/json"})
        self.assertEqual((status, r["blad"]), (400, "Nieprawidłowe zapytanie."))

    def test_runda_backend_error_is_502(self):
        message = "Serwer modelu nie odpowiedział w 900 s. Spróbuj krótszego tekstu."
        with Running(FakeBackend([BackendError(message)])) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota."))
            self.assertEqual((status, r["blad"]), (502, message))
            self.assertEqual(s.call("GET", "/")[0], 200)


class Stan(unittest.TestCase):
    def test_stan_reports_backend_error(self):
        backend = FakeBackend(list_error=BackendError("Nie mogę połączyć się z serwerem modelu (x)."))
        with Running(backend, default_model=None) as s:
            status, st, _ = s.call("GET", "/api/stan")
        self.assertEqual(status, 200)
        self.assertEqual(st["modele"], [])
        self.assertTrue(st["blad"])
        self.assertEqual(st["limit"], 12000)

    def test_stan_no_model_hint(self):
        with Running(FakeBackend(models=[]), default_model=None) as s:
            st = s.call("GET", "/api/stan")[1]
        self.assertIsNone(st["model"])
        self.assertIn("Brak modelu", st["blad"])
        self.assertIn("instaluj", st["blad"])

    def test_stan_picks_bielik(self):
        with Running(FakeBackend(models=["llama3", BIELIK]), default_model=None) as s:
            st = s.call("GET", "/api/stan")[1]
        self.assertEqual(st["model"], BIELIK)
        self.assertEqual((st["rodzaj"], st["lokalny"], st["chmura_wylaczona"]), ("ollama", True, True))

    def test_stan_remote(self):
        backend = FakeBackend(models=["b"], kind="openai", url="https://example.org/v1")
        with Running(backend, default_model=None) as s:
            st = s.call("GET", "/api/stan")[1]
        self.assertEqual((st["lokalny"], st["chmura_wylaczona"], st["serwer"]),
                         (False, None, "https://example.org/v1"))


if __name__ == "__main__":
    unittest.main()
