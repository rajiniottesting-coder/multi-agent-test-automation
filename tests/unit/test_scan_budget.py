"""F-4 (M2): one scan finishes what it starts.

Before: `max_stories_per_run` (2) applied to EACH of Agent 2's three passes
(normal, ai-regenerate, ai-update) - up to 6 stories - inside a 10-minute job.
The slowest stories measured ~8 minutes, so the job could be killed mid-story,
wasting what it had spent and leaving a half-done branch.

Now the cap is one budget for the whole scan (pass order), no story starts
after `scan_deadline_minutes`, and the job timeout is sized for the deadline
plus one slow story. Deferred stories keep their labels: the next scan takes
them. Generic names only.
"""
import re
import sys
from unittest.mock import MagicMock

import pytest
import yaml

import agents.agent2_coder as a2

S = lambda *keys: [{"key": k} for k in keys]


def test_the_cap_is_one_budget_for_all_passes():
    to_run, deferred = a2.plan_scan([("normal", S("A-1", "A-2")), ("regenerate", S("A-3")),
                                     ("update", S("A-4"))], 2)
    assert [(m, s["key"]) for m, s in to_run] == [("normal", "A-1"), ("normal", "A-2")]
    assert [(m, s["key"]) for m, s, _w in deferred] == [("regenerate", "A-3"), ("update", "A-4")]
    assert all("max_stories_per_run (2)" in w for _m, _s, w in deferred)


def test_a_story_in_two_passes_is_taken_once():
    to_run, deferred = a2.plan_scan([("normal", S("A-1")), ("regenerate", S("A-1", "A-2"))], 5)
    assert [(m, s["key"]) for m, s in to_run] == [("normal", "A-1"), ("regenerate", "A-2")]
    assert deferred == []


@pytest.mark.parametrize("cap", [0, -1])
def test_a_zero_cap_runs_nothing(cap):
    to_run, deferred = a2.plan_scan([("normal", S("A-1"))], cap)
    assert to_run == [] and len(deferred) == 1


def _scan(monkeypatch, stories, cap=5, deadline=12, durations=None):
    """Run main() in scan mode; each story advances the fake clock."""
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = [S(*stories), [], []]
    now = {"t": 0.0}
    monkeypatch.setattr(a2, "_clock", lambda: now["t"])
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "load_agent_config", lambda: {
        "selection": {"x": 1}, "regenerate_selection": {"x": 1}, "update_selection": {"x": 1},
        "max_stories_per_run": cap, "scan_deadline_minutes": deadline})
    ran, summary = [], []

    def run(key, **kw):
        ran.append(key)
        now["t"] += (durations or {}).get(key, 60)
        return {"story_id": key, "status": "pr_opened"}
    monkeypatch.setattr(a2, "run", run)
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: summary.extend(r))
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    code = 0
    try:
        a2.main()
    except SystemExit as e:
        code = e.code
    return ran, summary, code


def test_no_story_starts_after_the_deadline(monkeypatch):
    ran, summary, code = _scan(monkeypatch, ["A-1", "A-2", "A-3"], deadline=10,
                               durations={"A-1": 8 * 60, "A-2": 3 * 60})
    assert ran == ["A-1", "A-2"], "A-2 started at 8 min (< 10); A-3 would start at 11"
    deferred = [r for r in summary if r["status"] == "deferred"]
    assert [(r["story_id"], "deadline" in r["error"]) for r in deferred] == [("A-3", True)]
    assert code == 0, "a deferred story is not a failure"


def test_deferred_stories_are_in_the_summary_and_never_fail_the_job(monkeypatch):
    ran, summary, code = _scan(monkeypatch, ["A-1", "A-2", "A-3"], cap=1)
    assert ran == ["A-1"] and code == 0
    lines = a2._scan_summary_lines(summary)
    assert any(l.startswith("[DEFER] A-2: deferred") for l in lines)
    assert any("labels unchanged, the next scan takes it" in l for l in lines)


def test_the_job_timeout_fits_the_deadline_and_one_slow_story():
    cfg = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))["agents"]["agent2_coder"]
    wf = open(".github/workflows/agent2_coder.yml", encoding="utf-8").read()
    timeout = int(re.search(r"timeout-minutes:\s*(\d+)", wf).group(1))
    slowest_story, setup = 8, 2
    assert cfg["scan_deadline_minutes"] + slowest_story + setup <= timeout < 30, \
        "the deadline plus one slow story fits; the job ends before the next 30-minute cron"
    assert cfg["max_stories_per_run"] >= 1
