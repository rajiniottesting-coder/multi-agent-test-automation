"""The live test track and the backlog keep up with what is built.

docs/TEST_TRACK.md keeps the live checks still open and the rows each new
change adds; docs/BACKLOG.md lists what is still to build. An item marked
Done in the backlog must have a check row naming it in *Built in*. Row ids
are unique, every row carries a known status, and a passed or not-applicable
row names its evidence.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACK = (ROOT / "docs" / "TEST_TRACK.md").read_text(encoding="utf-8")
BACKLOG = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
STATUSES = {"⬜", "✅", "❌", "➖"}


def _rows():
    """(id, built in, status, evidence) for every check row (6 columns)."""
    out = []
    for line in TRACK.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("| ") and len(cells) == 6 and cells[0] != "ID" \
                and not set(cells[0]) <= {"-"}:
            out.append((cells[0], cells[1], cells[4], cells[5]))
    return out


def _backlog():
    """{item id: status} for every backlog row (7 columns)."""
    out = {}
    for line in BACKLOG.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("| ") and len(cells) == 7 and cells[0] != "ID" \
                and not set(cells[0]) <= {"-"}:
            assert cells[0] not in out, f"backlog id {cells[0]} twice"
            out[cells[0]] = cells[6]
    return out


def test_every_check_row_is_read():
    """A `|` inside a cell would split it and hide that row from these checks."""
    starts = [l for l in TRACK.splitlines()
              if re.match(r"\| [A-Z][A-Za-z0-9-]* \| ", l) and not l.startswith("| ID")]
    assert len(starts) == len(_rows()), "a check row does not have exactly 6 cells"


def test_row_ids_are_unique_and_statuses_known():
    rows = _rows()
    assert rows, "no check rows - update this test"
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate row ids"
    assert all(r[2] in STATUSES for r in rows), "unknown status"


def test_a_passed_row_names_its_evidence():
    for row_id, _b, status, evidence in _rows():
        if status in ("✅", "➖"):
            assert evidence, f"{row_id} is marked {status} without evidence"


def test_backlog_items_read_and_have_known_status():
    items = _backlog()
    assert len(items) >= 30, "the backlog no longer reads as expected - update this test"
    bad = {i: s for i, s in items.items() if not re.fullmatch(r"Open|Done \(#\d+\)", s)}
    assert not bad, f"backlog status must be 'Open' or 'Done (#PR)': {bad}"


def test_every_done_item_has_a_check_row():
    built = " ".join(r[1] for r in _rows())
    done = [i for i, s in _backlog().items() if s.startswith("Done")]
    missing = [i for i in done if not re.search(rf"\b{re.escape(i)}\b", built)]
    assert not missing, f"built but no live check in TEST_TRACK.md: {missing}"
