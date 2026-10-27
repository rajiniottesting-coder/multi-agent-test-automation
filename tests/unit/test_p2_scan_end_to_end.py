"""P2 end to end: one Agent 2 scan through the REAL run(), in the sandbox.

Three approved stories; `max_stories_per_run: 2`. The first is refused by the
final gate after spending model calls, the second opens its PR, the third is
over the budget. Checks F-3, F-4 and F-1 together, where they meet:

  * the refused story's cost is on ITS ledger, marked failed; the second
    story's comment carries only its own calls (M1);
  * the third is deferred - labels unchanged, nothing posted - and the job
    fails only for the refused story (M2);
  * the PR is opened only after the last in-flight check (G1).

Only the model-facing functions are replaced; each "model call" adds usage to
the real counter, as a real call does. Generic names only.
"""
import re
import sys
from unittest.mock import patch

import pytest

from core import llm_client
from core.schemas import CodePlan, FilePlan
from core.usage_ledger import USAGE_MARKER
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira

STORIES = {"SBX-101": ("A shopper writes a review", "[Positive] Write a review"),
           "SBX-102": ("A shopper rates a product", "[Positive] Rate a product"),
           "SBX-103": ("A shopper shares a product", "[Positive] Share a product")}


@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    for n, (story, (summary, case)) in enumerate(STORIES.items()):
        fake.add("Story", summary, key=story, labels=["ai-processed", "human-approved"])
        tc = f"SBX-{201 + n}"
        fake.add("Test Case", case, key=tc, description=f"steps of {tc}")
        fake.link("Relates", tc, story)
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import agents.agent2_coder as a2
    import config.paths as paths
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    llm_client.reset_usage()
    yield fake, jira, FakeRepoHost(repo_files(root))
    llm_client.reset_usage()


def _usage(fake, story):
    out = []
    for c in fake.comments.get(story, []):
        m = re.search(r'agent="([^"]+)" calls=(\d+)', c)
        if c.startswith(USAGE_MARKER) and m:
            out.append((m.group(1), int(m.group(2))))
    return out


def test_one_scan_three_stories(world, monkeypatch):
    import agents.agent2_coder as a2
    fake, jira, gh = world
    order = list(STORIES)

    def stories_for(selection, max_results=5, sprint_override=None):
        if "ai-regenerate" in (selection.get("required_labels") or []) or \
                "ai-update" in (selection.get("required_labels") or []):
            return []
        return [{"key": k} for k in order]

    def plan_for(llm, cases, *a, **k):
        llm_client._tracker.add(1000, 200)                    # the plan call
        story = next(s for s, (_sm, c) in STORIES.items() if c == cases[0]["summary"])
        stem = STORIES[story][1].split("] ")[1].lower().replace(" ", "_")
        return CodePlan(feature_name=stem.replace("_", "-"), branch_name=f"auto/{story}-x",
                        pr_title=stem, pr_body="b", notes="", files_to_create=[
                            FilePlan(file_path=f"features/{stem}.feature", file_type="feature",
                                     purpose="f")])

    def gen(llm, file_plan, plan, cases, *a, **k):
        llm_client._tracker.add(2000, 400)                    # one call per file
        title = cases[0]["summary"].split("] ")[1]
        return f"Feature: X\n\n  Scenario: {title}\n    Given I am home\n"

    def validate(files, story_id, cases=None):
        if story_id == "SBX-101":
            raise a2.GateFailure("refused", errors=["a rule broken after every repair"])

    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(jira, "find_stories_to_process", side_effect=stories_for), \
         patch.object(a2, "get_repo_host", return_value=gh), patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", side_effect=plan_for), \
         patch.object(a2, "generate_file_content", side_effect=gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_validate_generated_files", side_effect=validate):
        with pytest.raises(SystemExit) as exit_:
            a2.main()

    assert exit_.value.code == 1, "the refused story fails the job; the deferred one does not"
    # M1: each story's own cost
    assert _usage(fake, "SBX-101") == [("Agent 2 (Coder, initial) (failed)", 2)]
    assert _usage(fake, "SBX-102") == [("Agent 2 (Coder, initial)", 2)]
    assert any(c.startswith("[agent2:blocked]") for c in fake.comments["SBX-101"])
    # the second story's PR, opened after the last in-flight check
    assert [p["head_ref"] for p in gh.prs] == ["auto/SBX-102-x"]
    assert "ai-coded" in fake.issues["SBX-102"]["labels"]
    # M2: the third waits for the next scan, untouched
    assert fake.comments.get("SBX-103", []) == []
    assert fake.issues["SBX-103"]["labels"] == ["ai-processed", "human-approved"]
    assert llm_client.get_usage_summary()["llm_calls"] == 0
