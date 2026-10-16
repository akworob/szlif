import contextlib
import http.client
import io
import json
import threading
import unittest

from szlif_core.backends import BackendError, Reply, Unreachable
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

    def test_csp_forbids_framing(self):  # review: clickjacking
        with Running(FakeBackend()) as s:
            self.assertIn("frame-ancestors 'none'", s.call("GET", "/")[2].getheader("Content-Security-Policy"))

    def test_bad_content_length(self):  # review: a non-numeric length dropped the connection
        with Running(FakeBackend()) as s:
            status = s.call("POST", "/api/widok", widok(tekst="a"), {"Content-Length": "abc"})[0]
        self.assertEqual(status, 400)

    def test_unexpected_error_is_500_json(self):  # review: any exception closed the connection silently
        class Broken(FakeBackend):
            def chat(self, model, system, user):
                raise RuntimeError("boom")
        err = io.StringIO()
        with Running(Broken()) as s, contextlib.redirect_stderr(err):
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota."))
        self.assertEqual(status, 500)
        self.assertIn("Nieoczekiwany błąd", r["blad"])
        self.assertNotIn("Ala", err.getvalue())

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

    def test_widok_lists_missing_terms(self):
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst="Zmiany technologiczne, ekonomiczne i społeczne.",
                                                   wynik="Zmiany technologiczne."))[1]
        self.assertEqual(v["znikniete"], ["ekonomiczne", "społeczne"])
        self.assertTrue(any(seg.get("lost") for seg in v["przed"]))

    def test_widok_nfd_input_no_phantom_diff(self):  # review: some PDF copies use decomposed letters
        import unicodedata
        tekst = unicodedata.normalize("NFD", "Zażółć gęślą jaźń.")
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst=tekst, wynik="Zażółć gęślą jaźń."))[1]
        self.assertEqual([seg for seg in v["przed"] + v["po"] if seg["t"] in ("del", "ins")], [])

    def test_clean_only_has_a_larger_limit(self):
        with Running(FakeBackend()) as s:
            self.assertEqual(s.call("POST", "/api/widok", widok(tekst="a" * 13000))[0], 200)
            self.assertEqual(s.call("GET", "/api/stan")[1]["limit_czyszczenia"], 200000)

    def test_negative_content_length_refused(self):  # review: rfile.read(-1) waited for the end of input
        import socket
        with Running(FakeBackend()) as s:
            sock = socket.create_connection(("127.0.0.1", s.port), timeout=5)
            sock.sendall(("POST /api/widok HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n"
                          "Content-Length: -1\r\n\r\n" % s.port).encode())
            answer = sock.recv(100)
            sock.close()
        self.assertIn(b" 400 ", answer)

    def test_widok_cut_flag(self):
        with Running(FakeBackend()) as s:
            v = s.call("POST", "/api/widok", widok(tekst="Ala ma kota.", wynik="Ala ma", uciete=True))[1]
        self.assertEqual([p["kind"] for p in v["problemy"]], ["cut"])


