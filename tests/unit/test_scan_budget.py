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


# ── F27: a story that did nothing hands its place on ─────────────────────

def test_a_blocked_or_still_waiting_story_does_not_use_up_a_place(monkeypatch):
    """4 Nov 2026: a blocked story and a waiting one took both places on every
    scan; the third, PRJ-201, was deferred every time."""
    ran = []
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = [S("A-1", "A-2", "A-3", "A-4"), [], []]
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "load_agent_config", lambda: {
        "selection": {"x": 1}, "regenerate_selection": {"x": 1}, "update_selection": {"x": 1},
        "max_stories_per_run": 2, "scan_deadline_minutes": 12})
    outcome = {"A-1": {"status": "blocked", "free": True},
               "A-2": {"status": "waiting_for_open_pr", "free": True},
               "A-3": {"status": "pr_opened"}, "A-4": {"status": "pr_opened"}}

    def run(key, **kw):
        ran.append(key)
        return {"story_id": key, **outcome[key]}
    summary = []
    monkeypatch.setattr(a2, "run", run)
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: summary.extend(r))
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    a2.main()
    assert ran == ["A-1", "A-2", "A-3", "A-4"], "two places of work: A-3 and A-4"
    assert not [r for r in summary if r["status"] == "deferred"]
    outcome["A-1"] = {"status": "waiting_for_open_pr"}          # a wait that cost a plan
    ran.clear(); summary.clear()
    tracker.find_stories_to_process.side_effect = [S("A-1", "A-2", "A-3", "A-4"), [], []]
    a2.main()
    assert ran == ["A-1", "A-2", "A-3"]
    assert [r["story_id"] for r in summary if r["status"] == "deferred"] == ["A-4"]


# ── F26: a story run by key runs in the mode its labels ask for ─────────

@pytest.mark.parametrize("labels, mode", [
    (["ai-processed", "human-approved"], "normal"),
    (["ai-processed", "human-approved", "ai-update"], "update"),
    (["ai-processed", "human-approved", "ai-regenerate"], "regenerate")])
def test_a_story_run_by_key_takes_its_mode_from_its_labels(labels, mode):
    tracker = MagicMock()
    tracker.get_story.return_value = {"key": "A-1", "labels": labels}
    cfg = {"update_label": "ai-update", "regenerate_label": "ai-regenerate"}
    assert a2.story_mode("A-1", tracker, cfg) == mode


def test_both_mode_labels_are_refused_and_unreadable_labels_mean_normal():
    tracker = MagicMock()
    tracker.get_story.return_value = {"labels": ["ai-update", "ai-regenerate"]}
    with pytest.raises(ValueError, match="both"):
        a2.story_mode("A-1", tracker, {})
    tracker.get_story.side_effect = RuntimeError("down")
    assert a2.story_mode("A-1", tracker, {}) == "normal"


def test_main_runs_a_keyed_story_in_its_mode(monkeypatch):
    called = []
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "story_mode", lambda key: "update")
    monkeypatch.setattr(a2, "run_update", lambda key, **kw: called.append(("update", key))
                        or {"story_id": key, "status": "pr_opened"})
    monkeypatch.setattr(a2, "run", lambda key, **kw: called.append(("run", key, kw))
                        or {"story_id": key, "status": "pr_opened"})
    import core.usage_ledger as ul
    from contextlib import nullcontext
    monkeypatch.setattr(ul, "story_usage", lambda *a, **k: nullcontext())
    monkeypatch.setattr(sys, "argv", ["agent2", "--story", "A-1"])
    a2.main()
    assert called == [("update", "A-1")]
    monkeypatch.setattr(a2, "story_mode", lambda key: "regenerate")
    called.clear()
    a2.main()
    assert called == [("run", "A-1", {"dry_run": False, "is_regenerate": True})]


def test_a_provider_refusal_stops_the_scan_red(monkeypatch):
    from core.spend_budget import PROVIDER, BudgetExceeded
    ran, summary, code = [], [], None
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = [S("A-1", "A-2", "A-3"), [], []]
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "load_agent_config", lambda: {
        "selection": {"x": 1}, "regenerate_selection": {"x": 1}, "update_selection": {"x": 1},
        "max_stories_per_run": 5, "scan_deadline_minutes": 12})

    def run(key, **kw):
        ran.append(key)
        if key == "A-2":
            raise BudgetExceeded(PROVIDER, "the provider refuses")
        return {"story_id": key, "status": "pr_opened"}
    monkeypatch.setattr(a2, "run", run)
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: summary.extend(r))
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    with pytest.raises(SystemExit) as out:
        a2.main()
    assert out.value.code == 1 and ran == ["A-1", "A-2"]
    assert [(r["story_id"], r["status"]) for r in summary] == [
        ("A-1", "pr_opened"), ("A-2", "failed"), ("A-3", "deferred")]
    assert "provider refuses" in summary[-1]["error"]
