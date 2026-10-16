import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from szlif_core import COMMAND, config, install
from tests.fakes import FakeServer

BREW_ONLY = {"brew": "/opt/homebrew/bin/brew"}.get
NOTHING = {}.get
Q6 = "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q6_K"
CHAT = (200, {"message": {"content": "Spotkanie odbędzie się 9 kwietnia o godz. 18:00 w sali nr 2. Udział jest "
                                     "bezpłatny, ale prosimy wcześniej potwierdzić swoją obecność."},
              "done_reason": "stop"}, 0)
SHORT_CHAT = (200, {"message": {"content": "Spotkanie 9 kwietnia o godz. 18:00 w sali nr 2."}, "done_reason": "stop"}, 0)


def never_asked(question):
    raise AssertionError("asked: " + question)


class Choices(unittest.TestCase):
    def test_choose_model(self):
        self.assertTrue(install.choose_model(32)[0].endswith(":Q6_K"))
        self.assertTrue(install.choose_model(16)[0].endswith(":Q4_K_M"))
        self.assertIn("4.5B", install.choose_model(8)[0])
        self.assertTrue(install.choose_model(None)[0].endswith(":Q4_K_M"))

    def test_install_command(self):
        self.assertEqual(install.install_command("Darwin", BREW_ONLY), ["brew", "install", "ollama"])
        self.assertIsNone(install.install_command("Darwin", NOTHING))
        self.assertEqual(install.install_command("Windows", {"winget": "winget.exe"}.get),
                         ["winget", "install", "-e", "--id", "Ollama.Ollama"])
        self.assertIsNone(install.install_command("Windows", NOTHING))

    def test_start_command(self):
        self.assertEqual(install.start_command("Darwin", BREW_ONLY), ["brew", "services", "start", "ollama"])
        self.assertEqual(install.start_command("Windows", NOTHING), ["cmd", "/c", "start", "", "ollama", "serve"])

    def test_ram_gb(self):
        ram = install.ram_gb()
        self.assertTrue(ram is None or ram > 0.5)


