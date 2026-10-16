import unittest

from szlif_core.backends import BackendError, Reply, make_backend
from tests.fakes import FakeServer

CHAT_OK = {"message": {"content": "x"}, "done_reason": "stop"}


class Detection(unittest.TestCase):
    def test_detect_ollama(self):
        with FakeServer({("GET", "/api/version"): (200, {"version": "0.40.1"}, 0)}) as s:
            self.assertEqual(make_backend(s.url).kind, "ollama")

    def test_detect_openai(self):
        with FakeServer({("GET", "/v1/models"): (200, {"data": [{"id": "b"}]}, 0)}) as s:
            backend = make_backend(s.url)
            self.assertEqual(backend.kind, "openai")
            self.assertEqual(backend.list_models(), ["b"])
            self.assertEqual(s.requests[-1][1], "/v1/models")

    def test_unreachable_is_ollama(self):
        self.assertEqual(make_backend("http://127.0.0.1:9").kind, "ollama")

    def test_is_local(self):
        for url, local in [("http://127.0.0.1:11434", True), ("http://localhost:1", True),
                           ("http://192.168.1.20:11434", False)]:
            with self.subTest(url=url):
                self.assertEqual(make_backend(url, kind="ollama").is_local, local)


class Ollama(unittest.TestCase):
    def test_ollama_chat_payload(self):
        routes = {("POST", "/api/chat"): (200, {"message": {"content": "x"}, "done_reason": "length"}, 0)}
        with FakeServer(routes) as s:
            reply = make_backend(s.url, kind="ollama").chat("m", "sys", "usr")
            body = s.requests[-1][3]
        self.assertEqual(reply, Reply("x", True))
        self.assertIs(body["stream"], False)
        self.assertEqual(body["options"], {"temperature": 0.3, "num_ctx": 16384})
        self.assertIs(body["truncate"], False)
        self.assertIs(body["shift"], False)
        self.assertEqual(body["model"], "m")
        self.assertEqual(body["messages"], [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}])

    def test_list_models(self):
        with FakeServer({("GET", "/api/tags"): (200, {"models": [{"name": "a"}]}, 0)}) as s:
            self.assertEqual(make_backend(s.url, kind="ollama").list_models(), ["a"])

    def test_cloud_disabled(self):
        for answer, expected in [((200, {"cloud": {"disabled": True}}, 0), True),
                                 ((200, {"cloud": {}}, 0), False), ((404, {}, 0), None)]:
            with self.subTest(answer=answer), FakeServer({("GET", "/api/status"): answer}) as s:
                self.assertIs(make_backend(s.url, kind="ollama").cloud_disabled(), expected)

    def test_missing_model(self):
        with FakeServer({("POST", "/api/chat"): (404, {"error": "model not found"}, 0)}) as s:
            with self.assertRaisesRegex(BackendError, "ollama pull m"):
                make_backend(s.url, kind="ollama").chat("m", "s", "u")

    def test_connection_refused(self):
        with self.assertRaisesRegex(BackendError, "Nie mogę połączyć się z serwerem modelu"):
            make_backend("http://127.0.0.1:9", kind="ollama").chat("m", "s", "u")

    def test_timeout_message(self):
        with FakeServer({("POST", "/api/chat"): (200, CHAT_OK, 2)}) as s:
            with self.assertRaisesRegex(BackendError, "nie odpowiedział"):
                make_backend(s.url, kind="ollama", timeout=0.5).chat("m", "s", "u")

    def test_redirect_not_followed(self):
        routes = {("GET", "/api/tags"): (302, b"", 0, {"Location": "http://127.0.0.1:9/x"})}
        with FakeServer(routes) as s:
            with self.assertRaises(BackendError):
                make_backend(s.url, kind="ollama").list_models()

    def test_unknown_format(self):
        with FakeServer({("POST", "/api/chat"): (200, {"nothing": 1}, 0)}) as s:
            with self.assertRaisesRegex(BackendError, "nieznanym formacie"):
                make_backend(s.url, kind="ollama").chat("m", "s", "u")


class OpenAI(unittest.TestCase):
    ROUTES = {("POST", "/v1/chat/completions"):
              (200, {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}, 0)}

    def test_openai_chat(self):
        with FakeServer(self.ROUTES) as s:
            reply = make_backend(s.url + "/v1", kind="openai", api_key="k").chat("m", "s", "u")
            self.assertEqual(s.requests[-1][2].get("Authorization"), "Bearer k")
            make_backend(s.url, kind="openai").chat("m", "s", "u")
            self.assertNotIn("Authorization", s.requests[-1][2])
        self.assertEqual(reply, Reply("x", True))

    def test_bad_key(self):
        with FakeServer({("POST", "/v1/chat/completions"): (401, {"error": "bad key"}, 0)}) as s:
            with self.assertRaisesRegex(BackendError, "SZLIF_API_KEY"):
                make_backend(s.url, kind="openai").chat("m", "s", "u")

    def test_cloud_not_applicable(self):
        self.assertIsNone(make_backend("http://127.0.0.1:9", kind="openai").cloud_disabled())


if __name__ == "__main__":
    unittest.main()
