"""The uncovered-element snapshot: from the nightly check to Agent 0's scan.

The nightly drift job writes a --compare report; the scan reads the newest one.
Every way the snapshot can be wrong must mean "no hint", never a failure and
never a stale hint. Generic names only; no browser, no tracker.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

import agents.agent0_impact as a0
from core import impact_analysis as ia
from core.impact_settings import impact_settings

NOW = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
PAGES = {"checkout": {"coupon_code_input": "#coupon"}}


def _write(tmp_path, **report):
    p = tmp_path / "drift.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def _fresh(tmp_path, hours_old=4, **extra):
    taken = (NOW - timedelta(hours=hours_old)).isoformat(timespec="seconds")
    return _write(tmp_path, checked_at=taken, new_elements=PAGES, **extra)


# ─────────────────────────────────────────────────────────────
# load_uncovered_snapshot: usable or refused with a reason
# ─────────────────────────────────────────────────────────────

def test_a_fresh_compare_report_is_used(tmp_path):
    assert ia.load_uncovered_snapshot(_fresh(tmp_path), 48, NOW) == (PAGES, "")


def test_a_fresh_report_with_nothing_uncovered_is_used_and_empty(tmp_path):
    p = _write(tmp_path, checked_at=NOW.isoformat(), new_elements={})
    assert ia.load_uncovered_snapshot(p, 48, NOW) == ({}, "")


@pytest.mark.parametrize("make, reason", [
    (lambda t: None, "no snapshot"),
    (lambda t: t / "missing.json", "unreadable"),
    (lambda t: (t / "bad.json").write_text("{not json") and t / "bad.json", "unreadable"),
    (lambda t: _write(t, checked_at=NOW.isoformat()), "without --compare"),
    (lambda t: _write(t, new_elements=PAGES), "checked_at"),
    (lambda t: _write(t, new_elements=PAGES, checked_at="yesterday"), "checked_at"),
    (lambda t: _fresh(t, hours_old=49), "old"),
    (lambda t: _fresh(t, hours_old=-3), "future"),
    (lambda t: (t / "list.json").write_text("[]") and t / "list.json", "without --compare"),
])
def test_every_bad_snapshot_means_no_hint_with_a_reason(tmp_path, make, reason):
    uncovered, why_not = ia.load_uncovered_snapshot(make(tmp_path), 48, NOW)
    assert uncovered == {} and reason in why_not


def test_a_timestamp_without_a_zone_is_read_as_utc(tmp_path):
    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None).isoformat()
    p = _write(tmp_path, checked_at=naive, new_elements=PAGES)
    assert ia.load_uncovered_snapshot(p, 48, NOW)[0] == PAGES


def test_the_age_limit_comes_from_the_caller(tmp_path):
    p = _fresh(tmp_path, hours_old=10)
    assert ia.load_uncovered_snapshot(p, 12, NOW)[0] == PAGES
    assert ia.load_uncovered_snapshot(p, 6, NOW)[0] == {}


# ─────────────────────────────────────────────────────────────
# Agent 0: read only when the hint is on, then passed down
# ─────────────────────────────────────────────────────────────

def test_the_snapshot_is_not_read_while_the_hint_is_off(tmp_path):
    settings = impact_settings({})
    assert settings["uncovered_hint"] is False
    assert a0._uncovered_for(str(_fresh(tmp_path)), settings) is None


def test_with_the_hint_on_a_fresh_snapshot_is_passed(tmp_path, monkeypatch):
    settings = impact_settings({"uncovered_hint": True})
    p = _write(tmp_path, checked_at=datetime.now(timezone.utc).isoformat(), new_elements=PAGES)
    assert a0._uncovered_for(str(p), settings) == PAGES


def test_with_the_hint_on_a_stale_snapshot_is_dropped(tmp_path):
    settings = impact_settings({"uncovered_hint": True, "uncovered_max_age_hours": 1})
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    assert a0._uncovered_for(str(_write(tmp_path, checked_at=old, new_elements=PAGES)),
                             settings) is None


def test_scan_hands_the_snapshot_to_every_story(monkeypatch):
    seen = []
    tracker = type("T", (), {"find_stories_to_process":
                             lambda self, sel, max_results: [{"key": "X-1"}, {"key": "X-2"}]})()
    monkeypatch.setattr(a0, "analyse_and_publish",
                        lambda tr, key, llm, s, root, host, dry_run=False, uncovered=None:
                        seen.append((key, uncovered)) or {"story": key})
    settings = impact_settings({"enabled": True, "shadow_mode": True})
    a0.scan(tracker, None, None, settings, ".", uncovered=PAGES)
    assert seen == [("X-1", PAGES), ("X-2", PAGES)]


def test_analyse_and_publish_hands_it_to_the_requirement_analysis(monkeypatch):
    seen = {}
    story = {"summary": "s", "description": "d", "components": []}
    tracker = type("T", (), {"get_story": lambda self, k: story})()
    monkeypatch.setattr(a0, "_already_analysed", lambda *a: False)
    monkeypatch.setattr(a0, "analyse_requirement",
                        lambda *a, uncovered=None, **k: seen.setdefault("u", uncovered) or {})
    monkeypatch.setattr(a0, "publish", lambda *a, **k: {"action": "published"})
    a0.analyse_and_publish(tracker, "X-1", None, impact_settings({}), ".", uncovered=PAGES)
    assert seen["u"] == PAGES


# ─────────────────────────────────────────────────────────────
# The workflow carries the snapshot from the nightly job to the scan
# ─────────────────────────────────────────────────────────────

def _jobs():
    from config.paths import PROJECT_ROOT
    wf = PROJECT_ROOT / ".github" / "workflows" / "agent0_impact.yml"
    return yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"]


def test_the_nightly_check_runs_compare_and_keeps_its_report():
    steps = _jobs()["drift"]["steps"]
    run = "\n".join(s.get("run", "") for s in steps)
    assert "check_inventory_staleness --compare --json reports/drift.json" in run
    upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert upload["with"]["name"] == "inventory-drift-report"
    assert upload["with"]["path"] == "reports/drift.json"
    assert upload.get("if") == "always()"


def test_the_scan_fetches_it_without_ever_failing_on_it():
    job = _jobs()["scan"]
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    names = [s.get("name") for s in job["steps"]]
    fetch = names.index("Fetch the latest nightly drift report")
    assert fetch < names.index("Run Agent 0")
    assert job["steps"][fetch]["continue-on-error"] is True
    assert "inventory-drift-report" in job["steps"][fetch]["run"]


def test_the_scan_passes_the_snapshot_to_both_modes():
    run = next(s for s in _jobs()["scan"]["steps"] if s.get("name") == "Run Agent 0")["run"]
    calls = [line for line in run.splitlines() if "python -m agents.agent0_impact" in line]
    assert len(calls) == 2                       # --story and --scan
    assert all(line.rstrip().endswith("$SNAP") for line in calls)
