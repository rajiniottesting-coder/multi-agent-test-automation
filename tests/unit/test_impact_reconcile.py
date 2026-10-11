"""
C7 (Agent 0 design): reconcile - finish or undo a change story.

End to end in the sandbox: hand-over -> Agent 1 impact-aware -> Agent 2 opens
the pull request -> the reconcile scan, through every outcome. Includes the
label-lifecycle walk of design section 9.
"""
from datetime import datetime, timedelta, timezone

import pytest

from core import impact_trace
from core.impact_reconcile import reconcile_all, reconcile_story
from tests.unit.test_agent2_impact import _hand_over_and_draft, _run_agent2, world  # noqa: F401

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _impact_labels(fake, story="SBX-5"):
    return sorted(l for l in fake.issues[story]["labels"] if l.startswith("impact-"))


@pytest.fixture
def opened(world):                                      # noqa: F811
    """A change story with its pull request open: SBX-11 revised, SBX-12 retired."""
    fake, jira, root = world
    original = dict(fake.issues["SBX-11"])
    _hand_over_and_draft(jira, {"SBX-11": "approve", "SBX-12": "retire"}, new=())
    _result, gh, *_ = _run_agent2(jira, root)
    assert gh.prs and fake.issues["SBX-11"]["description"] != original["description"]
    return fake, jira, gh, original


def _scan(jira, gh, now=NOW):
    return reconcile_story(jira, gh, "SBX-5", now=now)


class TestReconcile:
    def test_open_pr_is_left_alone(self, opened):
        fake, jira, gh, _o = opened
        assert _scan(jira, gh)["action"] == "open"
        assert _impact_labels(fake) == ["impact-applied"]

    def test_merged_posts_the_trace_once_and_clears_the_label(self, opened):
        fake, jira, gh, _o = opened
        gh.merge(1)
        assert _scan(jira, gh)["action"] == "merged"
        # A re-scan finds the same merged PR: "merged" again, nothing new posted
        # (Agent 3 suggested it fell through to the no-PR branch; it does not).
        before = {k: list(v) for k, v in fake.comments.items()}
        assert _scan(jira, gh)["action"] == "merged"
        assert fake.comments == before
        # ...and the scheduled scan never selects it again: its label is gone.
        assert reconcile_all(jira, gh, now=NOW) == []
        merged = [c for c in fake.comments["SBX-1"]
                  if (impact_trace.parse(c) or {}).get("kind") == "merged"]
        assert len(merged) == 1 and "SBX-11" in merged[0]
        assert _impact_labels(fake) == []
        assert "ai-retired" in fake.issues["SBX-12"]["labels"]          # the retire stands

    def test_closed_is_reverted_only_on_the_second_scan(self, opened):
        fake, jira, gh, original = opened
        gh.close(1)
        assert _scan(jira, gh)["action"] == "pending-close"
        assert fake.issues["SBX-11"]["description"] != original["description"]   # not yet
        r = _scan(jira, gh)
        assert r["action"] == "reverted" and r["restored"] == ["SBX-11"]
        assert fake.issues["SBX-11"]["description"] == original["description"]
        assert fake.issues["SBX-11"]["summary"] == original["summary"]
        assert "ai-retired" not in fake.issues["SBX-12"]["labels"]
        assert r["unretired"] == ["SBX-12"]
        assert jira.get_impacted_test_cases("SBX-5", include_retired=True) == []
        assert not any(t == "Impacts" and i == "SBX-5" for t, i, _ in fake.links.values())
        restored = [c for c in fake.comments["SBX-1"]
                    if (impact_trace.parse(c) or {}).get("kind") == "restored"]
        assert len(restored) == 1 and "SBX-11" in restored[0]
        assert "Retirement withdrawn - these stay active: SBX-12" in restored[0]
        assert _impact_labels(fake) == ["impact-reverted"]

    def test_the_sweepers_close_and_reopen_is_absorbed(self, opened):
        fake, jira, gh, original = opened
        gh.close(1)
        assert _scan(jira, gh)["action"] == "pending-close"
        gh.reopen(1)                                   # the sweeper restarts it...
        assert _scan(jira, gh)["action"] == "open"
        gh.close(1)                                    # ...and a later close is a NEW close
        assert _scan(jira, gh)["action"] == "pending-close"
        assert fake.issues["SBX-11"]["description"] != original["description"]

    def test_a_case_edited_since_is_left_for_a_person(self, opened):
        fake, jira, gh, original = opened
        fake.issues["SBX-11"]["description"] = "a person improved this after the revision"
        gh.close(1)
        _scan(jira, gh)
        r = _scan(jira, gh)
        assert r["restored"] == [] and r["left_for_a_person"] == ["SBX-11"]
        assert fake.issues["SBX-11"]["description"] == "a person improved this after the revision"
        restored = next(c for c in fake.comments["SBX-1"]
                        if (impact_trace.parse(c) or {}).get("kind") == "restored")
        assert "NOT restored" in restored and "SBX-11" in restored

    def test_no_pr_asks_a_person_once_after_the_window(self, world):   # noqa: F811
        fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
        from tests.sandbox.fake_jira import FakeRepoHost
        gh = FakeRepoHost({})
        assert _scan(jira, gh)["action"] == "no-pr-noted"
        assert _scan(jira, gh, NOW + timedelta(days=3))["action"] == "waiting-for-pr"
        assert _scan(jira, gh, NOW + timedelta(days=15))["action"] == "asked-a-person"
        assert _scan(jira, gh, NOW + timedelta(days=16))["action"] == "waiting-for-pr"
        asks = [c for c in fake.comments["SBX-5"] if "ask-a-person" in c]
        assert len(asks) == 1

    def test_reconcile_all_finds_applied_stories(self, opened):
        fake, jira, gh, _o = opened
        gh.merge(1)
        results = reconcile_all(jira, gh, now=NOW)
        assert [(r["story"], r["action"]) for r in results] == [("SBX-5", "merged")]


