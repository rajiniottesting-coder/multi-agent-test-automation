"""
Agent 1 — Analyst.

Role:
    The Analyst reads a user story (requirement) from Jira, uses an LLM to
    derive comprehensive manual test cases (positive, negative, edge cases),
    and creates them as linked "Test Case" issues in Jira.

Position in pipeline:
    [Agent 1: Analyst] → Agent 2: Coder → Agent 3: Reviewer → Agent 4: Runner → Agent 5: Reporter

Inputs:
    - A Jira story key (manual mode), OR
    - All stories matching a config-driven JQL filter (scan mode).

Outputs:
    - Jira "Test Case" issues, linked to the parent story.
    - Idempotency marker: parent story tagged with 'ai-processed'.

Usage:
    # Dev mode — process one specific story
    python -m agents.agent1_analyst --story PROJ-123 --dry-run
    python -m agents.agent1_analyst --story PROJ-123

    # Production mode — process all stories matching config criteria
    python -m agents.agent1_analyst --scan --dry-run
    python -m agents.agent1_analyst --scan
"""
import argparse
import logging
import sys
import yaml

from agents.app_context import AppContext
from agents.jira_client import JiraClient
from agents.llm_client import LLMClient
from agents.schemas import TestCaseList
from config import (
    REQUIRED_JIRA_ENV_VARS,
    REQUIRED_LLM_ENV_VARS,
    validate_required_env,
)
from config.paths import PROMPTS_DIR, CONFIG_YAML

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent1_analyst")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def load_prompt(prompt_file: str = "agent1_analyst.md") -> str:
    """Load the agent's prompt template from disk."""
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")


def load_app_context_block() -> str:
    """Load the app-specific context block (test users, error messages, etc.)
    that gets injected into the analyst's prompt.

    This file is the ONE place to put app-specific guidance for the analyst.
    For a new app, edit prompts/app_context.md — no Python code changes.

    Returns an empty string if app_context.md is missing (the prompt still
    works, just with less app-specific guidance).
    """
    path = PROMPTS_DIR / "app_context.md"
    if not path.exists():
        logger.warning(
            f"prompts/app_context.md not found — Agent 1 will run with the "
            f"generic prompt only. Create this file to add app-specific "
            f"context (test users, known error messages, app URL, etc.) "
            f"so the analyst produces more concrete test cases."
        )
        return ""
    return path.read_text(encoding="utf-8")


def load_agent_config(agent_key: str = "agent1_analyst") -> dict:
    """Load this agent's config section from config.yaml."""
    with open(CONFIG_YAML) as f:
        full_config = yaml.safe_load(f)
    return full_config.get("agents", {}).get(agent_key, {})


# ─────────────────────────────────────────────────────────────
# Core agent workflow (Read → Reason → Act → Return)
# ─────────────────────────────────────────────────────────────
def run(story_id: str, dry_run: bool = False) -> dict:
    """Process a single story end-to-end."""
    logger.info(f"=== Agent 1 (Analyst) starting for {story_id} (dry_run={dry_run}) ===")

    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name} ({ctx.base_url})")

    # 1. INPUT: fetch the story
    jira = JiraClient()
    story = jira.get_story(story_id)
    logger.info(f"Story: {story['summary']}")

    story_text = f"Title: {story['summary']}\n\nDescription:\n{story['description']}"

    # 2. REASON: call LLM with structured output
    prompt_template = load_prompt()
    app_context_block = load_app_context_block()
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{app_base_url}", ctx.base_url)
        .replace("{app_context}", app_context_block)
        .replace("{story_text}", story_text)
    )

    # max_output_tokens=8192 (not the default 4096): a TestCaseList of 5
    # detailed test cases (each with 5-10 steps carrying action + expected
    # result) runs ~2,000-3,000 tokens — only ~1.4-2x headroom at 4096. A
    # verbose story or a raised TC-count target in the prompt could truncate
    # mid-JSON, which fails the Pydantic parse and burns a retry. 8192 gives
    # comfortable ~3x headroom, matching the margin the other caps have.
    # NOTE: if you raise the "3-5 test cases" target in
    # prompts/agent1_analyst.md, revisit this cap in the same commit.
    llm = LLMClient(temperature=0.3, max_output_tokens=8192)
    test_case_list: TestCaseList = llm.invoke_structured(
        system_prompt="You are a meticulous, expert QA test analyst.",
        user_prompt=user_prompt,
        output_schema=TestCaseList,
    )

    logger.info(f"LLM generated {len(test_case_list.test_cases)} test cases:")
    for i, tc in enumerate(test_case_list.test_cases, 1):
        prefix = f"[{tc.test_type}]"
        label = tc.title if tc.title.startswith(prefix) else f"{prefix} {tc.title}"
        logger.info(f"  {i}. {label}")

    # 3. ACT: create Jira tickets (unless dry-run)
    created_keys = []
    if dry_run:
        logger.warning("DRY RUN — skipping Jira ticket creation")
    else:
        for tc in test_case_list.test_cases:
            issue = jira.create_test_case(tc, parent_story_key=story_id)
            created_keys.append(issue.key)

        # IDEMPOTENCY MARKER: tag parent story so the next --scan run skips it.
        agent_config = load_agent_config()
        completion_label = agent_config.get("completion_label", "ai-processed")
        jira.add_label(story_id, completion_label)
        logger.info(f"Marked {story_id} with label '{completion_label}' (idempotency)")

        # ONE-SHOT TRIGGER CLEANUP: remove the trigger label(s) that brought
        # this story into Agent 1's scope. After successful run, those labels
        # are stale — completion_label is the new state. Mirrors Agent 2's
        # one-shot pattern for ai-regenerate / ai-update.
        # Configurable via `trigger_labels_to_remove` in config.yaml. Defaults
        # to the agent's own `required_labels` so behavior is correct without
        # explicit config. Failure to remove a label is non-fatal — we log
        # and continue.
        trigger_labels = agent_config.get(
            "trigger_labels_to_remove",
            agent_config.get("selection", {}).get("required_labels", []),
        )
        for label in trigger_labels:
            try:
                jira.remove_label(story_id, label)
                logger.info(f"Removed trigger label '{label}' from {story_id} (one-shot consumed)")
            except Exception as e:
                logger.warning(
                    f"Could not remove trigger label '{label}' from {story_id}: {e}. "
                    "Non-fatal — story still has completion label as primary state marker."
                )

    # 4. OUTPUT: return state for orchestrator / next agent
    from agents.llm_client import log_usage_summary, reset_usage
    usage = log_usage_summary(f"story {story_id} (analyst)")
    reset_usage()  # per-story numbers in scan mode
    if not dry_run:
        from agents.usage_ledger import post_usage_to_story
        post_usage_to_story(story_id, "Agent 1 (Analyst)", usage, jira=jira)

    result = {
        "story_id": story_id,
        "story_summary": story["summary"],
        "test_cases_generated": len(test_case_list.test_cases),
        "test_case_keys": created_keys,
        "status": "tests_drafted" if not dry_run else "tests_drafted_dry_run",
        "llm_usage": usage,
    }

    logger.info(f"=== Agent 1 (Analyst) complete for {story_id}. Created: {created_keys} ===")
    return result


