"""Settings of the operational features (P3): one reader for their blocks.

`pipeline_health`, `flaky_tests`, `defects` and `budget` are top-level blocks
of config/config.yaml. Each is merged over its defaults here, so a deployment
whose config predates a block - or whose block is malformed - gets the
defaults instead of an error. Never raises.
"""
from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)

DEFAULTS: dict = {
    # One standing issue people watch: alerts open and close as comments on it,
    # its description is the current picture (core/pipeline_health.py).
    "pipeline_health": {
        "enabled": True,
        "issue_type": "Task",
        "summary": "Pipeline health",
        "label": "pipeline-health",
        # A scheduled workflow is reported after this many failed scheduled
        # runs in a row (scripts/pipeline_health_check.py).
        "consecutive_failures": 3,
        # Warn this many days before a credential expires, where the provider
        # says when (GitHub tokens do; Jira and model keys do not).
        "expiry_warn_days": 14,
        # How the model endpoint is checked: "completion" sends a one-token
        # request (catches a spent key budget, costs a fraction of a cent),
        # "models" only lists models (free, misses a spent budget), "off".
        "model_check": "completion",
        # Day-spend records older than this are deleted by the health check.
        "spend_keep_days": 35,
    },
    # A test that failed and then passed when retried once (F-19).
    "flaky_tests": {
        "enabled": True,
        "window_days": 30,
    },
    # A test failing on main or in the scheduled run raises a defect (F-22).
    "defects": {
        "enabled": True,
        "issue_type": "Bug",
        "label": "ai-defect",
        "passing_label": "ai-defect-passing",
        # Statuses in which a raised defect is still open (board columns
        # before done). A done defect is never updated; a new one is raised.
        "open_statuses": ["To Do", "In Progress", "In Review"],
        # A run with more new failures than this raises this many defects and
        # one health alert, rather than a flood.
        "max_new_per_run": 10,
    },
    # Where a story's model-cost ledger is kept (F-31, core/usage_ledger.py):
    # "auto" - hidden issue properties and one cost comment per attempt, edited
    # in place, when the tracker can; "comments" - one [LLM-USAGE] comment per
    # agent run and the table in every Agent 5 report (the original behaviour).
    "usage_ledger": {
        "store": "auto",
    },
    # Model spend limits (F-24). Costs need LLM_PRICE_INPUT_PER_1M and
    # LLM_PRICE_OUTPUT_PER_1M; without pricing nothing can be enforced.
    "budget": {
        "enabled": True,
        "per_story_usd": 8.0,
        "per_day_usd": 12.0,
        # A health alert when the day's spend passes this share of the limit;
        # Agent 5's cost line marks a story past it.
        "warn_at": 0.5,
        # The day the daily limit counts, as an IANA zone name.
        "timezone": "UTC",
        # A story stopped by its budget carries this label; every agent's
        # selection excludes it. Removing it allows the story one more budget.
        "hold_label": "budget-hold",
    },
}


def section(name: str) -> dict:
    """The `name` block of config.yaml merged over DEFAULTS[name]."""
    merged = copy.deepcopy(DEFAULTS.get(name, {}))
    try:
        import yaml
        from config.paths import CONFIG_YAML
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        block = data.get(name)
    except Exception as e:                                         # noqa: BLE001
        logger.debug("config %s unreadable (%s); defaults used.", name, e)
        return merged
    if block is None:
        return merged
    if not isinstance(block, dict):
        logger.warning("config %s is not a mapping; defaults used.", name)
        return merged
    for key, value in block.items():
        default = merged.get(key)
        # bool is an int in Python: `true` is no number of runs or dollars.
        wrong_bool = isinstance(value, bool) and not isinstance(default, bool)
        if default is not None and value is not None and (wrong_bool or (
                not isinstance(value, type(default))
                and not (isinstance(default, float) and isinstance(value, int)))):
            logger.warning("config %s.%s=%r is not a %s; default %r used.",
                           name, key, value, type(default).__name__, default)
            continue
        merged[key] = float(value) if isinstance(default, float) else value
    return merged
