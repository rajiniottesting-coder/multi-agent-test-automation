"""Agent 0's full scan honours dry_run: no report, no review, no hand-over
written (see tests/unit/test_dry_run.py for why)."""
import copy

import agents.agent0_impact as a0
from tests.sandbox.fake_jira import FakeRepoHost
from tests.sandbox.seed import repo_files
from tests.unit.test_agent0 import (  # noqa: F401
    TITLE_12,
    FakeModel,
    _only_in,
    _settings,
    world,
)


def _state(fake):
    return copy.deepcopy((fake.issues, fake.comments, fake.links))


# ─────────────────────────────────────────────────────────────
def test_scan_dry_run_neither_publishes_nor_hands_over(world, capsys):  # noqa: F811
    fake, jira, root, g = world
    s = _settings(enabled=True, shadow_mode=False,
                  context_update={"enabled": False, "branch_prefix": "context-update/"})
    host = FakeRepoHost(repo_files(root))
    page, key = _only_in(g, "SBX-12", "SBX-11")
    model = FakeModel([f"{page}:{key}"], must={TITLE_12})

    before = _state(fake)
    out = a0.scan(jira, host, model, s, root, dry_run=True)
    assert [r["action"] for r in out] == ["dry-run"]
    assert _state(fake) == before                                  # no review, labels kept

    assert a0.scan(jira, host, model, s, root)[0]["action"] == "review-created"   # live
    review = jira.get_subtasks("SBX-5")[0]
    fake.issues[review["key"]]["status"] = "Done"
    before = _state(fake)
    out = a0.scan(jira, host, model, s, root, dry_run=True)
    handed = [r for r in out if r.get("action") == "would-hand-over"]
    assert handed and handed[0]["story"] == "SBX-5" and handed[0]["writes"] > 0
    assert _state(fake) == before                                  # nothing handed over
    assert "impact-proposed" in fake.issues["SBX-5"]["labels"]
    assert "[dry run] tracker.link_issues('SBX-5'" in capsys.readouterr().out
