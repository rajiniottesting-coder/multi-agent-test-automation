"""An agent that leaves work for another starts it (core/handoff.py).

3 Nov 2026: PRJ-283 and PRJ-284 reached ai-ready at 13:22 IST; by 14:10
not one of Agent 1's half-hourly scheduled runs had started that day. Over the
two weeks before, GitHub started about 4 of its 19 daily runs, some hours
late. Agent 2's schedule showed the same.

Now Agent 0 starts Agent 1 when a story waits for it, and Agents 1 and 2 start
themselves again while stories still wait. A start needs work (asked with the
started agent's own selections), is bounded (handoff.max_chain), never follows
a failed run of the agent itself, and never fails the run it follows. A
tracker rule can start Agents 1 and 2 too (repository_dispatch). The schedules
stay. Generic names only.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from core import handoff

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
SETTINGS = {"enabled": True, "max_chain": 3,
            "workflows": {"agent_a": "a.yml", "agent_b": "b.yml"}}
CONFIG = {"agents": {
    "agent_a": {"selection": {"required_labels": ["ready"]}, "max_stories_per_run": 2},
    "agent_b": {"update_selection": {"required_labels": ["update"]},
                "selection": {"required_labels": ["approved"]},
                "regenerate_selection": {"required_labels": ["regen"]},
                "empty_selection": {}, "selection_notes": {"x": 1}},
}}


class Tracker:
    def __init__(self, by_label=None, fail=False):
        self.by_label, self.fail, self.asked = by_label or {}, fail, []

    def find_stories_to_process(self, selection, max_results=50):
        if self.fail:
            raise RuntimeError("tracker down")
        label = selection["required_labels"][0]
        self.asked.append((label, max_results))
        return [{"key": k} for k in self.by_label.get(label, [])][:max_results]


class Host:
    def __init__(self, fail=False):
        self.fail, self.started = fail, []

    def dispatch_workflow(self, workflow, ref, inputs):
        if self.fail:
            raise RuntimeError("403 Resource not accessible by integration")
        self.started.append((workflow, ref, inputs))


def _start(tracker, host, agent="agent_a", previous="", **kw):
    return handoff.start(tracker, host, agent, previous, settings=kw.pop("settings", SETTINGS),
                         config=CONFIG, **kw)


# ── what waits ──────────────────────────────────────────────────────────────

def test_every_selection_of_the_agent_is_asked_selection_first():
    assert [s["required_labels"][0] for s in handoff.selections("agent_b", CONFIG)] == \
        ["approved", "regen", "update"]
    t = Tracker({"update": ["S-3"]})
    assert handoff.waiting(t, "agent_b", CONFIG) == ["S-3"]
    assert all(n == 1 for _, n in t.asked), "one story is enough to know"


def test_an_unknown_agent_has_nothing_waiting():
    assert handoff.selections("agent_x", CONFIG) == []


# ── starting ────────────────────────────────────────────────────────────────

def test_a_waiting_story_starts_the_agent_in_scan_mode():
    host = Host()
    out = _start(Tracker({"ready": ["S-1", "S-2"]}), host)
    assert out["started"] and out["waiting"] == ["S-1"] and out["chain"] == 1
    assert host.started == [("a.yml", "main", {"chain": "1"})], "scan mode: no story_key"


def test_nothing_waiting_starts_nothing():
    host = Host()
    out = _start(Tracker(), host)
    assert not out["started"] and host.started == [] and not out.get("error")
    assert out["why"] == "no story waits for it"


@pytest.mark.parametrize("previous, chain", [("", 1), ("0", 1), ("2", 3), (" 1 ", 2),
                                             ("x; rm -rf /", 1), (None, 1), ("-4", 1)])
def test_the_chain_counts_runs_in_a_row(previous, chain):
    host = Host()
    out = _start(Tracker({"ready": ["S-1"]}), host, previous=previous)
    assert out["chain"] == chain and host.started[0][2] == {"chain": str(chain)}


def test_the_chain_stops_at_max_chain():
    host = Host()
    out = _start(Tracker({"ready": ["S-1"]}), host, previous="3")
    assert not out["started"] and host.started == [] and out["error"]
    assert "max_chain" in out["why"] and "schedule" in out["why"]


def test_the_end_of_a_chain_with_nothing_waiting_is_no_warning():
    host = Host()
    out = _start(Tracker(), host, previous="3")
    assert not out["started"] and not out.get("error") and out["why"] == "no story waits for it"


@pytest.mark.parametrize("settings, why", [
    (dict(SETTINGS, enabled=False), "handoff.enabled is false"),
    (dict(SETTINGS, workflows={}), "no workflow for agent_a"),
])
def test_switched_off_or_unnamed_starts_nothing(settings, why):
    t, host = Tracker({"ready": ["S-1"]}), Host()
    out = _start(t, host, settings=settings)
    assert not out["started"] and why in out["why"] and host.started == [] and t.asked == []


def test_a_dry_run_says_what_it_would_start():
    host = Host()
    out = _start(Tracker({"ready": ["S-1"]}), host, dry_run=True)
    assert not out["started"] and "would start a.yml" in out["why"] and host.started == []


@pytest.mark.parametrize("tracker, host, why", [
    (Tracker(fail=True), Host(), "could not ask the tracker"),
    (Tracker({"ready": ["S-1"]}), Host(fail=True), "a.yml not started"),
    (Tracker({"ready": ["S-1"]}), object(), "cannot start a workflow"),
])
def test_a_failure_is_reported_never_raised(tracker, host, why):
    out = _start(tracker, host)
    assert not out["started"] and out["error"] and why in out["why"]


def test_the_defaults_name_the_two_agents_the_schedules_start():
    from core.ops_settings import DEFAULTS, section
    assert DEFAULTS["handoff"]["workflows"] == {"agent1_analyst": "agent1_analyst.yml",
                                                "agent2_coder": "agent2_coder.yml"}
    s = section("handoff")
    for key, wf in s["workflows"].items():
        assert (WF / wf).exists(), f"{key}: {wf} is a workflow of this repository"
    real = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    for key in s["workflows"]:
        assert handoff.selections(key, real), f"{key} has a selection in config.yaml"


def test_the_script_never_fails_the_run(tmp_path):
    out, summary = tmp_path / "out", tmp_path / "summary"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JIRA_", "GITHUB_"))}
    env.update(PYTHONPATH=str(ROOT), GITHUB_OUTPUT=str(out), GITHUB_STEP_SUMMARY=str(summary),
               JIRA_URL="", JIRA_EMAIL="", JIRA_API_TOKEN="")
    r = subprocess.run([sys.executable, "-m", "scripts.start_agent", "--agent", "agent1_analyst"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert out.read_text() == "started=false\n"
    assert summary.read_text().startswith("Hand-off to agent1_analyst:")


def test_the_github_client_starts_the_workflow_and_raises_on_refusal(monkeypatch):
    from unittest.mock import MagicMock
    from integrations.github_client import GitHubClient
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    gh = GitHubClient()
    wf = MagicMock()
    wf.create_dispatch.return_value = True
    gh._repo = MagicMock()
    gh._repo.get_workflow.return_value = wf
    gh.dispatch_workflow("a.yml", "main", {"chain": 2})
    gh._repo.get_workflow.assert_called_once_with("a.yml")
    wf.create_dispatch.assert_called_once_with("main", {"chain": "2"}, throw=True)
    wf.create_dispatch.return_value = False
    with pytest.raises(RuntimeError, match="refused"):
        gh.dispatch_workflow("a.yml")


# ── the workflows ───────────────────────────────────────────────────────────

def _wf(name):
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def _start_steps(job):
    """The steps that may start an agent (recording what waits starts nothing)."""
    return [s for s in job.get("steps") or [] if "scripts.start_agent" in str(s.get("run", ""))
            and "--record-waiting" not in str(s.get("run", ""))]


def test_agent0_starts_agent1_after_its_story_analysis():
    job = _wf("agent0_impact.yml")["jobs"]["scan"]
    names = [s.get("name") or "" for s in job["steps"]]
    (step,) = _start_steps(job)
    assert names.index(step["name"]) == names.index("Run Agent 0") + 1
    assert "--agent agent1_analyst" in step["run"]
    assert step["if"].startswith("always()") and "dry_run != 'true'" in step["if"]
    assert step.get("continue-on-error") is True
    assert job["permissions"]["actions"] == "write"
    assert step["env"]["GITHUB_TOKEN"] == "${{ github.token }}", \
        "the built-in token: a workflow_dispatch it makes still runs"
    for name, other in _wf("agent0_impact.yml")["jobs"].items():
        if name != "scan":
            assert not _start_steps(other), f"{name}: only the story analysis releases stories"


@pytest.mark.parametrize("name, agent", [("agent1_analyst.yml", "agent1_analyst"),
                                         ("agent2_coder.yml", "agent2_coder")])
def test_agents_1_and_2_start_again_while_stories_wait(name, agent):
    wf = _wf(name)
    on = wf[True]
    assert "chain" in on["workflow_dispatch"]["inputs"], "the hand-off's input is declared"
    assert on["repository_dispatch"]["types"] == [agent], "a tracker rule can start it"
    assert "schedule" in on, "the schedule stays as the safety net"
    assert wf["permissions"]["actions"] == "write"
    (job,) = wf["jobs"].values()
    (step,) = _start_steps(job)
    assert job["steps"][-1] is step, "after the agent ran"
    assert step["if"].startswith("${{ !cancelled()"), \
        "also after a red run (one story needing a person must not strand the rest); " \
        "no loop: the restart needs progress (core/handoff.py)"
    assert "steps.deps.outcome == 'success'" in step["if"], \
        "not when the run stopped before its checkout and dependencies"
    (deps,) = [s for s in job["steps"] if s.get("id") == "deps"]
    assert "requirements.txt" in deps["run"]
    assert step.get("continue-on-error") is True
    assert f"--agent {agent}" in step["run"] and '--previous-chain "$CHAIN"' in step["run"]
    assert step["env"]["CHAIN"] == "${{ github.event.inputs.chain }}", \
        "the input reaches the script as data, never pasted into it"
    assert wf["concurrency"]["cancel-in-progress"] is False, \
        "a start while a run is going waits for it"


# ── restart only after progress (3-4 Nov 2026) ─────────────────────────
#
# PRJ-284 carried human-approved but was blocked (its earlier refusal): Agent
# 2 skips it, yet it matched the selection, so the hand-off restarted Agent 2
# five times per scheduled run until max_chain stopped it - ten empty runs.

def test_a_run_that_took_none_of_what_waited_starts_nothing():
    host = Host()
    out = _start(Tracker({"ready": ["S-9"]}), host, previous="1", waiting_before=["S-9"])
    assert not out["started"] and host.started == [] and not out.get("error")
    assert "took none of the stories" in out["why"]


def test_a_run_that_took_one_starts_again_for_the_rest():
    host = Host()
    out = _start(Tracker({"ready": ["S-9", "S-3"]}), host, previous="1",
                 waiting_before=["S-1", "S-9"])
    assert out["started"] and host.started[0][2] == {"chain": "2"}


def test_progress_is_judged_on_every_waiting_story_not_the_first():
    t = Tracker({"ready": [f"S-{i}" for i in range(1, 8)]})
    _start(t, Host(), waiting_before=["S-1"])
    assert t.asked and all(n == handoff.PROGRESS_LIMIT for _, n in t.asked)


def test_without_a_record_the_start_is_decided_as_before():
    host = Host()
    assert _start(Tracker({"ready": ["S-9"]}), host, waiting_before=None)["started"]


def test_the_record_round_trips_and_a_bad_one_means_unknown(tmp_path, monkeypatch):
    from scripts import start_agent as sa
    path = tmp_path / "w.json"
    monkeypatch.setattr(handoff, "waiting", lambda tracker, agent, config=None, limit=1: ["S-1", "S-2"])
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: object())
    assert sa.main(["--agent", "agent_a", "--record-waiting", str(path)]) == 0
    assert sa._read_record(str(path)) == ["S-1", "S-2"]
    path.write_text("{not json")
    assert sa._read_record(str(path)) is None
    assert sa._read_record(str(tmp_path / "missing.json")) is None
    assert sa._read_record("") is None


def test_recording_never_fails_the_run(tmp_path, monkeypatch):
    from scripts import start_agent as sa

    def down():
        raise RuntimeError("tracker down")
    monkeypatch.setattr("integrations.tracker.get_tracker", down)
    assert sa.main(["--agent", "agent_a", "--record-waiting", str(tmp_path / "w.json")]) == 0
    assert not (tmp_path / "w.json").exists()


@pytest.mark.parametrize("name, agent, run_step", [("agent1_analyst.yml", "agent1_analyst", "Run Agent 1"),
                                                   ("agent2_coder.yml", "agent2_coder", "Run Agent 2")])
def test_the_workflow_records_before_and_passes_it_to_the_restart(name, agent, run_step):
    (job,) = _wf(name)["jobs"].values()
    names = [s.get("name") or "" for s in job["steps"]]
    rec = job["steps"][names.index("Record the stories waiting before the run")]
    assert names.index("Record the stories waiting before the run") == names.index(run_step) - 1
    assert f"--agent {agent} --record-waiting reports/handoff_waiting.json" in rec["run"]
    assert rec.get("continue-on-error") is True
    (restart,) = _start_steps(job)[-1:]
    assert "--waiting-before reports/handoff_waiting.json" in restart["run"]


def test_agent0_starting_agent1_passes_no_record():
    (step,) = _start_steps(_wf("agent0_impact.yml")["jobs"]["scan"])
    assert "--waiting-before" not in step["run"], "a story released to Agent 1 is new work"


def test_the_script_passes_the_record_to_the_decision(tmp_path, monkeypatch):
    from scripts import start_agent as sa
    record = tmp_path / "w.json"
    record.write_text('["S-9"]')
    seen = {}

    def start(tracker, host, agent, previous, dry_run=False, waiting_before=None):
        seen["before"] = waiting_before
        return {"agent": agent, "started": False, "why": "x", "waiting": []}
    monkeypatch.setattr(handoff, "start", start)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: object())
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: object())
    sa.main(["--agent", "agent_a", "--previous-chain", "1", "--waiting-before", str(record)])
    assert seen["before"] == ["S-9"]


# ── a red run still hands off; a start never replaces a waiting run ───────────

@pytest.mark.parametrize("name", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_red_run_still_hands_off(name):
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    (job,) = wf["jobs"].values()
    step = next(s for s in job["steps"] if "again while stories wait" in s.get("name", ""))
    assert step["if"].startswith("${{ !cancelled()")
    src = (ROOT / "core" / "handoff.py").read_text(encoding="utf-8")
    assert "the run took none of the stories that waited when it began" in src, \
        "the progress rule is what keeps a red run from looping"


def test_a_run_waiting_to_start_is_not_replaced():
    from tests.unit.test_agents_start_the_next_agent import Host, Tracker, _start

    class Waiting(Host):
        def __init__(self, statuses):
            super().__init__()
            self.statuses = statuses

        def get_workflow_runs(self, workflow, branch, limit=20):
            return [{"status": s} for s in self.statuses]
    host = Waiting(["queued", "in_progress"])
    out = _start(Tracker({"ready": ["S-1"]}), host)
    assert not out["started"] and host.started == [] and not out.get("error")
    assert "already waiting to start" in out["why"]
    host = Waiting(["in_progress", "completed"])                 # the run asking is going
    assert _start(Tracker({"ready": ["S-1"]}), host)["started"]

    class Broken(Host):
        def get_workflow_runs(self, *a, **k):
            raise RuntimeError("down")
    assert _start(Tracker({"ready": ["S-1"]}), Broken())["started"], "cannot tell: as before"


@pytest.mark.parametrize("name", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_one_story_run_starts_the_scan_without_the_progress_rule(name):
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    (job,) = wf["jobs"].values()
    step = next(s for s in job["steps"] if "again while stories wait" in s.get("name", ""))
    assert step["env"]["STORY_KEY"] == "${{ github.event.inputs.story_key }}"
    assert 'if [ -n "$STORY_KEY" ]; then WAITED=""; fi' in step["run"]
