"""Group B X4: a change story waits for its deployment. Its failing tests are
expected (no defect on main, a line in Agent 5's report) until the deployed
signal, which removes the pending label and reminds once to merge the story's
context-update pull request.

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import defects, deployment
from core import pipeline_health as ph
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over
from tests.unit.test_defect_triage import RUN, _case, _junit

pytestmark = pytest.mark.gates_on
ON = {"enabled": True, "story_type": "Story", "pending_label": "awaiting-deployment",
      "deployed_label": "deployed", "mark_on_handover": True}
BUG = defects.settings()["issue_type"]


def _plain(text: str) -> str:
    return text.replace("{{", "").replace("}}", "").replace("\\", "").replace("`", "")


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    monkeypatch.setattr(deployment, "settings", lambda: dict(ON))
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-1")
    fake.add("Story", "The cart loses its delete button", key="SBX-9")
    fake.add("Test Case", "[Positive] Add an item", key="SBX-5")
    jira = jira_client_over(fake, monkeypatch)
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "max_new_per_run": 10,
                                                      "reuse_person_defects": False,
                                                      "retest_resolved": False,
                                                      "link_recurrences": False})
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-5 (hash: abc12345) owner: SBX-1\n"
        "  Scenario: Add an item\n    Given I am home\n")
    yield fake, jira, features
    ph.reset_cache()


def _triage(world, tmp_path, n=1):
    fake, jira, features = world
    return tf.run(jira, _junit(tmp_path, _case("test_add_an_item", "failed")), f"{RUN}{n}",
                  features)


def _bugs(fake):
    return [k for k, d in fake.issues.items() if d["issuetype"] == BUG]


def test_the_owner_story_awaiting_deployment_makes_its_failure_expected(world, tmp_path):
    fake, *_ = world
    fake.issues["SBX-1"]["labels"].append("awaiting-deployment")
    out = _triage(world, tmp_path)
    assert out["expected"] == ["tests.step_defs.test_cart::test_add_an_item (SBX-1)"]
    assert out["raised"] == [] and _bugs(fake) == []


def test_a_test_case_revised_by_a_pending_change_story_is_expected_too(world, tmp_path):
    fake, jira, _ = world
    fake.issues["SBX-9"]["labels"].append("awaiting-deployment")
    jira.link_issues("SBX-9", "SBX-5", "impacts")
    out = _triage(world, tmp_path)
    assert out["expected"] and out["expected"][0].endswith("(SBX-9)") and _bugs(fake) == []


def test_once_deployed_the_failure_is_real(world, tmp_path):
    fake, *_ = world
    fake.issues["SBX-1"]["labels"] += ["awaiting-deployment", "deployed"]
    out = _triage(world, tmp_path)
    assert out["expected"] == [] and len(out["raised"]) == 1


def test_off_by_default_nothing_is_expected(world, tmp_path, monkeypatch):
    fake, *_ = world
    monkeypatch.setattr(deployment, "settings", lambda: {**ON, "enabled": False})
    fake.issues["SBX-1"]["labels"].append("awaiting-deployment")
    assert len(_triage(world, tmp_path)["raised"]) == 1


def test_the_hand_over_marks_the_change_story(world):
    fake, jira, _ = world
    assert deployment.mark_pending(jira, "SBX-9")
    assert "awaiting-deployment" in fake.issues["SBX-9"]["labels"]
    (body,) = map(_plain, fake.comments["SBX-9"])
    assert body.startswith("[deployment]") and "add deployed" in body
    src = (Path(__file__).resolve().parents[2] / "core" / "impact_handover.py").read_text()
    assert "deployment.mark_pending(tracker, change_story, d)" in src


class Host:
    def __init__(self, prs):
        self.prs, self.comments = prs, {}

    def list_open_prs(self, prefix=""):
        return [p for p in self.prs if p["head_ref"].startswith(prefix)]

    def post_pr_comment(self, n, body):
        self.comments.setdefault(n, []).append(body)


def test_deployed_removes_the_label_and_reminds_once(world):
    fake, jira, _ = world
    from core.context_update import branch_for
    from core.impact_settings import impact_settings
    prefix = impact_settings()["context_update"]["branch_prefix"]
    fake.issues["SBX-9"]["labels"] += ["awaiting-deployment", "deployed"]
    host = Host([{"number": 41, "head_ref": branch_for("SBX-9", prefix) + "-2"},
                 {"number": 42, "head_ref": "auto/SBX-9-x"}])
    result = {"deployed": [], "reminded": [], "errors": [], "write_errors": []}
    deployment.deployed(jira, host, result)
    assert result["deployed"] == ["SBX-9"] and result["reminded"] == [41]
    assert "awaiting-deployment" not in fake.issues["SBX-9"]["labels"]
    body = _plain(fake.comments["SBX-9"][-1])
    assert "pull request #41 now" in body and "real again" in body
    assert "merge this pull request now" in host.comments[41][0] and 42 not in host.comments
    again = {"deployed": [], "reminded": [], "errors": [], "write_errors": []}
    deployment.deployed(jira, host, again)
    assert again["deployed"] == [], "said once: the pending label is gone"


def test_the_watcher_runs_the_deployment_step(world, monkeypatch):
    fake, jira, features = world
    from core import tracker_watch as tw
    fake.issues["SBX-9"]["labels"] += ["awaiting-deployment", "deployed"]
    out = tw.run(jira, Host([]), features)
    assert out["deployed"] == ["SBX-9"]
    assert "no open context-update pull request" in _plain(fake.comments["SBX-9"][-1])


def test_the_signal_labels_only_stories_awaiting_deployment(world):
    fake, jira, _ = world
    fake.issues["SBX-9"]["labels"].append("awaiting-deployment")
    assert deployment.signal(jira, ["SBX-9", "SBX-1"]) == ["SBX-9"]
    assert "deployed" in fake.issues["SBX-9"]["labels"]
    assert "deployed" not in fake.issues["SBX-1"]["labels"]


def test_the_webhook_payload_is_read_as_keys():
    from scripts.deployment_signal import keys_of
    assert keys_of('["SBX-1","SBX-22"]') == ["SBX-1", "SBX-22"]
    assert keys_of("SBX-1, SBX-2") == ["SBX-1", "SBX-2"]
    assert keys_of("none") == []


def test_the_workflow_passes_the_payload_through_the_environment():
    wf = (Path(__file__).resolve().parents[2] / ".github" / "workflows"
          / "deployment_signal.yml").read_text()
    assert "types: [deployed]" in wf and "client_payload.stories" in wf
    run_line = [line for line in wf.splitlines() if line.strip().startswith("run: python")][0]
    assert "${{" not in run_line, "the caller's text never lands in the script"


def test_agent5_says_the_failures_are_expected(world):
    fake, jira, _ = world
    from agents import agent5_reporter as a5
    assert a5._awaiting_deployment(jira, "SBX-1") == ""
    fake.issues["SBX-1"]["labels"].append("awaiting-deployment")
    note = a5._awaiting_deployment(jira, "SBX-1")
    assert note.startswith("> ⏳ **Awaiting deployment**")
    report = a5.RunReport(total=1, passed=0, failed=1, errors=0, skipped=0,
                          duration_seconds=1.0, results=[])
    body = a5.build_final_comment("❌ 1 failed", report, awaiting=note)
    assert body.splitlines()[0] == note
