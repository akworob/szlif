import unittest

from szlif_core.guard import check, find_values


def key(text):
    return [v.key for v in find_values(text)]


class Values(unittest.TestCase):
    def test_equivalent_spellings(self):
        for a, b in [("1 000 zł", "1000 PLN"), ("12,5 %", "12,5 procent"), ("15 zł", "15 złotych"),
                     ("30 min", "30 minut"), ("3 godz.", "3 godzin"), ("2,5 mln zł", "2,5 miliona złotych")]:
            with self.subTest(a=a, b=b):
                self.assertEqual(key(a), key(b))

    def test_different_values(self):
        for a, b in [("9 kwietnia", "9 maja"), ("12,5", "12.5"), ("2,5 mln", "2 500 000"),
                     ("12.03.2026", "12 marca 2026"), ("5 kWh", "5 MWh"), ("-3 %", "3 %")]:
            with self.subTest(a=a, b=b):
                self.assertNotEqual(key(a), key(b))

    def test_symbolic_units(self):
        self.assertEqual(key("5 kWh, 20 °C, 3 CO2"), ["5 kWh", "20 °C", "3 CO2"])

    def test_capitalised_word_not_unit(self):
        self.assertEqual(key("w 2026 Polska"), ["2026"])

    def test_noun_not_unit(self):
        self.assertEqual(check("Przyszło 5 osób.", "Przyszło 5 rodzin."), [])

    def test_list_numbering_ignored(self):
        self.assertEqual(find_values("1. Pierwszy\n2) Drugi"), [])

    def test_range_has_no_sign(self):
        self.assertEqual(key("10-20 osób"), ["10", "20"])

    def test_dates_and_times(self):
        self.assertEqual(key("o 14:30, 2026-03-12, 12.03.2026"), ["14:30", "2026-03-12", "12.03.2026"])


class Check(unittest.TestCase):
    def test_missing_reported(self):
        p = check("Spotkanie 9 kwietnia o 18:00.", "Spotkanie w kwietniu o 18:00.")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0].kind, "values")
        self.assertEqual(p[0].missing, ["9 kwietnia"])
        self.assertEqual(p[0].added, [])
        self.assertEqual(p[0].missing_spans, [(10, 20)])

    def test_added_reported(self):
        p = check("Bilet kosztuje 15 zł.", "Bilet kosztuje 15 zł, ulgowy 10 zł.")
        self.assertEqual(p[0].added, ["10 zł"])

    def test_multiplicity(self):
        self.assertEqual(check("5 zł i 5 zł", "5 zł")[0].missing, ["5 zł"])

    def test_cut(self):
        self.assertEqual([p.kind for p in check("a", "a", cut=True)], ["cut"])

    def test_too_long(self):
        self.assertEqual([p.kind for p in check("dwa słowa", " ".join(["x"] * 20))], ["too_long"])


if __name__ == "__main__":
    unittest.main()
