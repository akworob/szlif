"""The text in blocks (paragraphs, headings, list items), rewritten one paragraph at a time.

Measured on a 1000-word article: given the whole text at once, Bielik returned a summary
(47 blocks became 7, headings and the list were gone). One paragraph at a time it kept every
block, and the guard can say which paragraph changed too much.

A paragraph ends at a blank line, and also at a single line break, since a paste from Word or
Google Docs has one per paragraph; a line that breaks mid-sentence (a paste from a PDF) is
joined with the next one. List items, headings and other short lines stay as they are."""

import re
from typing import Dict, List, Union

MIN_WORDS = 12  # shorter blocks (headings, captions) are kept as they are
LINE_BREAK = re.compile(r"(\n\s*)")
NOT_PROSE = re.compile(r"\s*(?:[-*•–#>|]|\d{1,2}[.)])\s?")  # list items, Markdown headings, quotes, tables
SENTENCE_END = re.compile(r"[.!?…:;\"”)\]]\s*$")

Block = Dict[str, Union[str, bool]]


def _continues(line: str, gap: str, next_line: str) -> bool:
    """A line broken mid-sentence: one newline, no sentence end, the next line goes on in lowercase."""
    return (gap.count("\n") == 1 and not SENTENCE_END.search(line) and not NOT_PROSE.match(line)
            and not NOT_PROSE.match(next_line) and next_line[:1].islower())


def split_blocks(text: str) -> List[Block]:
    """Blocks with what follows each of them; "".join(tekst + odstep) gives back the text.
    przepisz: a paragraph of prose worth rewriting (not a heading, not a list item)."""
    parts = LINE_BREAK.split(text)  # line, gap, line, gap, ..., line
    blocks: List[Block] = []
    i = 0
    while i < len(parts):
        core = parts[i]
        while i + 2 < len(parts) and core.strip() and _continues(core, parts[i + 1], parts[i + 2]):
            core += parts[i + 1] + parts[i + 2]
            i += 2
        stripped = core.rstrip()
        gap = core[len(stripped):] + (parts[i + 1] if i + 1 < len(parts) else "")
        if not stripped and blocks:  # nothing between two gaps: the gap belongs to the block before
            blocks[-1]["odstep"] += gap
        else:
            rewrite = len(stripped.split()) >= MIN_WORDS and not NOT_PROSE.match(stripped)
            blocks.append({"tekst": stripped, "odstep": gap, "przepisz": rewrite})
        i += 2
    return blocks
