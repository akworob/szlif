"""A whole text through Szlif, one paragraph at a time, as the page does it; for the command
line and for agents (`szlif.py przepisz`)."""

from dataclasses import asdict
from typing import Callable, Dict, List, Optional

from .backends import Backend, BackendError, Unreachable
from .blocks import split_blocks
from .cleaner import clean, summary
from .guard import check, missing_terms
from .rewrite import run_round

Progress = Callable[[int, int, int], None]  # paragraph done, paragraphs to do, round


def covered(problem: Dict, whole: List[Dict]) -> bool:
    """A paragraph's numbers problem the whole-text check already reports (and marks in the
    text). One that it does not, such as a number moved to another paragraph, stays."""
    if problem["kind"] != "values":
        return False
    missing = {m for p in whole for m in p["missing"]}
    added = {a for p in whole for a in p["added"]}
    return set(problem["missing"]) <= missing and set(problem["added"]) <= added


def warning_lines(result: Dict) -> List[str]:
    """One line per warning: numbers on the whole text, then per paragraph."""
    def detail(p: Dict) -> str:
        parts = [part for part in ("brakuje: " + ", ".join(p["missing"]) if p["missing"] else "",
                                   "dodane: " + ", ".join(p["added"]) if p["added"] else "") if part]
        return p["message"] + (" (%s)" % "; ".join(parts) if parts else "")

    lines = [detail(p) for p in result["problemy"]]
    for a in result["akapity"]:
        lines += ["Akapit %d: %s" % (a["numer"], detail(p)) for p in a["problemy"]]
        if a["powod"]:
            lines.append("Akapit %d: %s" % (a["numer"], a["powod"]))
    return lines


def process_text(backend: Backend, model: str, text: str, rounds: int = 2, hidden: bool = True,
                 dashes: bool = False, progress: Optional[Progress] = None, readability: str = "normalna",
                 purpose: str = "ogolny") -> Dict:
    """{"wynik", "akapity", "problemy", "czyszczenie", "ostrzezenia", "znikniete"}. Numbers are checked
    on the whole text ("problemy"); length, paragraphs, comments and certainty per paragraph
    ("akapity"); "znikniete" lists long words of the original with no trace in the result."""
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
            try:
                res = run_round(backend, model, block["tekst"], current or block["tekst"], round_no, hidden, dashes,
                                readability, purpose)
            except Unreachable:
                raise  # no server: every paragraph would fail the same way
            except BackendError as e:  # one paragraph failed (an empty reply, a cut): keep it as it was
                reason = "Akapit nie został przepisany: %s" % e
                break
            if res["przyjeta"]:
                current, problems = res["tekst"], res["problemy"]
            if res["stop"]:
                reason = None if res["przyjeta"] else res["powod"]
                break
        after = current or block["tekst"]
        paragraphs.append({"numer": number, "przed": block["tekst"], "po": after, "przepisany": True,
                           "problemy": problems, "powod": reason})
        out.append(after + block["odstep"])
    result = "".join(out)
    values = [asdict(p) for p in check(cleaned.text, result) if p.kind == "values"]
    for paragraph in paragraphs:
        paragraph["problemy"] = [p for p in paragraph["problemy"] if not covered(p, values)]
    warnings = len(values) + sum(1 for p in paragraphs if p["problemy"] or p["powod"])
    terms = list(dict.fromkeys(term for _, _, term in missing_terms(cleaned.text, result)))
    return {"wynik": result, "akapity": paragraphs, "problemy": values, "czyszczenie": summary(cleaned.changes),
            "ostrzezenia": warnings, "znikniete": terms}
