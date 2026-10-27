"""F-23: one standing tracker issue people watch, and the checks that feed it.

Before: a scheduled agent failing run after run, an expired token or a spent
model key showed up only as red runs in the Actions tab; nobody was told.

Now: core/pipeline_health.py keeps ONE issue (found by label, created when
first needed). An alert posts a comment when it opens and one when it closes -
nothing while it persists - and the description is the current picture.
scripts/pipeline_health_check.py runs the checks on a schedule.

Sandbox: the real JiraClient over a fake Jira. Generic names only.
"""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import health_checks as hc
from core import pipeline_health as ph
from integrations.tracker import capability
from tests.sandbox.fake_jira import FakeJira, jira_client_over

NOW = dt.datetime(2026, 10, 27, 9, 0, tzinfo=dt.timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def fresh_cache():
    ph.reset_cache()
    yield
    ph.reset_cache()


@pytest.fixture
def world(monkeypatch):
    fake = FakeJira()
    jira = jira_client_over(fake, monkeypatch)
    return fake, jira


def _health(fake):
    return [k for k, d in fake.issues.items() if "pipeline-health" in d["labels"]]


def _alert_comments(fake, key):
    return [c for c in fake.comments.get(key, []) if c.startswith("[health:")]


# ── the tracker's optional capabilities ───────────────────────

def test_capability_is_none_when_the_adapter_lacks_it():
    class Bare:
        project_key = "X"
    assert capability(Bare(), "create_issue") is None
    assert capability(None, "create_issue") is None


def test_properties_round_trip_through_the_real_adapter(world):
    fake, jira = world
    key = fake.add("Task", "t")
    assert jira.property_keys(key) == []
    jira.set_property(key, "a.b", {"x": 1})
    assert jira.get_property(key, "a.b") == {"x": 1}
    assert jira.get_property(key, "missing") is None
    assert jira.property_keys(key) == ["a.b"]
    jira.delete_property(key, "a.b")
    jira.delete_property(key, "a.b")                       # already gone: not an error
    assert jira.property_keys(key) == []
    assert jira.check_access()["ok"] is True


def test_create_issue_any_type_with_labels(world):
    fake, jira = world
    key = jira.create_issue("Bug", "s", "d", ["l1"])
    assert fake.issues[key]["issuetype"] == "Bug" and fake.issues[key]["labels"] == ["l1"]


# ── the issue ─────────────────────────────────────────────────

def test_the_issue_is_created_once_and_then_found(world):
    fake, jira = world
    key = ph.issue_key(jira)
    assert _health(fake) == [key] and fake.issues[key]["issuetype"] == "Task"
    ph.reset_cache()
    assert ph.issue_key(jira) == key and _health(fake) == [key]


def test_the_oldest_of_two_is_always_used(world):
    fake, jira = world
    for key in ("SBX-30", "SBX-7", "SBX-12"):
        fake.add("Task", "Pipeline health", key=key, labels=["pipeline-health"])
    assert ph.issue_key(jira) == "SBX-7", "the lowest key, whatever order the search returns"


def test_not_created_when_only_looking(world):
    fake, jira = world
    assert ph.issue_key(jira, create=False) is None and _health(fake) == []
    assert ph.open_alerts(jira) == {}
    assert ph.resolve_alert(jira, "x") is False and _health(fake) == []


def test_disabled_means_no_issue_and_no_write(world, monkeypatch):
    fake, jira = world
    monkeypatch.setattr(ph, "settings", lambda: {"enabled": False})
    assert ph.issue_key(jira) is None
    assert ph.raise_alert(jira, "a", "t") is False
    assert fake.issues == {}


def test_a_tracker_that_cannot_create_issues_only_logs(caplog):
    tracker = MagicMock(spec=["find_stories_to_process", "get_comments", "add_comment"])
    tracker.find_stories_to_process.return_value = []
    assert ph.raise_alert(tracker, "a", "Something broke") is False
    assert "ALERT (not posted" in caplog.text
    tracker.add_comment.assert_not_called()


def test_a_tracker_outage_never_raises(caplog):
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = OSError("down")
    assert ph.issue_key(tracker) is None
    assert ph.raise_alert(tracker, "a", "t") is False


# ── alerts: a comment on each change, never on a repeat ──────

def test_an_alert_comments_when_it_opens_and_closes_only(world):
    fake, jira = world
    assert ph.raise_alert(jira, "workflow-failing:a.yml", "A failed 3 runs", "details")
    key = ph.issue_key(jira)
    assert ph.raise_alert(jira, "workflow-failing:a.yml", "A failed 4 runs") is False
    assert len(_alert_comments(fake, key)) == 1
    assert "workflow-failing:a.yml" in ph.open_alerts(jira)
    assert ph.resolve_alert(jira, "workflow-failing:a.yml", "A passed.")
    assert ph.resolve_alert(jira, "workflow-failing:a.yml") is False
    assert ph.open_alerts(jira) == {}
    assert ph.raise_alert(jira, "workflow-failing:a.yml", "A failed again")
    assert [c.split()[0] for c in _alert_comments(fake, key)] == \
        ["[health:open]", "[health:resolved]", "[health:open]"]


def test_comments_are_rendered_for_the_tracker_and_still_read_back(world):
    fake, jira = world
    ph.raise_alert(jira, "credential:model", "The model refused", "Check `the key`")
    body = _alert_comments(fake, ph.issue_key(jira))[0]
    assert "*The model refused*" in body and "{{the key}}" in body     # Jira wiki markup
    assert list(ph.open_alerts(jira)) == ["credential:model"]


def test_the_description_lists_the_open_alerts(world):
    fake, jira = world
    ph.raise_alert(jira, "b", "Second problem")
    ph.raise_alert(jira, "a", "First problem")
    desc = fake.issues[ph.issue_key(jira)]["description"]
    assert "Open alerts (2)" in desc and "{{a}} - First problem" in desc
    ph.resolve_alert(jira, "a")
    ph.resolve_alert(jira, "b")
    assert "Open alerts (0)" in fake.issues[ph.issue_key(jira)]["description"]


def test_alert_ids_with_spaces_are_one_token():
    assert ph._alert_id("budget day  2026") == "budget-day-2026"
    states = ph.alert_states(["  [health:open] x-1\n*T*", "[health:resolved] x-1", "[health:open] y"])
    assert {k: v[0] for k, v in states.items()} == {"x-1": "resolved", "y": "open"}


def test_resolve_where_closes_only_matching(world):
    fake, jira = world
    for a in ("budget-day-20261025", "budget-day-20261027", "other"):
        ph.raise_alert(jira, a, a)
    assert ph.resolve_where(jira, lambda a: a.startswith("budget-day-") and a < "budget-day-20261027") \
        == ["budget-day-20261025"]
    assert set(ph.open_alerts(jira)) == {"budget-day-20261027", "other"}


# ── append-only records ──────────────────────────────────────

def test_records_never_overwrite_each_other(world):
    fake, jira = world
    assert ph.record(jira, "spend", ["20261027", 5], {"v": 1})
    assert ph.record(jira, "spend", ["20261027", 5], {"v": 2})
    keys = ph.record_keys(jira, "spend")
    assert len(keys) == 2 and len(set(keys)) == 2
    assert all(k.startswith("spend.20261027.5.") for k in keys)
    assert ph.record_keys(jira, "spen") == []                         # prefix is a whole segment


def test_prune_deletes_only_older_days(world):
    fake, jira = world
    ph.record(jira, "spend", ["20260901", 1], {})
    ph.record(jira, "spend", ["20261027", 1], {})
    ph.record(jira, "flaky", ["abc", "20260901"], {})
    assert ph.prune(jira, "spend", "20261001") == 1
    assert ph.prune(jira, "flaky", "20261001", day_part=2) == 1
    assert [k.split(".")[1] for k in ph.record_keys(jira, "spend")] == ["20261027"]


def test_records_are_off_without_properties(caplog):
    tracker = MagicMock(spec=["find_stories_to_process", "create_issue"])
    tracker.find_stories_to_process.return_value = [{"key": "X-1"}]
    assert ph.record(tracker, "spend", ["d"], {}) is False
    assert ph.record(tracker, "spend", ["d"], {}) is False
    assert caplog.text.count("no issue properties") == 1
    assert ph.record_keys(tracker, "spend") == []


# ── checks: scheduled workflows ──────────────────────────────

def test_the_scheduled_workflows_are_read_from_the_repository():
    names = hc.scheduled_workflows(ROOT)
    assert "pipeline_health.yml" in names
    assert "agent3-reviewer.yml" not in names, "an event-only workflow has no schedule"
    for name in names:
        assert "schedule" in (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_a_new_scheduled_workflow_is_watched_without_a_code_change(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "nightly.yml").write_text("on:\n  schedule:\n    - cron: '0 1 * * *'\njobs: {}\n")
    (wf / "manual.yaml").write_text("on: workflow_dispatch\njobs: {}\n")
    (wf / "broken.yml").write_text("on: [\n")
    assert hc.scheduled_workflows(tmp_path) == ["nightly.yml"]


def R(conclusion, event="schedule", status="completed", url=None):
    return {"conclusion": conclusion, "event": event, "status": status, "url": url}


@pytest.mark.parametrize("runs,expected", [
    ([R("failure", url="u1"), R("failure"), R("failure"), R("success")], 3),
    ([R("failure"), R("success"), R("failure"), R("failure")], 1),
    ([R("failure"), R("failure", event="push"), R("success", event="pull_request"),
      R("timed_out")], 2),
    ([R("failure"), R("cancelled"), R(None, status="in_progress"), R("failure")], 2),
    ([R("success")], 0),
    ([], 0),
])
def test_the_failing_streak_counts_scheduled_runs_only(runs, expected):
    assert hc.failing_streak(runs)[0] == expected


def test_a_run_without_an_event_is_not_scheduled():
    assert hc.failing_streak([{"conclusion": "failure", "status": "completed"}])[0] == 0


def test_workflow_findings_alert_at_the_threshold(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    for n in ("a.yml", "b.yml", "self.yml"):
        (wf / n).write_text("on:\n  schedule:\n    - cron: '0 1 * * *'\n")
    host = MagicMock()
    host.get_workflow_runs.side_effect = lambda name, branch, limit: {
        "a.yml": [R("failure", url="https://run/9"), R("failure"), R("failure")],
        "b.yml": [R("failure"), R("failure"), R("success")]}.get(name, [])
    out = {f.alert_id: f for f in hc.workflow_findings(host, tmp_path, 3, exclude=("self.yml",))}
    assert set(out) == {"workflow-failing:a.yml", "workflow-failing:b.yml"}
    assert out["workflow-failing:a.yml"].problem and "https://run/9" in out["workflow-failing:a.yml"].detail
    assert not out["workflow-failing:b.yml"].problem
    assert all(c.args[1] == "main" for c in host.get_workflow_runs.call_args_list)


# ── checks: credentials ──────────────────────────────────────

@pytest.mark.parametrize("expires,problem", [
    ("2026-11-05 10:00:00 UTC", True),          # GitHub's header format, 9 days left
    ("2026-12-31T00:00:00+00:00", False),
    ("2026-10-20 00:00:00 UTC", True),          # already expired
])
def test_expiry_warns_within_the_window(expires, problem):
    f = hc.expiry_finding("x", "The token", expires, NOW, 14)
    assert f.problem is problem


def test_no_expiry_closes_a_warning_and_an_unreadable_one_changes_nothing():
    f = hc.expiry_finding("x", "The token", None, NOW, 14)
    assert f.problem is False and "no expiry date" in f.title, "a replaced, non-expiring token"
    assert hc.expiry_finding("x", "t", "next tuesday", NOW, 14) is None


def test_a_refused_repo_host_token_is_an_alert_without_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "s" * 30)

    def refuse():
        raise RuntimeError("Bad credentials for ghp_" + "s" * 30 + " owner a@b.co")
    (f,) = hc.repo_host_findings(refuse, NOW, 14)
    assert f.problem and f.alert_id == "credential:repo-host"
    assert "ghp_" not in f.detail and "a@b.co" not in f.detail


def test_a_repo_host_token_near_expiry():
    host = SimpleNamespace(check_access=lambda: {"ok": True, "expires": "2026-11-01 00:00:00 UTC"})
    found = {f.alert_id: f.problem for f in hc.repo_host_findings(lambda: host, NOW, 14)}
    assert found == {"credential:repo-host": False, "credential-expiry:repo-host": True}


def test_a_repo_host_without_the_capability_is_fine():
    found = hc.repo_host_findings(lambda: SimpleNamespace(), NOW, 14)
    assert [(f.alert_id, f.problem) for f in found] == [("credential:repo-host", False),
                                                        ("credential-expiry:repo-host", False)]


def test_the_model_check_completion(monkeypatch):
    from core import llm_client

    class Client:
        def __init__(self, temperature, max_output_tokens):
            assert max_output_tokens == 1
            self.llm = SimpleNamespace(invoke=lambda m: SimpleNamespace(usage_metadata={
                "input_tokens": 5, "output_tokens": 1}))

        def _call_with_quota_check(self, fn, *a):
            return fn(*a)
    monkeypatch.setattr(llm_client, "LLMClient", Client)
    llm_client.reset_usage()
    assert hc.check_model("completion").problem is False
    assert llm_client.get_usage_summary()["llm_calls"] == 1, "its cost is counted like any call"
    llm_client.reset_usage()


def test_a_refused_model_key_is_an_alert(monkeypatch):
    from core import llm_client
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "k" * 30)

    class Client:
        def __init__(self, *a, **k):
            raise llm_client.QuotaExhaustedError("budget exceeded for sk-" + "k" * 30)
    monkeypatch.setattr(llm_client, "LLMClient", Client)
    f = hc.check_model("completion")
    assert f.problem and "sk-" not in f.detail and "QuotaExhaustedError" in f.detail


def test_the_model_check_by_listing_and_off(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(status_code=401))
    assert hc.check_model("models").problem is True
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(status_code=200))
    assert hc.check_model("models").problem is False
    assert hc.check_model("off") is None


