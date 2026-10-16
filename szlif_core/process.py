"""A whole text through Szlif, one paragraph at a time, as the page does it; for the command
line and for agents (`szlif.py przepisz`)."""

from dataclasses import asdict
from typing import Callable, Dict, List, Optional

from .backends import Backend
from .blocks import split_blocks
from .cleaner import clean, summary
from .guard import check
from .rewrite import run_round

Progress = Callable[[int, int, int], None]  # paragraph done, paragraphs to do, round


def warning_lines(result: Dict) -> List[str]:
    """One line per warning: numbers on the whole text, then per paragraph."""
    lines = []
    for p in result["problemy"]:
        details = "; ".join(part for part in ("brakuje: " + ", ".join(p["missing"]) if p["missing"] else "",
                                              "dodane: " + ", ".join(p["added"]) if p["added"] else "") if part)
        lines.append(p["message"] + (" (%s)" % details if details else ""))
    for a in result["akapity"]:
        lines += ["Akapit %d: %s" % (a["numer"], p["message"]) for p in a["problemy"]]
        if a["powod"]:
            lines.append("Akapit %d: %s" % (a["numer"], a["powod"]))
    return lines


def process_text(backend: Backend, model: str, text: str, rounds: int = 2, hidden: bool = True,
                 dashes: bool = False, progress: Optional[Progress] = None) -> Dict:
    """{"wynik", "akapity", "problemy", "czyszczenie", "ostrzezenia"}. Numbers are checked on the
    whole text ("problemy"); length, paragraphs and comments per paragraph ("akapity")."""
    cleaned = clean(text.replace("\r\n", "\n").replace("\r", "\n"), hidden, dashes)
    blocks = split_blocks(cleaned.text)
    todo = sum(1 for b in blocks if b["przepisz"])
    out, paragraphs, number, done = [], [], 0, 0
    for block in blocks:
        if block["tekst"]:
            number += 1
        if not block["przepisz"]:
            out.append(block["tekst"] + block["odstep"])
            continue
        done += 1
        current, problems, reason = None, [], None
        for round_no in range(1, rounds + 1):
            if progress:
                progress(done, todo, round_no)
            res = run_round(backend, model, block["tekst"], current or block["tekst"], round_no, hidden, dashes)
            if res["przyjeta"]:
                current, problems = res["tekst"], res["problemy"]
            if res["stop"]:
                reason = None if res["przyjeta"] else res["powod"]
                break
        after = current or block["tekst"]
        paragraphs.append({"numer": number, "przed": block["tekst"], "po": after, "przepisany": True,
                           "problemy": [p for p in problems if p["kind"] != "values"], "powod": reason})
        out.append(after + block["odstep"])
    result = "".join(out)
    values = [asdict(p) for p in check(cleaned.text, result) if p.kind == "values"]
    warnings = len(values) + sum(1 for p in paragraphs if p["problemy"] or p["powod"])
    return {"wynik": result, "akapity": paragraphs, "problemy": values, "czyszczenie": summary(cleaned.changes),
            "ostrzezenia": warnings}
