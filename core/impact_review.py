"""The Impact Review: one sub-task under the change story, with a Decision column.

A person reads the table, sets each row's Decision, and moves the sub-task to
Done. Nothing is handed over while it is open, and a Done review with an
undecided row is refused, not guessed.

Decisions: approve (revise this test), retire (remove its scenario, label the
test case retired), reject (leave it). Rows default to `approve` for the
must-update tier and to `?` (undecided) for the review tier.

The table is Jira wiki markup, so it renders as a table in the issue view and
stays editable as text. Rows are read back by their test case key, so a
reviewer may reorder rows or edit other cells freely.
"""
from __future__ import annotations

import re
from typing import Iterable

DECISIONS = ("approve", "reject", "retire")
UNDECIDED = "?"
_ROW = re.compile(r"^\|\s*(?P<key>[A-Z][A-Z0-9_]*-\d+)\s*\|(?P<rest>.*)\|\s*$")


def render(change: str, rows: Iterable[dict], intro: str = "") -> str:
    """rows: dicts with key, owner, tier, score, evidence, and optionally decision."""
    lines = [f"Impact Review for {change}.",
             "Set each Decision to approve, reject or retire, then move this "
             "sub-task to Done. Rows still marked ? block the hand-over."]
    if intro:
        lines += ["", intro]
    lines += ["", "||Test case||Owner||Tier||Score||Evidence||Decision||"]
    for r in rows:
        decision = r.get("decision") or ("approve" if r.get("tier") == "must-update" else UNDECIDED)
        evidence = str(r.get("evidence", "")).replace("|", "/").replace("\n", " ")
        lines.append(f"|{r['key']}|{r.get('owner') or '-'}|{r.get('tier', '-')}|"
                     f"{r.get('score', '-')}|{evidence or '-'}|{decision}|")
    return "\n".join(lines)


def parse(description: str) -> dict:
    """{test case key: decision} from the table; the decision is the LAST cell.
    Unknown words count as undecided."""
    out: dict = {}
    for line in (description or "").splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        last = m.group("rest").split("|")[-1].strip().lower()
        out[m.group("key")] = last if last in DECISIONS else UNDECIDED
    return out


def parse_rows(description: str) -> dict:
    """{key: {"owner", "tier", "score", "evidence", "decision"}} - every cell."""
    out: dict = {}
    for line in (description or "").splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group("rest").split("|")]
        cells += [""] * (5 - len(cells))
        decision = cells[-1].lower()
        out[m.group("key")] = {"owner": cells[0], "tier": cells[1], "score": cells[2],
                               "evidence": cells[3] if len(cells) > 4 else "",
                               "decision": decision if decision in DECISIONS else UNDECIDED}
    return out


def undecided(decisions: dict) -> list:
    return sorted(k for k, v in decisions.items() if v not in DECISIONS)
