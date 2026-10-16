"""The text in blocks (paragraphs, headings, lists), rewritten one paragraph at a time.

Measured on a 1000-word article: given the whole text at once, Bielik returned a summary
(47 blocks became 7, headings and the list were gone). One paragraph at a time it kept every
block, and the guard can say which paragraph changed too much."""

import re
from typing import Dict, List, Union

MIN_WORDS = 12  # shorter blocks (headings, captions) are kept as they are
SEPARATOR = re.compile(r"(\n[ \t]*\n\s*)")
LIST_LINE = re.compile(r"(?m)^\s*(?:[-*•–]|\d{1,2}[.)])\s")

Block = Dict[str, Union[str, bool]]


def split_blocks(text: str) -> List[Block]:
    """Blocks with what follows each of them; "".join(tekst + odstep) gives back the text.
    przepisz: a paragraph of prose worth rewriting (not a heading, not a list)."""
    parts = SEPARATOR.split(text)
    blocks: List[Block] = []
    for i in range(0, len(parts), 2):
        core = parts[i].rstrip()
        gap = parts[i][len(core):] + (parts[i + 1] if i + 1 < len(parts) else "")
        if not core and blocks:  # nothing between two separators: the gap belongs to the block before
            blocks[-1]["odstep"] += gap
            continue
        rewrite = len(core.split()) >= MIN_WORDS and not LIST_LINE.search(core)
        blocks.append({"tekst": core, "odstep": gap, "przepisz": rewrite})
    return blocks