# ── the repo host adapter ────────────────────────────────────

def test_github_runs_carry_event_time_and_link(monkeypatch):
    from integrations.github_client import GitHubClient
    gh = GitHubClient.__new__(GitHubClient)
    run = SimpleNamespace(id=1, status="completed", conclusion="failure", head_sha="s",
                          event="schedule", created_at=dt.datetime(2026, 10, 27),
                          html_url="https://run/1")
    gh._repo = MagicMock()
    gh._repo.get_workflow.return_value.get_runs.return_value = [run]
    (r,) = gh.get_workflow_runs("x.yml", "main")
    assert r["event"] == "schedule" and r["url"] == "https://run/1"
    assert r["created_at"].startswith("2026-10-27") and r["head_sha"] == "s"


def test_github_check_access_reads_the_expiry(monkeypatch):
    import requests
    from integrations.github_client import GitHubClient
    gh = GitHubClient.__new__(GitHubClient)
    gh.token, gh.repo_full_name = "t", "o/r"
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, headers={"github-authentication-token-expiration": "2026-11-01 00:00:00 UTC"}))
    assert gh.check_access()["expires"] == "2026-11-01 00:00:00 UTC"
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=401, headers={}, json=lambda: {"message": "Bad credentials"}, text=""))
    with pytest.raises(RuntimeError, match="401: Bad credentials"):
        gh.check_access()


