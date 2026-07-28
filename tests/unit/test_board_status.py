"""Board column automation must be tool-agnostic, opt-in, and never fatal.

Labels drive the agents; statuses tell a human where the work is. Both must
stay independent: a card that fails to move is cosmetic, but a label that fails
to set breaks the pipeline.
"""
from unittest.mock import MagicMock, patch

import pytest

from core.board_status import (load_status_workflow, move_card_for_label,
                                 status_for_label)

WF = {"enabled": True,
      "on_label": {"ai-processed": "In Progress", "ai-coded": "In Review"}}


# ── mapping ──────────────────────────────────────────────────

def test_completion_labels_map_to_columns():
    assert status_for_label("ai-processed", WF) == "In Progress"
    assert status_for_label("ai-coded", WF) == "In Review"


def test_pending_labels_do_not_move_the_card():
    """ai-ready / ai-update / ai-regenerate mean work is still queued."""
    for label in ("ai-ready", "ai-update", "ai-regenerate", "human-approved"):
        assert status_for_label(label, WF) is None


def test_disabled_workflow_moves_nothing():
    off = {"enabled": False, "on_label": {"ai-coded": "In Review"}}
    assert status_for_label("ai-coded", off) is None


def test_missing_config_block_disables_the_feature(tmp_path, monkeypatch):
    """An existing deployment with no status_workflow keeps its old behaviour."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("app_under_test:\n  name: X\n")
    monkeypatch.setattr("core.board_status.CONFIG_YAML", cfg)
    wf = load_status_workflow()
    assert wf["enabled"] is False
    assert wf["on_label"] == {}
    assert wf["on_merge"] is None


# ── moving ───────────────────────────────────────────────────

def test_move_calls_the_tracker_with_the_mapped_status():
    tracker = MagicMock()
    tracker.transition_status.return_value = True
    assert move_card_for_label(tracker, "S-1", "ai-coded", WF) is True
    tracker.transition_status.assert_called_once_with("S-1", "In Review")


def test_no_mapping_means_no_tracker_call():
    tracker = MagicMock()
    assert move_card_for_label(tracker, "S-1", "human-approved", WF) is False
    tracker.transition_status.assert_not_called()


def test_declined_transition_is_not_an_error():
    """A workflow that forbids the move must not fail the run."""
    tracker = MagicMock()
    tracker.transition_status.return_value = False
    assert move_card_for_label(tracker, "S-1", "ai-coded", WF) is False


def test_tracker_exception_is_swallowed():
    """Board position is cosmetic; the pipeline has already done real work."""
    tracker = MagicMock()
    tracker.transition_status.side_effect = Exception("workflow locked")
    assert move_card_for_label(tracker, "S-1", "ai-coded", WF) is False


# ── tool-agnostic ────────────────────────────────────────────

def test_works_with_any_tracker_adapter():
    """A non-Jira tracker with its own column names."""
    class AzureLike:
        def __init__(self): self.status = "New"
        def transition_status(self, issue_key, status):
            self.status = status
            return True

    azure_wf = {"enabled": True,
                "on_label": {"ai-processed": "Active", "ai-coded": "Resolved"}}
    t = AzureLike()
    assert move_card_for_label(t, "AB-1", "ai-processed", azure_wf) is True
    assert t.status == "Active"
    assert move_card_for_label(t, "AB-1", "ai-coded", azure_wf) is True
    assert t.status == "Resolved"


def test_tracker_without_a_workflow_degrades_cleanly():
    """A flat task list returns False always; nothing breaks."""
    class FlatList:
        def transition_status(self, issue_key, status): return False
    assert move_card_for_label(FlatList(), "T-1", "ai-coded", WF) is False


# ── the trap: rework flows must still find moved stories ─────

def test_selection_rules_include_the_status_cards_move_to():
    """If Agent 2 moves a story to 'In Review', ai-regenerate / ai-update must
    still match it - otherwise rework silently stops working."""
    import yaml
    from config.paths import CONFIG_YAML
    cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))
    targets = set((cfg.get("status_workflow") or {}).get("on_label", {}).values())
    for agent, acfg in (cfg.get("agents") or {}).items():
        for key in ("selection", "regenerate_selection", "update_selection"):
            sel = acfg.get(key)
            if not sel or not sel.get("allowed_statuses"):
                continue
            allowed = set(sel["allowed_statuses"])
            missing = targets - allowed
            assert not missing, (
                f"{agent}.{key} allows {sorted(allowed)} but status_workflow "
                f"moves cards to {sorted(targets)} - {sorted(missing)} would "
                f"become invisible to this selection")


# ── Done is driven by a MERGE, never by a label ──────────────

WF_MERGE = {"enabled": True,
            "on_label": {"ai-processed": "In Progress", "ai-coded": "In Review"},
            "on_merge": "Done"}


def test_no_label_ever_maps_to_done():
    """Done means a human accepted the work. No agent may claim it."""
    for label in ("ai-ready", "ai-processed", "human-approved", "ai-coded",
                  "tests-run", "ai-update", "ai-regenerate"):
        assert status_for_label(label, WF_MERGE) != "Done"


def test_merge_moves_the_card_to_done():
    from core.board_status import move_card_on_merge
    tracker = MagicMock()
    tracker.transition_status.return_value = True
    assert move_card_on_merge(tracker, "S-1", WF_MERGE) is True
    tracker.transition_status.assert_called_once_with("S-1", "Done")


def test_merge_move_is_never_fatal():
    from core.board_status import move_card_on_merge
    tracker = MagicMock()
    tracker.transition_status.side_effect = Exception("workflow locked")
    assert move_card_on_merge(tracker, "S-1", WF_MERGE) is False


def test_on_merge_unset_means_no_done_transition():
    from core.board_status import move_card_on_merge
    tracker = MagicMock()
    assert move_card_on_merge(tracker, "S-1", WF) is False   # WF has no on_merge
    tracker.transition_status.assert_not_called()


def test_merge_target_is_tool_agnostic():
    from core.board_status import move_card_on_merge
    class AzureLike:
        def __init__(self): self.status = "Resolved"
        def transition_status(self, issue_key, status):
            self.status = status; return True
    t = AzureLike()
    azure = {"enabled": True, "on_label": {}, "on_merge": "Closed"}
    assert move_card_on_merge(t, "AB-1", azure) is True
    assert t.status == "Closed"


def test_closed_without_merge_does_not_mark_done():
    """A rejected PR must leave the story in In Review. The CLI is the gate."""
    import subprocess, sys, os
    env = dict(os.environ, JIRA_URL="x", JIRA_EMAIL="x",
               JIRA_API_TOKEN="x", JIRA_PROJECT_KEY="SCRUM")
    r = subprocess.run(
        [sys.executable, "-m", "scripts.close_merged_story",
         "--branch", "auto/SCRUM-5-login", "--merged", "false"],
        capture_output=True, text=True, env=env, cwd=str(
            __import__("pathlib").Path(__file__).resolve().parents[2]))
    assert r.returncode == 0
    assert "WITHOUT merging" in r.stdout

# ── NEGATIVE: malformed config must never crash an agent ─────
#
# status_for_label is called BEFORE the try block in move_card_for_label, so an
# exception here would propagate and fail a run that has already created test
# cases or opened a PR. A YAML indentation slip must not cost that.

@pytest.mark.parametrize("bad_workflow", [
    {"enabled": True, "on_label": "ai-coded: In Review"},   # string, not mapping
    {"enabled": True, "on_label": ["ai-coded"]},            # list
    {"enabled": True, "on_label": {"ai-coded": None}},      # null status
    {"enabled": True, "on_label": {"ai-coded": 42}},        # non-string status
    {"enabled": True, "on_label": {"ai-coded": {"a": 1}}},  # nested mapping
    {"enabled": True, "on_label": {"ai-coded": "   "}},     # whitespace only
    "not a mapping at all",                                 # whole block wrong
    ["also", "not", "a", "mapping"],
])
def test_malformed_config_degrades_instead_of_raising(bad_workflow):
    assert status_for_label("ai-coded", bad_workflow) is None
    assert move_card_for_label(MagicMock(), "S-1", "ai-coded", bad_workflow) is False


@pytest.mark.parametrize("bad_merge", [
    {"enabled": True, "on_label": {}, "on_merge": 7},
    {"enabled": True, "on_label": {}, "on_merge": ["Done"]},
    {"enabled": True, "on_label": {}, "on_merge": ""},
])
def test_malformed_on_merge_degrades(bad_merge):
    from core.board_status import move_card_on_merge
    tracker = MagicMock()
    assert move_card_on_merge(tracker, "S-1", bad_merge) is False
    tracker.transition_status.assert_not_called()