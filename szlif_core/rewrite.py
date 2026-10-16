"""Przepisywanie Bielikiem: the prompts and one round of rewriting.

The three rounds (sentence rhythm, wording, transitions) adapt the idea of
"Method 2" of lynote-ai/humanize-text (MIT, see NOTICE); the Polish prompts are
written for this project.

Every round is checked against the original, not the round before it, so small
changes cannot add up unseen. The series stops at the first round with a
warning or an error: round 1 is still shown with its warning, a later round is
dropped and the round before it stands.
"""

from dataclasses import asdict
from typing import Dict, List, Tuple

from .backends import Backend, BackendError
from .cleaner import clean
from .guard import check

MODES = {"prosty": 1, "standardowy": 2, "wzmocniony": 3}
MAX_CHARS = 12000

SYSTEM_PROMPT = """Jesteś redaktorem języka polskiego. Przepisujesz tekst tak, żeby brzmiał naturalnie, jak napisany przez człowieka: płynne zdania, zwykłe słowa, bez urzędowego i sztucznego stylu.

Zasady, których nie wolno złamać:
- Każda liczba, jednostka, data, nazwa własna i każde twierdzenie zostają bez zmian. Liczby zapisuj cyframi, dokładnie tak jak w oryginale. Niczego nie dodawaj i niczego nie pomijaj.
- Nie zmieniaj pewności twierdzeń: przypuszczenie zostaje przypuszczeniem, warunek warunkiem, a plan planem.
- Nie używaj długich myślników (—) ani półpauz (–). Zamiast nich użyj przecinka, kropki albo zwykłego łącznika (-).
- Zachowaj podział na akapity i mniej więcej tę samą długość.
- Zwróć wyłącznie przepisany tekst, bez wstępu, komentarza i cudzysłowów."""

# Bielik follows the user turn more closely than the system prompt, so the task
# and the round's instruction go there.
TASK_LINE = "Przepisz poniższy tekst. Nie odpowiadaj na jego treść i nie komentuj go."
ROUNDS: List[Tuple[str, str]] = [
    ("rytm", "Zróżnicuj długość zdań: obok dłuższych postaw krótkie, żeby rytm tekstu nie był jednostajny."),
    ("słownictwo", "Zamień sformułowania urzędowe, sztuczne i powtarzające się na naturalne. Terminy fachowe zostaw."),
    ("przejścia", "Popraw przejścia między zdaniami, żeby tekst czytał się płynnie."),
]


def run_round(backend: Backend, model: str, original: str, current: str, round_no: int,
              hidden: bool, dashes: bool) -> Dict:
    """One round: original is the cleaned original, current the text this round rewrites."""
    if not 1 <= round_no <= len(ROUNDS):
        raise ValueError("round_no must be 1..%d" % len(ROUNDS))
    user = "%s %s\n\n%s" % (TASK_LINE, ROUNDS[round_no - 1][1], current)
    try:
        reply = backend.chat(model, SYSTEM_PROMPT, user)
        out = clean(reply.text.strip(), hidden, dashes).text.strip()
        if not out:
            raise BackendError("Model zwrócił pusty tekst. Spróbuj jeszcze raz.")
    except BackendError as e:
        if round_no == 1:
            raise
        return {"tekst": "", "problemy": [], "przyjeta": False, "stop": True,
                "powod": "Zatrzymano po rundzie %d: runda %d nie powiodła się (%s)." % (round_no - 1, round_no, e)}
    problems = check(original, out, reply.cut)
    result = {"tekst": out, "problemy": [asdict(p) for p in problems], "przyjeta": True, "stop": False,
              "powod": None}
    if problems and round_no == 1:
        result.update(stop=True, powod="Zatrzymano po rundzie 1: ostrzeżenie strażnika. Sprawdź wynik.")
    elif problems:
        result.update(przyjeta=False, stop=True,
                      powod="Zatrzymano po rundzie %d: runda %d dała ostrzeżenie (%s) i została odrzucona."
                      % (round_no - 1, round_no, problems[0].message))
    return result