# ── the script ───────────────────────────────────────────────

@pytest.fixture
def script_world(world, monkeypatch, tmp_path):
    from scripts import pipeline_health_check as script
    fake, jira = world
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    for n in ("job.yml", "pipeline_health.yml"):
        (wf / n).write_text("on:\n  schedule:\n    - cron: '0 1 * * *'\n")
    state = {"runs": [R("failure")] * 3, "model": False}
    host = SimpleNamespace(get_workflow_runs=lambda *a, **k: state["runs"],
                           check_access=lambda: {"ok": True})
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: jira)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: host)
    monkeypatch.setattr(hc, "check_model", lambda mode: hc.Finding(
        "credential:model", state["model"], "model"))
    return fake, jira, state, lambda *extra: script.main(["--root", str(tmp_path), *extra])


def test_the_script_alerts_once_and_resolves(script_world):
    fake, jira, state, run = script_world
    assert run() == 0
    key = ph.issue_key(jira)
    assert [c.splitlines()[0] for c in _alert_comments(fake, key)] == \
        ["[health:open] workflow-failing:job.yml"], "its own workflow is not watched"
    assert run() == 0
    assert len(_alert_comments(fake, key)) == 1, "a persisting problem posts nothing more"
    state["runs"] = [R("success")] + [R("failure")] * 3
    state["model"] = True
    assert run() == 0
    assert [c.splitlines()[0] for c in _alert_comments(fake, key)][1:] == \
        ["[health:resolved] workflow-failing:job.yml", "[health:open] credential:model"]
    assert "no longer failing" in _alert_comments(fake, key)[1]


