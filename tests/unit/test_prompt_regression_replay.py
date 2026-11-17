"""A fixed set is replayed when Agent 1-3 prompts change (C3).

scripts/prompt_regression.py replays, as dry runs, the stories and pull
requests config names, and holds each to what the agent must keep doing; the
workflow replays only the agents whose files a pull request changed and posts
one comment. Nothing here calls a model: the agents' run() is stood in for.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import scripts.prompt_regression as pr

ROOT = Path(__file__).resolve().parents[2]
S = {"enabled": True, "agent1_stories": ["PRJ-1", "PRJ-2"], "agent1_min_cases": 1,
     "agent1_max_cases": 7, "agent2_stories": ["PRJ-1"],
     "agent3_reviews": {"10": "approve", "11": "request_changes"},
     "triggers": {"agent1": ["prompts/agent1_", "agents/agent1_analyst.py"],
                  "agent2": ["prompts/agent2_"], "agent3": ["prompts/agent3_"]}}


# ── which agents a change replays ─────────────────────────────────────

@pytest.mark.parametrize("changed, agents", [
    (["prompts/agent1_bug_report.md"], ["agent1"]),
    (["./agents/agent1_analyst.py", "prompts/agent3_reviewer.md"], ["agent1", "agent3"]),
    (["prompts/agent2_coder_generate.md"], ["agent2"]),
    (["docs/GUIDE.md", "pages/base_page.py"], []),
])
def test_only_the_agents_whose_files_changed_replay(changed, agents):
    assert pr.agents_for(changed, S["triggers"]) == agents


def test_the_shipped_triggers_cover_every_prompt_of_agents_1_to_3():
    from core.ops_settings import section
    triggers = section("prompt_regression")["triggers"]
    for prompt in (ROOT / "prompts").glob("agent[123]_*.md"):
        assert pr.agents_for([f"prompts/{prompt.name}"], triggers), prompt.name


# ── each replay is held to what the agent must keep doing ─────────────

def test_agent1_must_draft_and_stay_in_range():
    ok = pr.replay_agent1("PRJ-1", S, lambda k, **kw: {
        "status": "tests_drafted_dry_run", "test_cases_generated": 3, "criteria": ["AC1", "AC2"]})
    assert ok["ok"] and "AC1, AC2 all mapped" in ok["detail"]
    many = pr.replay_agent1("PRJ-1", S, lambda k, **kw: {
        "status": "tests_drafted_dry_run", "test_cases_generated": 9})
    assert not many["ok"] and "outside 1-7" in many["detail"]
    held = pr.replay_agent1("PRJ-1", S, lambda k, **kw: {"status": "not_ready",
                                                        "readiness": "no list"})
    assert not held["ok"] and "no list" in held["detail"]


def test_agent1_is_replayed_as_a_dry_run_that_does_not_count_its_own_scenarios():
    seen = {}
    pr.replay_agent1("PRJ-1", S, lambda k, **kw: seen.update(kw) or {
        "status": "tests_drafted_dry_run", "test_cases_generated": 2})
    assert seen == {"dry_run": True, "replay": True}


def test_a_draft_refused_by_its_rules_is_a_failed_replay():
    def refuse(k, **kw):
        raise RuntimeError("AC2 is mapped to no test case")
    row = pr.replay_agent1("PRJ-1", S, refuse)
    assert not row["ok"] and "AC2 is mapped to no test case" in row["detail"]


def test_agent2_must_pass_its_gate_with_nothing_left_out():
    seen = {}
    ok = pr.replay_agent2("PRJ-1", S, lambda k, **kw: seen.update(kw) or {
        "status": "code_generated_dry_run", "files_generated": 3, "not_automated": []})
    assert ok["ok"] and seen == {"dry_run": True, "is_regenerate": True}
    left = pr.replay_agent2("PRJ-1", S, lambda k, **kw: {
        "status": "code_generated_dry_run", "not_automated": ["PRJ-5"]})
    assert not left["ok"] and "PRJ-5" in left["detail"]

    class Gate(ValueError):
        errors = ["Unsafe code error in 'pages/x_page.py': line 2"]

    def refuse(k, **kw):
        raise Gate("Code safety validation failed")
    gate = pr.replay_agent2("PRJ-1", S, refuse)
    assert not gate["ok"] and "Unsafe code error" in gate["detail"]


@pytest.mark.parametrize("expected, verdict, ok", [
    ("approve", "approve", True), ("approve", "comment", True),
    ("approve", "request_changes", False),
    ("request_changes", "request_changes", True), ("request_changes", "approve", False)])
def test_agent3_keeps_its_verdict_on_a_known_pull_request(expected, verdict, ok):
    seen = {}
    row = pr.replay_agent3("10", expected, S, lambda n, **kw: seen.update(n=n, **kw) or {
        "verdict": verdict, "blocking_count": 0})
    assert row["ok"] is ok and seen == {"n": 10, "dry_run": True}


def test_one_failing_replay_never_stops_the_others():
    def boom(k, **kw):
        raise RuntimeError("gateway down")
    rows = pr.replay(["agent1", "agent3"], S, {
        "agent1": boom,
        "agent3": lambda n, **kw: {"verdict": "request_changes", "blocking_count": 1}})
    assert [(r["agent"], r["item"], r["ok"]) for r in rows] == [
        ("agent1", "PRJ-1", False), ("agent1", "PRJ-2", False),
        ("agent3", "#10", False), ("agent3", "#11", True)]


def test_the_report_lists_every_replay():
    rows = [pr._row("agent1", "PRJ-1", True, "3 test case(s)"),
            pr._row("agent1", "PRJ-2", False, "draft refused: a | b")]
    text = pr.report(rows, ["agent1"])
    assert "1 of 2 replay(s) hold" in text and "| agent1 | PRJ-2 | ❌ | draft refused: a / b |" in text
    assert "nothing was written" in text
    assert "Nothing replayed" in pr.report([], ["agent2"])


# ── the command ───────────────────────────────────────────────────────

def test_the_command_exits_by_its_result(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pr, "settings", lambda: dict(S))
    monkeypatch.setattr(pr, "replay", lambda agents, s: [pr._row("agent1", "PRJ-1", False, "x")])
    out = tmp_path / "r.md"
    assert pr.main(["--agents", "agent1", "--report", str(out)]) == 1
    assert "❌" in out.read_text(encoding="utf-8")
    monkeypatch.setattr(pr, "replay", lambda agents, s: [pr._row("agent1", "PRJ-1", True, "x")])
    assert pr.main(["--agents", "agent1"]) == 0
    assert pr.main(["--agents", "agent9"]) == 2
    assert pr.main([]) == 2


def test_the_plan_is_written_for_the_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "settings", lambda: dict(S))
    changed = tmp_path / "changed.txt"
    changed.write_text("prompts/agent3_reviewer.md\nREADME.md\n", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert pr.main(["--plan", "--changed-files", str(changed)]) == 0
    assert out.read_text(encoding="utf-8") == "agents=agent3\n"


def test_switched_off_nothing_is_replayed(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "settings", lambda: {**S, "enabled": False})
    monkeypatch.setattr(pr, "replay", lambda *a: pytest.fail("replayed while off"))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert pr.main(["--agents", "agent1"]) == 0
    assert pr.main(["--plan", "--changed-files", "x"]) == 0
    assert "agents=\n" in out.read_text(encoding="utf-8")


# ── Agent 1's replay mode ─────────────────────────────────────────────

def test_a_replay_does_not_count_the_story_s_own_scenarios(tmp_path, monkeypatch):
    from agents import agent1_analyst
    (tmp_path / "a.feature").write_text(
        "Feature: f\n\n"
        "  # JIRA: PRJ-11 (hash: aaaaaaaa)\n  Scenario: Own one\n    Given x\n\n"
        "  # JIRA: PRJ-12 (hash: bbbbbbbb) owner: PRJ-1\n  Scenario: Own by marker\n    Given x\n\n"
        "  # JIRA: PRJ-21 (hash: cccccccc)\n  Scenario: Another story's\n    Given x\n",
        encoding="utf-8")
    monkeypatch.setattr("config.paths.FEATURES_DIR", tmp_path)
    every = agent1_analyst.existing_scenario_titles()
    assert len(every) == 3
    left = agent1_analyst.existing_scenario_titles(own_keys={"PRJ-11"}, owner="PRJ-1")
    assert left == {t for t in every if "another" in t}


# ── the workflow ──────────────────────────────────────────────────────

def _wf():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "prompt_regression.yml")
                          .read_text(encoding="utf-8"))


def test_the_workflow_runs_on_the_files_that_replay_an_agent():
    from core.ops_settings import section
    wf = _wf()
    on = wf.get("on") or wf.get(True)
    paths = on["pull_request"]["paths"]
    for prefixes in section("prompt_regression")["triggers"].values():
        for prefix in prefixes:
            assert any(p.rstrip("*") == prefix or prefix.startswith(p.rstrip("*")) for p in paths), prefix
    assert "workflow_dispatch" in on


def test_each_agent_replays_on_its_own_model_and_the_report_always_runs():
    steps = {s.get("id") or s["name"]: s for s in _wf()["jobs"]["replay"]["steps"]}
    models = {a: steps[a]["env"]["LLM_MODEL"] for a in ("agent1", "agent2", "agent3")}
    assert "LLM_MODEL_LIGHT" in models["agent1"]
    assert "LLM_MODEL_LIGHT" not in models["agent2"] and "LLM_MODEL_LIGHT" not in models["agent3"]
    for a in ("agent1", "agent2", "agent3"):
        assert steps[a]["continue-on-error"] is True
        assert f"contains(steps.plan.outputs.agents, '{a}')" in steps[a]["if"]
        assert f"--agents {a}" in steps[a]["run"]
    report = steps["Report the replays"]
    assert report["if"] == "always()"
    assert '*" failure "*' in report["run"] and "exit 1" in report["run"]
    assert "startswith(\"## Prompt regression (C3)\")" in report["run"]   # one comment, updated


def test_the_shipped_config_names_a_set():
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    block = cfg["prompt_regression"]
    assert block["enabled"] is True
    assert block["agent1_stories"] and block["agent2_stories"] and block["agent3_reviews"]
    assert set(block["agent3_reviews"].values()) <= {"approve", "request_changes"}
