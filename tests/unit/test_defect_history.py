"""The defect history on the results store (D7), the module of a defect (D8)
and what a closed defect was (D9).

13 Nov 2026: the reports read open defects only, live; 24 closed defects the
nightly run had raised were deleted from the tracker and nothing still knew
when they were opened or closed - no trend, no time to fix, no density.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from core import defect_ledger as dl

NOW = _dt.datetime(2026, 11, 14, 6, 0, tzinfo=_dt.timezone.utc)
PATTERNS = {"Basket": ["basket*.feature", "item_detail_basket.feature"]}


def _issue(key, *, open=True, created="2026-11-10T10:00:00.000+0530", resolved=None,
           labels=("ai-defect",), components=(), resolution=None, links=(), state=None,
           updated=None):
    desc = ""
    if state:
        desc = "text\n{code:json}\n" + json.dumps(state) + "\n{code}"
    return {"key": key, "summary": f"defect {key}", "status": "To Do" if open else "Done",
            "open": open, "labels": list(labels), "components": list(components),
            "created": created, "resolved": resolved, "updated": updated,
            "resolution": resolution, "priority": "Medium", "links": list(links),
            "description": desc}


class Tracker:
    """defects_for_history over a dict of issues; None when `down`."""
    def __init__(self, issues):
        self.issues = {i["key"]: i for i in issues}
        self.down = False
        self.asked = []

    def defects_for_history(self, issue_type, updated_since=None, open_only=False):
        self.asked.append((updated_since, open_only))
        if self.down:
            return None
        return [i for i in self.issues.values() if not open_only or i["open"]]


@pytest.fixture
def features(tmp_path):
    f = tmp_path / "features"
    f.mkdir()
    (f / "basket_management.feature").write_text(
        "Feature: B\n\n  # JIRA: PRJ-10 (hash: a0135022) owner: PRJ-5\n  Scenario: one\n    Given x\n\n"
        "  # JIRA: PRJ-11 (hash: b0135022) owner: PRJ-5\n  Scenario: two\n    Given x\n")
    (f / "sign_in.feature").write_text("Feature: S\n\n  Scenario: unmarked\n    Given x\n")
    return f


@pytest.fixture
def settings(monkeypatch):
    import core.ops_settings as ops
    real = ops.section

    def section(name):
        s = real(name)
        if name == "reporting":
            s = {**s, "modules": PATTERNS, "defect_history": True, "defect_keep_days": 730}
        if name == "cleanup":
            s = {"delete_label": "test-data"}
        return s
    monkeypatch.setattr(ops, "section", section)


# ── D8 module, D9 category ──────────────────────────────────────────────

def test_module_component_first_then_feature_file_then_its_own_name():
    files = {"PRJ-10": "basket_management.feature", "PRJ-20": "sign_in.feature"}
    assert dl.module_of(["Payments"], "tests.step_defs.test_basket_management::t", [], files,
                        PATTERNS) == "Payments"
    assert dl.module_of([], "tests.step_defs.test_basket_management::t", [], files,
                        PATTERNS) == "Basket"
    assert dl.module_of([], None, ["PRJ-1", "PRJ-20"], files, PATTERNS) == "sign_in"
    assert dl.module_of([], None, ["PRJ-1"], files, PATTERNS) == dl.UNASSIGNED


def test_category_from_the_label_else_the_resolution():
    s = {"close_categories": {"defect-test": "test", "defect-x": "made-up"},
         "resolution_categories": {"Duplicate": "duplicate"}}
    assert dl.category_of(["ai-defect", "defect-test"], "Done", s) == "test"
    assert dl.category_of(["defect-x"], "Duplicate", s) == "duplicate"   # unknown category ignored
    assert dl.category_of([], "Done", s) is None


def test_the_close_hint_names_each_label():
    hint = dl.close_hint({"close_categories": {"defect-app": "app", "defect-env": "environment"}})
    assert "`defect-app` (a bug in the application)" in hint and "`defect-env`" in hint
    assert dl.close_hint({}) == ""


# ── D7 the history ──────────────────────────────────────────────────────

def test_first_sync_reads_everything_and_keeps_what_the_trend_needs(tmp_path, features, settings):
    t = Tracker([
        _issue("PRJ-1", state={"test": "tests.step_defs.test_basket_management::t1",
                               "test_case": "PRJ-10", "owner": "PRJ-5", "cause": "timeout"}),
        _issue("PRJ-2", open=False, resolved="2026-11-12T08:00:00.000+0000",
               labels=["ai-defect", "defect-test"], links=["PRJ-11"]),
        _issue("PRJ-3", labels=["test-data"]),                     # throw-away: left out
        _issue("PRJ-4", labels=[], components=["Payments"]),      # raised by a person
    ])
    counts = dl.sync(tmp_path, t, features, NOW)
    assert t.asked == [(None, False)]                              # one full read
    assert counts["new"] == 3 and counts["left_out"] == 1
    recs = {r["key"]: r for r in dl.records(tmp_path)}
    assert set(recs) == {"PRJ-1", "PRJ-2", "PRJ-4"}
    one = recs["PRJ-1"]
    assert one["opened"] == "2026-11-10T04:30:00+00:00" and one["open"] and one["closed"] is None
    assert (one["module"], one["test_case"], one["story"], one["cause"], one["source"]) == \
        ("Basket", "PRJ-10", "PRJ-5", "timeout", "pipeline")
    two = recs["PRJ-2"]
    assert (two["closed"], two["category"], two["module"]) == \
        ("2026-11-12T08:00:00+00:00", "test", "Basket")
    assert (recs["PRJ-4"]["module"], recs["PRJ-4"]["source"]) == ("Payments", "person")


def test_a_deleted_defect_keeps_its_history_and_a_reopened_one_is_counted(tmp_path, features, settings):
    t = Tracker([_issue("PRJ-1"), _issue("PRJ-2", open=False, resolved="2026-11-12T08:00:00Z")])
    dl.sync(tmp_path, t, features, NOW)
    del t.issues["PRJ-1"]                                          # deleted in the tracker
    t.issues["PRJ-2"] = _issue("PRJ-2")                            # opened again
    later = NOW + _dt.timedelta(days=1)
    counts = dl.sync(tmp_path, t, features, later)
    assert t.asked[1:] == [("2026-11-12 06:00", False), (None, True)]   # changed + open
    assert counts["deleted"] == 1 and counts["reopened"] == 1
    recs = {r["key"]: r for r in dl.records(tmp_path)}
    assert recs["PRJ-1"]["deleted"] == later.isoformat(timespec="seconds")
    assert recs["PRJ-1"]["open"] is False and recs["PRJ-1"]["opened"]   # still there
    assert recs["PRJ-2"]["reopened"] == 1 and recs["PRJ-2"]["closed"] is None


def test_an_unreadable_tracker_leaves_the_history_alone(tmp_path, features, settings):
    t = Tracker([_issue("PRJ-1")])
    dl.sync(tmp_path, t, features, NOW)
    before = (tmp_path / dl.LEDGER_FILE).read_text()
    t.down = True
    assert dl.sync(tmp_path, t, features, NOW + _dt.timedelta(days=1)) is None
    assert (tmp_path / dl.LEDGER_FILE).read_text() == before
    assert dl.sync(tmp_path, object(), features, NOW) is None      # no such capability


def test_closed_long_ago_leaves_the_history(tmp_path, features, settings, monkeypatch):
    t = Tracker([_issue("PRJ-1", open=False, created="2023-01-01T00:00:00Z",
                        resolved="2023-01-02T00:00:00Z")])
    assert dl.sync(tmp_path, t, features, NOW)["dropped"] == 1
    assert dl.records(tmp_path) == []


def test_no_resolution_date_takes_the_last_change(tmp_path, features, settings):
    t = Tracker([_issue("PRJ-1", open=False, updated="2026-11-11T09:00:00Z")])
    dl.sync(tmp_path, t, features, NOW)
    assert dl.records(tmp_path)[0]["closed"] == "2026-11-11T09:00:00+00:00"


# ── the figures ─────────────────────────────────────────────────────────

def _recs():
    return [
        {"key": "A", "opened": "2026-11-10T01:00:00+00:00", "closed": "2026-11-12T01:00:00+00:00",
         "open": False, "module": "Basket", "category": "app", "source": "pipeline", "reopened": 0},
        {"key": "B", "opened": "2026-11-11T01:00:00+00:00", "closed": "2026-11-12T13:00:00+00:00",
         "open": False, "module": "Basket", "category": "test", "source": "pipeline", "reopened": 0},
        {"key": "C", "opened": "2026-11-12T01:00:00+00:00", "closed": None, "open": True,
         "module": "sign_in", "category": None, "source": "person", "reopened": 1},
    ]


def test_trend_per_day():
    t = dl.trend(_recs(), _dt.date(2026, 11, 10), _dt.date(2026, 11, 13))
    assert t["days"] == ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
    assert t["opened"] == [1, 1, 1, 0] and t["closed"] == [0, 0, 2, 0]
    assert t["open"] == [1, 2, 1, 1]


def test_summary_and_density_count_product_defects_only():
    sm = dl.summary(_recs(), "2026-11-01", "2026-11-14")
    assert (sm["opened"], sm["closed"], sm["open"], sm["by_person"]) == (3, 2, 1, 1)
    assert sm["mean_days_to_close"] == 1.8                  # (2.0 + 1.5) / 2 = 1.75
    assert sm["closed_by_category"] == [("app", 1), ("test", 1)] and sm["reopened"] == 1
    rows = {r["module"]: r for r in dl.by_module(_recs(), "2026-11-01", "2026-11-14",
                                                  {"Basket": 2, "sign_in": 1, "Empty": 4}, 10)}
    assert (rows["Basket"]["opened"], rows["Basket"]["product"], rows["Basket"]["density"]) == (2, 1, 5.0)
    assert rows["sign_in"]["density"] == 10.0              # not categorised: counted
    assert rows["Empty"]["density"] == 0.0 and rows["Empty"]["opened"] == 0


def test_scenarios_per_module(features):
    assert dl.scenarios_per_module(features, PATTERNS) == {"Basket": 2, "sign_in": 1}


def test_a_sprint_record_survives_and_is_rewritten_while_active(tmp_path):
    sprint = {"id": 7, "name": "Team Sprint 3", "start": "2026-11-10T04:00:00.000Z",
              "end": "2026-11-23T18:00:00.000Z"}
    snap = dl.sprint_snapshot(tmp_path, sprint, _recs(), {"Basket": 2}, 10, NOW)
    assert (snap["start"], snap["end"], snap["opened"]) == ("2026-11-10", "2026-11-23", 3)
    assert (tmp_path / "sprints" / "7-team-sprint-3.json").is_file()
    dl.sprint_snapshot(tmp_path, sprint, _recs()[:1], {"Basket": 2}, 10, NOW)
    assert [s["opened"] for s in dl.read_sprints(tmp_path)] == [1]
    assert dl.sprint_snapshot(tmp_path, None, _recs(), {}, 10, NOW) is None


def test_the_store_prune_never_touches_the_history(tmp_path):
    from core.results_store import prune
    dl.write(tmp_path, {"synced": "x", "defects": {"A": {"key": "A"}}})
    (tmp_path / "runs.jsonl").write_text(json.dumps({"run_id": 1, "started": "2020-01-01"}) + "\n")
    prune(tmp_path, 90, NOW)
    assert dl.read(tmp_path)["defects"] == {"A": {"key": "A"}}


# ── D9 on the defect itself ─────────────────────────────────────────────

def test_a_raised_defect_says_which_label_to_add_when_closing():
    from core import defects
    text = defects.render(None, {"test": "t", "test_case": None, "owner": "PRJ-5",
                                 "cause": "c", "cause_text": "x", "remedy": "y", "failure": "f",
                                 "first_seen": "d", "last_seen": "d", "times": 1})
    assert "When you close it, add the label that says what it was" in text
    assert "`defect-app`" in text
