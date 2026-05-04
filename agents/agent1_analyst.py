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
    python -m agents.agent1_analyst --story SCRUM-3 --dry-run
    python -m agents.agent1_analyst --story SCRUM-3

    # Production mode — process all stories matching config criteria
    python -m agents.agent1_analyst --scan --dry-run
    python -m agents.agent1_analyst --scan
"""
import argparse
import logging
import sys
import yaml

from agents.jira_client import JiraClient
from agents.llm_client import LLMClient
from agents.schemas import TestCaseList
from config.paths import PROMPTS_DIR, CONFIG_YAML

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
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


def load_agent_config(agent_key: str = "agent1_analyst") -> dict:
    """Load this agent's config section from config.yaml."""
    with open(CONFIG_YAML) as f:
        full_config = yaml.safe_load(f)
    return full_config.get("agents", {}).get(agent_key, {})


# ─────────────────────────────────────────────────────────────
# Core agent workflow (Read → Reason → Act → Return)
# ─────────────────────────────────────────────────────────────
def run(story_id: str, dry_run: bool = False) -> dict:
    """
    Process a single story end-to-end:
      1. Fetch story from Jira
      2. Call LLM to generate test cases
      3. Create Jira Test Case issues (unless dry-run)
      4. Return result dict

    Returns:
        Dict with story_id, test_cases_generated, test_case_keys, status.
    """
    logger.info(f"=== Agent 1 (Analyst) starting for {story_id} (dry_run={dry_run}) ===")

    # 1. INPUT: fetch the story
    jira = JiraClient()
    story = jira.get_story(story_id)
    logger.info(f"Story: {story['summary']}")

    story_text = f"Title: {story['summary']}\n\nDescription:\n{story['description']}"

    # 2. REASON: call LLM with structured output
    prompt_template = load_prompt()
    user_prompt = prompt_template.replace("{story_text}", story_text)

    llm = LLMClient(temperature=0.3)
    test_case_list: TestCaseList = llm.invoke_structured(
        system_prompt="You are a meticulous, expert QA test analyst.",
        user_prompt=user_prompt,
        output_schema=TestCaseList,
    )

    logger.info(f"LLM generated {len(test_case_list.test_cases)} test cases:")
    for i, tc in enumerate(test_case_list.test_cases, 1):
        logger.info(f"  {i}. [{tc.test_type}] {tc.title}")

    # 3. ACT: create Jira tickets (unless dry-run)
    created_keys = []
    if dry_run:
        logger.warning("DRY RUN — skipping Jira ticket creation")
    else:
        for tc in test_case_list.test_cases:
            issue = jira.create_test_case(tc, parent_story_key=story_id)
            created_keys.append(issue.key)

    # 4. OUTPUT: return state for orchestrator / next agent
    result = {
        "story_id": story_id,
        "story_summary": story["summary"],
        "test_cases_generated": len(test_case_list.test_cases),
        "test_case_keys": created_keys,
        "status": "tests_drafted" if not dry_run else "tests_drafted_dry_run",
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
        help="Process a specific story by key (e.g., SCRUM-3) — for dev/testing",
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
    args = parser.parse_args()

    try:
        if args.story:
            # ─── Manual mode: bypass selection logic ───
            logger.info(f"Manual mode: processing {args.story}")
            result = run(args.story, dry_run=args.dry_run)
            print_summary([result])

        else:
            # ─── Scan mode: config-driven selection ───
            config = load_agent_config()
            selection = config.get("selection", {})
            completion_label = config.get("completion_label", "ai-processed")
            max_stories = config.get("max_stories_per_run", 10)

            if not selection:
                logger.error("No 'selection' config found for agent1_analyst in config.yaml")
                sys.exit(1)

            jira = JiraClient()
            stories = jira.find_stories_to_process(selection, max_results=max_stories)

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

                    # Mark complete only if real run AND succeeded
                    if not args.dry_run:
                        jira.add_label(story["key"], completion_label)

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