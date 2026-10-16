import io
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from szlif_core import update
from tests.fakes import FakeServer

RELEASE = {"tag_name": "v9.1.0", "html_url": "https://github.com/akworob/szlif/releases/tag/v9.1.0",
           "zipball_url": "https://api.github.com/repos/akworob/szlif/zipball/v9.1.0", "body": "Nowości."}


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class Versions(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(update.newer("0.3.0", "0.2.0"))
        self.assertTrue(update.newer("v0.10.0", "0.9.1"))
        self.assertFalse(update.newer("v0.2.0", "0.2.0"))
        self.assertFalse(update.newer("nonsense", "0.2.0"))

    def test_check_due(self):
        now = time.time()
        self.assertFalse(update.check_due({}, now))  # nobody agreed to checking
        self.assertTrue(update.check_due({"aktualizacje": True}, now))
        self.assertFalse(update.check_due({"aktualizacje": True, "sprawdzono": now - 3600}, now))
        self.assertTrue(update.check_due({"aktualizacje": True, "sprawdzono": now - 2 * 86400}, now))


class LatestRelease(unittest.TestCase):
    def test_found(self):
        with FakeServer({("GET", "/repos/akworob/szlif/releases/latest"): (200, RELEASE, 0)}) as s:
            r = update.latest_release(s.url + "/repos/akworob/szlif/releases/latest")
        self.assertEqual((r["wersja"], r["adres"]), ("9.1.0", RELEASE["html_url"]))

    def test_none_on_a_broken_answer(self):  # review: IncompleteRead is not an OSError
        import http.client
        with mock.patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"")):
            self.assertIsNone(update.latest_release())

    def test_none_without_release_or_network(self):
        with FakeServer({}) as s:
            self.assertIsNone(update.latest_release(s.url + "/repos/akworob/szlif/releases/latest"))
        self.assertIsNone(update.latest_release("http://127.0.0.1:9/x"))


class Updating(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_install_kind(self):
        self.assertEqual(update.install_kind(self.root), "zip")
        (self.root / ".git").mkdir()
        self.assertEqual(update.install_kind(self.root), "git")

    def test_clone_without_git_command_is_not_overwritten(self):  # review: GitHub Desktop has no git on PATH
        (self.root / ".git").mkdir()
        (self.root / "szlif.py").write_text("stary")
        out = io.StringIO()
        release = {"wersja": "99.0.0", "adres": "a", "zip": "https://api.github.com/x", "opis": ""}
        with mock.patch.object(update, "update_zip") as update_zip:
            code = update.run_update(out, self.root, release, which={}.get)
        self.assertEqual(code, 1)
        update_zip.assert_not_called()
        self.assertIn("git", out.getvalue())

    def test_git_ignores_untracked_files(self):  # review: wynik.txt from the README examples blocked updates
        calls = []

        def run(cmd):
            calls.append(cmd)
            return 0, "abc\n" if cmd[3:4] == ["rev-parse"] and len(calls) < 3 else ("def\n" if cmd[3:4] == ["rev-parse"] else "")
        update.update_git(self.root, run, io.StringIO())
        self.assertIn("--untracked-files=no", calls[0])

    def test_git_pull_without_a_new_commit_is_not_an_update(self):  # review: Szlif exited after "t" with nothing new
        def run(cmd):
            return 0, "abc\n" if "rev-parse" in cmd else ""
        out = io.StringIO()
        self.assertEqual(update.update_git(self.root, run, out), 1)
        self.assertIn("nie przyniósł", out.getvalue())

    def test_git_refuses_local_changes(self):
        calls = []

        def run(cmd):
            calls.append(cmd)
            return 0, " M szlif.py\n"
        out = io.StringIO()
        self.assertEqual(update.update_git(self.root, run, out), 1)
        self.assertEqual(len(calls), 1)  # only the status, no pull
        self.assertIn("zmiany", out.getvalue())

    def test_git_pulls_when_clean(self):
        calls, heads = [], iter(["abc\n", "def\n"])

        def run(cmd):
            calls.append(cmd)
            return 0, next(heads) if "rev-parse" in cmd else ""
        self.assertEqual(update.update_git(self.root, run, io.StringIO()), 0)
        self.assertIn(["git", "-C", str(self.root), "pull", "--ff-only"], calls)

    def test_zip_update_writes_files_and_skips_escapes(self):
        data = zip_bytes({"szlif-abc/szlif.py": "nowy", "szlif-abc/szlif_core/x.py": "x",
                          "szlif-abc/../ucieczka.txt": "zle"})
        (self.root / "szlif.py").write_text("stary")
        with FakeServer({("GET", "/zip"): (200, data, 0)}) as s:
            update.update_zip(self.root, s.url + "/zip", io.StringIO(), allowed_hosts={"127.0.0.1"})
        self.assertEqual((self.root / "szlif.py").read_text(), "nowy")
        self.assertEqual((self.root / "szlif_core" / "x.py").read_text(), "x")
        self.assertFalse((self.root.parent / "ucieczka.txt").exists())

    def test_zip_writes_nothing_when_one_file_is_locked(self):  # review: a half-written install
        data = zip_bytes({"szlif-abc/a.txt": "nowy", "szlif-abc/locked.txt": "nowy", "szlif-abc/c.txt": "nowy"})
        for name in ("a.txt", "locked.txt", "c.txt"):
            (self.root / name).write_text("stary")
        os.chmod(self.root / "locked.txt", 0o444)
        self.addCleanup(os.chmod, self.root / "locked.txt", 0o644)
        with FakeServer({("GET", "/zip"): (200, data, 0)}) as s, self.assertRaises(update.UpdateError):
            update.update_zip(self.root, s.url + "/zip", io.StringIO(), allowed_hosts={"127.0.0.1"})
        self.assertEqual([(self.root / n).read_text() for n in ("a.txt", "locked.txt", "c.txt")], ["stary"] * 3)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["a.txt", "c.txt", "locked.txt"])

    def test_zip_with_a_damaged_file_writes_nothing(self):
        data = bytearray(zip_bytes({"szlif-abc/a.txt": "nowa treść pliku"}))
        data[data.index(b"nowa")] ^= 1  # breaks the CRC
        (self.root / "a.txt").write_text("stary")
        with FakeServer({("GET", "/zip"): (200, bytes(data), 0)}) as s, self.assertRaises(update.UpdateError):
            update.update_zip(self.root, s.url + "/zip", io.StringIO(), allowed_hosts={"127.0.0.1"})
        self.assertEqual((self.root / "a.txt").read_text(), "stary")

    def test_zip_from_unknown_host_refused(self):
        with self.assertRaises(update.UpdateError):
            update.update_zip(self.root, "https://example.org/szlif.zip", io.StringIO())


if __name__ == "__main__":
    unittest.main()