# ─────────────────────────────────────────────────────────────
# CLI entrypoint
# ─────────────────────────────────────────────────────────────
def print_summary(results: list[dict]) -> None:
    """Pretty-print a summary of all stories processed."""
    print("\n" + "=" * 60)
    print(f"✅ Agent 1 (Analyst) finished — processed {len(results)} story(ies)")
    for r in results:
        status_marker = "✅" if "failed" not in r["status"] else "❌"
        print(f"\n{status_marker} {r['story_id']} — {r['story_summary']}")
        print(f"   Status: {r['status']}")
        print(f"   Test cases generated: {r['test_cases_generated']}")
        if r["test_case_keys"]:
            print(f"   Created Jira issues: {', '.join(r['test_case_keys'])}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Agent 1 (Analyst): Generate manual test cases from Jira stories"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--story",
        help="Process a specific story by key (e.g., PROJ-123) — for dev/testing",
    )
    group.add_argument(
        "--scan",
        action="store_true",
        help="Auto-process stories matching config criteria (production mode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't create Jira tickets — just print what would happen",
    )
    parser.add_argument(
        "--sprint",
        default=None,
        metavar="SPRINT",
        help=(
            "Override the sprint filter for this run only. "
            "Accepts a sprint name (e.g. 'Sprint 10'), a numeric sprint ID, "
            "or 'openSprints' to target the currently active sprint. "
            "Overrides the 'sprint' key in config.yaml. "
            "Only applies in --scan mode; ignored with --story."
        ),
    )
    args = parser.parse_args()

    # Fast-fail on missing config
    validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)

    try:
        if args.story:
            logger.info(f"Manual mode: processing {args.story}")
            result = run(args.story, dry_run=args.dry_run)
            print_summary([result])
            return

        # Scan mode: config-driven selection
        agent_config = load_agent_config()
        selection = agent_config.get("selection", {})
        max_stories = agent_config.get("max_stories_per_run", 10)

        if not selection:
            logger.error("No 'selection' config found for agent1_analyst in config.yaml")
            sys.exit(1)

        # Log the effective sprint so it's visible in CI logs
        effective_sprint = args.sprint or selection.get("sprint")
        if effective_sprint:
            logger.info(
                f"Sprint scope: {effective_sprint!r} "
                f"(source: {'--sprint flag' if args.sprint else 'config.yaml'})"
            )
        else:
            logger.info("Sprint scope: ALL sprints (no sprint filter configured)")

        jira = JiraClient()
        stories = jira.find_stories_to_process(
            selection,
            max_results=max_stories,
            sprint_override=args.sprint,
        )

        if not stories:
            logger.info("No stories match selection criteria. Nothing to do.")
            print("\n✅ Scan complete — 0 stories needed processing.")
            return

        logger.info(f"Will process {len(stories)} stories:")
        for s in stories:
            logger.info(f"  - {s['key']} [{s['status']}] {s['summary']}")

        results = []
        for story in stories:
            try:
                result = run(story["key"], dry_run=args.dry_run)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']}: {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "story_summary": story["summary"],
                    "test_cases_generated": 0,
                    "test_case_keys": [],
                    "status": f"failed: {type(e).__name__}",
                })

        print_summary(results)

    except Exception as e:
        logger.error(f"Agent 1 (Analyst) failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()