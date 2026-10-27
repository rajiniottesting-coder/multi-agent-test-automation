"""F-16 (G8): a new story whose pull request is closed without merging is set back.

Before: reconcile acted only on change stories (impact-applied). A new story's
PR closed unmerged left it labelled ai-coded, its card In Review, with nothing
left to act on it - a state a person had to notice and untangle.

Now the same scheduled scan settles every coded story that is not a change in
progress: after the close is seen on `closed_scans` scans, the
`story_reset_labels` come off (approval included, so it is not re-coded by
itself; ai-processed stays, so its test cases are not drafted again), the card
moves to `on_close_unmerged`, and one comment says how to retry or drop it.

Sandbox: real JiraClient over a fake Jira, fake repository host. Generic names.
"""
import sys
from unittest.mock import MagicMock

import pytest

from core import impact_reconcile as rc
from core.impact_settings import impact_settings
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import seed_jira

STORY = "SBX-90"
PIPELINE = ["ai-processed", "human-approved", "ai-coded", "ai-incomplete", "tests-run"]


@pytest.fixture
def world(monkeypatch):
    fake = seed_jira()
    fake.add("Story", "A shopper saves an address", key=STORY, status="In Review",
             labels=list(PIPELINE))
    fake.add("Test Case", "[Positive] Save an address", key="SBX-91", description="steps")
    fake.link("Relates", "SBX-91", STORY)
    jira = jira_client_over(fake, monkeypatch)
    gh = FakeRepoHost({})
    gh.create_branch(f"auto/{STORY}-address")
    gh.open_pull_request("Address", "b", f"auto/{STORY}-address")
    return fake, jira, gh


def _settings(**reconcile):
    s = impact_settings()
    s["reconcile"] = {**s["reconcile"], **reconcile}
    return s


def _notes(fake, kind):
    return [c for c in fake.comments.get(STORY, []) if c.startswith(f"[agent0:reconcile] {kind}")]


def test_an_open_pr_is_left_alone(world):
    fake, jira, gh = world
    assert rc.reconcile_all(jira, gh) == []
    assert fake.issues[STORY]["labels"] == PIPELINE and not fake.comments.get(STORY)


def test_a_close_seen_on_two_scans_sets_the_story_back(world):
    fake, jira, gh = world
    gh.close(1)
    first = rc.reconcile_all(jira, gh)
    assert first == [{"story": STORY, "action": "pending-close", "pr": 1}]
    assert fake.issues[STORY]["labels"] == PIPELINE, "nothing changes on the first sighting"
    assert "set back so it can be coded again or dropped" in _notes(fake, "closed-unmerged")[0]

    second = rc.reconcile_all(jira, gh)
    assert second[0]["action"] == "reset" and second[0]["pr"] == 1
    assert fake.issues[STORY]["labels"] == ["ai-processed"], "approval off: not re-coded by itself"
    assert fake.issues[STORY]["status"] == "To Do"
    note, = _notes(fake, "story-reset")
    assert "never reached main" in note and "test cases are not changed" in note
    assert "add human-approved" in note and "To drop it: nothing more to do" in note
    assert fake.issues["SBX-91"]["labels"] == [], "its test cases are untouched"

    assert rc.reconcile_all(jira, gh) == [], "settled once: no longer coded, never selected"
    assert rc.reconcile_unmerged_story(jira, gh, STORY)["action"] == "already-reset"


def test_retry_by_approval_makes_agent2_select_it_again(world):
    from agents.agent2_coder import load_agent_config
    fake, jira, gh = world
    selection = load_agent_config()["selection"]
    gh.close(1)
    rc.reconcile_all(jira, gh, _settings(closed_scans=1))
    picked = lambda: [s["key"] for s in jira.find_stories_to_process(selection, max_results=50)]
    assert STORY not in picked(), "not coded again until a person decides"
    jira.add_label(STORY, "human-approved")
    assert STORY in picked()


def test_a_close_the_sweeper_reopens_is_absorbed(world):
    fake, jira, gh = world
    gh.close(1)
    rc.reconcile_all(jira, gh)
    gh.reopen(1)
    assert rc.reconcile_all(jira, gh) == []
    gh.close(1)                              # a new close: counted afresh
    assert rc.reconcile_all(jira, gh)[0]["action"] == "pending-close"
    assert "ai-coded" in fake.issues[STORY]["labels"]


