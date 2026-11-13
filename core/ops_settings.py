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
        # A scheduled workflow whose schedule asked for at least
        # `schedule_min_expected` runs in the last `schedule_window_hours`,
        # none of which the repository host started, is reported.
        "schedule_window_hours": 24,
        "schedule_min_expected": 3,
        # ... and one whose host started fewer than this share of them (X8).
        # 0 switches that half off.
        "schedule_min_share": 0.25,
    },
    # A test that failed and then passed when retried once (F-19).
    "flaky_tests": {
        "enabled": True,
        "window_days": 14,
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
        # Only a test that failed, was run again (after the application was
        # found up) and failed again is raised as a defect. A failure that was
        # not run again is listed in one health alert instead.
        "only_after_retry": True,
        # Traceability: link each defect to its test case ("blocks") and story
        # ("relates to") - link kinds `defect_of` / `defect_story` in
        # tracker.link_types - and give it the story's components.
        "trace_links": True,
        "copy_components": True,
        # A defect no marker, feature file or trace_owners entry traces.
        "unmapped_label": "ai-defect-unmapped",
        # Feature files that cannot carry `# JIRA:` markers (the reserved
        # reference files) -> the story they belong to: {path: story key}.
        "trace_owners": {},
        # D9: what a closed defect was - a label a person adds when closing
        # it, else the tracker's resolution. Categories: app (a bug in the
        # application), test (the test was wrong), environment, duplicate,
        # not-a-bug. The density counts app defects and the ones nobody
        # categorised; the rest are listed apart.
        "close_categories": {"defect-app": "app", "defect-test": "test",
                             "defect-env": "environment", "defect-duplicate": "duplicate"},
        "resolution_categories": {"Duplicate": "duplicate", "Won't Do": "not-a-bug",
                                  "Cannot Reproduce": "not-a-bug"},
    },
    # The application health probe (core/app_probe.py): asked by Agent 4 after
    # a run with failures, before anything is retried or raised as a defect.
    # WHAT is checked is application-specific: app_under_test.health_check.
    "app_health": {
        # Wait this long for an application that is not up before calling the
        # run's failures an outage; checks this often meanwhile.
        "wait_minutes": 8,
        "interval_seconds": 60,
        # How long each checked element may take to show.
        "element_timeout_ms": 15000,
    },
    # Hand-off between agents (core/handoff.py). GitHub drops or delays most
    # scheduled runs of a quiet repository (3 Nov 2026: none of Agent 1's
    # ~10 scheduled runs that day had started by 14:00 IST), so an agent that
    # leaves work for another starts it: Agent 0 starts Agent 1 when a story
    # reaches it, and Agents 1 and 2 start themselves again while stories wait
    # past max_stories_per_run. The schedules stay as the safety net.
    "handoff": {
        "enabled": True,
        # Runs one hand-off may start in a row - a bound, never reached by a
        # normal queue (each run takes max_stories_per_run stories).
        "max_chain": 5,
        # Agent config key (agents.<key> in config.yaml) -> its workflow file.
        # Only these agents are ever started.
        "workflows": {"agent1_analyst": "agent1_analyst.yml",
                      "agent2_coder": "agent2_coder.yml"},
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
    # Agent 3's review (X7): the whole prompt is capped; a larger change is
    # reviewed in parts (more calls), at most `max_parts`; files beyond them
    # are named on the review as not reviewed.
    "review": {
        "max_prompt_tokens": 100_000,
        "max_parts": 3,
    },
    # Reports beyond one run (core/results_store.py, scripts/build_site.py,
    # .github/workflows/reports.yml): every full run on the default branch is
    # recorded on `store_branch` and published as a site.
    "reporting": {
        "enabled": True,
        # The branch that keeps the history (written by the agents' identity).
        "store_branch": "metrics-data",
        # How far back the dashboard and the PDF look.
        "window_days": 30,
        # Results older than this are deleted from the store - the store
        # branch and a local run's store alike (at least window_days; 0: keep
        # everything).
        "keep_days": 90,
        # Allure severity of a scenario by its tags (the most severe match);
        # every other scenario is `default_severity`.
        "severity_by_tag": {"smoke": "critical"},
        "default_severity": "normal",
        # Dated PDFs kept on the store (the latest is always published, and a
        # sprint's PDF is attached to its summary issue). 0: none.
        "pdf_keep": 0,
        # A sprint's summary on the tracker (RP7): one issue of this type per
        # sprint, the PDF attached, moved to this status (it is a record, not
        # work), made on the sprint's last day or by hand.
        "sprint_summary": True,
        "sprint_summary_issue_type": "Task",
        "sprint_summary_status": "Done",
        # A trend chart on Agent 5's comment (RP10): the story's results over
        # its last runs, once it has at least `story_trend_min_points`.
        "story_trend": True,
        "story_trend_points": 10,
        "story_trend_min_points": 2,
        # D7: the defect history kept on the store (core/defect_ledger.py) -
        # every defect's last known state, so the trend and density survive
        # a defect deleted from the tracker. A closed defect is dropped this
        # many days after it was closed (0: kept for ever).
        "defect_history": True,
        "defect_keep_days": 730,
        # Keys dropped from the history at once: a throw-away issue deleted
        # before it carried cleanup.delete_label stays as 'deleted' otherwise.
        "defect_history_forget": [],
        # D8: the module of a defect: its tracker component when it has one;
        # else the module whose feature-file patterns match its test's (or
        # its test case's) feature file; else the feature file's name.
        # {module name: [feature file patterns]}.
        "modules": {},
        # RP12: the density is a module's product defects per this many
        # scenarios.
        "density_per": 10,
    },
    # D10: scripts/delete_issues.py deletes only closed issues carrying this
    # label - throw-away issues (validation runs, dummy defects). A real
    # defect is closed, never deleted: it is the defect trend's history. The
    # defect history leaves issues with this label out. "" turns it off.
    "cleanup": {
        "delete_label": "test-data",
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
