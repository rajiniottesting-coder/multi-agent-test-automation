"""The tracker watchers (core/tracker_watch.py): a story edited after its test
cases were drafted or its tests coded, a test case edited or deleted after
coding, a cancelled or deleted story whose test cases are retired, and an agent
pull request out of sync with main. Each finding is said once.
(Backlog items R2, R3, R4, X5.)

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from agents.agent2_coder import compute_description_hash
from core import tracker_watch as tw
from tests.sandbox.fake_jira import FakeJira, jira_client_over

NOW = _dt.datetime(2026, 11, 14, 12, 0, tzinfo=_dt.timezone.utc)


def _label(at, before, after, by="pat"):
    return {"created": at, "author": {"accountId": by, "displayName": by.title()},
            "items": [{"field": "labels", "fromString": before, "toString": after}]}


def _edit(at, field="description", by="pat"):
    return {"created": at, "author": {"accountId": by, "displayName": by.title()},
            "items": [{"field": field, "fromString": "old", "toString": "new"}]}



def _plain(text: str) -> str:
    """A comment as a person reads it. The sandbox runs the REAL JiraClient,
    whose render_markdown (integrations/jira_markup.py) turns `x` into Jira's
    {{x}} and escapes - and _ inside it; the fake Jira only stores what it is
    given. Drop those marks to read the text."""
    return text.replace("{{", "").replace("}}", "").replace("\\", "").replace("`", "")

@pytest.fixture
def world(monkeypatch, tmp_path):
    fake = FakeJira()
    fake.add("Story", "Drafted story", key="SBX-1", labels=["ai-processed"])
    fake.add("Story", "Coded story", key="SBX-2", labels=["ai-processed", "ai-coded"],
             status="Done")
    fake.add("Test Case", "Add an item", key="SBX-5", description="Steps: add an item")
    fake.add("Test Case", "Remove an item", key="SBX-6", description="Steps: remove")
    fake.link("Relates", "SBX-5", "SBX-2")
    fake.link("Relates", "SBX-6", "SBX-2")
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    h5 = compute_description_hash("Steps: add an item")
    h6 = compute_description_hash("Steps: remove")
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n"
        f"  # JIRA: SBX-5 (hash: {h5}) owner: SBX-2\n  Scenario: Add an item\n    Given x\n\n"
        f"  # JIRA: SBX-6 (hash: {h6}) owner: SBX-2\n  Scenario: Remove an item\n    Given x\n")
    return fake, jira, features


def _run(world, **kw):
    fake, jira, features = world
    return tw.run(jira, kw.pop("host", None), features, now=NOW, **kw)


# ── R2 ──────────────────────────────────────────────────────

def test_an_edit_after_drafting_suggests_checking_the_test_cases(world):
    fake, *_ = world
    fake.histories["SBX-1"] = [_label("2026-11-10T05:00:00.000+0000", "", "ai-processed"),
                               _edit("2026-11-12T05:00:00.000+0000")]
    out = _run(world)
    assert out["story_edited"] == ["SBX-1"]
    (body,) = map(_plain, fake.comments["SBX-1"])
    assert body.startswith("[watch:story-edited]") and "after its test cases were drafted" in body
    assert "add ai-ready" in body and "Nothing was changed automatically" in body
    assert _run(world)["story_edited"] == [], "said once"
    fake.histories["SBX-1"].append(_edit("2026-11-13T05:00:00.000+0000", field="summary"))
    assert _run(world)["story_edited"] == ["SBX-1"], "a newer edit is news again"


def test_an_edit_after_coding_suggests_the_impact_check(world):
    fake, *_ = world
    fake.histories["SBX-2"] = [_label("2026-11-09T05:00:00.000+0000", "", "ai-processed"),
                               _label("2026-11-10T05:00:00.000+0000", "ai-processed",
                                      "ai-processed ai-coded"),
                               _edit("2026-11-13T05:00:00.000+0000")]
    _run(world)
    assert "after its tests were coded. Add impact-check" in _plain(fake.comments["SBX-2"][0])


def test_edits_before_drafting_or_long_ago_are_quiet(world):
    fake, *_ = world
    fake.histories["SBX-1"] = [_edit("2026-11-09T05:00:00.000+0000"),
                               _label("2026-11-10T05:00:00.000+0000", "", "ai-processed")]
    fake.histories["SBX-2"] = [_label("2026-10-01T05:00:00.000+0000", "", "ai-processed"),
                               _edit("2026-10-02T05:00:00.000+0000")]
    assert _run(world)["story_edited"] == []


# ── R3 ──────────────────────────────────────────────────────

def test_an_edited_test_case_asks_for_an_update_once(world):
    fake, *_ = world
    fake.issues["SBX-5"]["description"] = "Steps: add TWO items"
    out = _run(world)
    assert out["test_case_changed"] == ["SBX-2"]
    body = [_plain(c) for c in fake.comments["SBX-2"] if c.startswith("[watch:test-case-changed]")]
    assert len(body) == 1 and "SBX-5" in body[0] and "Add ai-update" in body[0]
    assert _run(world)["test_case_changed"] == []


def test_a_deleted_test_case_flags_its_scenario(world):
    fake, *_ = world
    del fake.issues["SBX-6"]
    out = _run(world)
    assert out["test_case_deleted"] == ["SBX-2"]
    assert any("SBX-6 no longer exists" in _plain(c) and "Remove an item" in c
               for c in fake.comments["SBX-2"])


# ── R4 ──────────────────────────────────────────────────────

def test_a_cancelled_story_retires_its_test_cases_and_flags_defects(world):
    fake, *_ = world
    fake.issues["SBX-2"]["status"] = "Won't Do"
    bug = fake.add("Bug", "Cart breaks", labels=["ai-defect"])
    fake.link("Blocks", bug, "SBX-5")
    out = _run(world)
    assert sorted(out["retired"]) == ["SBX-5", "SBX-6"]
    assert "ai-retired" in fake.issues["SBX-5"]["labels"]
    assert "remove it in a pull request" in _plain(fake.comments["SBX-5"][-1])
    assert out["defects_flagged"] == [bug]
    again = _run(world)
    assert again["retired"] == [] and again["defects_flagged"] == []


def test_a_deleted_story_retires_too_and_a_done_story_does_not(world):
    fake, *_ = world
    assert _run(world)["retired"] == [], "Done is not cancelled"
    del fake.issues["SBX-2"]                  # the tracker drops its links too
    fake.links = {k: v for k, v in fake.links.items() if "SBX-2" not in v[1:]}
    assert sorted(_run(world)["retired"]) == ["SBX-5", "SBX-6"]


# ── X5 ──────────────────────────────────────────────────────

class Host:
    def __init__(self, states):
        self.states, self.comments = states, {}

    def list_open_prs(self, prefix=""):
        return [{"number": n, "head_sha": f"sha{n}"} for n in self.states]

    def pr_sync_state(self, n):
        return self.states[n]

    def get_pr_comments(self, n):
        return self.comments.get(n, [])

    def post_pr_comment(self, n, body):
        self.comments.setdefault(n, []).append(body)


def test_agent_prs_in_conflict_or_behind_get_one_comment(world):
    host = Host({1: {"base": "main", "conflict": True, "behind_by": 3,
                     "overlap": ["features/a.feature"], "conflict_files": ["features/a.feature"]},
                 2: {"base": "main", "conflict": False, "behind_by": 5,
                     "overlap": ["pages/p.py"]},
                 3: {"base": "main", "conflict": False, "behind_by": 9, "overlap": []}})
    out = _run(world, host=host)
    assert out["prs_conflict"] == [1] and out["prs_behind"] == [2]
    assert "merge conflicts" in host.comments[1][0] and "`ai-regenerate`" in host.comments[1][0]
    assert "changing files it also changes: pages/p.py" in host.comments[2][0]
    assert "Nothing was pushed" in host.comments[2][0] and 3 not in host.comments
    _run(world, host=host)
    assert len(host.comments[1]) == 1 and len(host.comments[2]) == 1


def test_dry_run_writes_nothing(world):
    fake, *_ = world
    fake.issues["SBX-5"]["description"] = "changed"
    out = _run(world, dry_run=True)
    assert out["test_case_changed"] == ["SBX-2"] and not fake.comments.get("SBX-2")


def test_a_refused_write_fails_the_step_and_a_read_only_warns(world, monkeypatch):
    from scripts import watch_tracker as wt
    fake, jira, features = world
    fake.issues["SBX-5"]["description"] = "changed"

    def refuse(*a, **k):
        raise RuntimeError("no permission")
    monkeypatch.setattr(jira, "add_comment", refuse)
    out = _run(world)
    assert out["write_errors"] and out["write_errors"] == out["errors"]
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: jira)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: None)
    assert wt.main(["--features-dir", str(features)]) == 1
    monkeypatch.setattr(jira, "get_all_test_cases", refuse)
    monkeypatch.setattr(jira, "find_stories_to_process", refuse)
    fake.issues["SBX-5"]["description"] = "Steps: add an item"
    assert wt.main(["--features-dir", str(features)]) == 0, "a step that cannot read only warns"


def test_a_done_story_labelled_cancelled_retires_too(world):
    """14 Nov 2026: this project's workflow has no Won't Do status."""
    fake, *_ = world
    fake.issues["SBX-2"]["labels"].append("cancelled")
    assert sorted(_run(world)["retired"]) == ["SBX-5", "SBX-6"]


def test_a_pr_whose_mergeability_is_not_known_yet_waits_for_the_next_run(world):
    """14 Nov 2026: GitHub answered None for a conflicting PR right after
    main moved, and it was called 'behind'."""
    host = Host({7: {"base": "main", "unknown": True, "conflict": False, "behind_by": 2,
                     "overlap": ["a"]}})
    out = _run(world, host=host)
    assert out["prs_conflict"] == [] and out["prs_behind"] == [] and not host.comments


def test_github_asks_again_while_mergeability_is_computed(monkeypatch):
    from types import SimpleNamespace
    from integrations import github_client as gc
    reads = iter([None, None, False])
    pr = lambda: SimpleNamespace(mergeable=next(reads), mergeable_state="dirty",
                                 base=SimpleNamespace(ref="main"),
                                 head=SimpleNamespace(sha="abc"),
                                 get_files=lambda: [SimpleNamespace(filename="f")])
    client = gc.GitHubClient.__new__(gc.GitHubClient)
    monkeypatch.setattr(gc.GitHubClient, "get_pull_request", lambda self, n: pr())
    monkeypatch.setattr(gc.GitHubClient, "repo", property(lambda self: SimpleNamespace(
        compare=lambda a, b: SimpleNamespace(ahead_by=1, files=[SimpleNamespace(filename="f")]))))
    monkeypatch.setattr("time.sleep", lambda s: None)
    state = client.pr_sync_state(3)
    assert state["conflict"] is True and state["overlap"] == ["f"] and not state.get("unknown")


def test_the_edit_time_is_said_in_utc(world):
    """14 Nov 2026: an edit at 11:38 +0530 was said as '11:38 UTC'."""
    fake, *_ = world
    fake.histories["SBX-1"] = [_label("2026-11-12T10:00:00.000+0530", "", "ai-processed"),
                               _edit("2026-11-13T11:38:00.000+0530")]
    _run(world)
    assert "edited on 2026-11-13 06:08 UTC" in fake.comments["SBX-1"][0]
