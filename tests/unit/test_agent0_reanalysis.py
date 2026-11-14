"""Agent 0 analysing a story again: a re-analysis that changes nothing says so
(a no-change delta), a first analysis posts none, a story can be analysed
again on request (force), and a re-analysis that finds nothing settles the
open Impact Review.
"""

from unittest.mock import MagicMock
from pathlib import Path
from types import SimpleNamespace as NS


def test_an_unchanged_reanalysis_posts_a_no_change_delta():
    from agents.agent0_impact import DELTA, _post_delta
    tracker = MagicMock()
    _post_delta(tracker, "AB-9", {"added": [], "removed": [], "tier_changed": []})
    body = tracker.add_comment.call_args.args[1]
    assert body.startswith(DELTA) and "no change to the affected tests" in body


def test_a_first_analysis_posts_no_delta():
    from agents.agent0_impact import _post_delta
    tracker = MagicMock()
    _post_delta(tracker, "AB-9", None)
    tracker.add_comment.assert_not_called()


# ── one story can be analysed again on request (force) ────────────────────────

ROOT = Path(__file__).resolve().parents[2]


def test_force_analyses_an_unchanged_story(monkeypatch):
    import agents.agent0_impact as a0
    calls = []
    monkeypatch.setattr(a0, "_start_usage", lambda: None)
    monkeypatch.setattr(a0, "_already_analysed", lambda *a: True)
    monkeypatch.setattr(a0, "requirement_hash", lambda s: "h")
    monkeypatch.setattr(a0, "analyse_requirement", lambda *a, **k: calls.append("analysed") or {})
    monkeypatch.setattr(a0, "publish", lambda *a, **k: calls.append(k.get("force")) or
                        {"action": "dry-run"})
    tracker = NS(get_story=lambda k: {"key": k}, remove_label=lambda *a: calls.append("label"))
    settings = {"labels": {"check": "c"}}
    assert a0.analyse_and_publish(tracker, "AB-1", None, settings, ROOT)["action"] == "unchanged"
    assert calls == ["label"]
    calls.clear()
    a0.analyse_and_publish(tracker, "AB-1", None, settings, ROOT, dry_run=True, force=True)
    assert calls == ["analysed", True]


def test_force_is_a_workflow_input_for_one_story():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "agent0_impact.yml").read_text())
    inputs = wf[True]["workflow_dispatch"]["inputs"] if True in wf else wf["on"]["workflow_dispatch"]["inputs"]
    assert inputs["force"]["type"] == "boolean"
    src = (ROOT / "agents" / "agent0_impact.py").read_text(encoding="utf-8")
    assert '"--force is for one story: use it with --story"' in src


# ── a re-analysis that finds nothing settles the open review ──────────────────

def test_an_empty_reanalysis_supersedes_the_open_review(tmp_path, monkeypatch):
    import agents.agent0_impact as a0
    from core import impact_review
    from tests.unit.test_agent0_end_to_end import FakeModel, TITLE_12, _only_in, _settings
    fake, jira, root, g = _world(tmp_path, monkeypatch)
    s = _settings(shadow_mode=False)
    page, key = _only_in(g, "SBX-12", "SBX-11")
    first = a0.analyse_requirement(jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}),
                                   _settings(), root)
    assert a0.publish(jira, "SBX-5", first, s)["action"] == "review-created"
    review = jira.get_subtasks("SBX-5")[0]
    again = a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(), root)
    again["ranked"], again["content_hash"] = [], "f" * 12
    out = a0.publish(jira, "SBX-5", again, s, force=True)
    assert out == {"story": "SBX-5", "action": "nothing-to-review", "review_superseded": review["key"]}
    labels = fake.issues["SBX-5"]["labels"]
    assert "ai-ready" in labels and "impact-proposed" not in labels
    text = jira.get_subtasks("SBX-5")[0]["description"]
    assert "Superseded" in text and impact_review.parse_rows(text) == {}


def _world(tmp_path, monkeypatch):
    import agents.agent0_impact as a0
    import config.paths as paths
    from core.impact_graph import build_impact_graph
    from tests.unit.test_agent0_end_to_end import build_repo, jira_client_over, seed_jira
    fake = seed_jira()
    fake.add("Story", "A story", key="SBX-5", labels=["impact-check"], components=["Login"],
             description="When the password is wrong, the error message also links to reset.")
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    a0._GRAPHS.clear()
    return fake, jira, root, build_impact_graph(root)
