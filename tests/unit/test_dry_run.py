"""Agent 0's manual-run inputs mean what the form says.

Found by asking what each input combination of agent0_impact.yml really does:
- "Print the report; write nothing" with story_key blank ran the full scan
  LIVE: the workflow passed no --dry-run to --scan, and scan() had no dry run,
  so decided reviews were handed over for real;
- the reconcile job ran live whatever dry_run said (it had no dry run), and it
  settled every impact-applied story even when one story_key was given;
- mode = drift silently ignored a story_key.

The fix gives one meaning to dry_run in every job (core/dry_run.py: the real
code runs against adapters that perform no writes), passes story_key to
reconcile, and stops a drift run that names a story. These tests pin each
part, and the last ones fail if a job is added that a manual run can start
without reading dry_run.
"""
import copy
import os
import re
import subprocess

import pytest
import yaml

from core import dry_run
from integrations.repo_host import RepoHost
from integrations.tracker import Tracker


def _members(protocol) -> set:
    return {n for n in vars(protocol) if not n.startswith("_")}


# ─────────────────────────────────────────────────────────────
# core/dry_run.py
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("protocol, reads, writes", [
    (Tracker, dry_run.TRACKER_READS, dry_run.TRACKER_WRITES),
    (RepoHost, dry_run.REPO_HOST_READS, dry_run.REPO_HOST_WRITES),
])
def test_every_protocol_operation_is_classified_once(protocol, reads, writes):
    """A new operation must be declared a read or a write; until then the dry
    run intercepts it (fail-safe) and this test says which one is missing."""
    assert not (reads & writes)
    assert reads | writes == _members(protocol)


def test_reads_pass_through_and_writes_are_recorded_not_sent():
    class Inner:
        project_key = "AB"

        def __init__(self):
            self.sent = []

        def get_comments(self, key):
            return [f"comment on {key}"]

        def add_comment(self, key, body):
            self.sent.append((key, body))
            return "id-1"

        def brand_new_operation(self, key):          # not classified: intercepted
            self.sent.append(key)

    inner = Inner()
    t = dry_run.tracker(inner)
    assert t.project_key == "AB"
    assert t.get_comments("AB-1") == ["comment on AB-1"]
    assert t.add_comment("AB-1", "hello") is None
    assert t.brand_new_operation("AB-2") is None
    assert inner.sent == []
    assert [w[0] for w in t.writes] == ["add_comment", "brand_new_operation"]
    assert t.describe()[0] == "[dry run] tracker.add_comment('AB-1', 'hello')"


# ─────────────────────────────────────────────────────────────
# Reconcile: same decision as a live run, no write
# ─────────────────────────────────────────────────────────────
from tests.unit.test_agent2_impact import world  # noqa: F401
from tests.unit.test_impact_reconcile import NOW, opened  # noqa: F401


def _state(fake):
    return copy.deepcopy((fake.issues, fake.comments, fake.links))


def test_reconcile_dry_run_decides_like_a_live_run_and_writes_nothing(opened):  # noqa: F811
    from core.impact_reconcile import reconcile_story
    from core.impact_settings import impact_settings
    fake, jira, gh, original = opened
    settings = impact_settings({"reconcile": {"closed_scans": 1}})
    gh.close(1)
    before = _state(fake)
    t, h = dry_run.tracker(jira), dry_run.repo_host(gh)
    dry = reconcile_story(t, h, "SBX-5", settings, now=NOW)
    assert dry["action"] == "reverted" and dry["restored"] == ["SBX-11"]
    assert _state(fake) == before                                  # nothing written
    done = {(name, args[0]) for name, args, _k in t.writes}
    assert ("set_description", "SBX-11") in done
    assert ("add_label", "SBX-5") in done

    live = reconcile_story(jira, gh, "SBX-5", settings, now=NOW)
    assert (live["action"], live["restored"]) == (dry["action"], dry["restored"])
    assert fake.issues["SBX-11"]["description"] == original["description"]


def test_reconcile_script_dry_run_and_story(opened, monkeypatch, capsys):  # noqa: F811
    import integrations.repo_host as rh
    import integrations.tracker as tr
    from scripts import impact_reconcile
    fake, jira, gh, _original = opened
    monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: jira)
    monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: gh)
    gh.close(1)
    before = _state(fake)
    assert impact_reconcile.main(["--dry-run", "--story", "sbx-5"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("SBX-5: pending-close")
    assert "[dry run] tracker.add_comment('SBX-5'" in out
    assert _state(fake) == before


# ─────────────────────────────────────────────────────────────
# The workflow: every input reaches the job that should use it
# ─────────────────────────────────────────────────────────────
def _workflow():
    from config.paths import PROJECT_ROOT
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "agent0_impact.yml")
                          .read_text(encoding="utf-8"))


