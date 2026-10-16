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
            self.assertEqual(json.load(f)["weryfikacja"], {"model": "m", "odpowiedz": R1})

    def test_missing_file(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = szlif.main(["przepisz", self.path("nie-ma.txt")])
        self.assertEqual(code, 1)
        self.assertIn("Nie mogę przeczytać pliku", err.getvalue())


if __name__ == "__main__":
    unittest.main()
