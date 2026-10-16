import unittest

from szlif_core.cleaner import Change
from szlif_core.view import build_view, tokenize


class View(unittest.TestCase):
    def setUp(self):
        self.v = build_view("Ala ma kota.", [], "Ala ma psa.", [])

    def test_tokenize(self):
        self.assertEqual(tokenize("Ala  ma, kota."), ["Ala", "  ", "ma", ",", " ", "kota", "."])

    def test_concat_invariant(self):
        self.assertEqual("".join(s["text"] for s in self.v["przed"] if s["t"] != "pill"), "Ala ma kota.")
        self.assertEqual("".join(s["text"] for s in self.v["po"]), "Ala ma psa.")

    def test_del_and_ins(self):
        self.assertIn({"t": "del", "text": "kota"}, self.v["przed"])
        self.assertIn({"t": "ins", "text": "psa"}, self.v["po"])

    def test_pill_placement(self):
        v = build_view("abc", [Change(2, 0, "​", "", "ZWSP")], "abc", [])
        self.assertEqual(v["przed"], [{"t": "eq", "text": "ab"}, {"t": "pill", "text": "", "label": "ZWSP"},
                                      {"t": "eq", "text": "c"}])

    def test_warn_flag(self):
        v = build_view("Ala ma kota", [], "Ala ma kota", [(0, 3)])
        self.assertEqual(v["przed"][0], {"t": "eq", "text": "Ala", "warn": True})

    def test_adjacent_merged(self):
        v = build_view("Ala ma kota i psa.", [Change(4, 1, " ", " ", "NBSP")], "Ala nie ma psa.", [(7, 11)])
        for column in ("przed", "po"):
            segs = v[column]
            for a, b in zip(segs, segs[1:]):
                self.assertFalse(a["t"] == b["t"] and a.get("warn") == b.get("warn"), (column, a, b))


if __name__ == "__main__":
    unittest.main()
