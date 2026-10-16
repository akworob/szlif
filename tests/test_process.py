import unittest

from szlif_core.backends import BackendError, Reply
from szlif_core.process import process_text
from tests.fakes import FakeBackend

P1 = "Pierwszy akapit ma tutaj dość dużo słów, żeby model mógł go spokojnie przepisać bez kłopotu."
P2 = "Drugi akapit także ma wystarczająco wiele słów, aby trafić do przepisania przez model językowy."
R1 = "Pierwszy akapit zawiera sporo słów, więc model może go bez kłopotu spokojnie przepisać od nowa."
TEXT = "Tytuł\n\n%s\n\n- punkt\n\n%s\n" % (P1, P2)


class Process(unittest.TestCase):
    def test_paragraphs_rewritten_layout_kept(self):
        # round 1 and 2 for P1 (round 2 unchanged stops), then P2 comes back with an invented addition
        long_p2 = P2 + " Warto też pamiętać o regularnych ćwiczeniach, zdrowej diecie i odpowiednio długim śnie każdej nocy."
        backend = FakeBackend([Reply(R1, False), Reply(R1, False), Reply(long_p2, False)])
        r = process_text(backend, "m", TEXT, rounds=2)
        self.assertEqual(r["wynik"], "Tytuł\n\n%s\n\n- punkt\n\n%s\n" % (R1, long_p2))
        self.assertEqual([(a["numer"], a["przepisany"]) for a in r["akapity"]], [(2, True), (4, True)])
        self.assertEqual(r["akapity"][0]["problemy"], [])
        self.assertEqual([p["kind"] for p in r["akapity"][1]["problemy"]], ["too_long"])
        self.assertEqual(r["ostrzezenia"], 1)

    def test_progress_reported(self):
        seen = []
        backend = FakeBackend([Reply(R1, False), Reply(R1, False), Reply(P2, False)])
        process_text(backend, "m", TEXT, rounds=2, progress=lambda done, todo, rnd: seen.append((done, todo, rnd)))
        self.assertEqual(seen, [(1, 2, 1), (1, 2, 2), (2, 2, 1)])

    def test_round1_error_raises(self):
        with self.assertRaises(BackendError):
            process_text(FakeBackend([BackendError("x")]), "m", TEXT, rounds=1)

    def test_value_moved_between_paragraphs_reported(self):  # review: the whole-text count hides it
        p1 = "Zniżka dla studentów wynosi 30% na wszystkie bilety kupione w kasie przed seansem w kinie."
        p2 = "Bilety dla seniorów można kupić w każdym kinie sieci przez cały tydzień bez żadnych ograniczeń."
        r1 = "Studenci dostają zniżkę na wszystkie bilety kupione w kasie kina przed rozpoczęciem seansu."
        r2 = "Seniorzy mogą kupić bilety z rabatem 30% w każdym kinie sieci przez cały tydzień bez ograniczeń."
        backend = FakeBackend([Reply(r1, False), Reply(r2, False)])
        r = process_text(backend, "m", p1 + "\n\n" + p2, rounds=1)
        self.assertEqual(r["problemy"], [])  # the whole text still has one "30%"
        self.assertEqual([p["kind"] for p in r["akapity"][0]["problemy"]], ["values"])
        self.assertEqual([p["kind"] for p in r["akapity"][1]["problemy"]], ["values"])
        self.assertEqual(r["ostrzezenia"], 2)

    def test_values_checked_on_whole_text(self):
        text = "Bilet na koncert w sobotę kosztuje 15 zł, a ulgowy bilet dla studentów kosztuje 10 zł."
        backend = FakeBackend([Reply("Bilet na sobotni koncert kosztuje 15 zł, a ulgowy dla studentów to 12 zł.", False)])
        r = process_text(backend, "m", text, rounds=1)
        self.assertEqual(r["problemy"][0]["missing"], ["10 zł"])
        self.assertEqual(r["ostrzezenia"], 1)


if __name__ == "__main__":
    unittest.main()
