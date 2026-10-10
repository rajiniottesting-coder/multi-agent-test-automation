"""
C4 and C5 (Agent 0 design): Agent 2's normal run on a change story revises
and retires scenarios in the feature files their OWNERS hold - one branch,
one pull request - and generates only the story's own files.

End to end in the sandbox: hand-over (C2) -> Agent 1 impact-aware (C3) ->
Agent 2 run. The LLM-facing functions return fixed content.
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.agent2_coder import (compute_description_hash, format_marker,
                                 parse_feature_file)
from core.impact_handover import handover
from core.schemas import (CodePlan, FilePlan, ImpactAwareDraft, TestCase,
                          TestCaseRevision, TestStep)
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira

for _cls in (TestCase, TestCaseRevision, TestStep):
    _cls.__test__ = False

OWNER_FILE = "features/sandbox_login.feature"
OWN_FEATURE = "features/remember_me.feature"
OWN_STEPS = "tests/step_defs/test_remember_me.py"


def _tc(title, test_type="Positive"):
    return TestCase(title=title, description="d", priority="High", test_type=test_type,
                    preconditions=[], steps=[TestStep(step_number=1, action="Log in, tick remember me",
                                                      expected_result="Still signed in")],
                    expected_outcome="ok", test_data=None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    fake.add("Story", "Remember-me keeps the session after login", key="SBX-5",
             labels=["impact-proposed"], components=["Login"])
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    import agents.agent2_coder as a2
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    return fake, jira, root


def _hand_over_and_draft(jira, decisions, new=("[Edge] Remember-me expires after a week",)):
    """C2 then C3, so Jira holds the revised text Agent 2 must splice."""
    import agents.agent1_analyst as a1
    handover(jira, "SBX-5", decisions)
    approved = [k for k, d in decisions.items() if d == "approve"]
    draft = ImpactAwareDraft(story_summary="s", revisions=[
        TestCaseRevision(key=k, revised=_tc("Successful login keeps me signed in"),
                         change_note="remembered") for k in approved],
        new_test_cases=[_tc(t, "Edge") for t in new])
    llm = MagicMock()
    llm.invoke_structured.return_value = draft
    with patch.object(a1, "get_tracker", return_value=jira), \
         patch.object(a1, "LLMClient", return_value=llm):
        a1.run("SBX-5")
    jira.add_label("SBX-5", "human-approved")


def _run_agent2(jira, root, *, stale_revision=False, plan_owner_file=True):
    """Agent 2 normal run on SBX-5 with the LLM-facing functions fixed."""
    import agents.agent2_coder as a2
    gh = FakeRepoHost(repo_files(root))
    generated_for = []

    plan_files = [FilePlan(file_path=OWN_FEATURE, file_type="feature", purpose="own"),
                  FilePlan(file_path=OWN_STEPS, file_type="step_definitions", purpose="own")]
    if plan_owner_file:      # the model proposes rewriting an owner's file: must be dropped
        plan_files.append(FilePlan(file_path=OWNER_FILE, file_type="feature", purpose="x",
                                   is_new_file=False))
    plan = CodePlan(feature_name="remember-me", branch_name="auto/SBX-5-remember-me",
                    pr_title="Remember me", pr_body="Body", notes="n", files_to_create=plan_files)

    def gen(llm, file_plan, plan_, cases, *a, **k):
        generated_for.append((file_plan.file_path, [c["key"] for c in cases]))
        if file_plan.file_path == OWN_FEATURE:
            return ("Feature: Remember me\n\n  Background:\n    Given I am on the signup and login page\n\n"
                    "  Scenario: Remember-me expires after a week\n    Then I should be logged in\n")
        return "# step definitions\n"

    def one(llm, path, tc, ctx, existing):
        desc = "STALE" if stale_revision else tc.get("description", "")
        return ("  " + format_marker(tc["key"], desc, tc.get("owner"), tc.get("impacted_by", ()))
                + "\n  Scenario: Successful login keeps me signed in\n"
                "    When I log in as a \"registered\" user\n    Then I should be logged in\n")

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", return_value=plan) as bp, \
         patch.object(a2, "generate_file_content", side_effect=gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_generate_single_scenario", side_effect=one), \
         patch.object(a2, "_splice_step_defs_incremental",
                      side_effect=lambda llm, gh_, path, content, sd, *a, **k:
                      (gh_.get_file_content(sd) + "\n# + steps for revised scenarios\n", "spliced")), \
         patch.object(a2, "_validate_generated_files") as validate:
        result = a2.run("SBX-5")
    return result, gh, bp, generated_for, validate


def _blocks(text):
    _h, blocks = parse_feature_file(text)
    return {b.jira_key or b.text().strip().splitlines()[-1]: b for b in blocks if b.kind == "scenario"}


class TestChangeStoryRun:
    def test_one_pr_revises_retires_and_adds(self, world):
        fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-11": "approve", "SBX-12": "retire"})
        result, gh, bp, generated_for, validate = _run_agent2(jira, root)

        assert result["status"] == "pr_opened"
        assert result["revised"] == ["SBX-11"] and result["retired"] == ["SBX-12"]
        assert len(gh.prs) == 1
        files = gh.branches[gh.prs[0]["head_ref"]]
        before = gh.branches["main"][OWNER_FILE]
        after = files[OWNER_FILE]

        # revised in place, marker carries the new hash, owner and impacted-by
        b = _blocks(after)["SBX-11"]
        assert b.jira_hash == compute_description_hash(fake.issues["SBX-11"]["description"])
        assert (b.owner, b.impacted_by) == ("SBX-1", ("SBX-5",))
        assert "@smoke" in b.text()                                         # tag kept
        # retired: gone, with its tag
        assert "SBX-12" not in _blocks(after) and "Login fails with an incorrect password" not in after
        # every other scenario in the owner's file is byte-for-byte unchanged
        unmarked = "Login fails with an unknown email address"
        assert [b.text() for k, b in _blocks(before).items() if unmarked in b.text()] == \
               [b.text() for k, b in _blocks(after).items() if unmarked in b.text()]
        # the reference file is untouched
        assert files["features/login.feature"] == gh.branches["main"]["features/login.feature"]
        # the story's own file holds only its own new case, owned by the story
        own = _blocks(files[OWN_FEATURE])
        assert len(own) == 1 and next(iter(own.values())).owner == "SBX-5"
        # the owner's step definitions gained step functions, nothing replaced
        assert files["tests/step_defs/test_sandbox_login.py"].startswith(
            gh.branches["main"]["tests/step_defs/test_sandbox_login.py"])
        # the PR says what changed in whose file
        body = gh.prs[0]["body"]
        assert "## Revised (owner)" in body and "SBX-11 - owner SBX-1" in body
        assert "## Retired" in body and "SBX-12" in body
        # the gate validated every file of the batch, owners' included
        checked = {f.file_path for f in validate.call_args.args[0]}
        assert {OWN_FEATURE, OWNER_FILE, "tests/step_defs/test_sandbox_login.py"} <= checked
        assert "ai-coded" in fake.issues["SBX-5"]["labels"]

    def test_owner_files_are_never_generated_whole(self, world):
        _fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-11": "approve"})
        _r, _gh, bp, generated_for, _v = _run_agent2(jira, root)
        assert OWNER_FILE not in [p for p, _ in generated_for]
        # the plan saw the revision; the own feature file did not
        plan_keys = [c["key"] for c in bp.call_args.args[1]]
        assert "SBX-11" in plan_keys
        assert "SBX-11" not in dict(generated_for)[OWN_FEATURE]

    def test_a_stale_revision_fails_the_gate_before_any_commit(self, world):
        _fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-11": "approve"})
        with pytest.raises(ValueError, match="approved SBX-11 is not revised"):
            _run_agent2(jira, root, stale_revision=True)

    def test_an_approved_case_without_a_marker_stops_the_run(self, world):
        fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-13": "approve"}, new=())
        result, gh, *_ = _run_agent2(jira, root)
        assert result["status"] == "impacted_unmarked" and result["unmarked"] == ["SBX-13"]
        assert gh.prs == []

    def test_revisions_only_no_new_cases_generate_no_own_feature(self, world):
        _fake, jira, root = world
        _hand_over_and_draft(jira, {"SBX-11": "approve"}, new=())
        result, gh, _bp, generated_for, _v = _run_agent2(jira, root)
        assert result["status"] == "pr_opened"
        assert OWN_FEATURE not in [p for p, _ in generated_for]
        assert OWN_FEATURE not in gh.branches[gh.prs[0]["head_ref"]]


def test_the_path_policy_rejects_an_owner_file():
    from agents.agent2_coder import validate_paths_against_policy
    from core.app_context import AppContext
    plan = CodePlan(feature_name="x", branch_name="auto/X-1-x", pr_title="t", pr_body="b",
                    notes="n", files_to_create=[FilePlan(file_path=OWNER_FILE, purpose="p")])
    with pytest.raises(ValueError, match="other stories own"):
        validate_paths_against_policy(plan, AppContext.load(), protected_files={OWNER_FILE})
    validate_paths_against_policy(plan, AppContext.load())     # unchanged without the set


def test_an_ordinary_story_has_no_impact_work():
    from agents.agent2_impact import impacted_for_run
    jira = MagicMock()
    jira.get_impacted_test_cases.return_value = []
    assert impacted_for_run(jira, "X-1") == ([], [])
    jira.get_impacted_test_cases.return_value = MagicMock()     # not a list: not trusted
    assert impacted_for_run(jira, "X-1") == ([], [])


def test_orphans_found_while_retiring_are_listed_in_the_pr():
    from agents.agent2_impact import pr_sections
    body = pr_sections({"revised": {}, "retired": {"AB-6": "features/f.feature"},
                        "owners": {}, "orphans": ["step definition `old_step` in `x.py`"]})
    assert "## Orphans after retiring" in body and "`old_step`" in body
    assert "## Orphans" not in pr_sections({"revised": {}, "retired": {"AB-6": "f"},
                                            "owners": {}, "orphans": []})
