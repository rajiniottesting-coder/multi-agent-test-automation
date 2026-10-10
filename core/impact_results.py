"""One-line run result on each owning story (Agent 0 design, stage 9).

After Agent 4 runs a change story's pull request, Agent 5 reports on the
change story as always. When that story revised test cases other stories
own, each owner also gets ONE `[agent0:trace] result` line naming its
revised tests and whether they passed - the owner's only view of the run.

For an ordinary story (no Impacts links) this does nothing at all.
"""
from __future__ import annotations

import logging
from pathlib import Path

from core import impact_trace

logger = logging.getLogger(__name__)


def _fallback_name(title: str) -> str:
    """pytest-bdd's naming rule, for an environment without pytest-bdd.
    Pinned against the real make_python_name by a unit test."""
    import re
    # pytest-bdd's rule as pinned in requirements.txt (pytest-bdd==7.3.0):
    # spaces -> "_", drop every other non-word character, drop a leading
    # number, lowercase (pytest_bdd.scenario.make_python_name). An upgrade that
    # changes the rule fails test_the_fallback_name_matches_pytest_bdd, and a
    # rename fails its import - loudly, in CI, either way.
    name = re.sub(r"\W", "", title.replace(" ", "_"))
    return re.sub(r"^\d+_*", "", name).lower()


def _test_name(title: str) -> str:
    """The pytest function pytest-bdd generates for a scenario title."""
    try:
        from pytest_bdd.scenario import make_python_name
        return "test_" + make_python_name(title)
    except ImportError:                                        # pragma: no cover
        return "test_" + _fallback_name(title)


def outcomes_by_key(results: list, index, keys: list) -> dict:
    """{test case key: passed | failed | error | skipped | not run}.

    A scenario outline yields several results (one per example row): it
    passed only if all of them passed.
    """
    out: dict = {}
    for key in keys:
        entry = index.by_key.get(key)
        if entry is None:
            out[key] = "not run"
            continue
        # features/X.feature runs from tests/step_defs/test_X.py: the pairing
        # the generation gate enforces (validate_filename_consistency) and the
        # impact graph relies on.
        module = "test_" + entry.file.rsplit(".", 1)[0]
        name = _test_name(entry.title)
        mine = [r for r in results
                if r.classname.rsplit(".", 1)[-1] == module
                and (r.name == name or r.name.startswith(name + "["))]
        if not mine:
            out[key] = "not run"
        elif all(r.status == "passed" for r in mine):
            out[key] = "passed"
        else:
            out[key] = next(r.status for r in mine if r.status != "passed")
    return out


def post_owner_results(tracker, story_key: str, pr_url: str | None, results: list,
                       features_dir: Path) -> dict:
    """Post the result line on each owner of the story's revised test cases.

    Returns {owner: outcomes} for what was posted (empty for an ordinary story).
    Never posts the same result twice for the same pull request.
    """
    from agents.agent2_coder import build_marker_index

    revised = [c["key"] for c in tracker.get_impacted_test_cases(story_key)]
    if not revised:
        return {}
    index = build_marker_index(Path(features_dir))
    outcomes = outcomes_by_key(results, index, revised)
    owners: dict = {}
    for key in revised:
        owner = tracker.get_parent_story_key(key)
        if owner and owner != story_key:
            owners.setdefault(owner, {})[key] = outcomes[key]
    ref = pr_url or "no-pr"
    posted = {}
    for owner, mine in sorted(owners.items()):
        if impact_trace.already_posted(tracker.get_comments(owner), "result", story_key, ref):
            continue
        tracker.add_comment(owner, impact_trace.result(story_key, ref, mine))
        posted[owner] = mine
    if posted:
        logger.info("Result lines posted on owners %s", sorted(posted))
    return posted


# ── stage 10: the prediction against the run ──────────────────

def changed_existing_keys(host, pr_number, branch_index) -> set:
    """Test case keys whose scenario the pull request changed or removed.

    "Changed" is what the backtest also counts (design section 10): a marker
    whose hash differs from main's, or a marked scenario that is gone. Main's
    side comes from the repository host; the branch's side is the checkout
    Agent 5 runs on (branch_index)."""
    from agents.agent2_coder import parse_feature_file

    out: set = set()
    for f in host.get_pr_changed_files(int(pr_number)) or []:
        path = (f.get("filename") or "").replace("\\", "/")
        if not (path.startswith("features/") and path.endswith(".feature")) \
                or f.get("status") == "added":
            continue
        try:
            main_text = host.get_file_content(path, "main")
        except Exception as e:                                 # noqa: BLE001
            logger.debug("%s not readable on main (%s): no existing tests there", path, e)
            continue
        _header, blocks = parse_feature_file(main_text)
        for block in blocks:
            if not block.jira_key:
                continue
            now = branch_index.by_key.get(block.jira_key)
            if now is None or now.hash != block.jira_hash:
                out.add(block.jira_key)
    return out


def record_prediction_outcome(tracker, host, story_key: str, pr_number, pr_url: str | None,
                              results: list, features_dir: Path, settings: dict | None = None):
    """Stage 10, run by Agent 5 after the change story's pull request ran.

    Predicted: the tests in Agent 0's last report for the story (shadow or
    live). Actual: existing tests the pull request changed, plus existing
    tests that failed on its branch - the second half the design takes from
    the run (Agent 5's outside failures are among them). The story's own
    test cases are not "existing tests" and are left out of both.

    Does nothing when Agent 0 is off, when no report exists, or without a
    pull request number."""
    from agents import agent0_impact as a0
    from agents.agent2_coder import build_marker_index
    from core.impact_settings import impact_settings

    settings = settings or impact_settings()
    if not settings["enabled"] or not pr_number:
        return None
    report, _review = a0._previous_report(tracker, story_key, settings)
    if not report:
        return None
    own = {c["key"] for c in tracker.get_linked_test_cases(story_key)}
    index = build_marker_index(Path(features_dir))
    status = outcomes_by_key(results, index, sorted(index.by_key))
    failed = sorted(k for k, v in status.items() if v in ("failed", "error") and k not in own)
    changed = sorted(changed_existing_keys(host, pr_number, index) - own)
    return a0.record_outcome(tracker, story_key, settings, changed, failed,
                             pr_url or f"#{pr_number}")