@pytest.mark.parametrize("merge_first", [True, False])
def test_a_merged_pr_means_nothing_to_settle(world, merge_first):
    fake, jira, gh = world
    gh.create_branch(f"auto/{STORY}-address-update2")
    gh.open_pull_request("Update", "b", f"auto/{STORY}-address-update2")
    if merge_first:
        gh.merge(1)
        gh.close(2)                              # an update rejected after the merge
    else:
        gh.close(1)
        gh.merge(2)
    for _ in range(3):
        assert rc.reconcile_all(jira, gh, _settings(closed_scans=1)) == []
    assert fake.issues[STORY]["labels"] == PIPELINE


def test_coded_without_a_pr_is_left_alone(world):
    fake, jira, _gh = world
    empty = FakeRepoHost({})
    assert rc.reconcile_unmerged_story(jira, empty, STORY)["action"] == "no-pr"
    assert rc.reconcile_all(jira, empty, _settings(closed_scans=1)) == []


def test_a_done_story_is_not_even_looked_up(world):
    fake, jira, gh = world
    fake.issues[STORY]["status"] = "Done"
    host = MagicMock(wraps=gh)
    rc.reconcile_all(jira, host)
    assert all(c.args[0] != STORY for c in host.find_prs_for_story.call_args_list)


def test_a_change_in_progress_is_left_to_the_change_path(world):
    fake, jira, gh = world
    fake.issues[STORY]["labels"].append("impact-applied")
    gh.close(1)
    out = rc.reconcile_all(jira, gh, _settings(closed_scans=1))
    assert [r["action"] for r in out if r["story"] == STORY] == ["reverted"], \
        "undone once, by the change path - not reset a second time"
    assert not _notes(fake, "story-reset")


def test_closed_scans_one_resets_on_the_first_scan(world):
    fake, jira, gh = world
    gh.close(1)
    assert rc.reconcile_all(jira, gh, _settings(closed_scans=1))[0]["action"] == "reset"


def test_reconcile_one_picks_the_right_path(world):
    fake, jira, gh = world
    gh.close(1)
    assert rc.reconcile_one(jira, gh, STORY, _settings(closed_scans=1))["action"] == "reset"
    fake.issues[STORY]["labels"] = ["impact-applied"]
    assert rc.reconcile_one(jira, gh, STORY)["action"] in {"reverted", "pending-close"}


def test_without_board_moves_the_labels_and_comment_still_happen(world, monkeypatch):
    fake, jira, gh = world
    import core.board_status as bs
    monkeypatch.setattr(bs, "load_status_workflow", lambda: {"enabled": False})
    gh.close(1)
    rc.reconcile_all(jira, gh, _settings(closed_scans=1))
    assert fake.issues[STORY]["status"] == "In Review"
    assert fake.issues[STORY]["labels"] == ["ai-processed"] and _notes(fake, "story-reset")


def test_unreadable_agent2_settings_fall_back_to_a_generic_retry_line(world, monkeypatch):
    fake, jira, gh = world
    monkeypatch.setattr(rc, "_agent2_config", lambda: {})
    gh.close(1)
    rc.reconcile_all(jira, gh, _settings(closed_scans=1))
    assert "add the approval label" in _notes(fake, "story-reset")[0]


def test_one_failing_story_does_not_stop_the_others(world, monkeypatch):
    fake, jira, gh = world
    fake.add("Story", "Another", key="SBX-95", status="In Review", labels=["ai-coded"])
    gh.close(1)
    real = rc.reconcile_unmerged_story

    def flaky(tracker, host, story, *a, **k):
        if story == "SBX-95":
            raise RuntimeError("boom")
        return real(tracker, host, story, *a, **k)
    monkeypatch.setattr(rc, "reconcile_unmerged_story", flaky)
    out = rc.reconcile_all(jira, gh, _settings(closed_scans=1))
    assert {(r["story"], r["action"]) for r in out} == {("SBX-95", "error"), (STORY, "reset")}


def test_the_dry_run_script_writes_nothing(world, monkeypatch, capsys):
    from scripts import impact_reconcile as script
    fake, jira, gh = world
    gh.close(1)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: jira)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: gh)
    before = (list(fake.issues[STORY]["labels"]), dict(fake.comments))
    assert script.main(["--dry-run"]) == 0
    assert (fake.issues[STORY]["labels"], fake.comments) == before
    assert f"{STORY}: pending-close" in capsys.readouterr().out


def test_the_settings_and_board_column_are_shipped():
    import yaml
    from core.board_status import load_status_workflow
    from core.impact_settings import DEFAULTS
    cfg = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
    shipped = cfg["agents"]["agent0_impact"]["reconcile"]["story_reset_labels"]
    assert shipped == DEFAULTS["reconcile"]["story_reset_labels"]
    assert "ai-processed" not in shipped and "human-approved" in shipped
    assert load_status_workflow()["on_close_unmerged"] == "To Do"
