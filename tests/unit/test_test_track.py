"""The live test track keeps up with what is built.

Every fix marked **Done** in docs/VALIDATION_AND_KNOWN_GAPS.md §4 must have at
least one row in docs/TEST_TRACK.md naming it in *Built in*, so nothing built
is left without a live check at the end. Row ids are unique, and every row
carries a known status.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACK = (ROOT / "docs" / "TEST_TRACK.md").read_text(encoding="utf-8")
GAPS = (ROOT / "docs" / "VALIDATION_AND_KNOWN_GAPS.md").read_text(encoding="utf-8")
STATUSES = {"⬜", "✅", "❌", "➖"}


def _rows():
    """(id, built in, status) for every check row (6 columns)."""
    out = []
    for line in TRACK.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0] not in ("ID", "---") and not set(cells[0]) <= {"-"}:
            out.append((cells[0], cells[1], cells[4]))
    return out


def test_every_done_fix_has_a_row():
    backlog = GAPS.split("## 4. Fix backlog")[1].split("## 5.")[0]
    done = re.findall(r"^\| (F-\d+) \|[^|]*\| \*\*Done", backlog, re.M)
    assert len(done) >= 18, "the backlog no longer reads as expected - update this test"
    built = " ".join(b for _i, b, _s in _rows())
    missing = [f for f in done if not re.search(rf"\b{f}\b", built)]
    assert not missing, f"built but no live check in TEST_TRACK.md: {missing}"


def test_row_ids_are_unique_and_statuses_known():
    rows = _rows()
    assert len(rows) > 80
    ids = [i for i, _b, _s in rows]
    assert len(ids) == len(set(ids)), "duplicate row ids"
    assert all(s in STATUSES for _i, _b, s in rows), "unknown status"


def test_a_passed_row_names_its_evidence():
    for line in TRACK.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[4] in ("✅", "➖"):
            assert cells[5], f"{cells[0]} is marked {cells[4]} without evidence"
