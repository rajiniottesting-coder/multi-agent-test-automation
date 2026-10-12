"""Agent 0 settings: `agents.agent0_impact` in config.yaml, merged over defaults.

Every label, threshold and switch Agent 0 and its hand-over use comes from
here, so no module hard-codes a label name (A4's rule for link types applies
to labels too). A deployment without the block gets the defaults below, which
leave Agent 0 DISABLED and in SHADOW mode: nothing is written until a person
switches it on.
"""
from __future__ import annotations

import copy

DEFAULTS: dict = {
    "enabled": False,          # master switch: the scan and the workflow do nothing while false
    "shadow_mode": True,       # report only: no Impact Review, no label added, no hand-over
    "uncovered_hint": False,   # E1 follow-up: a named uncovered element adds its page as a review candidate
    "uncovered_max_age_hours": 48,   # an older uncovered snapshot is ignored, never trusted
    "selection": {
        "issue_type": "Story",
        "allowed_statuses": ["To Do", "In Progress", "In Review"],
        "required_labels": ["impact-check"],
        "excluded_labels": ["ai-skip"],
    },
    "labels": {
        "check": "impact-check",
        "proposed": "impact-proposed",
        "applied": "impact-applied",
        "reverted": "impact-reverted",
        "ready": "ai-ready",
        "drift": "inventory-drift",       # marks the one open drift maintenance story
    },
    "review": {
        "issue_type": "Subtask",          # a standard type on every Jira plan
        "summary_prefix": "Impact Review",
        "done_status": "Done",
    },
    "weights": {"structural": 0.45, "component": 0.15, "semantic": 0.15, "adjudicated": 0.25},
    "thresholds": {"must_update": 0.6, "review": 0.3},
    "max_candidates": 300,
    "reconcile": {"closed_scans": 2, "no_pr_days": 14,
                  # Pipeline-progress labels a closed-unmerged PR makes untrue:
                  # removed on undo so the story can simply be retried.
                  "reset_labels": ["ai-processed", "human-approved", "ai-coded", "tests-run"]},
    # Live mode only: when a change story is handed over (or has nothing to
    # review), propose the inventory / context-note wording update as a pull
    # request for a person to merge after deployment (core.context_update).
    "context_update": {"enabled": True, "branch_prefix": "context-update/"},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def impact_settings(raw: dict | None = None) -> dict:
    """The effective settings. `raw` overrides config.yaml (tests)."""
    if raw is None:
        try:
            import yaml
            from config.paths import CONFIG_YAML
            data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
            raw = (data.get("agents") or {}).get("agent0_impact") or {}
        except Exception:                      # unreadable config -> safe defaults
            raw = {}
    return _merge(DEFAULTS, raw)
