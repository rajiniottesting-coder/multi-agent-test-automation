"""
C3 (Agent 0 design): Agent 1's impact-aware mode.

Validator rules as unit tests; the mode end to end in the sandbox: a
hand-over approves SBX-11 and retires SBX-13 for change story SBX-5, then
Agent 1 runs on SBX-5 with the LLM replaced by a fixed draft.
"""
from unittest.mock import MagicMock, patch

import pytest

from core import impact_trace
from core.impact_handover import handover
from core.schemas import ImpactAwareDraft, TestCase, TestCaseRevision, TestStep
from agents.agent2_coder import compute_description_hash
from tests.sandbox.fake_jira import jira_client_over
from tests.sandbox.seed import build_repo, seed_jira

for _cls in (TestCase, TestCaseRevision, TestStep):
    _cls.__test__ = False


def _tc(title, test_type=None, action="Log in with a wrong password"):
    if test_type is None:                       # the [Type] tag decides, as Agent 1's prompt asks
        test_type = next((t for t in ("Positive", "Negative", "Edge")
                          if title.startswith(f"[{t}]")), "Negative")
    return TestCase(title=title, description="d", priority="High", test_type=test_type,
                    preconditions=[], steps=[TestStep(step_number=1, action=action,
                                                      expected_result="An error is shown")],
                    expected_outcome="ok", test_data=None)


def _draft(revisions=(("SBX-11", "Successful login keeps me signed in"),), new=()):
    return ImpactAwareDraft(
        story_summary="s",
        revisions=[TestCaseRevision(key=k, revised=_tc(t, "Positive", "Log in, tick remember me"),
                                    change_note="session now remembered")
                   for k, t in revisions],
        new_test_cases=[_tc(t) for t in new])


# ─────────────────────────────────────────────────────────────────
# the validator
# ─────────────────────────────────────────────────────────────────
class TestValidateDraft:
    from agents.agent1_impact import validate_draft as _v
    validate = staticmethod(_v)

    def test_a_good_draft(self):
        errors, near = self.validate(_draft(new=["[Edge] Remember me expires after a week"]),
                                     {"SBX-11"}, {"some other scenario"})
        assert errors == [] and near == []

    def test_every_approved_key_exactly_once_and_nothing_else(self):
        d = _draft(revisions=[("SBX-11", "a"), ("SBX-11", "b"), ("SBX-99", "c")])
        errors, _ = self.validate(d, {"SBX-11", "SBX-12"}, set())
        assert any("SBX-12 was not revised" in e for e in errors)
        assert any("SBX-99 is not an approved" in e for e in errors)
        assert any("SBX-11 was revised 2 times" in e for e in errors)

    def test_a_new_case_repeating_a_revision_or_a_scenario_is_rejected(self):
        d = _draft(new=["[Positive] Successful login keeps me signed in",
                        "[Negative] Login fails with an incorrect password"])
        errors, _ = self.validate(d, {"SBX-11"}, {"login fails with an incorrect password"})
        assert any("repeats revised SBX-11" in e for e in errors)
        assert any("repeats an existing scenario" in e for e in errors)

    def test_two_new_cases_with_one_title_are_rejected(self):
        d = _draft(new=["[Edge] Remember me expires", "[Negative] remember me expires"])
        errors, _ = self.validate(d, {"SBX-11"}, set())
        assert any("repeats another new test case" in e for e in errors)

    def test_near_matches_are_flagged_not_rejected(self):
        d = _draft(new=["[Edge] Successful login keeps me signed in on mobile"])
        errors, near = self.validate(d, {"SBX-11"}, set())
        assert errors == [] and near and "SBX-11" in near[0]


# ─────────────────────────────────────────────────────────────────
# end to end in the sandbox
# ─────────────────────────────────────────────────────────────────
@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    fake.add("Story", "Remember-me keeps the session after login", key="SBX-5",
             labels=["impact-proposed"], components=["Login"])
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    handover(jira, "SBX-5", {"SBX-11": "approve", "SBX-13": "retire"})
    return fake, jira


def _run(jira, drafts, dry_run=False):
    import agents.agent1_analyst as a1
    llm = MagicMock()
    llm.invoke_structured.side_effect = list(drafts)
    with patch.object(a1, "get_tracker", return_value=jira), \
         patch.object(a1, "LLMClient", return_value=llm):
        return a1.run("SBX-5", dry_run=dry_run), llm


