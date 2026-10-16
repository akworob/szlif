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
- Nie dopisuj nowych zdań, przykładów, rad, wniosków ani podsumowań. Jeśli w tekście jest pytanie, przepisz je jako pytanie i na nie nie odpowiadaj.
- Zachowaj podział na akapity i podobną długość: wynik nie może być wyraźnie dłuższy od oryginału.
- Zwróć wyłącznie przepisany tekst, bez wstępu, komentarza i cudzysłowów."""

# Bielik follows the user turn more closely than the system prompt, so the task
# and the round's instruction go there.
# Measured on a 1000-word article, 2 runs each: this prompt gave 1 and 5 flagged paragraphs
# (1090 and 1169 words), the earlier one 5 and 5 (1225 and 1174): better on average, not reliably.
TASK_LINE = "Przepisz poniższy tekst. Nie odpowiadaj na jego treść, nie komentuj go i niczego nie dopisuj."
ROUNDS: List[Tuple[str, str]] = [
    ("rytm", "Zróżnicuj długość zdań: obok dłuższych postaw krótkie, żeby rytm tekstu nie był jednostajny."),
    ("słownictwo", "Zamień sformułowania urzędowe, sztuczne i powtarzające się na naturalne. Terminy fachowe zostaw."),
    ("przejścia", "Popraw przejścia między zdaniami, żeby tekst czytał się płynnie."),
]


# Writing styles, two choices as in the author's earlier tool: how hard the text reads and what it
# is for; key -> (label on the page, the instruction added to every round). The defaults add
# nothing. A style asks for a register, never for new content, and the guard checks every style.
READABILITY = {
    "normalna": ("Normalna", ""),
    "prosta": ("Prosta", "Pisz prosto: krótsze zdania i codzienne słowa. Trudne słowo zamień na prostsze tylko "
                         "wtedy, gdy sens zostaje ten sam."),
    "akademicka": ("Akademicka", "Pisz językiem akademickim: precyzyjnie, pełnymi zdaniami, z terminologią "
                                 "fachową, bez potocyzmów."),
    "ekspercka": ("Ekspercka", "Pisz jak specjalista do specjalistów: zwięźle i gęsto, z terminologią fachową."),
}
PURPOSE = {
    "ogolny": ("Ogólny", ""),
    "naukowy": ("Naukowy", "Styl naukowy: rzeczowo i bezosobowo, bez ocen i emocji. Zachowaj każde zastrzeżenie "
                           "(„może”, „nie zawsze”, „w wielu”), każdy element wyliczenia i każdy przypis."),
    "biznesowy": ("Biznesowy", "Styl biznesowy: konkretnie, uprzejmie i bez ozdobników."),
    "email": ("E-mail", "Styl e-maila: uprzejmie i do rzeczy. Zachowaj powitanie i podpis, jeśli są w tekście, "
                        "i nie dodawaj nowych."),
    "esej": ("Esej", "Styl eseju: płynny wywód z naturalnymi przejściami między myślami."),
    "marketingowy": ("Marketingowy", "Styl marketingowy: lekko i przekonująco, z korzyścią dla czytelnika na "
                                     "początku, ale bez nowych obietnic, superlatywów i liczb, których nie ma w tekście."),
    "prawny": ("Prawny", "Styl prawniczy: precyzyjnie, jednoznacznie i formalnie. Nie upraszczaj terminów "
                         "prawnych i nie zmieniaj zakresu praw ani obowiązków."),
}


def run_round(backend: Backend, model: str, original: str, current: str, round_no: int,
              hidden: bool, dashes: bool, readability: str = "normalna", purpose: str = "ogolny") -> Dict:
    """One round: original is the cleaned original, current the text this round rewrites."""
    if not 1 <= round_no <= len(ROUNDS):
        raise ValueError("round_no must be 1..%d" % len(ROUNDS))
    if readability not in READABILITY or purpose not in PURPOSE:
        raise ValueError("unknown style %s/%s" % (readability, purpose))
    task = " ".join(part for part in (TASK_LINE, ROUNDS[round_no - 1][1], READABILITY[readability][1],
                                      PURPOSE[purpose][1]) if part)
    user = "%s\n\n%s" % (task, current)
    try:
        reply = backend.chat(model, SYSTEM_PROMPT, user)
        out = clean(reply.text.strip(), hidden, dashes).text.strip()
        if not out:
            raise BackendError("Model zwrócił pusty tekst. Spróbuj jeszcze raz.")
    except BackendError as e:
        if round_no == 1:
            raise
        return {"tekst": "", "problemy": [], "przyjeta": False, "stop": True, "bez_zmian": False,
                "powod": "Zatrzymano po rundzie %d: runda %d nie powiodła się (%s)." % (round_no - 1, round_no, e)}
    if out == current.strip():
        # Measured: given its own clean output, Bielik returned it word for word, minutes per round;
        # the rounds after it would do the same.
        return {"tekst": out, "problemy": [], "przyjeta": True, "stop": True, "bez_zmian": True, "powod": None}
    problems = check(original, out, reply.cut)
    result = {"tekst": out, "problemy": [asdict(p) for p in problems], "przyjeta": True, "stop": False,
              "bez_zmian": False, "powod": None}
    if problems and round_no == 1:
        result.update(stop=True, powod="Zatrzymano po rundzie 1: ostrzeżenie strażnika. Sprawdź wynik.")
    elif problems:
        result.update(przyjeta=False, stop=True,
                      powod="Zatrzymano po rundzie %d: runda %d dała ostrzeżenie (%s) i została odrzucona."
                      % (round_no - 1, round_no, problems[0].message))
    return result
