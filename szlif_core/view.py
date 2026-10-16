"""The before/after view: a word diff of the cleaned original against the
result, with the cleaning pills and the guard's warnings placed in the text."""

import difflib
import re
from typing import Dict, List, Optional, Tuple

from .cleaner import Change

TOKEN = re.compile(r"\w+|\s+|[^\w\s]")


def tokenize(text: str) -> List[str]:
    return TOKEN.findall(text)


def _append(segments: List[Dict], kind: str, text: str, warn: bool = False, lost: bool = False) -> None:
    last = segments[-1] if segments else None
    if (last and last["t"] == kind and last.get("warn", False) == warn and last.get("lost", False) == lost
            and kind != "pill"):
        last["text"] += text
        return
    segment = {"t": kind, "text": text}
    if warn:
        segment["warn"] = True
    if lost:
        segment["lost"] = True
    segments.append(segment)


def build_view(before: str, pills: List[Change], after: str, missing_spans: List[Tuple[int, int]],
               lost_spans: Optional[List[Tuple[int, int]]] = None) -> Dict[str, List[Dict]]:
    """missing_spans: values the guard misses in the result ("warn"); lost_spans: terms with no
    trace in the result ("lost")."""
    a, b = tokenize(before), tokenize(after)
    kinds = ["eq"] * len(before)  # per character of before
    po: List[Dict] = []
    starts_a = [0]
    for token in a:
        starts_a.append(starts_a[-1] + len(token))
    # Cleaning alone gives the same text twice; difflib would take a minute on 200 000 characters.
    opcodes = ([("equal", 0, len(a), 0, len(b))] if before == after
               else difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes())
    for op, i1, i2, j1, j2 in opcodes:
        if op == "replace" and all(t.isspace() for t in a[i1:i2] + b[j1:j2]):
            op = "equal"  # a double space or a moved line break is not a change worth red and green
        if op in ("delete", "replace"):
            kinds[starts_a[i1]:starts_a[i2]] = ["del"] * (starts_a[i2] - starts_a[i1])
        if op == "equal":
            _append(po, "eq", "".join(b[j1:j2]))
        elif op in ("insert", "replace"):
            _append(po, "ins", "".join(b[j1:j2]))

    warn = [False] * len(before)
    for start, end in missing_spans:
        warn[start:end] = [True] * (end - start)
    lost = [False] * len(before)
    for start, end in lost_spans or []:
        lost[start:end] = [True] * (end - start)
    pills_at: Dict[int, List[str]] = {}
    for change in pills:
        pills_at.setdefault(change.pos, []).append(change.label)

    przed: List[Dict] = []
    for i in range(len(before) + 1):
        for label in pills_at.get(i, []):
            przed.append({"t": "pill", "text": "", "label": label})
        if i < len(before):
            _append(przed, kinds[i], before[i], warn[i], lost[i])
    return {"przed": przed, "po": po}
