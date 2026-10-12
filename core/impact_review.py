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

Reading it back must survive the tracker's round trip. A tracker that stores
rich text may return an issue key it auto-linked as a link - "[KEY|url]",
"[url|url|smart-link]" or a URL ending "#icft=KEY" - whose own "|" is not a
cell boundary. Cells are therefore split outside brackets, and the key is
found anywhere in the first cell. A data row whose key cannot be read is
reported by unreadable_rows(), so the hand-over refuses instead of treating
it as absent.
"""
from __future__ import annotations

import re
from typing import Iterable

DECISIONS = ("approve", "reject", "retire")
UNDECIDED = "?"
_KEY = r"[A-Z][A-Z0-9_]*-\d+"
# Most specific first: a link's issue-card fragment or browse path names the
# issue exactly; a bare key is the plain-text form.
_KEY_IN_CELL = (re.compile(r"#icft=(" + _KEY + r")"), re.compile(r"/browse/(" + _KEY + r")"),
                re.compile(r"\b(" + _KEY + r")\b"))


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


def _cells(line: str) -> list[str]:
    """A wiki table data row's cells, splitting on "|" outside [...] links."""
    body = line.strip()[1:]
    body = body[:-1] if body.endswith("|") else body
    cells, depth, cur = [], 0, []
    for ch in body:
        if ch == "[":
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
        if ch == "|" and depth == 0:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def _key(cell: str) -> str | None:
    for pattern in _KEY_IN_CELL:
        m = pattern.search(cell or "")
        if m:
            return m.group(1)
    return None


def _decision(cell: str) -> str:
    word = re.sub(r"[^a-z?]", "", (cell or "").lower())
    return word if word in DECISIONS else UNDECIDED


def _data_rows(description: str):
    """(key or None, cells) for every table data row; header rows ("||") skipped."""
    for line in (description or "").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("||"):
            continue
        cells = _cells(line)
        if len(cells) < 2:
            continue
        yield _key(cells[0]), cells


def parse(description: str) -> dict:
    """{test case key: decision} from the table; the decision is the LAST cell.
    Unknown words count as undecided."""
    return {key: _decision(cells[-1]) for key, cells in _data_rows(description) if key}


def parse_rows(description: str) -> dict:
    """{key: {"owner", "tier", "score", "evidence", "decision"}} - every cell."""
    out: dict = {}
    for key, cells in _data_rows(description):
        if not key:
            continue
        rest = cells[1:] + [""] * (5 - len(cells[1:]))
        out[key] = {"owner": _key(rest[0]) or rest[0], "tier": rest[1], "score": rest[2],
                    "evidence": rest[3] if len(rest) > 4 else "",
                    "decision": _decision(rest[-1])}
    return out


def unreadable_rows(description: str) -> list:
    """Table data rows whose test case key could not be read."""
    return [" | ".join(cells)[:80] for key, cells in _data_rows(description) if not key]


def undecided(decisions: dict) -> list:
    return sorted(k for k, v in decisions.items() if v not in DECISIONS)
