"""A prompt for a second model (Bielik itself, Claude, GPT, Grok, ...) that compares each
rewritten paragraph with its original and lists every change of meaning.

The guard checks numbers the same way every time; meaning only a reader can judge. This
prompt makes a second model one more reader. It errs too, so its answer is a list of places
to look at, not a verdict."""

from typing import List, Tuple

Pair = Tuple[int, str, str]  # paragraph number on the page, before, after

# Measured with Bielik 11B v3.0 as the verifier: asked for a table with six categories it
# answered "no change" and missed an invented sentence; asked this way, per paragraph, it
# found the sentence, a "może" -> "zawsze" and an omission. Large models handle both.
VERIFY_PROMPT = """Porównaj każdy akapit PRZED z akapitem PO. PO powstał przez przepisanie PRZED innym modelem językowym. Szukasz tylko zmian treści, nie stylu.

Dla każdego akapitu napisz jedną z dwóch odpowiedzi:
- „Akapit N: BEZ ZMIAN”, jeśli PO mówi to samo co PRZED, tylko innymi słowami;
- „Akapit N:” i wypunktuj, co PO DODAJE (fakty, rady, przykłady, wnioski, odpowiedzi na pytania z tekstu), co POMIJA i co ZMIENIA: liczby, jednostki, daty, nazwy, pewność („może” → „jest”, „czasami” → „często”), zakres („tylko”, „zawsze”, „nigdy”), przyczynę i skutek, zaprzeczenia.

Cytuj dokładnie. Nie poprawiaj tekstu i nie oceniaj stylu."""


def build_prompt(pairs: List[Pair], warnings: List[str]) -> str:
    """The whole prompt, with the guard's warnings and the changed pairs; "" when no
    paragraph changed."""
    changed = [(n, before, after) for n, before, after in pairs if before.strip() != after.strip()]
    if not changed:
        return ""
    guard = "\n".join("- " + w for w in warnings) if warnings else "Strażnik Szlifa nie zgłosił uwag."
    body = "\n\n".join("Akapit %d\nPRZED: %s\nPO: %s" % (n, before.strip(), after.strip())
                       for n, before, after in changed)
    return "%s\n\nUwagi strażnika Szlifa (sprawdzają liczby i długość, nie sens):\n%s\n\n%s\n" % (
        VERIFY_PROMPT, guard, body)


def chunk_pairs(pairs: List[Pair], max_chars: int = 6000) -> List[List[Pair]]:
    """Pairs in groups small enough for one check each: a long prompt in one call can be cut
    off by the model's context, instructions first."""
    chunks: List[List[Pair]] = []
    current: List[Pair] = []
    size = 0
    for pair in pairs:
        length = len(pair[1]) + len(pair[2])
        if current and size + length > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(pair)
        size += length
    if current:
        chunks.append(current)
    return chunks
