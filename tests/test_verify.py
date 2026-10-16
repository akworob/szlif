import unittest

from szlif_core.backends import BackendError, Reply
from szlif_core.verify import build_prompt, check_meaning, chunk_pairs
from tests.fakes import FakeBackend

LONG_A, LONG_B = "Pierwsze zdanie. " * 200, "Drugie zdanie. " * 200  # one pair fills a part


class VerifyPrompt(unittest.TestCase):
    def test_pairs_and_warnings_listed(self):
        prompt = build_prompt([(1, "Ala ma kota.", "Kot należy do Ali."), (4, "Ból bywa ostry.", "Ból jest ostry.")],
                              ["Akapit 4: Wynik jest wyraźnie dłuższy od tekstu (150% słów)."])
        self.assertIn("Akapit 1\nPRZED: Ala ma kota.\nPO: Kot należy do Ali.", prompt)
        self.assertIn("Akapit 4\nPRZED: Ból bywa ostry.\nPO: Ból jest ostry.", prompt)
        self.assertIn("- Akapit 4: Wynik jest wyraźnie dłuższy od tekstu (150% słów).", prompt)
        # The simple per-paragraph answer format: measured, Bielik 11B handles it (the table did not).
        self.assertIn("Akapit N: BEZ ZMIAN", prompt)
        for word in ("DODAJE", "POMIJA", "ZMIENIA"):
            self.assertIn(word, prompt)
        self.assertIn("Nie poprawiaj tekstu", prompt)
        self.assertNotIn("tabel", prompt)

    def test_no_warnings(self):
        self.assertIn("Strażnik Szlifa nie zgłosił uwag.", build_prompt([(1, "Ala ma kota.", "Kot jest Ali.")], []))

    def test_unchanged_pairs_skipped(self):
        prompt = build_prompt([(1, "Ala ma kota.", "Ala ma kota."), (2, "Kot ma Alę.", "Alę ma kot.")], [])
        self.assertNotIn("Akapit 1\n", prompt)
        self.assertIn("Akapit 2\n", prompt)

    def test_chunks_stay_under_limit(self):
        pairs = [(n, "a" * 1000, "b" * 1000) for n in range(1, 8)]
        chunks = chunk_pairs(pairs, max_chars=4500)
        self.assertEqual([[n for n, _, _ in c] for c in chunks], [[1, 2], [3, 4], [5, 6], [7]])

    def test_oversized_pair_gets_its_own_chunk(self):
        self.assertEqual(len(chunk_pairs([(1, "a" * 9000, "b"), (2, "c", "d")], max_chars=4500)), 2)

    def test_nothing_to_verify(self):
        self.assertEqual(build_prompt([(1, "Ala ma kota.", "Ala ma kota.")], []), "")


class CheckMeaning(unittest.TestCase):
    def test_one_call_per_part(self):
        backend = FakeBackend([Reply(" Akapit 1: BEZ ZMIAN ", False), Reply("Akapit 2: DODAJE „zawsze”.", False)])
        check = check_meaning(backend, "m", [(1, LONG_A, LONG_B), (2, LONG_B, LONG_A)], [])
        self.assertEqual(check, {"model": "m", "odpowiedz": "Akapit 1: BEZ ZMIAN\n\nAkapit 2: DODAJE „zawsze”.",
                                 "uciete": False})
        self.assertEqual([model for model, _, _ in backend.calls], ["m", "m"])
        self.assertIn("Akapit 1\nPRZED: " + LONG_A.strip(), backend.calls[0][2])
        self.assertNotIn("Akapit 2\n", backend.calls[0][2])
        self.assertIn("Akapit 2\nPRZED: " + LONG_B.strip(), backend.calls[1][2])

    def test_cut_reply_marked(self):
        check = check_meaning(FakeBackend([Reply("Akapit 1: POMIJA", True)]), "m", [(1, "Ala ma kota.", "Kot.")], [])
        self.assertEqual((check["odpowiedz"], check["uciete"]), ("Akapit 1: POMIJA\n(odpowiedź ucięta)", True))

    def test_error_keeps_answers_so_far(self):
        backend = FakeBackend([Reply("Akapit 1: BEZ ZMIAN", False), BackendError("Serwer modelu nie odpowiedział.")])
        check = check_meaning(backend, "m", [(1, LONG_A, LONG_B), (2, LONG_B, LONG_A)], [])
        self.assertEqual(check, {"model": "m", "odpowiedz": "Akapit 1: BEZ ZMIAN", "uciete": False,
                                 "blad": "Serwer modelu nie odpowiedział."})

    def test_unchanged_pairs_not_sent(self):  # an unchanged pair alone in a part made an empty prompt
        backend = FakeBackend([Reply("Akapit 2: BEZ ZMIAN", False)])
        check_meaning(backend, "m", [(1, LONG_A, LONG_A), (2, LONG_B, LONG_A)], [])
        self.assertEqual(len(backend.calls), 1)
        self.assertIn("Akapit 2\n", backend.calls[0][2])

    def test_nothing_changed_no_call(self):
        backend = FakeBackend()
        self.assertEqual(check_meaning(backend, "m", [(1, "Ala ma kota.", "Ala ma kota. ")], ["Uwaga"]),
                         {"model": "m", "odpowiedz": "", "uciete": False})
        self.assertEqual(backend.calls, [])

    def test_warnings_go_with_their_part(self):
        backend = FakeBackend([Reply("a", False), Reply("b", False)])
        check_meaning(backend, "m", [(1, LONG_A, LONG_B), (12, LONG_B, LONG_A)],
                      ["Liczby się nie zgadzają.", "Akapit 1: za długi", "Akapit 12: za krótki"])
        first, second = backend.calls[0][2], backend.calls[1][2]
        self.assertIn("- Liczby się nie zgadzają.", first)
        self.assertIn("- Liczby się nie zgadzają.", second)
        self.assertIn("- Akapit 1: za długi", first)
        self.assertNotIn("Akapit 12: za krótki", first)
        self.assertIn("- Akapit 12: za krótki", second)
        self.assertNotIn("Akapit 1: za długi", second)

    def test_odd_warning_text(self):  # warnings come from the page's request; "1:x"[:-1] made int() fail
        backend = FakeBackend([Reply("a", False)])
        odd = ["Akapit 1:x", "Akapit 2:y", "Akapit " + "9" * 5000 + ":"]
        check_meaning(backend, "m", [(1, "Ala ma kota.", "Kot.")], odd)
        self.assertIn("- Akapit 1:x", backend.calls[0][2])
        self.assertNotIn("Akapit 2:y", backend.calls[0][2])


if __name__ == "__main__":
    unittest.main()