def _step(job: str, name: str) -> dict:
    return next(s for s in _workflow()["jobs"][job]["steps"] if s.get("name") == name)


def _render(text: str, inputs: dict) -> str:
    def value(m):
        expr = m.group(1).strip()
        if expr.startswith("github.event.inputs."):
            return str(inputs.get(expr.split(".")[-1], ""))
        return ""
    return re.sub(r"\$\{\{(.*?)\}\}", value, text)


def _run_step(tmp_path, step: dict, inputs: dict):
    """Run a step's own script with a fake `python` that records its arguments."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "python.log"
    (bin_dir / "python").write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    (bin_dir / "python").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    env.update({k: _render(str(v), inputs) for k, v in (step.get("env") or {}).items()})
    proc = subprocess.run(["bash", "-e", "-c", _render(step["run"], inputs)], cwd=tmp_path,
                          env=env, capture_output=True, text=True, check=False)
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


@pytest.mark.parametrize("inputs, expected", [
    ({"story_key": "", "dry_run": "true"}, "-m agents.agent0_impact --scan --dry-run"),
    ({"story_key": "", "dry_run": "false"}, "-m agents.agent0_impact --scan"),
    ({"story_key": "AB-7", "dry_run": "true"}, "-m agents.agent0_impact --story AB-7 --dry-run"),
    ({"story_key": "AB-7", "dry_run": "false"}, "-m agents.agent0_impact --story AB-7"),
])
def test_scan_step_passes_dry_run_and_story(tmp_path, inputs, expected):
    step = next(s for s in _workflow()["jobs"]["scan"]["steps"]
                if "agents.agent0_impact" in (s.get("run") or ""))
    proc, calls = _run_step(tmp_path, step, inputs)
    assert proc.returncode == 0, proc.stderr
    assert [c.strip() for c in calls] == [expected]


@pytest.mark.parametrize("inputs, expected", [
    ({"story_key": "", "dry_run": "false"}, "-m scripts.impact_reconcile"),
    ({"story_key": "", "dry_run": "true"}, "-m scripts.impact_reconcile --dry-run"),
    ({"story_key": "AB-7", "dry_run": "false"}, "-m scripts.impact_reconcile --story AB-7"),
    ({"story_key": "AB-7", "dry_run": "true"},
     "-m scripts.impact_reconcile --dry-run --story AB-7"),
    ({"story_key": "AB-7; touch pwned", "dry_run": "false"},       # never executed
     "-m scripts.impact_reconcile --story AB-7; touch pwned"),
])
def test_reconcile_step_passes_dry_run_and_story(tmp_path, inputs, expected):
    proc, calls = _run_step(tmp_path, _step("reconcile", "Settle stories labelled impact-applied"),
                            inputs)
    assert proc.returncode == 0, proc.stderr
    assert [c.strip() for c in calls] == [expected]
    assert not (tmp_path / "pwned").exists()


def test_drift_mode_with_a_story_key_stops_and_says_why(tmp_path):
    step = _step("drift", "Refuse a story key in drift mode")
    assert step["if"] == ("github.event_name == 'workflow_dispatch' && "
                          "github.event.inputs.story_key != ''")
    assert _workflow()["jobs"]["drift"]["steps"][0] is not None
    assert _workflow()["jobs"]["drift"]["steps"][0]["name"] == step["name"]   # first step
    proc, _calls = _run_step(tmp_path, step, {"story_key": "AB-7"})
    assert proc.returncode == 1
    assert "story_key 'AB-7' cannot be used with mode = drift" in proc.stdout


def test_every_job_a_manual_run_can_start_reads_dry_run():
    """The generic guard: a job a person can start from Run workflow must
    honour 'write nothing'. Read-only jobs are listed by name."""
    read_only = {"gate"}
    for name, job in _workflow()["jobs"].items():
        cond = job.get("if", "")
        if name in read_only or "workflow_dispatch" not in cond:
            continue
        text = yaml.safe_dump(job)
        assert "github.event.inputs.dry_run" in text, f"job {name} ignores dry_run"
