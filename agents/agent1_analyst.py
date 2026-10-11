"""
Agent 1 — Test Designer.

Role:
    The Test Designer reads a user story (requirement) from Jira, uses an LLM to
    derive comprehensive manual test cases (positive, negative, edge cases),
    and creates them as linked "Test Case" issues in Jira.

Position in pipeline:
    [Agent 1: Test Designer] → Agent 2: Coder → Agent 3: Reviewer → Agent 4: Runner → Agent 5: Reporter

Inputs:
    - A Jira story key (manual mode), OR
    - All stories matching the config-driven selection rule (scan mode).

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

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m agents.agent1_analyst --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
import argparse
import logging
import sys
import yaml

from core.app_context import AppContext
from integrations.tracker import get_tracker
from core.board_status import move_card_for_label
from core.llm_client import LLMClient
from core.schemas import TestCaseList
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


def load_app_context_block(components: list[str] | None = None) -> str:
    """Load the app-specific context injected into the analyst's prompt.

    Two layouts, chosen automatically from the filesystem:

    1. **Single file (default, unchanged).** `prompts/app_context.md`. Used
       whenever the module folder below does not exist.
    2. **Module-wise (backlog 2.1).** If `prompts/app_context/` exists, inject
       `core.md` (always) plus one `<component>.md` per Jira Component on the
       story. Focuses Agent 1's prompt on the relevant module for a large app.
       Matching is case/space/hyphen-insensitive ("User Management" ->
       user_management.md). A story with NO components, or a component with no
       matching file, injects ALL modules — a safe default that never silently
       drops context.

    Args:
        components: Jira Component names on the story (from get_story). None/[]
            -> inject everything (safe default).

    Returns an empty string if no context is found at all.
    """
    folder = PROMPTS_DIR / "app_context"

    if not folder.is_dir():
        path = PROMPTS_DIR / "app_context.md"
        if not path.exists():
            logger.warning(
                "prompts/app_context.md not found — Agent 1 will run with the "
                "generic prompt only. Create this file (or a prompts/app_context/ "
                "folder) to add app-specific context so the analyst produces more "
                "concrete test cases."
            )
            return ""
        return path.read_text(encoding="utf-8")

    def _norm(name: str) -> str:
        return name.strip().lower().replace(" ", "_").replace("-", "_")

    module_files = {_norm(p.stem): p for p in sorted(folder.glob("*.md"))}

    blocks: list[str] = []
    core = module_files.pop("core", None)
    if core is not None:
        blocks.append(core.read_text(encoding="utf-8"))

    requested = [_norm(c) for c in (components or [])]
    matched = [module_files[r] for r in requested if r in module_files]

    if matched:
        for p in matched:
            blocks.append(p.read_text(encoding="utf-8"))
        unmatched = [r for r in requested if r not in module_files]
        if unmatched:
            logger.info(
                "Module context: no file for component(s) %s — injecting matched "
                "modules only (%s).", unmatched, [p.stem for p in matched],
            )
    else:
        if requested:
            logger.info(
                "Module context: story components %s matched no files — "
                "injecting all modules as a safe default.", requested,
            )
        for p in module_files.values():
            blocks.append(p.read_text(encoding="utf-8"))

    if not blocks:
        logger.warning(
            "prompts/app_context/ exists but contains no readable .md files — "
            "Agent 1 will run with the generic prompt only."
        )
        return ""

    return "\n\n".join(blocks)


def _impacted_test_cases(jira, story_id: str) -> list:
    """Approved impacted test cases of the story, [] for an ordinary story.

    A lookup failure (a Jira without the Impacts link type, say) must not
    stop Agent 1's normal work while Agent 0 is switched off, so it is
    logged and treated as "none". With Agent 0 on, it is raised: drafting
    from scratch a story that should revise existing tests would duplicate them.
    """
    try:
        return jira.get_impacted_test_cases(story_id)
    except Exception as e:                                     # noqa: BLE001
        from core.impact_settings import impact_settings
        if impact_settings()["enabled"]:
            raise
        logger.warning(f"Impacted test case lookup failed for {story_id} "
                       f"({type(e).__name__}: {e}); Agent 0 is off - normal mode.")
        return []


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
    logger.info(f"=== Agent 1 (Test Designer) starting for {story_id} (dry_run={dry_run}) ===")

    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name} ({ctx.base_url})")

    # 1. INPUT: fetch the story
    jira = get_tracker()

    # DUPLICATE GUARD. Test Cases are created in a LOOP and `ai-processed` is
    # added only afterwards, so three routes end in duplicates:
    #   - `--story` run twice by hand (there was no guard at all)
    #   - a crash mid-loop: some cases created, story unmarked, next tick
    #     recreates the WHOLE set
    #   - a story reset to ai-ready without deleting the previous cases
    #
    # Unlike Agent 2 - where an open PR proves every file was committed, because
    # the PR is opened AFTER the commit loop - a COUNT of linked Test Cases is
    # ambiguous on its own: 4 linked cases could be "4 of 4, finished" or
    # "4 of 6, died". The completion LABEL is what disambiguates, since it is
    # written after the loop for exactly the same reason the PR is:
    #
    #   label PRESENT + cases exist  -> previous run FINISHED
    #   label ABSENT  + cases exist  -> previous run was INTERRUPTED
    #
    # Either way we refuse and hand back to a human, but the message says which,
    # because the right remedy differs. Runs BEFORE the LLM call, so a repeat
    # costs two API calls instead of a full generation.
    #
    # Deliberately NOT auto-deleting: those issues may already be approved,
    # edited by a human, or referenced by an open PR. Removing them is a
    # judgement call that belongs to a person.
    existing = jira.count_linked_test_cases(story_id)
    if existing and not dry_run:
        agent_config = load_agent_config()
        completion_label = agent_config.get("completion_label", "ai-processed")
        try:
            labels = jira.get_story(story_id).get("labels", []) or []
        except Exception:
            labels = []
        finished = completion_label in labels

        if finished:
            logger.warning(
                f"{story_id} already has {existing} linked Test Case(s) and is "
                f"labelled '{completion_label}' - the previous run COMPLETED. "
                f"Nothing to do.\n"
                f"  To draft a fresh set, delete the existing Test Cases and "
                f"remove the '{completion_label}' label first."
            )
            status = "already_processed"
        else:
            logger.warning(
                f"{story_id} has {existing} linked Test Case(s) but NO "
                f"'{completion_label}' label - a previous run was INTERRUPTED "
                f"part-way through creating them, so that set is INCOMPLETE.\n"
                f"  Delete those {existing} partial Test Case(s) in Jira and "
                f"re-run to get a clean, complete set.\n"
                f"  (Refusing to add more: appending to a partial set would mix "
                f"two drafts and leave duplicates.)"
            )
            status = "partial_test_cases"

        return {"story_id": story_id, "status": status,
                "test_cases_created": 0, "existing_test_cases": existing}

    story = jira.get_story(story_id)
    logger.info(f"Story: {story['summary']}")

    story_text = f"Title: {story['summary']}\n\nDescription:\n{story['description']}"

    # ── Ledger boundary ──────────────────────────────────────────────
    # If this story already carries usage comments, it was costed by a
    # previous run that has since been discarded (test cases deleted and the
    # story reset to `ai-ready`). Post a [LEDGER-RESET] boundary so Agent 5
    # aggregates only THIS run's usage — otherwise the end-to-end cost table
    # would sum the discarded run's tokens with the new one.
    #
    # Deliberately scoped to Agent 1: ai-update / ai-regenerate are rework on
    # the same costed story, and their usage SHOULD accumulate.
    # Best-effort — never fails the run.
    if not dry_run:
        from core.usage_ledger import has_usage_comments, post_reset_to_story
        try:
            if has_usage_comments(jira.get_comments(story_id)):
                logger.info(
                    f"{story_id} already has usage entries from a previous run — "
                    "posting ledger reset boundary."
                )
                post_reset_to_story(
                    story_id,
                    reason="story reprocessed from ai-ready",
                    jira=jira,
                )
        except Exception as e:
            logger.warning(
                f"Usage ledger: reset check failed for {story_id}: "
                f"{type(e).__name__}: {e}. Non-fatal — continuing."
            )

    # IMPACT-AWARE MODE (Agent 0 design, C3). A story whose Impact Review
    # approved existing test cases carries Impacts links to them; it revises
    # those in place and drafts new ones only for uncovered criteria. A story
    # with no impacted cases - every story today - continues below unchanged.
    impacted = _impacted_test_cases(jira, story_id)
    if impacted:
        from agents.agent1_impact import run_impact_aware
        logger.info(f"{story_id} impacts {len(impacted)} approved test case(s): "
                    f"impact-aware mode")
        llm = LLMClient(temperature=0.3, max_output_tokens=12288)
        result = run_impact_aware(
            jira, story_id, story,
            {"app_name": ctx.name, "app_base_url": ctx.base_url,
             "app_context": load_app_context_block(story.get("components")),
             "story_text": story_text},
            llm, dry_run, load_agent_config())
        from core.llm_client import log_usage_summary, reset_usage
        result["llm_usage"] = log_usage_summary(f"story {story_id} (analyst, impact-aware)")
        reset_usage()
        if not dry_run:
            from core.usage_ledger import post_usage_to_story
            post_usage_to_story(story_id, "Agent 1 (Test Designer)", result["llm_usage"], jira=jira)
        logger.info(f"=== Agent 1 (Test Designer) complete for {story_id}: revised "
                    f"{result['revised']}, created {result['test_case_keys']} ===")
        return result

    # 2. REASON: call LLM with structured output
    prompt_template = load_prompt()
    # Pass the story's Jira Components so module-wise app context (backlog 2.1)
    # injects only the relevant module files. Harmless in single-file mode — the
    # components arg is simply ignored there.
    app_context_block = load_app_context_block(story.get("components"))
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{app_base_url}", ctx.base_url)
        .replace("{app_context}", app_context_block)
        .replace("{story_text}", story_text)
    )

    # max_output_tokens=12288 (not the default 4096): a TestCaseList of 7
    # detailed test cases (each with 5-10 steps carrying action + expected
    # result) runs ~2,800-4,200 tokens — only ~1x headroom at 4096, and ~2x at
    # 8192. A verbose story or a raised TC-count target in the prompt could
    # truncate mid-JSON, which fails the Pydantic parse and burns a retry.
    # 12288 restores the ~3x headroom the other caps carry.
    # NOTE: if you raise the "3-7 test cases" target in
    # prompts/agent1_analyst.md, revisit this cap in the same commit.
    llm = LLMClient(temperature=0.3, max_output_tokens=12288)
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
        # Board hygiene: follow the label with a column move so the card
        # reflects real progress. Opt-in via config; never fatal.
        move_card_for_label(jira, story_id, completion_label)

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
    from core.llm_client import log_usage_summary, reset_usage
    usage = log_usage_summary(f"story {story_id} (analyst)")
    reset_usage()  # per-story numbers in scan mode
    if not dry_run:
        from core.usage_ledger import post_usage_to_story
        post_usage_to_story(story_id, "Agent 1 (Test Designer)", usage, jira=jira)

    result = {
        "story_id": story_id,
        "story_summary": story["summary"],
        "test_cases_generated": len(test_case_list.test_cases),
        "test_case_keys": created_keys,
        "status": "tests_drafted" if not dry_run else "tests_drafted_dry_run",
        "llm_usage": usage,
    }

    logger.info(f"=== Agent 1 (Test Designer) complete for {story_id}. Created: {created_keys} ===")
    return result


# ─────────────────────────────────────────────────────────────
# CLI entrypoint
# ─────────────────────────────────────────────────────────────
def print_summary(results: list[dict]) -> None:
    """Pretty-print a summary of all stories processed."""
    print("\n" + "=" * 60)
    print(f"✅ Agent 1 (Test Designer) finished — processed {len(results)} story(ies)")
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
        description="Agent 1 (Test Designer): Generate manual test cases from Jira stories",
        epilog=("examples:\n  one story          --story SCRUM-5\n  scan for ai-ready  (no flags - uses config.yaml selection rules)\n  preview only       --story SCRUM-5 --dry-run\n\nNOTE: --story has no re-processing guard. Running it twice on the same\nstory creates DUPLICATE test cases in Jira."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
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

        jira = get_tracker()
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
        logger.error(f"Agent 1 (Test Designer) failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()