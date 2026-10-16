import unittest

from szlif_core.verify import build_prompt, chunk_pairs


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


if __name__ == "__main__":
    unittest.main()
