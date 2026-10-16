import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import szlif
from tests.fakes import FakeServer

P1 = "Pierwszy akapit ma tutaj dość dużo słów, żeby model mógł go spokojnie przepisać bez kłopotu."
R1 = "Pierwszy akapit zawiera sporo słów, więc model może go bez kłopotu spokojnie przepisać od nowa."
LONG = R1 + " Warto też pamiętać o regularnych ćwiczeniach, zdrowej diecie i odpowiednio długim śnie każdej nocy."


def ollama(reply):
    return {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
            ("GET", "/api/tags"): (200, {"models": [{"name": "m"}]}, 0),
            ("POST", "/api/chat"): (200, {"message": {"content": reply}, "done_reason": "stop"}, 0)}


class Instaluj(unittest.TestCase):
    def test_model_option_reaches_installer(self):
        with mock.patch("szlif_core.install.main", return_value=0) as installer:
            self.assertEqual(szlif.main(["instaluj", "--model", "m"]), 0)
        installer.assert_called_once_with("http://127.0.0.1:11434", "m")


class Przepisz(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = folder.name
        patcher = mock.patch.dict(os.environ, {"SZLIF_CONFIG": os.path.join(folder.name, "szlif.json")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = self.path("tekst.txt")
        with open(self.source, "w", encoding="utf-8") as f:
            f.write("Tytuł\n\n" + P1 + "\n")

    def path(self, name):
        return os.path.join(self.dir, name)

    def run_cli(self, reply, *extra):
        err, out = io.StringIO(), io.StringIO()
        with FakeServer(ollama(reply)) as s, contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = szlif.main(["przepisz", self.source, "--serwer", s.url] + list(extra))
        return code, out.getvalue(), err.getvalue()

    def test_files_written_and_no_warnings(self):
        code, _, err = self.run_cli(R1, "--wynik", self.path("wynik.txt"), "--raport", self.path("raport.json"),
                                    "--weryfikacja", self.path("prompt.txt"))
        self.assertEqual(code, 0, err)
        with open(self.path("wynik.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Tytuł\n\n" + R1 + "\n")
        with open(self.path("raport.json"), encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual((report["model"], report["akapity"][0]["numer"], report["ostrzezenia"]), ("m", 2, 0))
        with open(self.path("prompt.txt"), encoding="utf-8") as f:
            self.assertIn("Akapit 2\nPRZED: " + P1, f.read())

    def test_result_on_stdout_and_warning_exit_3(self):
        code, out, err = self.run_cli(LONG)
        self.assertEqual(code, 3)
        self.assertIn(LONG, out)
        self.assertIn("Akapit 2: Wynik jest wyraźnie dłuższy", err)

    def test_local_verification(self):
        report = self.path("raport.json")
        with FakeServer(ollama(R1)) as s:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = szlif.main(["przepisz", self.source, "--serwer", s.url, "--raport", report, "--sprawdz"])
            chats = [r for r in s.requests if r[1] == "/api/chat"]
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(len(chats), 3)  # round 1, round 2 (unchanged, stops), the check
        self.assertIn("Akapit 2\nPRZED: " + P1, chats[-1][3]["messages"][-1]["content"])
        self.assertIn("Weryfikacja (m):", err.getvalue())
        with open(report, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["weryfikacja"], {"model": "m", "odpowiedz": R1, "uciete": False})

    def test_unwritable_output_fails_before_the_model(self):
        with FakeServer(ollama(R1)) as s:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = szlif.main(["przepisz", self.source, "--serwer", s.url,
                                   "--raport", self.path("nie-ma/raport.json")])
            chats = [r for r in s.requests if r[1] == "/api/chat"]
        self.assertEqual((code, chats), (1, []))
        self.assertIn("Nie mogę zapisać", err.getvalue())

    def test_failed_check_keeps_report(self):
        routes = ollama(R1)
        ok = routes[("POST", "/api/chat")]
        routes[("POST", "/api/chat")] = [ok, ok, (500, {"error": "brak pamięci"}, 0)]
        report = self.path("raport.json")
        with FakeServer(routes) as s:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                code = szlif.main(["przepisz", self.source, "--serwer", s.url, "--raport", report, "--sprawdz"])
        self.assertEqual(code, 0)
        with open(report, encoding="utf-8") as f:
            check = json.load(f)["weryfikacja"]
        self.assertIn("błędem 500", check["blad"])

    def test_stdin_read_as_utf8(self):  # review: a Windows pipe is decoded with the code page otherwise
        stdin = io.TextIOWrapper(io.BytesIO(("Tytuł\n\n" + P1 + "\n").encode("utf-8")), encoding="cp1250")
        out = io.StringIO()
        with FakeServer(ollama(R1)) as s, mock.patch("sys.stdin", stdin), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
            code = szlif.main(["przepisz", "-", "--serwer", s.url])
            prompt = [r for r in s.requests if r[1] == "/api/chat"][0][3]["messages"][-1]["content"]
        self.assertEqual(code, 0)
        self.assertIn(P1, prompt)
        self.assertIn("Tytuł", out.getvalue())

    def test_missing_file(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = szlif.main(["przepisz", self.path("nie-ma.txt")])
        self.assertEqual(code, 1)
        self.assertIn("Nie mogę przeczytać pliku", err.getvalue())


if __name__ == "__main__":
    unittest.main()
