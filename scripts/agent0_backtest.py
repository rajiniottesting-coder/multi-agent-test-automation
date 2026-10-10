"""Backtest Agent 0 against the repository's own history (Agent 0 design, D2).

Every `# JIRA:` marker carries a hash of its test case's description, so a
merge that changed a marker's hash recorded a test case revised because of
the story behind that merge. Replaying each such story through Agent 0 at
the commit BEFORE the merge, and comparing its prediction with the markers
that actually changed, gives:

    recall     share of truly revised tests Agent 0 found     (safety)
    precision  share of Agent 0's list that was truly revised (reviewer time)

Target before hand-over is switched on (design section 10):
recall >= 0.9 at precision >= 0.5.

It also sweeps the review threshold over the stored scores, so the
thresholds in agents.agent0_impact can be tuned from the result.

    python -m scripts.agent0_backtest                  # needs tracker + model credentials
    python -m scripts.agent0_backtest --json reports/backtest.json

The working clone is shallow; the script fetches full history first
(--no-fetch to skip). It writes nothing to the tracker: each story is
analysed in dry form, never published.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TARGET_RECALL, TARGET_PRECISION = 0.9, 0.5


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True).stdout


@dataclass
class Event:
    commit: str
    parent: str
    story: str
    revised: set = field(default_factory=set)        # test case keys whose hash changed


def _markers(text: str) -> dict:
    from agents.agent2_coder import parse_feature_file
    _h, blocks = parse_feature_file(text)
    return {b.jira_key: b.jira_hash for b in blocks if b.jira_key}


def _show(root: Path, rev: str, path: str) -> str:
    try:
        return _git(root, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return ""


def find_events(root: Path) -> tuple[list, int]:
    """(events attributed to a story, count of hash changes with no story).

    Walks the first-parent history: each commit there is a merged change.
    """
    from config import extract_jira_key
    events, unattributed = [], 0
    log = _git(root, "log", "--first-parent", "--format=%H%x09%P%x09%s", "--", "features")
    for line in log.splitlines():
        commit, parents, subject = (line.split("\t") + ["", ""])[:3]
        parent = parents.split()[0] if parents.split() else ""
        if not parent:
            continue
        changed = [p for p in _git(root, "diff", "--name-only", parent, commit, "--",
                                   "features").splitlines() if p.endswith(".feature")]
        revised = set()
        for path in changed:
            before, after = _markers(_show(root, parent, path)), _markers(_show(root, commit, path))
            revised |= {k for k in before.keys() & after.keys() if before[k] != after[k]}
        if not revised:
            continue
        story = extract_jira_key(subject)
        if story:
            events.append(Event(commit, parent, story, revised))
        else:
            unattributed += 1
    return events, unattributed


def score(predicted: set, actual: set) -> tuple:
    hit = predicted & actual
    return (len(hit) / len(actual) if actual else None,
            len(hit) / len(predicted) if predicted else None)


def sweep(results: list, thresholds=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7)) -> list:
    """Micro recall/precision if everything scoring >= t were predicted."""
    out = []
    for t in thresholds:
        hit = pred = act = 0
        for r in results:
            p = {row["key"] for row in r["ranked"] if row["key"] and row["score"] >= t}
            hit += len(p & r["actual"])
            pred += len(p)
            act += len(r["actual"])
        out.append({"threshold": t, "recall": round(hit / act, 3) if act else None,
                    "precision": round(hit / pred, 3) if pred else None})
    return out


def run_backtest(root: Path, analyse) -> dict:
    """analyse(story_key, checkout_root) -> ranked rows [{"key", "score", "tier"}]."""
    events, unattributed = find_events(root)
    results = []
    for ev in events:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "at"
            _git(root, "worktree", "add", "--detach", str(checkout), ev.parent)
            try:
                ranked = analyse(ev.story, checkout)
            finally:
                _git(root, "worktree", "remove", "--force", str(checkout))
        predicted = {r["key"] for r in ranked if r["key"] and r["tier"] != "unaffected"}
        recall, precision = score(predicted, ev.revised)
        results.append({"story": ev.story, "commit": ev.commit[:12], "actual": ev.revised,
                        "predicted": predicted, "ranked": ranked,
                        "recall": recall, "precision": precision})
    hit = sum(len(r["predicted"] & r["actual"]) for r in results)
    pred = sum(len(r["predicted"]) for r in results)
    act = sum(len(r["actual"]) for r in results)
    recall = round(hit / act, 3) if act else None
    precision = round(hit / pred, 3) if pred else None
    return {"events": len(events), "unattributed_changes": unattributed,
            "recall": recall, "precision": precision,
            "meets_target": bool(recall is not None and precision is not None
                                 and recall >= TARGET_RECALL and precision >= TARGET_PRECISION),
            "threshold_sweep": sweep(results), "stories": results}


def _live_analyser():
    from agents.agent0_impact import analyse_requirement
    from core.impact_settings import impact_settings
    from core.llm_client import LLMClient
    from integrations.tracker import get_tracker
    tracker, llm, settings = get_tracker(), LLMClient(temperature=0.0), impact_settings()

    def analyse(story: str, checkout: Path) -> list:
        report = analyse_requirement(tracker, story, llm, settings, checkout)
        return report["ranked"] + report["unaffected"]
    return analyse


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    from config.paths import PROJECT_ROOT
    ap = argparse.ArgumentParser(prog="python -m scripts.agent0_backtest")
    ap.add_argument("--no-fetch", action="store_true", help="do not unshallow the clone")
    ap.add_argument("--json", help="write the full result here")
    args = ap.parse_args(argv)
    root = Path(PROJECT_ROOT)
    if not args.no_fetch and _git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        print("Fetching full history (the clone is shallow)...")
        _git(root, "fetch", "--unshallow")
    result = run_backtest(root, _live_analyser())
    print(f"Stories replayed: {result['events']}  (hash changes with no story: "
          f"{result['unattributed_changes']})")
    print(f"Recall {result['recall']}  precision {result['precision']}  -> "
          f"{'MEETS' if result['meets_target'] else 'below'} the target "
          f"(recall >= {TARGET_RECALL} at precision >= {TARGET_PRECISION})")
    for row in result["threshold_sweep"]:
        print(f"  score >= {row['threshold']}: recall {row['recall']} precision {row['precision']}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=1, default=sorted), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
