"""F-1 (G1): the last in-flight check covers every file Agent 2 commits.

Before: the in-flight checks looked at the files the PLAN names (and, for a
change story, the owners' feature and step files). Writers that add files
after the plan - a regeneration's or a change story's orphan cleanup, which
comments methods out of page objects no plan named - were not checked, and
neither was a pull request opened WHILE the story was being generated. The
clash surfaced later as a merge conflict.

Now, right before the branch is created, `_last_in_flight_check` takes a
fresh snapshot of the other open pull requests and checks every file in the
batch, in run() and run_update(). Sandbox: fake Jira, fake repository host;
the model-facing functions return fixed content. Generic names only.
"""
from unittest.mock import patch

import pytest

from agents.agent2_coder import format_marker
from core.in_flight import WAITING_MARKER
from core.schemas import CodePlan, FilePlan, GeneratedFile
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira

STORY = "SBX-80"
FEATURE = "features/gift_card.feature"
STEPS = "tests/step_defs/test_gift_card.py"
SHARED_PAGE = "pages/shared_page.py"          # written by no plan: a cleanup's edit


@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    fake.add("Story", "A shopper redeems a gift card", key=STORY,
             labels=["ai-processed", "human-approved"])
    fake.add("Test Case", "[Positive] Redeem a gift card", key="SBX-81", description="d81")
    fake.link("Relates", "SBX-81", STORY)
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import agents.agent2_coder as a2
    import config.paths as paths
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    files = repo_files(root)
    files[SHARED_PAGE] = "class SharedPage:\n    pass\n"
    return fake, jira, FakeRepoHost(files)


def _other_pr(gh, path, branch="auto/SBX-99-other"):
    gh.create_branch(branch)
    gh.create_or_update_file(path, "changed by another story\n", "c", branch)
    gh.open_pull_request("Other", "b", branch)


def _run(jira, gh, extra_writer=False, during=None, **kw):
    import agents.agent2_coder as a2
    plan = CodePlan(feature_name="gift-card", branch_name=f"auto/{STORY}-gift-card",
                    pr_title="Gift card", pr_body="Body", notes="",
                    files_to_create=[FilePlan(file_path=FEATURE, file_type="feature", purpose="f"),
                                     FilePlan(file_path=STEPS, file_type="step_definitions",
                                              purpose="s")])

    def gen(llm, file_plan, *a, **k):
        if during:
            during()
        if file_plan.file_path == FEATURE:
            return "Feature: Gift card\n\n  Scenario: Redeem a gift card\n    Given I am home\n"
        return "# steps\n"

    real_markers = a2._ensure_jira_markers_on_feature_files

    def markers(files, cases):
        out = real_markers(files, cases)
        if extra_writer:            # a writer after the plan: edits a page no plan named
            out = out + [GeneratedFile(file_path=SHARED_PAGE, content="# cleaned\n",
                                       is_new_file=False, purpose="cleanup")]
        return out

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", return_value=plan), \
         patch.object(a2, "generate_file_content", side_effect=gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_ensure_jira_markers_on_feature_files", side_effect=markers), \
         patch.object(a2, "_validate_generated_files"):
        return a2.run(STORY, **kw)


def _waiting_comments(fake):
    return [c for c in fake.comments.get(STORY, []) if c.startswith(WAITING_MARKER)]


def test_a_file_no_plan_named_that_another_pr_changes_makes_the_story_wait(world):
    fake, jira, gh = world
    _other_pr(gh, SHARED_PAGE)
    result = _run(jira, gh, extra_writer=True)
    assert result["status"] == "waiting_for_open_pr" and result["waiting_for"] == [1]
    assert len(gh.prs) == 1 and f"auto/{STORY}-gift-card" not in gh.branches, "nothing committed"
    note, = _waiting_comments(fake)
    assert SHARED_PAGE in note and "PR #1" in note
    assert "ai-coded" not in fake.issues[STORY]["labels"]


def test_a_pr_opened_while_the_story_was_generated_is_caught(world):
    fake, jira, gh = world
    opened = []

    def open_once():
        if not opened:
            opened.append(1)
            _other_pr(gh, STEPS)                # after the early checks passed
    result = _run(jira, gh, during=open_once)
    assert result["status"] == "waiting_for_open_pr"
    assert STEPS in _waiting_comments(fake)[0]


def test_no_clash_opens_the_pr_as_before(world):
    fake, jira, gh = world
    _other_pr(gh, "pages/unrelated_page.py")
    result = _run(jira, gh, extra_writer=True)
    assert result["status"] == "pr_opened" and len(gh.prs) == 2
    assert not _waiting_comments(fake)


def test_the_storys_own_open_pr_never_counts(world):
    fake, jira, gh = world
    _other_pr(gh, SHARED_PAGE, branch=f"auto/{STORY}-gift-card")      # its previous PR
    result = _run(jira, gh, extra_writer=True, is_regenerate=True)
    assert result["status"] == "pr_opened"


def test_a_dry_run_reports_the_wait_and_writes_nothing(world):
    fake, jira, gh = world
    _other_pr(gh, SHARED_PAGE)
    result = _run(jira, gh, extra_writer=True, dry_run=True)
    assert result["status"] == "waiting_for_open_pr"
    assert not _waiting_comments(fake) and len(gh.prs) == 1


def test_unreadable_open_prs_fail_open(world, monkeypatch):
    fake, jira, gh = world
    _other_pr(gh, SHARED_PAGE)
    calls = {"n": 0}
    real = gh.list_open_prs

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] > 1:                      # the early check reads; the last one fails
            raise RuntimeError("API down")
        return real(*a, **k)
    monkeypatch.setattr(gh, "list_open_prs", flaky)
    result = _run(jira, gh, extra_writer=True)
    assert result["status"] == "pr_opened", "an API hiccup never stops the work"


# ── run_update ───────────────────────────────────────────────────────────

def test_ai_update_waits_for_a_pr_opened_while_it_ran(world, tmp_path):
    import agents.agent2_coder as a2
    fake, jira, gh = world
    marked = ("Feature: Gift card\n\n  " + format_marker("SBX-81", "old", owner=STORY)
              + "\n  Scenario: Redeem a gift card\n    Given I am home\n")
    gh.branches["main"][FEATURE] = marked
    gh.branches["main"][STEPS] = "# steps\n"
    (a2.FEATURES_DIR / "gift_card.feature").write_text(marked, encoding="utf-8")
    fake.issues[STORY]["labels"].append("ai-update")

    def one(llm, path, tc, ctx, existing):
        _other_pr(gh, STEPS)                     # opened while the update was generating
        return ("  " + format_marker(tc["key"], tc.get("description", ""), owner=STORY)
                + "\n  Scenario: Redeem a gift card\n    Given I am home\n")

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), patch.object(a2, "LLMClient"), \
         patch.object(a2, "_generate_single_scenario", side_effect=one), \
         patch.object(a2, "_splice_step_defs_incremental",
                      side_effect=lambda *a, **k: ("# steps\n# more\n", "spliced")), \
         patch.object(a2, "_validate_generated_files"):
        result = a2.run_update(STORY)
    assert result["status"] == "waiting_for_open_pr"
    assert STEPS in _waiting_comments(fake)[0]
    assert len(gh.prs) == 1 and "ai-update" in fake.issues[STORY]["labels"], "retried next scan"
