"""Scheduled workflow runs the repository host never started - or started only
rarely - are reported by the pipeline health check: how often a cron line
fires, a schedule with no or too few starts in the window, a workflow younger
than the window, and runs that cannot be read (a refused token) judging no
workflow.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import pytest
from core import health_checks as hc


ROOT = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc


@pytest.mark.parametrize("expr, start, end, n", [
    ("*/30 * * * *", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 5, 2, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 6, 0, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 0),
    ("45 1 * * *", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 2),
    ("0 0 1 * 0", dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 1, 12, 0, 0), 2),
    ("0 12 * * 7", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 1),
])
def test_cron_fires_counts_the_minutes_a_line_names(expr, start, end, n):
    # 5 Jan 2026 is a Monday. "0 0 1 * 0" is the 1st OR a Sunday: the window
    # starts after 1 Jan 00:00, so Sunday 4 and Sunday 11 Jan count.
    assert hc.cron_fires(expr, start.replace(tzinfo=UTC), end.replace(tzinfo=UTC)) == n


@pytest.mark.parametrize("expr", ["", "* * * *", "60 * * * *", "0 0 * * MON", "*/0 * * * *"])
def test_a_line_that_cannot_be_read_counts_nothing(expr):
    now = dt.datetime(2026, 1, 5, tzinfo=UTC)
    assert hc.cron_fires(expr, now - dt.timedelta(hours=1), now) is None


def _tree(tmp_path, cron):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "job.yml").write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n  workflow_dispatch:\n')
    return tmp_path


class _Host:
    def __init__(self, runs):
        self.runs = runs

    def get_workflow_runs(self, name, branch, limit=20):
        return self.runs[:limit]


NOW = dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)


def _run(hours_ago, event="schedule"):
    return {"event": event, "created_at": (NOW - dt.timedelta(hours=hours_ago)).isoformat()}


def test_a_schedule_that_never_started_is_reported(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(2, "workflow_dispatch"), _run(30)]), root, NOW, 24, 3)
    assert f.problem and f.alert_id == "workflow-not-starting:job.yml"
    assert "asked for 24 runs" in f.detail and "started none" in f.detail


def test_one_started_run_closes_it(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(5), _run(30)]), root, NOW, 24, 3)
    assert not f.problem and f.title.startswith("Scheduled runs of job.yml start again")


def test_a_schedule_asking_for_few_runs_is_not_judged_silent(tmp_path):
    root = _tree(tmp_path, "0 3 * * *")                # once a day: below the minimum of 3
    (f,) = hc.schedule_findings(_Host([_run(30)]), root, NOW, 24, 3)
    assert not f.problem


def test_runs_that_do_not_reach_the_window_start_give_no_finding(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    busy = [_run(h / 10, "push") for h in range(100)]   # 100 runs, all inside the last 10 h
    assert hc.schedule_findings(_Host(busy), root, NOW, 24, 3) == []


class _HostWithAge(_Host):
    def __init__(self, runs, created_hours_ago):
        super().__init__(runs)
        self.created = (NOW - dt.timedelta(hours=created_hours_ago)).isoformat()

    def workflow_created_at(self, name):
        return self.created


def test_a_workflow_younger_than_the_window_is_not_judged(tmp_path):
    """E130: a workflow added minutes before the check cannot have missed a
    day of runs - no finding (an open alert stays as it is)."""
    root = _tree(tmp_path, "*/5 * * * *")
    assert hc.schedule_findings(_HostWithAge([], 0.3), root, NOW, 24, 3) == []
    (f,) = hc.schedule_findings(_HostWithAge([], 30), root, NOW, 24, 3)
    assert f.problem, "old enough: judged as before"


def test_a_host_without_the_capability_judges_as_before(tmp_path):
    root = _tree(tmp_path, "*/5 * * * *")
    (f,) = hc.schedule_findings(_Host([]), root, NOW, 24, 3)
    assert f.problem


def test_the_github_adapter_reads_a_workflow_with_no_runs(monkeypatch):
    """Slicing PyGithub's empty paginated list raised IndexError, logged as
    "could not read runs"; islice reads it as no runs."""
    from integrations import github_client as gc

    class _Empty:
        def __iter__(self):
            return iter(())

        def __getitem__(self, item):
            raise IndexError("list index out of range")
    client = gc.GitHubClient.__new__(gc.GitHubClient)
    client._repo = type("R", (), {"get_workflow": lambda self, f: type(
        "W", (), {"get_runs": lambda self, branch: _Empty(),
                  "created_at": dt.datetime(2026, 1, 6, tzinfo=UTC)})()})()
    assert client.get_workflow_runs("job.yml", "main", limit=5) == []
    assert client.workflow_created_at("job.yml").startswith("2026-01-06")


def test_an_unreadable_schedule_gives_no_finding(tmp_path):
    root = _tree(tmp_path, "0 0 * * MON")
    assert hc.schedule_findings(_Host([]), root, NOW, 24, 3) == []


def test_the_health_check_runs_it_with_the_shipped_settings():
    import yaml
    from core.ops_settings import DEFAULTS
    shipped = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())["pipeline_health"]
    # configured, of the default's kind, not pinned: the values are the project's to tune
    for key in ("schedule_window_hours", "schedule_min_expected"):
        assert isinstance(shipped[key], type(DEFAULTS["pipeline_health"][key])) and shipped[key] > 0
    src = (ROOT / "scripts" / "pipeline_health_check.py").read_text(encoding="utf-8")
    assert "hc.schedule_findings(host, root, now," in src


class _RefusedHost:
    """A repo host whose token is refused: the adapter returns [] unless
    asked to raise (strict), as GitHubClient does."""
    def get_workflow_runs(self, name, branch, limit=20, strict=False):
        if strict:
            raise RuntimeError("401 Bad credentials")
        return []


def test_runs_that_cannot_be_read_judge_no_workflow(tmp_path):
    """11 Nov 2026 (validation window L, health run 43016854504): with a
    refused token every workflow's runs read as [] - five workflow-not-starting
    alerts opened, and a workflow-failing alert would have been resolved."""
    root = _tree(tmp_path, "0 * * * *")
    assert hc.schedule_findings(_RefusedHost(), root, NOW, 24, 3) == []
    assert hc.workflow_findings(_RefusedHost(), root, 3) == []


def test_an_adapter_without_strict_is_read_as_before(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(30)]), root, NOW, 24, 3)
    assert f.problem


def test_the_github_adapter_raises_when_asked_to():
    from integrations.github_client import GitHubClient
    client = GitHubClient.__new__(GitHubClient)

    class Repo:
        def get_workflow(self, name):
            raise RuntimeError("401 Bad credentials")
    client._repo = Repo()
    assert client.get_workflow_runs("x.yml", "main") == []
    with pytest.raises(RuntimeError):
        client.get_workflow_runs("x.yml", "main", strict=True)


def test_a_refused_app_token_names_the_secret_to_fix():
    from pathlib import Path
    action = Path(".github/actions/agent-identity/action.yml").read_text(encoding="utf-8")
    step = action[action.index("Say why the App's token was refused"):]
    assert "if: failure() && steps.app.outcome == 'failure'" in step[:200]
    assert "GH_APP_PRIVATE_KEY" in step and "never falls back to GH_PAT" in step