class Bloki(unittest.TestCase):
    PARAGRAPH = "Pierwszy akapit ma tutaj dość dużo słów, żeby model mógł go spokojnie przepisać bez kłopotu."

    def test_bloki_cleaned_and_marked(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/bloki", {"tekst": "Tytuł\r\n\r\n" + self.PARAGRAPH + "\u200b",
                                                        "ukryte": True, "myslniki": False})
        self.assertEqual(status, 200)
        self.assertEqual([(b["tekst"], b["przepisz"]) for b in r["bloki"]],
                         [("Tytuł", False), (self.PARAGRAPH, True)])

    def test_bloki_rejects_empty(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/bloki", {"tekst": " ", "ukryte": True, "myslniki": False})
        self.assertEqual((status, r["blad"]), (400, "Wklej tekst."))


class Weryfikacja(unittest.TestCase):
    def test_prompt_built(self):
        body = {"pary": [{"numer": 2, "przed": "Ala ma kota.", "po": "Kot jest Ali."}], "uwagi": ["Akapit 2: uwaga"]}
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/weryfikacja", body)
        self.assertEqual(status, 200)
        self.assertIn("Akapit 2\nPRZED: Ala ma kota.\nPO: Kot jest Ali.", r["prompt"])
        self.assertIn("- Akapit 2: uwaga", r["prompt"])

    def test_huge_number_rejected(self):  # review: int(1e999) raised OverflowError, the connection dropped
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/weryfikacja", b'{"pary": [{"numer": 1e999, "przed": "a", "po": "b"}]}',
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_bad_pairs(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/weryfikacja", {"pary": "x", "uwagi": []})
        self.assertEqual((status, r["blad"]), (400, "Nieprawidłowe zapytanie."))


def sprawdz(**body):
    return dict({"pary": [{"numer": 2, "przed": "Ala ma kota.", "po": "Kot jest Ali."}], "uwagi": [], "model": "v"},
                **body)


LONG_A, LONG_B = "Pierwsze zdanie. " * 200, "Drugie zdanie. " * 200  # one pair fills a part
TWO_PARTS = [{"numer": 1, "przed": LONG_A, "po": LONG_B}, {"numer": 3, "przed": LONG_B, "po": LONG_A}]


class Sprawdz(unittest.TestCase):
    def test_whole_check(self):
        backend = FakeBackend([Reply("Akapit 2: BEZ ZMIAN", False)])
        with Running(backend) as s:
            status, r, _ = s.call("POST", "/api/sprawdz", sprawdz(uwagi=["Akapit 2: uwaga"]))
        self.assertEqual(status, 200)
        self.assertEqual(r, {"model": "v", "odpowiedz": "Akapit 2: BEZ ZMIAN", "uciete": False, "czesci": 1})
        self.assertEqual(backend.calls[0][0], "v")
        self.assertIn("Akapit 2\nPRZED: Ala ma kota.\nPO: Kot jest Ali.", backend.calls[0][2])
        self.assertIn("- Akapit 2: uwaga", backend.calls[0][2])

    def test_one_part_per_request(self):  # the page shows progress and can stop between parts
        backend = FakeBackend([Reply("Akapit 3: POMIJA", True)])
        with Running(backend) as s:
            status, r, _ = s.call("POST", "/api/sprawdz", sprawdz(pary=TWO_PARTS, czesc=2))
        self.assertEqual(status, 200)
        self.assertEqual(r, {"model": "v", "odpowiedz": "Akapit 3: POMIJA\n(odpowiedź ucięta)", "uciete": True,
                             "czesci": 2})
        self.assertEqual(len(backend.calls), 1)
        self.assertIn("Akapit 3\nPRZED: ", backend.calls[0][2])
        self.assertNotIn("Akapit 1\n", backend.calls[0][2])

    def test_default_model(self):
        backend = FakeBackend([Reply("Akapit 2: BEZ ZMIAN", False)])
        with Running(backend, default_model="bielik") as s:
            r = s.call("POST", "/api/sprawdz", sprawdz(model=None))[1]
        self.assertEqual((r["model"], backend.calls[0][0]), ("bielik", "bielik"))

    def test_no_model(self):
        with Running(FakeBackend(), default_model=None) as s:
            status, r, _ = s.call("POST", "/api/sprawdz", sprawdz(model=None))
        self.assertEqual(status, 400)
        self.assertIn("Brak modelu", r["blad"])

    def test_nothing_changed(self):
        backend = FakeBackend()
        with Running(backend) as s:
            same = [{"numer": 1, "przed": "a", "po": "a"}]
            status, r, _ = s.call("POST", "/api/sprawdz", sprawdz(pary=same, czesc=1))
        self.assertEqual((status, r["odpowiedz"], r["czesci"], backend.calls), (200, "", 0, []))

    def test_backend_error_is_502(self):
        message = "Serwer modelu nie odpowiedział w 900 s. Spróbuj krótszego tekstu."
        with Running(FakeBackend([BackendError(message)])) as s:
            status, r, _ = s.call("POST", "/api/sprawdz", sprawdz())
        self.assertEqual((status, r["blad"]), (502, message))

    def test_bad_input(self):
        bad = [sprawdz(pary="x"), sprawdz(pary=[{"numer": 1}]), sprawdz(uwagi="x"), sprawdz(model=5),
               sprawdz(pary=TWO_PARTS, czesc=3), sprawdz(pary=TWO_PARTS, czesc=0), sprawdz(czesc="x")]
        backend = FakeBackend()
        with Running(backend) as s:
            answers = [s.call("POST", "/api/sprawdz", body)[:2] for body in bad]
            huge = s.call("POST", "/api/sprawdz", b'{"pary": [{"numer": 1, "przed": "a", "po": "b"}], "czesc": 1e999}',
                          {"Content-Type": "application/json"})[:2]
        for status, r in answers + [huge]:
            self.assertEqual(status, 400, r)
            self.assertTrue(r["blad"])
        self.assertEqual(backend.calls, [])


class Runda(unittest.TestCase):
    def test_runda_ok(self):
        with Running(FakeBackend([Reply("Kot jest Ali.", False)])) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota."))
        self.assertEqual(status, 200)
        self.assertEqual((r["tekst"], r["przyjeta"], r["stop"]), ("Kot jest Ali.", True, False))

    def test_runda_passes_style(self):
        backend = FakeBackend([Reply("Kot jest Ali i ma się dobrze.", False)])
        with Running(backend) as s:
            status, _, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota, który ma się dobrze.",
                                                              czytelnosc="akademicka", cel="naukowy"))
        self.assertEqual(status, 200)
        self.assertIn("akademickim", backend.calls[0][2])
        self.assertIn("Styl naukowy", backend.calls[0][2])

    def test_runda_unknown_style(self):
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="Ala ma kota.", cel="x"))
        self.assertEqual((status, r["blad"]), (400, "Nieprawidłowe zapytanie."))

    def test_runda_rejects_invisible_only(self):  # review: ZWSP-only text reached the model empty
        with Running(FakeBackend()) as s:
            status, r, _ = s.call("POST", "/api/runda", runda(tekst="\u200b\u200b"))
        self.assertEqual((status, r["blad"]), (400, "Wklej tekst."))

    def test_unreachable_is_503(self):  # the page stops the whole run on it, but keeps going on other errors
        with Running(FakeBackend([Unreachable("Nie mogę połączyć się z serwerem modelu (x).")])) as s:
            self.assertEqual(s.call("POST", "/api/runda", runda(tekst="Ala ma kota."))[0], 503)

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

    def test_stan_reports_new_version(self):
        info = {"wersja": "99.0.0", "adres": "https://github.com/akworob/szlif/releases"}
        server = make_server(FakeBackend(models=["m"]), "m", 0, update_info=info)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/api/stan")
            st = json.loads(conn.getresponse().read())
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(st["aktualizacja"], info)

    def test_stan_lists_styles(self):
        with Running(FakeBackend(models=["m"])) as s:
            st = s.call("GET", "/api/stan")[1]
        self.assertEqual(st["czytelnosci"][0], ["normalna", "Normalna"])
        self.assertEqual(st["cele"][0], ["ogolny", "Ogólny"])
        self.assertIn(["naukowy", "Naukowy"], st["cele"])

    def test_stan_flags_cloud_models(self):
        with Running(FakeBackend(models=["hf.co/speakleash/Bielik-11B", "gpt-oss:120b-cloud"]), default_model=None) as s:
            st = s.call("GET", "/api/stan")[1]
        self.assertEqual(st["modele_w_chmurze"], ["gpt-oss:120b-cloud"])

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
