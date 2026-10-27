"""F-21 + F-22: the nightly run on main, and one defect per failing test and cause.

Before: Agent 4 ran only for pull requests and framework pushes - no schedule -
so an application regression with no PR open was found when someone next
opened one. And a test failing on main reached nobody: Agent 5 reports only on
a PR's story.

Now agent4_runner.yml also runs nightly on main (its own concurrency group, a
turn among PR runs, no story report), and its `triage` job
(scripts/triage_failures.py, core/defects.py) raises ONE defect per test and
cause, updates it on a repeat without a comment, flags it once when the test
passes again (a person closes it), and keeps outages (one health alert) and
flakes (recorded) out of defects. A flood of new failures raises at most
`max_new_per_run` and one alert.

Sandbox: the real JiraClient over a fake Jira. Generic names only.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from core import defects
from core import pipeline_health as ph
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over

ROOT = Path(__file__).resolve().parents[2]
NAV_503 = ("AssertionError: Navigation to https://s.example/x returned HTTP 503 (x) after 3 "
           "attempts. The page did not load, so every selector on it will time out.")
MULTI = "Error: strict mode violation: locator('.row') resolved to 3 elements"
TIMEOUT = "TimeoutError: Locator.click: Timeout 30000ms exceeded"
RUN = "https://ci.example/runs/"


def _case(name, outcome="passed", msg=MULTI, props=None, module="test_cart"):
    body = {"passed": "", "failed": f'<failure message="{msg}">{msg}</failure>',
            "error": f'<error message="{msg}">{msg}</error>'}[outcome]
    p = "".join(f'<property name="{k}" value="{v}"/>' for k, v in (props or {}).items())
    return (f'<testcase classname="tests.step_defs.{module}" name="{name}">'
            + (f"<properties>{p}</properties>" if p else "") + body + "</testcase>")


def _junit(tmp_path, *cases):
    p = tmp_path / "junit.xml"
    p.write_text(f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>')
    return p


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-1")
    fake.add("Test Case", "[Positive] Add an item", key="SBX-5")
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-5 (hash: abc12345) owner: SBX-1\n"
        "  Scenario: Add an item\n    Given I am home\n\n"
        "  Scenario: Remove an item\n    Given I am home\n")
    yield fake, jira, features
    ph.reset_cache()


def _bugs(fake):
    return {k: d for k, d in fake.issues.items() if d["issuetype"] == "Bug"}


def _triage(world, tmp_path, *cases, n=1, **kw):
    fake, jira, features = world
    return tf.run(jira, _junit(tmp_path, *cases), f"{RUN}{n}", features, **kw)


def _health_alerts(fake):
    key = next((k for k, d in fake.issues.items() if "pipeline-health" in d["labels"]), None)
    return [c.splitlines()[0] for c in fake.comments.get(key, [])] if key else []


# ── raising, repeating, passing again ────────────────────────

def test_a_failure_raises_one_defect_with_its_owner_and_cause(world, tmp_path):
    fake, jira, _ = world
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"), _case("test_ok"))
    (key,) = out["raised"]
    bug = fake.issues[key]
    assert bug["issuetype"] == "Bug"
    label = defects.defect_label("tests.step_defs.test_cart::test_add_an_item", "multi-match selector")
    assert bug["labels"] == ["ai-defect", label]
    assert "test_add_an_item fails on main: multi-match selector" in bug["summary"]
    state = defects.state_of(bug["description"])
    assert (state["test_case"], state["owner"], state["times"]) == ("SBX-5", "SBX-1", 1)
    assert "SBX-5 (owning story: SBX-1)" in bug["description"]
    assert state["last_run"] == f"{RUN}1" and "strict mode violation" in state["failure"]
    assert not fake.comments.get(key), "a new defect posts no comment"


def test_a_repeat_updates_without_a_comment(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=1)
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=2)
    assert out["raised"] == [] and len(_bugs(fake)) == 1
    (key, bug), = _bugs(fake).items()
    state = defects.state_of(bug["description"])
    assert state["times"] == 2 and state["last_run"] == f"{RUN}2"
    assert not fake.comments.get(key)


def test_passing_again_is_flagged_once_and_failing_again_unflags(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=1)
    (key,) = _bugs(fake)
    assert _triage(world, tmp_path, _case("test_add_an_item"), n=2)["passing"] == [key]
    assert "ai-defect-passing" in fake.issues[key]["labels"]
    assert _triage(world, tmp_path, _case("test_add_an_item"), n=3)["passing"] == []
    assert len(fake.comments[key]) == 1 and "Suggest closing" in fake.comments[key][0]
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=4)
    assert out["failing_again"] == [key] and "ai-defect-passing" not in fake.issues[key]["labels"]
    assert fake.comments[key][-1] == f"Failing again on main: {RUN}4"
    assert fake.issues[key]["status"] == "To Do", "never closed by the pipeline"


def test_a_test_not_run_is_not_called_passing(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"))
    assert _triage(world, tmp_path, _case("test_other"), n=2)["passing"] == []


def test_another_cause_is_another_defect(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"))
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed", msg=TIMEOUT), n=2)
    assert len(out["raised"]) == 1 and len(_bugs(fake)) == 2


def test_a_closed_defect_is_left_alone_and_a_new_one_raised(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"))
    (old,) = _bugs(fake)
    fake.issues[old]["status"] = "Done"
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=2)
    assert len(out["raised"]) == 1 and out["raised"][0] != old
    assert defects.state_of(fake.issues[old]["description"])["times"] == 1


def test_an_unmarked_test_still_raises_a_defect(world, tmp_path):
    fake, *_ = world
    (key,) = _triage(world, tmp_path, _case("test_remove_an_item", "error"))["raised"]
    assert "not marked" in fake.issues[key]["description"]


def test_the_owner_falls_back_to_the_tracker(world, tmp_path, monkeypatch):
    fake, jira, features = world
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-5 (hash: abc12345)\n  Scenario: Add an item\n"
        "    Given I am home\n")
    monkeypatch.setattr(jira, "get_parent_story_key", lambda key: "SBX-1" if key == "SBX-5" else None)
    assert defects.owner_of("tests.step_defs.test_cart::test_add_an_item[x]", features, jira) \
        == ("SBX-5", "SBX-1"), "an outline's parameters do not hide its scenario"


def test_failure_text_cannot_break_the_stored_data(world, tmp_path):
    fake, *_ = world
    nasty = "AssertionError: got {code}x{code} and ```fence```"
    (key,) = _triage(world, tmp_path, _case("test_add_an_item", "failed", msg=nasty))["raised"]
    state = defects.state_of(fake.issues[key]["description"])
    assert state and state["times"] == 1
    assert _triage(world, tmp_path, _case("test_add_an_item", "failed", msg=nasty), n=2)["raised"] == []


# ── kept out of defects ──────────────────────────────────────

def test_outages_and_flakes_never_raise_a_defect(world, tmp_path):
    fake, jira, _ = world
    out = _triage(world, tmp_path,
                  _case("test_add_an_item", "failed", msg=NAV_503, props={"outage": "1"}),
                  _case("test_flaky", props={"flaky": "1", "first_failure": "once"}))
    assert out["raised"] == [] and _bugs(fake) == {}
    assert out["outages"] == ["tests.step_defs.test_cart::test_add_an_item"]
    assert _health_alerts(fake) == [f"[health:open] {tf.OUTAGE}"]
    keys = jira.property_keys(ph.issue_key(jira))
    assert any(k.startswith("flaky.") for k in keys), "the flake is recorded"
    _triage(world, tmp_path, _case("test_add_an_item"), n=2)
    assert _health_alerts(fake)[-1] == f"[health:resolved] {tf.OUTAGE}"


def test_a_flood_raises_at_most_the_cap_and_one_alert(world, tmp_path, monkeypatch):
    fake, *_ = world
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "max_new_per_run": 2})
    out = _triage(world, tmp_path, *[_case(f"test_{i}", "failed") for i in range(4)])
    assert len(out["raised"]) == 2 and len(out["capped"]) == 2 and len(_bugs(fake)) == 2
    assert _health_alerts(fake) == [f"[health:open] {tf.CAPPED}"]
    out = _triage(world, tmp_path, *[_case(f"test_{i}", "failed") for i in range(2)], n=2)
    assert _health_alerts(fake)[-1] == f"[health:resolved] {tf.CAPPED}"


def test_no_report_is_an_alert_and_the_next_report_closes_it(world, tmp_path):
    fake, jira, features = world
    assert tf.run(jira, tmp_path / "missing.xml", f"{RUN}1", features) == {"report": False}
    assert _health_alerts(fake) == [f"[health:open] {tf.NO_REPORT}"]
    _triage(world, tmp_path, _case("test_ok"), n=2)
    assert _health_alerts(fake)[-1] == f"[health:resolved] {tf.NO_REPORT}"


def test_disabled_or_dry_run_writes_nothing(world, tmp_path, monkeypatch):
    fake, *_ = world
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"),
                  _case("test_x", "failed", msg=NAV_503, props={"outage": "1"}), dry_run=True)
    assert out["raised"] and out["raised"][0].startswith("(dry run)")
    assert _bugs(fake) == {} and _health_alerts(fake) == []
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "enabled": False})
    assert _triage(world, tmp_path, _case("test_add_an_item", "failed"))["raised"] == []
    assert _bugs(fake) == {}


def test_a_tracker_that_cannot_create_issues_raises_nothing(tmp_path):
    class Bare:
        def find_stories_to_process(self, *a, **k):
            return []
    root = ET.fromstring(f"<testsuite>{_case('test_a', 'failed')}</testsuite>")
    out = defects.triage(Bare(), root, "r", tmp_path)
    assert out["raised"] == [] and out["capped"] == ["tests.step_defs.test_cart::test_a"]


def test_a_tracker_outage_raises_nothing_and_never_raises(tmp_path):
    class Down:
        def find_stories_to_process(self, *a, **k):
            raise OSError("down")
    root = ET.fromstring(f"<testsuite>{_case('test_a', 'failed')}</testsuite>")
    assert defects.triage(Down(), root, "r", tmp_path)["raised"] == []


def test_the_script_exits_1_only_without_a_tracker(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("integrations.tracker.get_tracker",
                        lambda: (_ for _ in ()).throw(RuntimeError("no creds")))
    assert tf.main(["--reports-dir", str(tmp_path)]) == 1


# ── the workflow ─────────────────────────────────────────────

def _wf():
    return yaml.safe_load((ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8"))


def test_the_suite_runs_nightly_outside_business_hours():
    on = _wf()[True]
    (cron,) = [c["cron"] for c in on["schedule"]]
    minute, hour = (int(x) for x in cron.split()[:2])
    ist = (hour * 60 + minute + 330) % (24 * 60)
    assert ist < 9 * 60 or ist >= 20 * 60, f"{cron} is {ist // 60:02d}:{ist % 60:02d} IST"


def test_the_nightly_run_has_its_own_group_and_no_story_report():
    jobs = _wf()["jobs"]
    group = jobs["test"]["concurrency"]["group"]
    assert "github.event_name == 'schedule' && 'scheduled'" in group
    assert "github.event_name == 'pull_request'" in jobs["report"]["if"]


def test_the_triage_runs_only_after_runs_on_main():
    triage = _wf()["jobs"]["triage"]
    cond = triage["if"]
    assert triage["needs"] == "test" and cond.startswith(
        "always() && needs.test.result != 'cancelled' && github.ref == 'refs/heads/main'"), \
        "a superseded (cancelled) push run is not reported as a run with no report"
    for event in ("schedule", "workflow_dispatch", "push"):
        assert f"github.event_name == '{event}'" in cond
    assert "needs.test.outputs.push_e2e != 'false'" in cond
    assert "pull_request" not in cond
    assert triage["concurrency"]["group"] == "defect-triage"
    steps = triage["steps"]
    download = next(s for s in steps if "Download" in s["name"])
    assert download.get("continue-on-error") is True, "a missing report is triaged, not a crash"
    assert "scripts.triage_failures" in steps[-1]["run"]
    assert _wf()["jobs"]["test"]["outputs"]["push_e2e"] == "${{ steps.changes.outputs.inventory }}"


def test_the_settings_are_shipped():
    from core.ops_settings import DEFAULTS
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    for block in ("defects", "flaky_tests"):
        assert set(cfg[block]) == set(DEFAULTS[block])


def test_a_pass_only_on_the_retry_is_not_passing_again(world, tmp_path):
    fake, *_ = world
    _triage(world, tmp_path, _case("test_add_an_item", "failed"))
    out = _triage(world, tmp_path, _case("test_add_an_item", props={"flaky": "1"}), n=2)
    assert out["passing"] == [] and not any(
        "ai-defect-passing" in d["labels"] for d in _bugs(fake).values())


def test_a_refused_defect_write_is_reported_and_fails_the_job(world, tmp_path, monkeypatch):
    """A Bug create screen with a required field the pipeline does not fill:
    the run must not look clean."""
    fake, jira, features = world
    real_create = jira.create_issue

    def refuse(issue_type, *a, **k):
        if issue_type == "Bug":
            raise RuntimeError("Field 'priority' is required.")
        return real_create(issue_type, *a, **k)
    monkeypatch.setattr(jira, "create_issue", refuse)
    out = _triage(world, tmp_path, _case("test_add_an_item", "failed"))
    assert out["raised"] == [] and out["errors"][0][0].endswith("::test_add_an_item")
    assert _health_alerts(fake) == [f"[health:open] {tf.NOT_WRITTEN}"]
    _junit(tmp_path, _case("test_add_an_item", "failed"))
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: jira)
    assert tf.main(["--reports-dir", str(tmp_path), "--features-dir", str(features)]) == 1
    monkeypatch.setattr(jira, "create_issue", real_create)
    assert _triage(world, tmp_path, _case("test_add_an_item", "failed"), n=3)["errors"] == []
    assert _health_alerts(fake)[-1] == f"[health:resolved] {tf.NOT_WRITTEN}"


def test_an_unreadable_defect_list_is_an_error_too(tmp_path):
    class Down:
        def find_stories_to_process(self, *a, **k):
            raise OSError("down")
    root = ET.fromstring(f"<testsuite>{_case('test_a', 'failed')}</testsuite>")
    assert defects.triage(Down(), root, "r", tmp_path)["errors"][0][0] == "the open defects"
