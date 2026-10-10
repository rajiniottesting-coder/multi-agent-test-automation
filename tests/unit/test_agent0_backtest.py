"""
D2 (Agent 0 design): the backtest harness, on a throwaway git repository.

Three merges: one attributed to a story that revised AB-1 (hash changed),
one adding a scenario (no revision), one revising AB-2 with no story in the
message. The analyser is injected, so the harness itself is what is tested.
"""
import subprocess

import pytest

from agents.agent2_coder import format_marker
from scripts.agent0_backtest import find_events, run_backtest, score, sweep


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@x", "HOME": str(root), "PATH": "/usr/bin:/bin"})


def _feature(*scenarios):
    return "Feature: f\n" + "".join(f"\n  {format_marker(k, d)}\n  Scenario: {t}\n    Then x\n"
                                     for k, d, t in scenarios)


def _commit(root, text, message):
    (root / "features").mkdir(exist_ok=True)
    (root / "features" / "f.feature").write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, _feature(("AB-1", "v1", "one"), ("AB-2", "v1", "two")), "initial")
    _commit(root, _feature(("AB-1", "v2", "one"), ("AB-2", "v1", "two")),
            "Merge pull request #5 from org/auto/AB-9-change-one")
    _commit(root, _feature(("AB-1", "v2", "one"), ("AB-2", "v1", "two"), ("AB-3", "v1", "three")),
            "Merge pull request #6 from org/auto/AB-10-add-three")
    _commit(root, _feature(("AB-1", "v2", "one"), ("AB-2", "v2", "two"), ("AB-3", "v1", "three")),
            "hand edit")
    return root


def test_events_are_hash_changes_attributed_to_a_story(repo):
    events, unattributed = find_events(repo)
    assert [(e.story, e.revised) for e in events] == [("AB-9", {"AB-1"})]
    assert unattributed == 1                        # the hand edit of AB-2


def test_replay_scores_the_prediction_at_the_parent_commit(repo):
    seen = []

    def analyse(story, checkout):
        seen.append((story, (checkout / "features" / "f.feature").read_text()))
        return [{"key": "AB-1", "score": 0.9, "tier": "must-update"},
                {"key": "AB-2", "score": 0.4, "tier": "review"},
                {"key": "AB-3", "score": 0.1, "tier": "unaffected"}]

    result = run_backtest(repo, analyse)
    assert seen[0][0] == "AB-9" and "(hash: " in seen[0][1]
    assert format_marker("AB-1", "v1") in seen[0][1]           # the state BEFORE the merge
    assert result["recall"] == 1.0 and result["precision"] == 0.5
    assert result["meets_target"] is True
    sweep_at = {r["threshold"]: r for r in result["threshold_sweep"]}
    assert sweep_at[0.5] == {"threshold": 0.5, "recall": 1.0, "precision": 1.0}
    assert subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True,
                          text=True).stdout.count("\n") == 1   # worktrees cleaned up


def test_score_and_sweep_edges():
    assert score(set(), set()) == (None, None)
    assert score({"A"}, {"A", "B"}) == (0.5, 1.0)
    assert sweep([], (0.5,)) == [{"threshold": 0.5, "recall": None, "precision": None}]
