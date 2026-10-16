"""Czyszczenie ukrytych znaków: hidden characters, unusual spaces, homoglyphs
and, on request, typographic dashes. Every change is recorded with its place
in the cleaned text, so the page can show it as a pill.

It removes characters only. A statistical (token-level) watermark is not a
character and is not touched here.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Change:
    pos: int          # offset in the CLEANED text where the change sits
    length: int       # length of the replacement in the cleaned text (0 = removal)
    original: str     # what was there in the input
    replacement: str  # what is there now
    label: str        # pill text: "ZWSP", "NBSP", "homoglif а→a", "— → ,", "ukryty tekst: hej"


@dataclass
class Cleaned:
    text: str
    changes: List[Change]


REMOVED = {0x200B: "ZWSP", 0x200C: "ZWNJ", 0x200D: "ZWJ", 0x2060: "WJ", 0xFEFF: "BOM",
           0x180E: "MVS", 0x00AD: "SHY"}
BIDI = {0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}
SPACES = {0x00A0: "NBSP", 0x202F: "NNBSP"}
OTHER_SPACES = {0x2007, 0x2009, 0x200A, *range(0x2002, 0x2007), 0x205F, 0x3000, 0x1680}
SEPARATORS = {0x2028: "LS", 0x2029: "PS"}
TAGS = range(0xE0000, 0xE0080)
BLACK_FLAG = "\U0001F3F4"
CANCEL_TAG = "\U000E007F"
HOMOGLYPHS = dict(zip("аеорсухіјѕАВЕКМНОРСТХ" "ονΑΒΕΖΗΙΚΜΝΟΡΤΥΧ",
                      "aeopcyxijsABEKMHOPCTX" "ovABEZHIKMNOPTYX"))
DASH = re.compile(r"[ \t]*([—–])[ \t]*")

# A piece of the cleaned text: (cleaned, original, label); label None = unchanged.
Piece = Tuple[str, str, Optional[str]]


def _emoji(ch: str) -> bool:
    cp = ord(ch)
    return cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or unicodedata.category(ch) == "So"


def _latin(ch: str) -> bool:
    return ch.isalpha() and ord(ch) < 0x250


def _homoglyph_positions(text: str) -> set:
    """Positions of look-alike letters inside words that also hold a Latin letter."""
    found = set()
    for word in re.finditer(r"\w+", text):
        if any(_latin(c) for c in word.group()):
            found.update(word.start() + i for i, c in enumerate(word.group()) if c in HOMOGLYPHS)
    return found


def _hidden(text: str) -> List[Piece]:
    pieces: List[Piece] = []
    homoglyphs = _homoglyph_positions(text)
    i = 0
    while i < len(text):
        ch, cp = text[i], ord(text[i])
        if cp in TAGS:
            end = i
            while end < len(text) and ord(text[end]) in TAGS:
                end += 1
            run = text[i:end]
            if i > 0 and text[i - 1] == BLACK_FLAG and run.endswith(CANCEL_TAG):
                pieces.extend((c, c, None) for c in run)
            else:
                hidden = "".join(chr(ord(c) - 0xE0000) for c in run if 0xE0020 <= ord(c) < 0xE007F)
                pieces.append(("", run, "ukryty tekst: " + hidden))
            i = end
            continue
        if cp == 0x200D and 0 < i < len(text) - 1 and (_emoji(text[i - 1]) or text[i - 1] == "️") \
                and _emoji(text[i + 1]):
            pieces.append((ch, ch, None))
        elif cp in REMOVED:
            pieces.append(("", ch, REMOVED[cp]))
        elif cp in BIDI:
            pieces.append(("", ch, "BIDI"))
        elif cp in SPACES:
            pieces.append((" ", ch, SPACES[cp]))
        elif cp in OTHER_SPACES:
            pieces.append((" ", ch, "SPACJA U+%04X" % cp))
        elif cp in SEPARATORS:
            pieces.append(("\n", ch, SEPARATORS[cp]))
        elif 0xFF01 <= cp <= 0xFF5E:
            new = chr(cp - 0xFEE0)
            pieces.append((new, ch, "pełna-szerokość %s→%s" % (ch, new)))
        elif i in homoglyphs:
            pieces.append((HOMOGLYPHS[ch], ch, "homoglif %s→%s" % (ch, HOMOGLYPHS[ch])))
        else:
            pieces.append((ch, ch, None))
        i += 1
    return pieces


def _dash_replacement(text: str, match) -> Optional[str]:
    """What a dash match becomes, or None to leave it alone."""
    s, e = match.span()
    prev = text[s - 1] if s > 0 else "\n"
    nxt = text[e] if e < len(text) else "\n"
    if prev == "\n" or nxt == "\n":  # opens a line (dialogue, list) or ends one
        return None
    if prev.isdigit() and nxt.isdigit():
        return "-"
    if match.group() == "–" and prev.isalpha() and nxt.isalpha():
        return "-"
    return ", "


def _dashes(pieces: List[Piece]) -> List[Piece]:
    """Replace dash matches in the cleaned text, folding the pieces they cover into one."""
    text = "".join(p[0] for p in pieces)
    starts, offset = [], 0
    for p in pieces:
        starts.append(offset)
        offset += len(p[0])
    out: List[Piece] = []
    k = 0
    for m in DASH.finditer(text):
        new = _dash_replacement(text, m)
        if new is None:
            continue
        s, e = m.span()
        while k < len(pieces) and (starts[k] < s or (starts[k] == s and not pieces[k][0])):
            out.append(pieces[k])
            k += 1
        covered = []
        while k < len(pieces) and starts[k] + len(pieces[k][0]) <= e and (pieces[k][0] or starts[k] < e):
            covered.append(pieces[k])
            k += 1
        out.append((new, "".join(p[1] for p in covered), "%s → %s" % (m.group(1), new.strip())))
    out.extend(pieces[k:])
    return out


def clean(text: str, hidden: bool = True, dashes: bool = False) -> Cleaned:
    pieces = _hidden(text) if hidden else [(c, c, None) for c in text]
    if dashes:
        pieces = _dashes(pieces)
    changes, pos = [], 0
    for new, original, label in pieces:
        if label:
            changes.append(Change(pos, len(new), original, new, label))
        pos += len(new)
    return Cleaned("".join(p[0] for p in pieces), changes)


def summary(changes: List[Change]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in changes:
        kind = c.label.split(" ", 1)[0]
        counts[kind] = counts.get(kind, 0) + 1
    return counts
