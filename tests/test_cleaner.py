import unittest

from szlif_core.cleaner import Change, clean, summary


def labels(result):
    return [c.label for c in result.changes]


def undo(result):
    """The input back from the cleaned text and its changes."""
    text = result.text
    for c in reversed(result.changes):
        text = text[:c.pos] + c.original + text[c.pos + c.length:]
    return text


class HiddenCharacters(unittest.TestCase):
    def test_zwsp_removed(self):
        r = clean("ab​c")
        self.assertEqual(r.text, "abc")
        self.assertEqual(r.changes, [Change(2, 0, "​", "", "ZWSP")])

    def test_bom_and_soft_hyphen(self):
        r = clean("﻿po­wie­dzieć")
        self.assertEqual(r.text, "powiedzieć")
        self.assertEqual(labels(r), ["BOM", "SHY", "SHY"])

    def test_bidi_removed(self):
        r = clean("a‮b‬c")
        self.assertEqual(r.text, "abc")
        self.assertEqual(labels(r), ["BIDI", "BIDI"])

    def test_tag_run_decoded(self):
        r = clean("Tekst" + "".join(chr(0xE0000 + ord(c)) for c in "hej"))
        self.assertEqual(r.text, "Tekst")
        self.assertEqual(labels(r), ["ukryty tekst: hej"])

    def test_emoji_zwj_kept(self):
        r = clean("👩‍💻 ok")
        self.assertEqual(r.text, "👩‍💻 ok")
        self.assertEqual(r.changes, [])

    def test_flag_tags_kept(self):
        flag = "🏴\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F"
        self.assertEqual(clean(flag).text, flag)
        self.assertEqual(clean(flag).changes, [])

    def test_variation_selector_kept(self):
        self.assertEqual(clean("❤️").text, "❤️")


class Spaces(unittest.TestCase):
    def test_spaces_normalized(self):
        r = clean("w domu 10 000")
        self.assertEqual(r.text, "w domu 10 000")
        self.assertEqual(labels(r), ["NBSP", "NNBSP"])
        self.assertEqual([c.length for c in r.changes], [1, 1])

    def test_other_space_label(self):
        r = clean("a b")
        self.assertEqual(r.text, "a b")
        self.assertEqual(labels(r), ["SPACJA U+2009"])

    def test_line_separator(self):
        r = clean("a b")
        self.assertEqual(r.text, "a\nb")
        self.assertEqual(labels(r), ["LS"])


class Homoglyphs(unittest.TestCase):
    def test_homoglyph_in_mixed_word(self):
        r = clean("Polskа")
        self.assertEqual(r.text, "Polska")
        self.assertEqual(labels(r), ["homoglif а→a"])

    def test_cyrillic_word_untouched(self):
        r = clean("Москва и Kraków")
        self.assertEqual(r.text, "Москва и Kraków")
        self.assertEqual(r.changes, [])

    def test_fullwidth(self):
        r = clean("Ａ１")
        self.assertEqual(r.text, "A1")
        self.assertEqual(labels(r), ["pełna-szerokość Ａ→A", "pełna-szerokość １→1"])

    def test_polish_quotes_kept(self):
        self.assertEqual(clean("„Tak” … dobrze").changes, [])


class Dashes(unittest.TestCase):
    def test_dashes_off_by_default(self):
        self.assertEqual(clean("To jest — test").text, "To jest — test")

    def test_dashes_sentence(self):
        r = clean("To jest — test", dashes=True)
        self.assertEqual(r.text, "To jest, test")
        self.assertEqual(labels(r), ["— → ,"])

    def test_dashes_unspaced_em(self):
        self.assertEqual(clean("słowo—słowo", dashes=True).text, "słowo, słowo")

    def test_dashes_unspaced_en(self):
        r = clean("polsko–niemiecki", dashes=True)
        self.assertEqual(r.text, "polsko-niemiecki")
        self.assertEqual(labels(r), ["– → -"])

    def test_dashes_range(self):
        r = clean("10–20 osób", dashes=True)
        self.assertEqual(r.text, "10-20 osób")
        self.assertEqual(labels(r), ["– → -"])

    def test_dash_line_start_kept(self):
        self.assertEqual(clean("– Tak – powiedział.", dashes=True).text, "– Tak, powiedział.")

    def test_hidden_false_only_dashes(self):
        self.assertEqual(clean("a​ — b", hidden=False, dashes=True).text, "a​, b")


class Bookkeeping(unittest.TestCase):
    def test_positions_rebuild(self):
        tags = "".join(chr(0xE0000 + ord(c)) for c in "ok")
        text = "Zd​anie w Polskа" + tags + " — to tyle.\n– Tak"
        r = clean(text, dashes=True)
        self.assertEqual(r.text, "Zdanie w Polska, to tyle.\n– Tak")
        self.assertEqual(undo(r), text)

    def test_summary(self):
        self.assertEqual(summary(clean("a​b​c d").changes), {"ZWSP": 2, "NBSP": 1})


if __name__ == "__main__":
    unittest.main()
