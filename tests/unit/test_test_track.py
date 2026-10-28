"""The live test track keeps up with what is built.

docs/TEST_TRACK.md must list:
- every fix marked **Done** in docs/VALIDATION_AND_KNOWN_GAPS.md §4, in the
  *Built in* column of at least one check row;
- every fix not done yet, in *Not built yet* (the rows to add when it is built);
- every PR number CHANGES.md cites, in *Every merged change and where it is
  proven* (or the line naming the cited PRs that were never merged).
Row ids are unique, every row carries a known status, and a passed or partly
passed row names its evidence.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACK = (ROOT / "docs" / "TEST_TRACK.md").read_text(encoding="utf-8")
GAPS = (ROOT / "docs" / "VALIDATION_AND_KNOWN_GAPS.md").read_text(encoding="utf-8")
CHANGES = (ROOT / "CHANGES.md").read_text(encoding="utf-8")
STATUSES = {"⬜", "✅", "❌", "➖"}


def _rows():
    """(id, built in, status) for every check row (6 columns)."""
    out = []
    for line in TRACK.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0] not in ("ID", "PR", "---") \
                and not set(cells[0]) <= {"-"} and not cells[0].startswith("#"):
            out.append((cells[0], cells[1], cells[4]))
    return out


def _backlog():
    """{F-n: done?} from VALIDATION_AND_KNOWN_GAPS.md §4."""
    backlog = GAPS.split("## 4. Fix backlog")[1].split("## 5.")[0]
    out = {}
    for fix, change in re.findall(r"^\| (F-\d+) \|[^|]*\| ([^\n]*)$", backlog, re.M):
        out[fix] = change.startswith("**Done")
    assert len(out) >= 31, "the backlog no longer reads as expected - update this test"
    return out


def test_every_done_fix_has_a_row():
    done = [f for f, d in _backlog().items() if d]
    assert len(done) >= 18
    built = " ".join(b for _i, b, _s in _rows())
    missing = [f for f in done if not re.search(rf"\b{f}\b", built)]
    assert not missing, f"built but no live check in TEST_TRACK.md: {missing}"


def test_every_fix_not_done_is_in_the_not_built_group():
    group = TRACK.split("## Not built yet: rows to add when each is built")[1].split("\n## ")[0]
    open_fixes = [f for f, d in _backlog().items() if not d]
    missing = [f for f in open_fixes if not re.search(rf"\| {f}\b", group)]
    assert not missing, f"fixes not built and not in *Not built yet*: {missing}"
    done = [f for f, d in _backlog().items() if d]
    stale = [f for f in done if re.search(rf"\| {f}\b", group)]
    assert not stale, f"built, but still listed as not built: {stale}"


def test_every_pr_changes_cites_is_in_the_coverage_list():
    coverage = TRACK.split("## Every merged change and where it is proven")[1]
    cited = sorted({int(n) for n in re.findall(r"#(\d{3,})\b", CHANGES)})
    assert cited, "CHANGES.md cites no PR - update this test"
    missing = [n for n in cited if not re.search(rf"#{n}\b", coverage)]
    assert not missing, f"PRs in CHANGES.md missing from TEST_TRACK's coverage list: {missing}"


def test_every_check_row_is_read():
    """A `|` inside a cell would split it and hide that row from these checks."""
    starts = [l for l in TRACK.split("## Every merged change")[0].splitlines()
              if re.match(r"\| [A-Z][A-Za-z0-9-]* \| ", l) and not l.startswith(("| ID", "| Session", "| Planned"))]
    assert len(starts) == len(_rows()), "a check row does not have exactly 6 cells"


def test_row_ids_are_unique_and_statuses_known():
    rows = _rows()
    assert len(rows) > 100
    ids = [i for i, _b, _s in rows]
    assert len(ids) == len(set(ids)), "duplicate row ids"
    assert all(s in STATUSES for _i, _b, s in rows), "unknown status"


def test_a_passed_row_names_its_evidence():
    for row_id, _b, status in _rows():
        line = next(l for l in TRACK.splitlines() if l.startswith(f"| {row_id} |"))
        evidence = line.strip().strip("|").split("|")[5].strip()
        if status in ("✅", "➖"):
            assert evidence, f"{row_id} is marked {status} without evidence"