class CloudSetting(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / ".ollama" / "server.json"

    def test_missing_file_created(self):
        self.assertIs(install.set_cloud_off(self.path), True)
        self.assertEqual(json.loads(self.path.read_text()), {"disable_ollama_cloud": True})

    def test_existing_settings_kept(self):
        self.path.parent.mkdir()
        self.path.write_text('{"a": 1}')
        self.assertIs(install.set_cloud_off(self.path), True)
        self.assertEqual(json.loads(self.path.read_text()), {"a": 1, "disable_ollama_cloud": True})

    def test_already_set(self):
        self.path.parent.mkdir()
        self.path.write_text('{"disable_ollama_cloud": true}')
        self.assertIs(install.set_cloud_off(self.path), False)

    def test_invalid_json_untouched(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json")
        self.assertIsNone(install.set_cloud_off(self.path))
        self.assertEqual(self.path.read_text(), "{not json")


class Ask(unittest.TestCase):
    def test_ask_yes(self):
        for answer, expected in [("t", True), ("TAK", True), ("n", False), ("", False)]:
            with self.subTest(answer=answer), mock.patch("builtins.input", return_value=answer):
                self.assertIs(install.ask_yes("?"), expected)
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIs(install.ask_yes("?"), False)


class Installer(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.dict(os.environ, {"SZLIF_CONFIG": os.path.join(folder.name, "szlif.json")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runs = []

    def run_cmd(self, cmd):
        self.runs.append(cmd)
        return 0

    def test_decline_install(self):
        out = io.StringIO()
        code = install.run_installer("http://127.0.0.1:9", lambda q: False, self.run_cmd, BREW_ONLY,
                                     "Darwin", out, 32)
        self.assertEqual(code, 1)
        self.assertEqual(self.runs, [])
        self.assertIn("brew install ollama", out.getvalue())

    def test_ready_system(self):
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": [{"name": Q6}]}, 0),
                  ("POST", "/api/chat"): CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, never_asked, self.run_cmd, NOTHING, "Darwin", out, 32)
            paths = [r[1] for r in s.requests]
        self.assertEqual(code, 0, out.getvalue())
        self.assertNotIn("/api/pull", paths)
        self.assertIn("Gotowe. Uruchom: " + COMMAND, out.getvalue())
        self.assertEqual(config.load()["model"], Q6)

    def test_pull_progress(self):
        lines = [{"status": "pulling", "total": 100, "completed": 50},
                 {"status": "pulling", "total": 100, "completed": 100}, {"status": "success"}]
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": []}, 0),
                  ("POST", "/api/pull"): (200, "".join(json.dumps(x) + "\n" for x in lines).encode(), 0),
                  ("POST", "/api/chat"): CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, lambda q: True, self.run_cmd, NOTHING, "Darwin", out, 32)
            pulled = [r[3] for r in s.requests if r[1] == "/api/pull"]
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("100%", out.getvalue())
        self.assertEqual(pulled, [{"model": Q6, "stream": True}])

    def test_failed_test_round_fails(self):
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": [{"name": Q6}]}, 0),
                  ("POST", "/api/chat"): (500, {"error": "model requires more system memory"}, 0)}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, never_asked, self.run_cmd, NOTHING, "Darwin", out, 32)
        self.assertEqual(code, 1, out.getvalue())
        self.assertNotIn("Gotowe", out.getvalue())
        self.assertIn("more system memory", out.getvalue())
        self.assertEqual(config.load(), {})

    def test_pull_resumes_after_a_break(self):  # measured: a 5 GB download stopped half way
        half = b'{"status": "pulling", "total": 100, "completed": 50}\n'
        done = b'{"status": "pulling", "total": 100, "completed": 100}\n{"status": "success"}\n'
        routes = {("POST", "/api/pull"): [(200, half, 0), (200, done, 0)]}
        out = io.StringIO()
        with FakeServer(routes) as s, mock.patch.object(install, "RETRY_WAIT", 0):
            install.pull_with_retry(s.url, Q6, out)
            pulls = [r for r in s.requests if r[1] == "/api/pull"]
        self.assertEqual(len(pulls), 2)
        self.assertIn("ponawiam", out.getvalue())
        self.assertIn("Pobrano", out.getvalue())

    def test_pull_refused_is_not_retried(self):
        routes = {("POST", "/api/pull"): (200, b'{"error": "pull model manifest: file does not exist"}\n', 0)}
        with FakeServer(routes) as s, mock.patch.object(install, "RETRY_WAIT", 0):
            with self.assertRaisesRegex(Exception, "file does not exist"):
                install.pull_with_retry(s.url, "nie-ma", io.StringIO())
            self.assertEqual(len([r for r in s.requests if r[1] == "/api/pull"]), 1)

    def test_pull_without_success_fails(self):
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": []}, 0),
                  ("POST", "/api/pull"): (200, b'{"status": "pulling", "total": 100, "completed": 50}\n', 0),
                  ("POST", "/api/chat"): CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s, mock.patch.object(install, "RETRY_WAIT", 0):
            code = install.run_installer(s.url, lambda q: True, self.run_cmd, NOTHING, "Darwin", out, 32)
        self.assertEqual(code, 1, out.getvalue())
        self.assertNotIn("Gotowe", out.getvalue())

    def test_test_round_warning_is_not_failure(self):
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": [{"name": Q6}]}, 0),
                  ("POST", "/api/chat"): SHORT_CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, never_asked, self.run_cmd, NOTHING, "Darwin", out, 32)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("uwaga:", out.getvalue())
        self.assertIn("Gotowe", out.getvalue())

    def test_forced_model_pulled(self):  # --model: check a download without touching the installed Bielik
        small = "hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0"
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": [{"name": Q6}]}, 0),
                  ("POST", "/api/pull"): (200, b'{"status": "success"}\n', 0),
                  ("POST", "/api/chat"): CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, lambda q: True, self.run_cmd, NOTHING, "Darwin", out, 32, model=small)
            pulled = [r[3]["model"] for r in s.requests if r[1] == "/api/pull"]
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(pulled, [small])
        self.assertIn("5,1 GB", out.getvalue())
        self.assertEqual(config.load()["model"], small)

    def test_other_bielik_reused(self):
        other = "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q5_K_M"
        routes = {("GET", "/api/version"): (200, {"version": "0.40.1"}, 0),
                  ("GET", "/api/status"): (200, {"cloud": {"disabled": True}}, 0),
                  ("GET", "/api/tags"): (200, {"models": [{"name": other}]}, 0),
                  ("POST", "/api/chat"): CHAT}
        out = io.StringIO()
        with FakeServer(routes) as s:
            code = install.run_installer(s.url, never_asked, self.run_cmd, NOTHING, "Darwin", out, 32)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(config.load()["model"], other)


if __name__ == "__main__":
    unittest.main()
