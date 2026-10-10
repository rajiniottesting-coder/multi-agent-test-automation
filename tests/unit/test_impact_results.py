"""
Agent 5's one-line run result on each owning story (Agent 0 design, stage 9).
"""
from core import impact_trace
from tests.unit.test_agent2_impact import world  # noqa: F401
from tests.unit.test_impact_reconcile import opened  # noqa: F401


# ─────────────────────────────────────────────────────────────────
# Agent 5's one-line result on each owner (stage 9)
# ─────────────────────────────────────────────────────────────────
def test_owner_gets_one_result_line_per_pr(opened):
    from core.impact_results import post_owner_results
    from core.schemas import TestResult
    TestResult.__test__ = False
    fake, jira, gh, _o = opened
    import config.paths as paths
    branch = gh.prs[0]["head_ref"]
    # the PR checkout: the branch's feature files
    features = paths.FEATURES_DIR
    (features / "sandbox_login.feature").write_text(gh.branches[branch]["features/sandbox_login.feature"])
    results = [TestResult(name="test_successful_login_keeps_me_signed_in",
                          classname="tests.step_defs.test_sandbox_login", status="failed"),
               TestResult(name="test_unrelated", classname="tests.step_defs.test_login",
                          status="passed")]
    url = gh.prs[0]["url"]
    assert post_owner_results(jira, "SBX-5", url, results, features) == {"SBX-1": {"SBX-11": "failed"}}
    assert post_owner_results(jira, "SBX-5", url, results, features) == {}       # once per PR
    line = [c for c in fake.comments["SBX-1"] if (impact_trace.parse(c) or {}).get("kind") == "result"]
    assert len(line) == 1 and "SBX-11 failed" in line[0] and url in line[0]


def test_ordinary_story_gets_no_owner_lines(world):                       # noqa: F811
    from core.impact_results import post_owner_results
    fake, jira, root = world
    before = {k: list(v) for k, v in fake.comments.items()}
    assert post_owner_results(jira, "SBX-1", "u", [], root / "features") == {}
    assert fake.comments == before


def test_outline_passes_only_if_every_row_passes():
    from core.impact_results import outcomes_by_key
    from core.schemas import TestResult
    from agents.agent2_coder import MarkerEntry, MarkerIndex
    idx = MarkerIndex(by_key={"AB-1": MarkerEntry("AB-1", "cart.feature", "h", "Add items")})
    rows = [TestResult(name="test_add_items[1]", classname="tests.step_defs.test_cart", status="passed"),
            TestResult(name="test_add_items[2]", classname="tests.step_defs.test_cart", status="failed")]
    assert outcomes_by_key(rows, idx, ["AB-1", "AB-2"]) == {"AB-1": "failed", "AB-2": "not run"}