def test_the_dry_run_writes_nothing(script_world, capsys):
    fake, jira, state, run = script_world
    assert run("--dry-run") == 0
    assert fake.issues == {} and "[ALERT] workflow-failing:job.yml" in capsys.readouterr().out


def test_a_refused_tracker_fails_the_run(monkeypatch, capsys):
    from scripts import pipeline_health_check as script
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-" + "x" * 20)

    def refuse():
        raise RuntimeError("401 for tok-" + "x" * 20)
    monkeypatch.setattr("integrations.tracker.get_tracker", refuse)
    assert script.main(["--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "refused" in out and "tok-xxxx" not in out


def test_the_workflow_runs_the_script_on_a_schedule():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/pipeline_health.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert on["schedule"] and "workflow_dispatch" in on
    step = wf["jobs"]["check"]["steps"][-1]
    assert "scripts.pipeline_health_check" in step["run"]
    assert {"JIRA_API_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY"} <= set(step["env"])
    from scripts.pipeline_health_check import OWN_WORKFLOW
    assert (ROOT / ".github/workflows" / OWN_WORKFLOW).is_file()


def test_the_settings_are_shipped():
    import yaml
    from core.ops_settings import DEFAULTS
    shipped = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))["pipeline_health"]
    assert set(shipped) == set(DEFAULTS["pipeline_health"])