class TestImpactAwareRun:
    NEW = "[Edge] Remember-me session expires after the configured period"

    def test_revises_in_place_snapshots_and_labels(self, world):
        fake, jira = world
        before = dict(fake.issues["SBX-11"])
        result, llm = _run(jira, [_draft(new=[self.NEW])])
        assert result["mode"] == "impact-aware" and result["revised"] == ["SBX-11"]
        assert result["retired"] == ["SBX-13"]
        # the prompt carried the approved case and the retired one
        prompt = llm.invoke_structured.call_args.kwargs["user_prompt"]
        assert "SBX-11" in prompt and before["description"] in prompt and "SBX-13" in prompt
        # revised in place: same key, same owner, new text
        assert fake.issues["SBX-11"]["summary"] == "[Positive] Successful login keeps me signed in"
        assert jira.get_parent_story_key("SBX-11") == "SBX-1"
        # snapshot holds the old text and both hashes
        snap = impact_trace.latest_snapshot(fake.comments["SBX-11"], "SBX-5")
        assert snap["old_description"] == before["description"]
        assert snap["old_hash"] == compute_description_hash(before["description"])
        assert snap["new_hash"] == compute_description_hash(fake.issues["SBX-11"]["description"])
        # the new case is owned by the change story
        owned = [c["key"] for c in jira.get_linked_test_cases("SBX-5")]
        assert len(owned) == 1 and fake.issues[owned[0]]["summary"] == self.NEW
        # labels: at most one impact- label, ai-ready consumed
        labels = fake.issues["SBX-5"]["labels"]
        assert "ai-processed" in labels and "impact-applied" in labels and "ai-ready" not in labels
        assert len([l for l in labels if l.startswith("impact-")]) == 1
        # the gate comment shows before and after
        gate = [c for c in fake.comments["SBX-5"] if c.startswith("[agent1:impact-draft]")]
        assert len(gate) == 1 and "Before - " + before["summary"] in gate[0]
        assert "Retired" in gate[0] and "SBX-13" in gate[0]

    def test_rerun_after_an_interruption_never_re_revises(self, world):
        fake, jira = world
        _run(jira, [_draft()])                              # no new cases -> guard passes again
        fake.issues["SBX-5"]["labels"] = ["ai-ready"]       # as if interrupted before labels
        first = fake.issues["SBX-11"]["description"]
        snaps = len([c for c in fake.comments["SBX-11"] if c.startswith(impact_trace.SNAPSHOT)])
        result, _ = _run(jira, [_draft(revisions=[("SBX-11", "A different wording")])])
        assert result["skipped_revisions"] == ["SBX-11"] and result["revised"] == []
        assert fake.issues["SBX-11"]["description"] == first
        assert len([c for c in fake.comments["SBX-11"]
                    if c.startswith(impact_trace.SNAPSHOT)]) == snaps

    def test_a_rejected_draft_is_retried_once_with_the_reasons(self, world):
        fake, jira = world
        bad = _draft(revisions=[])                                         # SBX-11 missing
        result, llm = _run(jira, [bad, _draft()])
        assert llm.invoke_structured.call_count == 2
        assert "SBX-11 was not revised" in llm.invoke_structured.call_args.kwargs["user_prompt"]
        assert result["revised"] == ["SBX-11"]

    def test_rejected_twice_writes_nothing(self, world):
        fake, jira = world
        before = dict(fake.issues["SBX-11"]), list(fake.issues["SBX-5"]["labels"])
        bad = _draft(new=["[Negative] Login fails with an incorrect password"])   # duplicate
        with pytest.raises(ValueError, match="rejected twice"):
            _run(jira, [bad, bad])
        assert (dict(fake.issues["SBX-11"]), list(fake.issues["SBX-5"]["labels"])) == before
        assert "SBX-11" not in fake.comments

    def test_dry_run_writes_nothing(self, world):
        fake, jira = world
        before = dict(fake.issues["SBX-11"])
        result, _ = _run(jira, [_draft(new=[self.NEW])], dry_run=True)
        assert result["status"] == "tests_revised_dry_run"
        assert result["test_case_keys"] == [] and result["would_create"] == 1
        assert fake.issues["SBX-11"] == before and "SBX-11" not in fake.comments

    def test_an_ordinary_story_never_enters_impact_mode(self, world, monkeypatch):
        fake, jira = world
        fake.add("Story", "Plain story", key="SBX-8", labels=["ai-ready"])
        import agents.agent1_analyst as a1
        from core.schemas import TestCaseList
        llm = MagicMock()
        llm.invoke_structured.return_value = TestCaseList(story_summary="s", test_cases=[_tc("[Positive] x")])
        with patch.object(a1, "get_tracker", return_value=jira), \
             patch.object(a1, "LLMClient", return_value=llm):
            result = a1.run("SBX-8")
        assert result["status"] == "tests_drafted" and "mode" not in result
        assert llm.invoke_structured.call_args.kwargs["output_schema"] is TestCaseList


def test_lookup_failure_with_agent0_off_falls_back_to_normal_mode():
    from agents.agent1_analyst import _impacted_test_cases
    jira = MagicMock()
    jira.get_impacted_test_cases.side_effect = RuntimeError("no such link type")
    assert _impacted_test_cases(jira, "X-1") == []


def test_lookup_failure_with_agent0_on_is_raised(monkeypatch):
    import core.impact_settings as s
    from agents.agent1_analyst import _impacted_test_cases
    monkeypatch.setattr(s, "impact_settings", lambda raw=None: {"enabled": True})
    jira = MagicMock()
    jira.get_impacted_test_cases.side_effect = RuntimeError("no such link type")
    with pytest.raises(RuntimeError):
        _impacted_test_cases(jira, "X-1")


def test_a_tagged_existing_scenario_title_still_counts_as_existing(world, monkeypatch):
    """Agent 3 review on #130: existing titles and new titles must be
    normalised the same way, or a [Type]-tagged scenario slips past."""
    fake, jira = world
    import config.paths as paths
    path = paths.FEATURES_DIR / "sandbox_login.feature"
    path.write_text(path.read_text() + "\n  Scenario: [Negative] Session expires on idle\n"
                                       "    Then I should be logged in\n")
    dup = _draft(new=["[Edge] Session expires on idle"])
    with pytest.raises(ValueError, match="repeats an existing scenario"):
        _run(jira, [dup, dup])
