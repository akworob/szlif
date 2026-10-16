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

    def test_en_dash_minus(self):
        self.assertEqual(key("do \u20135 \u00b0C"), ["-5 \u00b0C"])
        self.assertEqual(len(check("Temperatura spad\u0142a do \u20135 \u00b0C.", "Temperatura spad\u0142a do 5 \u00b0C.")), 1)
        self.assertEqual(key("15 z\u0142 \u2013 20 z\u0142"), ["15 z\u0142", "20 z\u0142"])

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

    def test_paragraph_grows_by_half(self):  # measured: an invented sentence appended to a paragraph
        original = " ".join(["słowo"] * 21)
        self.assertEqual([p.kind for p in check(original, " ".join(["słowo"] * 32))], ["too_long"])
        self.assertEqual(check(original, " ".join(["słowo"] * 26)), [])

    def test_too_short(self):  # measured: a whole article came back as a summary (1035 -> 420 words)
        original = " ".join(["słowo"] * 40)
        problems = check(original, " ".join(["słowo"] * 20))
        self.assertEqual([p.kind for p in problems], ["too_short"])
        self.assertIn("50%", problems[0].message)
        self.assertEqual(check(original, " ".join(["słowo"] * 30)), [])
        self.assertEqual(check("Bardzo krótki tekst tutaj.", "Krótki tekst."), [])

    def test_paragraph_count(self):
        problems = check("Ala ma kota.\n\nKot ma Alę.", "Ala ma kota, a kot ma Alę.")
        self.assertIn("paragraphs", [p.kind for p in problems])
        self.assertIn("2 \u2192 1", [p.message for p in problems if p.kind == "paragraphs"][0])

    def test_line_break_counts_as_paragraph(self):  # a paragraph is one line in a Word paste
        kinds = [p.kind for p in check("Ala ma kota, a kot ma Alę i psa.", "Ala ma kota.\nKot ma Alę i psa.")]
        self.assertIn("paragraphs", kinds)

    def test_soft_wrap_not_a_paragraph(self):
        self.assertEqual(check("Ala ma kota, a kot\nma Alę i psa.", "Ala ma kota, a kot ma Alę i psa."), [])

    def test_meta_comment(self):  # measured: an instruction leaked into the text
        original = "Jeśli dolegliwości wyraźnie się zmniejszają, może to pomóc w planowaniu dalszego leczenia."
        output = original + " Krótkie zdania przeplatają się z dłuższymi, co nadaje tekstowi naturalny rytm."
        kinds = [p.kind for p in check(original, output)]
        self.assertIn("meta", kinds)

    def test_meta_single_ordinary_word_not_flagged(self):  # review: everyday words share the stems
        for before, after in [("Uważam, że to dobry pomysł na wyjazd.", "Moim zdaniem to dobry pomysł na wyjazd."),
                              ("Postępujemy zgodnie z regulacjami.", "Postępujemy zgodnie z przepisami."),
                              ("Lekarz poda lek na receptę.", "Lekarz przepisze lek na receptę."),
                              ("Utrzymaj stałe tempo marszu.", "Utrzymaj stały rytm marszu."),
                              ("Sklep sprzedaje tkaniny.", "Sklep sprzedaje tekstylia.")]:
            with self.subTest(after=after):
                self.assertNotIn("meta", [p.kind for p in check(before, after)])

    def test_meta_words_already_in_original(self):
        text = "Ten tekst ma dobry rytm, a zdania są krótkie."
        self.assertEqual(check(text, "Zdania są krótkie, a ten tekst ma dobry rytm."), [])


if __name__ == "__main__":
    unittest.main()
