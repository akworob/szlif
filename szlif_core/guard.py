"""Strażnik liczb: compares the values (numbers with their units, dates, times)
of the original and the rewrite, and says what went missing or was added.

It does NOT check names, claims, swapped values, numbers written in words or a
change in how certain a sentence is. Only a person reading both texts does.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Tuple

from .blocks import split_blocks


@dataclass
class Value:
    key: str    # normalized: "1000 zł", "12,5 %", "9 kwietnia", "2026-03-12", "14:30"
    shown: str  # as written
    start: int
    end: int


@dataclass
class Problem:
    kind: str                             # "values" | "cut" | "too_long" | "too_short" | "paragraphs" | "meta"
    message: str
    missing: List[str]                    # shown forms from the original
    added: List[str]                      # shown forms from the output
    missing_spans: List[Tuple[int, int]]  # spans of missing values in the original


MESSAGES = {
    "values": "Liczby, jednostki lub daty różnią się od oryginału. Sprawdź przed użyciem.",
    "cut": "Odpowiedź modelu została ucięta. Podziel tekst na części.",
    "too_long": "Wynik jest wyraźnie dłuższy od tekstu (%d%% słów). Model mógł coś dopisać albo odpowiedzieć "
                "na tekst zamiast go przepisać.",
    "too_short": "Wynik jest wyraźnie krótszy od tekstu (%d%% słów). Model mógł coś pominąć albo streścić tekst.",
    "paragraphs": "Zmieniła się liczba akapitów (%d \u2192 %d). Model mógł połączyć, rozdzielić albo dopisać akapity.",
    "meta": "Wynik mówi o samym tekście („%s”), a oryginał nie. Model mógł dopisać komentarz albo fragment "
            "polecenia.",
}
# Measured on a 1000-word article: Bielik appended invented sentences to a paragraph (+50% words),
# summarised a whole text (-60%) and once wrote its own instruction into the text ("Krótkie zdania
# przeplatają się z dłuższymi, co nadaje tekstowi naturalny rytm."). None of it has numbers.
LONGER, SHORTER, MIN_WORDS_FOR_SHORT = 1.4, 0.7, 8
META_STEMS = ("rytm", "zdani", "tekst", "przepis", "akapit", "redakc", "redakt")

MONTHS = "stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października listopada grudnia"
# Each unit word a rewrite may spell another way, and the one spelling the guard compares.
CANON = [
    (r"%|procent\w*|proc\.", "%"), (r"zł|zl|złot\w*|PLN", "zł"), (r"gr|grosz\w*", "gr"),
    (r"€|EUR|euro", "EUR"), (r"\$|USD|dolar\w*", "USD"),
    (r"tys\.|tysi\w*", "tys."), (r"mln|milion\w*", "mln"), (r"mld|miliard\w*", "mld"),
    (r"s|sek\.|sekund\w*", "s"), (r"min\.?|minut\w*", "min"), (r"h|godz\.|godzin\w*", "godz."),
    (r"dni\w*|dzień|dnia|dniu", "dni"), (r"tydz\.|tydzień|tygodni\w*", "tydz."),
    (r"mies\.|miesi\w*", "mies."), (r"r\.|rok\w*|roku|lat\w*|lata", "lat"),
    (r"szt\.?|sztuk\w*", "szt."), (r"km|kilometr\w*", "km"), (r"kg|kilogram\w*", "kg"),
] + [(m, m) for m in MONTHS.split()] + [(u, u) for u in ("m", "cm", "mm", "g", "t", "l", "ml")]

SP = "[   ]"
MULT = r"(?:tys\.|tysi\w*|mln|milion\w*|mld|miliard\w*)(?!\w)"
WORD = r"(?:%s)(?!\w)" % "|".join("(?:%s)" % pattern for pattern, _ in CANON)
# A unit written with a capital, a digit or a degree sign (kWh, MWp, °C, CO2), not an
# ordinary capitalised word ("Polska") and not a number.
SYMBOLIC = r"(?![A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,}(?!\w))(?!\d)(?=[\w°²³]*[A-ZĄĆĘŁŃÓŚŹŻ°²³\d])[\w°²³]+"
UNIT = r"(?:%s(?:%s(?:%s|%s))?|%s|%s)" % (MULT, SP, WORD, SYMBOLIC, WORD, SYMBOLIC)
VALUE = re.compile(
    r"(?<![\w.,])(?:"
    r"(?P<date>\d{4}-\d\d-\d\d|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}:\d\d)(?!\d)"
    r"|(?:(?<![^\s(])(?P<sign>[-+−–]))?"
    r"(?P<whole>\d{1,3}(?:" + SP + r"\d{3})+(?!\d)|\d+)(?P<frac>[.,]\d+)?"
    r"(?:" + SP + r"?(?P<unit>" + UNIT + r"))?)")
# List numbering ("1." or "2)" opening a line) is not a value.
MARKER = re.compile(r"(?m)^[ \t]*\d{1,2}[.)](?=\s)")


def _canon(word: str) -> str:
    for pattern, spelling in CANON:
        if re.fullmatch(pattern, word):
            return spelling
    return word


def find_values(text: str) -> List[Value]:
    text = MARKER.sub(lambda m: " " * len(m.group()), text)
    found = []
    for m in VALUE.finditer(text):
        if m.group("date"):
            key = m.group("date")
        else:
            sign = "-" if m.group("sign") in ("-", "−", "–") else (m.group("sign") or "")
            key = sign + re.sub(SP, "", m.group("whole")) + (m.group("frac") or "")
            if m.group("unit"):
                key += " " + " ".join(_canon(w) for w in re.split(SP, m.group("unit")))
        found.append(Value(key, " ".join(m.group().split()), m.start(), m.end()))
    return found


def _first(values: List[Value], wanted: Counter) -> List[Value]:
    """The first occurrences of each wanted key, as many as it is wanted."""
    left, out = Counter(wanted), []
    for v in values:
        if left[v.key] > 0:
            out.append(v)
            left[v.key] -= 1
    return out


def check(original: str, output: str, cut: bool = False) -> List[Problem]:
    problems = []
    before, after = find_values(original), find_values(output)
    keys_before, keys_after = Counter(v.key for v in before), Counter(v.key for v in after)
    if keys_before != keys_after:
        missing = _first(before, keys_before - keys_after)
        added = _first(after, keys_after - keys_before)
        problems.append(Problem("values", MESSAGES["values"], [v.shown for v in missing],
                                [v.shown for v in added], [(v.start, v.end) for v in missing]))
    if cut:
        problems.append(Problem("cut", MESSAGES["cut"], [], [], []))
    words_in, words_out = len(original.split()), len(output.split())
    ratio = round(100 * words_out / words_in) if words_in else 100
    if words_out > max(LONGER * words_in, words_in + 6):
        problems.append(Problem("too_long", MESSAGES["too_long"] % ratio, [], [], []))
    elif words_in >= MIN_WORDS_FOR_SHORT and words_out < SHORTER * words_in:
        problems.append(Problem("too_short", MESSAGES["too_short"] % ratio, [], [], []))
    paragraphs_in, paragraphs_out = _paragraphs(original), _paragraphs(output)
    if paragraphs_in != paragraphs_out:
        problems.append(Problem("paragraphs", MESSAGES["paragraphs"] % (paragraphs_in, paragraphs_out), [], [], []))
    meta = _meta_word(original, output)
    if meta:
        problems.append(Problem("meta", MESSAGES["meta"] % meta, [], [], []))
    return problems


def _paragraphs(text: str) -> int:
    """Paragraphs as Szlif splits them: a line break ends one unless it breaks a sentence."""
    return sum(1 for b in split_blocks(text) if b["tekst"])


def _meta_word(original: str, output: str) -> str:
    """The start of a sentence of output that talks about writing (rytm, zdania, tekst, ...) with
    two or more such words the original never uses: a comment or a piece of the instruction,
    not a rewrite. One such word alone is ordinary Polish ("moim zdaniem", "przepisy")."""
    def stems(text: str) -> set:
        return {s for w in re.findall(r"\w+", text.lower()) for s in META_STEMS if w.startswith(s)}
    old = stems(original)
    for sentence in re.split(r"(?<=[.!?…])\s+", output):
        if len(stems(sentence) - old) >= 2:
            return " ".join(sentence.split()[:6]) + ("…" if len(sentence.split()) > 6 else "")
    return ""