def test_a_malformed_block_falls_back_to_defaults(monkeypatch, tmp_path):
    import config.paths as paths
    cfg = tmp_path / "c.yaml"
    cfg.write_text("pipeline_health:\n  consecutive_failures: many\n  label: x\n")
    monkeypatch.setattr(paths, "CONFIG_YAML", cfg)
    from core.ops_settings import section
    s = section("pipeline_health")
    assert s["consecutive_failures"] == 3 and s["label"] == "x"
    cfg.write_text("pipeline_health: yes\n")
    assert section("pipeline_health")["label"] == "pipeline-health"


def test_a_removed_workflows_alert_closes_but_an_unreadable_ones_stays(script_world, tmp_path):
    fake, jira, state, run = script_world
    assert run() == 0
    (tmp_path / ".github/workflows/other.yml").write_text("on:\n  schedule:\n    - cron: '0 1 * * *'\n")
    run()
    key = ph.issue_key(jira)
    assert {"workflow-failing:job.yml", "workflow-failing:other.yml"} <= set(ph.open_alerts(jira))
    # other.yml's runs cannot be read this time: its alert is kept
    import core.health_checks as hcm
    real = hcm.workflow_findings
    hcm.workflow_findings = lambda host, root, n, exclude=(): [
        f for f in real(host, root, n, exclude) if f.alert_id != "workflow-failing:other.yml"]
    try:
        run()
        assert "workflow-failing:other.yml" in ph.open_alerts(jira)
    finally:
        hcm.workflow_findings = real
    (tmp_path / ".github/workflows/other.yml").unlink()
    run()
    assert "workflow-failing:other.yml" not in ph.open_alerts(jira)
    assert "workflow-failing:job.yml" in ph.open_alerts(jira)
    assert any(c.startswith("[health:resolved] workflow-failing:other.yml\nThe workflow is no "
                            "longer scheduled") for c in fake.comments[key])