def test_label_lifecycle_never_two_impact_labels(world):                  # noqa: F811
    """Design section 9: walk one story through every row."""
    fake, jira, root = world
    seen = []

    def snap():
        labels = _impact_labels(fake)
        assert len(labels) <= 1, labels
        seen.append(labels)

    fake.issues["SBX-5"]["labels"] = ["impact-check"]
    snap()                                                     # marked for analysis
    jira.remove_label("SBX-5", "impact-check")
    jira.add_label("SBX-5", "impact-proposed")
    snap()                                                     # report published
    _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())  # hand-over + Agent 1
    snap()                                                     # impact-applied
    _r, gh, *_ = _run_agent2(jira, root)
    gh.close(1)
    reconcile_story(jira, gh, "SBX-5", now=NOW)
    snap()
    reconcile_story(jira, gh, "SBX-5", now=NOW)
    snap()                                                     # impact-reverted
    assert seen == [["impact-check"], ["impact-proposed"], ["impact-applied"],
                    ["impact-applied"], ["impact-reverted"]]


def test_the_cli_reconciles_a_manual_hand_over_while_agent0_is_off(opened, monkeypatch, capsys):
    """Design C7: phase C runs without Agent 0, so the scheduled reconcile
    must too. The shipped config has Agent 0 off; a person handed over
    (scripts.impact_handover), the pull request was closed - two runs of the
    command restore the test case."""
    import integrations.repo_host as rh
    import integrations.tracker as tr
    from core.impact_settings import impact_settings
    from scripts.impact_reconcile import main
    fake, jira, gh, original = opened
    # Agent 0 OFF regardless of the shipped config: reconcile must not depend on it.
    import core.impact_settings as settings_module
    monkeypatch.setattr(settings_module, "impact_settings",
                        lambda raw=None, _real=impact_settings: _real({"enabled": False}))
    import scripts.impact_reconcile as script
    if hasattr(script, "impact_settings"):
        monkeypatch.setattr(script, "impact_settings",
                            lambda raw=None, _real=impact_settings: _real({"enabled": False}))
    assert settings_module.impact_settings()["enabled"] is False
    monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: jira)
    monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: gh)
    gh.close(1)
    assert main([]) == 0 and "SBX-5: pending-close" in capsys.readouterr().out
    assert main([]) == 0 and "SBX-5: reverted" in capsys.readouterr().out
    assert fake.issues["SBX-11"]["description"] == original["description"]


def test_the_latest_pr_is_chosen_whatever_order_the_host_returns(opened):
    """Agent 3 review of #130: an adapter returning oldest-first must not make
    the revert act on an older PR."""
    fake, jira, gh, _o = opened
    gh.close(1)
    old = dict(gh.prs[0], number=99, updated_at="0000")         # an older, closed PR
    real = gh.find_prs_for_story
    gh.find_prs_for_story = lambda story, branch_prefix="auto/": [old] + real(story)
    assert _scan(jira, gh)["pr"] == 1
