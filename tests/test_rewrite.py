import unittest

from szlif_core.backends import BackendError, Reply
from szlif_core.rewrite import PURPOSE, READABILITY, ROUNDS, SYSTEM_PROMPT, TASK_LINE, run_round
from tests.fakes import FakeBackend

ORIGINAL = "Spotkanie odbędzie się 9 kwietnia."


def run(replies, round_no=1, current=ORIGINAL, hidden=True, dashes=False, **style):
    backend = FakeBackend(replies)
    return run_round(backend, "m", ORIGINAL, current, round_no, hidden, dashes, **style), backend


class Rounds(unittest.TestCase):
    def test_round1_clean(self):
        r, _ = run([Reply("Spotkanie jest 9 kwietnia.", False)])
        self.assertEqual((r["przyjeta"], r["stop"], r["problemy"]), (True, False, []))
        self.assertEqual(r["tekst"], "Spotkanie jest 9 kwietnia.")

    def test_round1_warns_stops(self):
        r, _ = run([Reply("Spotkanie jest w kwietniu.", False)])
        self.assertEqual((r["przyjeta"], r["stop"]), (True, True))
        self.assertTrue(r["powod"].startswith("Zatrzymano po rundzie 1"))
        self.assertEqual(r["problemy"][0]["missing"], ["9 kwietnia"])

    def test_round2_warns_rejected(self):
        r, _ = run([Reply("Spotkanie jest w kwietniu.", False)], round_no=2, current="Spotkanie jest 9 kwietnia.")
        self.assertEqual((r["przyjeta"], r["stop"]), (False, True))
        self.assertTrue(r["powod"].startswith("Zatrzymano po rundzie 1: runda 2 dała ostrzeżenie"), r["powod"])

    def test_round2_error_stops(self):
        r, _ = run([BackendError("x")], round_no=2)
        self.assertEqual((r["przyjeta"], r["stop"]), (False, True))
        self.assertIn("runda 2 nie powiodła się (x)", r["powod"])

    def test_round1_error_raises(self):
        with self.assertRaises(BackendError):
            run([BackendError("x")])

    def test_empty_reply(self):
        with self.assertRaisesRegex(BackendError, "Model zwrócił pusty tekst. Spróbuj jeszcze raz."):
            run([Reply("  ", False)])
        r, _ = run([Reply("  ", False)], round_no=2)
        self.assertEqual((r["przyjeta"], r["stop"]), (False, True))

    def test_output_cleaned(self):
        r, _ = run([Reply("Spotkanie jest 9​ kwietnia.", False)])
        self.assertEqual(r["tekst"], "Spotkanie jest 9 kwietnia.")
        r, _ = run([Reply("Spotkanie — 9 kwietnia.", False)], dashes=True)
        self.assertEqual(r["tekst"], "Spotkanie, 9 kwietnia.")

    def test_prompt_shape(self):
        current = "Spotkanie jest 9 kwietnia."
        _, backend = run([Reply(current, False)], round_no=2, current=current)
        model, system, user = backend.calls[0]
        self.assertEqual(system, SYSTEM_PROMPT)
        self.assertEqual(user, "%s %s\n\n%s" % (TASK_LINE, ROUNDS[1][1], current))

    def test_unchanged_round_stops(self):  # measured: rounds 2 and 3 returned round 1 word for word, 4 minutes
        current = "Spotkanie jest 9 kwietnia."
        r, _ = run([Reply(current, False)], round_no=2, current=current)
        self.assertEqual((r["przyjeta"], r["stop"], r["bez_zmian"], r["powod"]), (True, True, True, None))

    def test_changed_round_continues(self):
        r, _ = run([Reply("Spotkanie jest 9 kwietnia.", False)])
        self.assertEqual((r["stop"], r["bez_zmian"]), (False, False))

    def test_prompt_forbids_additions(self):  # measured: the model appended advice and answered questions
        self.assertIn("Nie dopisuj nowych zdań", SYSTEM_PROMPT)
        self.assertIn("na nie nie odpowiadaj", SYSTEM_PROMPT)
        self.assertIn("niczego nie dopisuj", TASK_LINE)

    def test_style_in_prompt(self):
        _, backend = run([Reply("Spotkanie odbędzie się 9 kwietnia.", False)],
                         readability="akademicka", purpose="naukowy")
        user = backend.calls[0][2]
        self.assertIn(READABILITY["akademicka"][1], user)
        self.assertIn(PURPOSE["naukowy"][1], user)
        self.assertTrue(user.endswith("\n\n" + ORIGINAL))

    def test_default_style_adds_nothing(self):
        _, backend = run([Reply("Spotkanie odbędzie się 9 kwietnia.", False)])
        self.assertEqual(backend.calls[0][2], "%s %s\n\n%s" % (TASK_LINE, ROUNDS[0][1], ORIGINAL))

    def test_scientific_style_keeps_hedges_and_citations(self):  # the academic example the user sent
        self.assertIn("zastrzeżenie", PURPOSE["naukowy"][1])
        self.assertIn("przypis", PURPOSE["naukowy"][1])

    def test_unknown_style(self):
        for style in ({"readability": "x"}, {"purpose": "x"}):
            with self.subTest(style=style), self.assertRaises(ValueError):
                run([], **style)

    def test_bad_round(self):
        for n in (0, 4):
            with self.subTest(n=n), self.assertRaises(ValueError):
                run([], round_no=n)


if __name__ == "__main__":
    unittest.main()
