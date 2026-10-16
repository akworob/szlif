import unittest

from szlif_core.backends import BackendError, Reply
from szlif_core.rewrite import ROUNDS, SYSTEM_PROMPT, TASK_LINE, run_round
from tests.fakes import FakeBackend

ORIGINAL = "Spotkanie odbędzie się 9 kwietnia."


def run(replies, round_no=1, current=ORIGINAL, hidden=True, dashes=False):
    backend = FakeBackend(replies)
    return run_round(backend, "m", ORIGINAL, current, round_no, hidden, dashes), backend


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

    def test_bad_round(self):
        for n in (0, 4):
            with self.subTest(n=n), self.assertRaises(ValueError):
                run([], round_no=n)


if __name__ == "__main__":
    unittest.main()
