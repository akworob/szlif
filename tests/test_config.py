import os
import tempfile
import unittest

from szlif_core import config


class Config(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "szlif.json")
        old = os.environ.get("SZLIF_CONFIG")
        os.environ["SZLIF_CONFIG"] = self.path
        self.addCleanup(lambda: os.environ.pop("SZLIF_CONFIG") if old is None
                        else os.environ.__setitem__("SZLIF_CONFIG", old))

    def test_roundtrip(self):
        config.save({"model": "m"})
        self.assertEqual(config.load(), {"model": "m"})

    def test_missing_is_empty(self):
        self.assertEqual(config.load(), {})

    def test_invalid_is_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(config.load(), {})


if __name__ == "__main__":
    unittest.main()
