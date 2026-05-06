"""
Agent 2 — Coder.

Role:
    Reads approved Test Cases from Jira, uses an LLM to generate Playwright +
    BDD + POM automation code, and opens a Pull Request on GitHub.

Architecture (TWO-STAGE):
    STAGE 1: Plan — LLM produces a CodePlan (structured): file paths, types,
             purposes, PR title, branch name. NO code content yet.
    STAGE 2: Generate — for EACH file in the plan, make a separate LLM call
             (text mode) to produce that file's content. Extract code from
             the response (handles markdown fences).

Defenses:
    - Reserved-path guard: refuses to overwrite reference files even if the
      LLM plans to. Reserved paths come from app_under_test config — NOT
      hardcoded — so the framework works for any app.
    - Filename-consistency validator: catches mismatches between feature
      file names and step-def feature_path() arguments.
    - Step-definition coverage validator: catches Gherkin steps without
      matching @given/@when/@then decorators.
    - Branch-name validator: ensures every PR branch contains a Jira key.
    - Dry-run mode: preview without touching GitHub.
    - Windows-safe printing: ASCII-only output (no emoji) to work in cp1252.

Usage:
    python -m agents.agent2_coder --story SCRUM-5 --dry-run
    python -m agents.agent2_coder --story SCRUM-5
    python -m agents.agent2_coder --scan
"""
import argparse
import logging
import re
import sys
import yaml

from agents.app_context import AppContext
from agents.jira_client import JiraClient
from agents.github_client import GitHubClient
from agents.llm_client import LLMClient
from agents.schemas import CodePlan, GeneratedFile, CodeGenerationOutput
from agents.test_inventory import (
    scan_features_dir,
    filter_duplicate_test_cases,
    validate_filename_consistency,
    validate_step_definitions_complete,
)
from config import (
    REQUIRED_GITHUB_ENV_VARS,
    REQUIRED_JIRA_ENV_VARS,
    REQUIRED_LLM_ENV_VARS,
    assert_valid_branch_for_pipeline,
    validate_required_env,
)
from config.paths import PROMPTS_DIR, CONFIG_YAML, FEATURES_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent2_coder")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _normalize_path(p: str) -> str:
    """Convert backslashes to forward slashes and strip leading ./ for comparison."""
    return p.replace("\\", "/").lstrip("./")


def validate_no_reserved_paths(plan: CodePlan, ctx: AppContext) -> None:
    """Raise ValueError if the plan tries to modify any reserved file.

    Reserved paths come from `app_under_test.reserved_paths` in config.yaml,
    so this check stays correct regardless of which app is being tested.
    """
    reserved = ctx.reserved_paths_normalized()
    collisions = [
        fp.file_path for fp in plan.files_to_create
        if _normalize_path(fp.file_path) in reserved
    ]
    if collisions:
        raise ValueError(
            f"LLM tried to overwrite reserved reference files: {collisions}. "
            f"These files are protected by app_under_test.reserved_paths in "
            f"config.yaml. The LLM should have used different file paths "
            f"(e.g., 'features/<theme>-validation.feature' instead of an "
            f"existing reference file). Consider tightening the prompt."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")


def load_test_cases_for_story(jira: JiraClient, story_key: str) -> list[dict]:
    jql = (
        f'project = {jira.project_key} AND issuetype = "Test Case" '
        f'AND issue in linkedIssues("{story_key}")'
    )
    logger.info(f"Fetching test cases linked to {story_key}: {jql}")
    issues = jira.client.enhanced_search_issues(jql, maxResults=50)

    test_cases = [
        {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
        }
        for issue in issues
    ]
    logger.info(f"Found {len(test_cases)} test cases linked to {story_key}")
    return test_cases


def format_test_cases_for_prompt(test_cases: list[dict]) -> str:
    blocks = [
        f"## {tc['key']}: {tc['summary']}\n\n{tc['description']}\n"
        for tc in test_cases
    ]
    return "\n---\n".join(blocks)


def extract_code_from_response(response_text: str) -> str:
    """Extract code from a markdown response. Handles fenced and bare code."""
    pattern = r"```(?:\w+)?\n?(.*?)```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    if matches:
        return matches[0].strip() + "\n"
    return response_text.strip() + "\n"


def load_agent_config(agent_key: str = "agent2_coder") -> dict:
    with open(CONFIG_YAML) as f:
        full_config = yaml.safe_load(f)
    return full_config.get("agents", {}).get(agent_key, {})


def _build_reserved_paths_block(ctx: AppContext) -> str:
    """Render the reserved-paths list as a markdown bullet block for the
    Stage 1 plan prompt."""
    return "\n".join(f"- `{p}` -- RESERVED" for p in ctx.reserved_paths)


# ---------------------------------------------------------------------------
# STAGE 1: Build the plan
# ---------------------------------------------------------------------------
def build_plan(
    llm: LLMClient,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
) -> CodePlan:
    """Stage 1: Get a structured plan describing what files to create. NO code yet."""
    prompt_template = load_prompt("agent2_coder_plan.md")
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{reserved_paths_block}", _build_reserved_paths_block(ctx))
        .replace("{reference_feature_path}", ctx.reference_feature)
        .replace("{reference_step_def_path}", ctx.reference_step_def)
        .replace("{reference_page_object_path}", ctx.reference_page_object)
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{test_cases_text}", format_test_cases_for_prompt(test_cases))
    )

    prompt_chars = len(user_prompt)
    logger.info(
        f"Stage 1 (plan) prompt size: {prompt_chars:,} chars "
        f"(~{prompt_chars // 4:,} tokens)"
    )

    plan: CodePlan = llm.invoke_structured(
        system_prompt="You are a Senior Test Automation Engineer (SDET).",
        user_prompt=user_prompt,
        output_schema=CodePlan,
    )

    logger.info(f"Stage 1 complete: {len(plan.files_to_create)} files planned")
    for fp in plan.files_to_create:
        logger.info(f"  - {fp.file_path} [{fp.file_type}] -- {fp.purpose}")

    # Defensive guard: refuse if the LLM planned to overwrite reference files
    validate_no_reserved_paths(plan, ctx)
    return plan


# ---------------------------------------------------------------------------
# STAGE 2: Generate each file's content
# ---------------------------------------------------------------------------
def generate_file_content(
    llm: LLMClient,
    file_plan,
    plan: CodePlan,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
) -> str:
    """Stage 2: For ONE file in the plan, get its full content as raw text."""
    related_test_cases = [
        tc for tc in test_cases if tc["key"] in file_plan.related_test_cases
    ]
    if not related_test_cases:
        related_test_cases = test_cases

    prompt_template = load_prompt("agent2_coder_generate.md")
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{file_path}", file_plan.file_path)
        .replace("{file_type}", file_plan.file_type)
        .replace("{file_purpose}", file_plan.purpose)
        .replace("{feature_name}", plan.feature_name)
        .replace("{reference_feature_path}", ctx.reference_feature)
        .replace("{reference_step_def_path}", ctx.reference_step_def)
        .replace("{reference_page_object_path}", ctx.reference_page_object)
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{test_cases_text}", format_test_cases_for_prompt(related_test_cases))
    )

    logger.info(f"Stage 2: generating content for {file_plan.file_path}...")
    response = llm.invoke_text(
        system_prompt="You are a Senior Test Automation Engineer (SDET). Produce complete, working code.",
        user_prompt=user_prompt,
    )
    content = extract_code_from_response(response)
    logger.info(f"  Generated {len(content)} chars for {file_plan.file_path}")
    return content


# ---------------------------------------------------------------------------
# Helpers for the run() workflow — extracted to keep run() readable
# ---------------------------------------------------------------------------
def _select_new_test_cases(
    test_cases: list[dict],
    is_regenerate: bool,
) -> tuple[list[dict], list[dict]]:
    """Filter out test cases already covered by existing scenarios.

    Returns (new_test_cases, skipped_test_cases). In regenerate mode, dedup
    is bypassed and all test cases are returned as new.
    """
    if is_regenerate:
        logger.info(
            f"Regeneration mode: bypassing dedup check. "
            f"All {len(test_cases)} test cases will be regenerated from scratch."
        )
        return test_cases, []

    inventory = scan_features_dir(FEATURES_DIR)
    new_cases, skipped = filter_duplicate_test_cases(test_cases, inventory)

    if skipped:
        logger.info(
            f"Dedup: {len(skipped)} of {len(test_cases)} test cases "
            f"already covered by existing scenarios. Skipping these."
        )
        for skip in skipped:
            tc = skip["test_case"]
            logger.info(
                f"  - {tc.get('key', '?')}: '{tc.get('summary', '?')}' "
                f"already covered by '{skip['matched_scenario']}' "
                f"in {skip['matched_file']}"
            )

    return new_cases, skipped


def _validate_generated_files(
    generated_files: list[GeneratedFile],
    story_id: str,
) -> None:
    """Run filename-consistency and step-def coverage validators.

    These catch the two failure modes Agent 2 has historically had:
      - PR #7: kebab-case feature filename vs snake_case feature_path() ref
      - PR #9: feature steps without matching @given/@when/@then decorators

    Raises ValueError if either validator finds problems.
    """
    consistency_errors = validate_filename_consistency(generated_files)
    if consistency_errors:
        logger.error(
            f"Filename consistency check FAILED with "
            f"{len(consistency_errors)} error(s):"
        )
        for err in consistency_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Filename consistency validation failed for {story_id}: "
            f"{len(consistency_errors)} mismatch(es) between feature files "
            f"and step definitions. See logs for details."
        )

    coverage_errors = validate_step_definitions_complete(generated_files)
    if coverage_errors:
        logger.error(
            f"Step definition coverage check FAILED with "
            f"{len(coverage_errors)} error(s):"
        )
        for err in coverage_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Step definition coverage validation failed for {story_id}: "
            f"{len(coverage_errors)} feature step(s) without matching "
            f"@given/@when/@then decorator(s). See logs for details."
        )


def _print_dry_run_preview(output: CodeGenerationOutput) -> None:
    """ASCII-safe preview of generated code (Windows cp1252 compatible)."""
    print("\n" + "=" * 60)
    print("DRY RUN -- Generated code preview")
    print("=" * 60)
    print(f"\n[Branch]    {output.branch_name}")
    print(f"[PR Title]  {output.pr_title}")
    print(f"[Feature]   {output.feature_name}")

    print(f"\n[PR Body]")
    print("-" * 60)
    print(output.pr_body.encode("ascii", "replace").decode("ascii"))

    if output.notes:
        print(f"\n[Notes from LLM]")
        print("-" * 60)
        print(output.notes.encode("ascii", "replace").decode("ascii"))

    for f in output.files:
        print(f"\n{'=' * 60}")
        status = "NEW" if f.is_new_file else "UPDATE"
        print(f"[FILE]  {f.file_path}  ({status})")
        if f.purpose:
            print(f"   Purpose: {f.purpose.encode('ascii', 'replace').decode('ascii')}")
        print(f"   Size: {len(f.content)} chars")
        print(f"   Preview (first 30 lines):")
        print(f"{'-' * 60}")
        lines = f.content.split("\n")
        for i, line in enumerate(lines[:30], 1):
            safe_line = line.encode("ascii", "replace").decode("ascii")
            print(f"   {i:3} | {safe_line}")
        if len(lines) > 30:
            print(f"   ... (and {len(lines) - 30} more lines)")


def _resolve_unused_revision_branch(gh: GitHubClient, base_branch: str) -> str:
    """Find the lowest unused -revN suffix for a regeneration branch.

    Starts from rev2 (rev1 = original). Used so the original PR stays open
    as historical record while the regen creates a new branch + PR.
    """
    rev_n = 2
    while gh.branch_exists(f"{base_branch}-rev{rev_n}"):
        rev_n += 1
    return f"{base_branch}-rev{rev_n}"


# ---------------------------------------------------------------------------
# Core agent workflow
# ---------------------------------------------------------------------------
def run(story_id: str, dry_run: bool = False, is_regenerate: bool = False) -> dict:
    """Main agent flow — Stage 1 plan, then Stage 2 per-file generation.

    Args:
        story_id: Jira story key (e.g., "SCRUM-5")
        dry_run: If True, don't create branch/commits/PR. Print preview.
        is_regenerate: If True, this is a REGENERATION run triggered by the
            `ai-regenerate` label. Skips dedup, uses -revN branch suffix,
            removes the regenerate label after success.
    """
    mode_label = "REGENERATE" if is_regenerate else "normal"
    logger.info(
        f"=== Agent 2 (Coder) starting for {story_id} "
        f"(mode={mode_label}, dry_run={dry_run}) ==="
    )

    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name} ({ctx.base_url})")

    # 1. INPUT
    jira = JiraClient()
    jira.get_story(story_id)
    test_cases = load_test_cases_for_story(jira, story_id)

    if not test_cases:
        logger.warning(f"No Test Cases linked to {story_id}. Run Agent 1 first.")
        return {"story_id": story_id, "status": "no_test_cases", "files_generated": 0}

    # 1b. DEDUP (skipped in regenerate mode)
    new_test_cases, skipped_test_cases = _select_new_test_cases(test_cases, is_regenerate)

    if not new_test_cases:
        # Every approved test case is already covered. No work needed.
        logger.info(
            f"All {len(test_cases)} test cases for {story_id} are already covered "
            "by existing scenarios. No new code generation needed."
        )
        if not dry_run:
            agent_config = load_agent_config()
            completion_label = agent_config.get("completion_label", "ai-coded")
            jira.add_label(story_id, completion_label)
            logger.info(f"Marked {story_id} with label '{completion_label}' (no work needed)")
        return {
            "story_id": story_id,
            "status": "skipped_all_duplicates",
            "files_generated": 0,
            "skipped_count": len(skipped_test_cases),
        }

    if len(new_test_cases) < len(test_cases):
        logger.info(
            f"Generating code for {len(new_test_cases)} new case(s); "
            f"{len(skipped_test_cases)} skipped as duplicates."
        )

    # 2. CONTEXT — read references and inventory once
    references = ctx.load_reference_files()
    page_inventory = ctx.load_page_inventory_json()
    llm = LLMClient(temperature=0.2)

    # 3. STAGE 1: PLAN
    plan = build_plan(llm, new_test_cases, references, page_inventory, ctx)

    # 4. STAGE 2: GENERATE PER-FILE CONTENT
    generated_files: list[GeneratedFile] = []
    for file_plan in plan.files_to_create:
        try:
            content = generate_file_content(
                llm, file_plan, plan, new_test_cases, references, page_inventory, ctx,
            )
            generated_files.append(GeneratedFile(
                file_path=file_plan.file_path,
                content=content,
                is_new_file=file_plan.is_new_file,
                purpose=file_plan.purpose,
            ))
        except Exception as e:
            logger.error(f"Failed to generate {file_plan.file_path}: {e}")
            raise

    output = CodeGenerationOutput(
        feature_name=plan.feature_name,
        branch_name=plan.branch_name,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        files=generated_files,
        notes=plan.notes,
    )

    # 4b. VALIDATORS
    _validate_generated_files(generated_files, story_id)

    # 5. ACT
    if dry_run:
        logger.warning("DRY RUN -- skipping branch/commit/PR creation")
        _print_dry_run_preview(output)
        return {
            "story_id": story_id,
            "files_generated": len(output.files),
            "status": "code_generated_dry_run",
        }

    # Real run — branch must contain a Jira key for downstream agents to work
    assert_valid_branch_for_pipeline(output.branch_name)

    gh = GitHubClient()

    # REGENERATE: append -revN suffix so we don't reuse the existing branch.
    if is_regenerate:
        new_branch_name = _resolve_unused_revision_branch(gh, output.branch_name)
        logger.info(
            f"Regeneration: changed branch from '{output.branch_name}' to "
            f"'{new_branch_name}' to preserve old PR as historical record"
        )
        output.branch_name = new_branch_name

    gh.create_branch(output.branch_name, from_branch="main")

    for f in output.files:
        commit_msg = f"[Agent 2] {'Add' if f.is_new_file else 'Update'} {f.file_path}"
        gh.create_or_update_file(
            path=f.file_path,
            content=f.content,
            commit_message=commit_msg,
            branch=output.branch_name,
        )

    pr_body_with_footer = (
        output.pr_body
        + f"\n\n---\n*This PR was automatically generated by Agent 2 (Coder) from {story_id}.*"
    )
    pr_url = gh.open_pull_request(
        title=output.pr_title,
        body=pr_body_with_footer,
        head_branch=output.branch_name,
        base_branch="main",
    )

    # Idempotency markers: tag the parent story so the next --scan run skips it.
    agent_config = load_agent_config()
    completion_label = agent_config.get("completion_label", "ai-coded")
    jira.add_label(story_id, completion_label)
    logger.info(f"Marked {story_id} with label '{completion_label}' (idempotency)")

    if is_regenerate:
        regenerate_label = agent_config.get("regenerate_label", "ai-regenerate")
        jira.remove_label(story_id, regenerate_label)
        logger.info(f"Removed label '{regenerate_label}' from {story_id} (one-shot consumed)")

    result = {
        "story_id": story_id,
        "files_generated": len(output.files),
        "branch_name": output.branch_name,
        "pr_url": pr_url,
        "status": "pr_opened",
    }

    logger.info(f"=== Agent 2 (Coder) complete. PR: {pr_url} ===")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_scan_summary(results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print(f"[OK] Agent 2 scan finished -- processed {len(results)} stories")
    for r in results:
        status = r.get("status", "unknown")
        if status == "pr_opened":
            marker = "OK"
        elif status == "skipped_all_duplicates":
            marker = "SKIP"
        elif status == "failed":
            marker = "FAIL"
        else:
            marker = "??"
        pr_info = f" -> {r.get('pr_url')}" if r.get("pr_url") else ""
        print(f"   [{marker}] {r.get('story_id')}: {status}{pr_info}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Agent 2 (Coder): Generate test code from Jira test cases"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--story", help="Process all test cases of a specific story")
    group.add_argument("--scan", action="store_true", help="Scan mode (config-driven)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't create branch/PR, just preview")
    args = parser.parse_args()

    # Fast-fail on missing config — much clearer than a 401 deep in a tool call
    validate_required_env(
        REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS + REQUIRED_GITHUB_ENV_VARS
    )

    try:
        if args.story:
            result = run(args.story, dry_run=args.dry_run)
            print("\n" + "=" * 60)
            print(f"[OK] Agent 2 finished -- story: {result['story_id']}")
            print(f"   Files generated: {result.get('files_generated', 0)}")
            print(f"   Status: {result['status']}")
            if result.get("pr_url"):
                print(f"   PR: {result['pr_url']}")
            print("=" * 60)
            return

        # Scan mode: two passes (normal + regenerate).
        agent_config = load_agent_config()
        normal_selection = agent_config.get("selection", {})
        regen_selection = agent_config.get("regenerate_selection", {})
        max_stories = agent_config.get("max_stories_per_run", 5)

        if not normal_selection:
            logger.error(
                "No 'selection' config found for agent2_coder in config.yaml. "
                "Add an 'agents.agent2_coder.selection' block or use --story KEY instead."
            )
            sys.exit(1)

        jira = JiraClient()

        logger.info("Scan pass 1/2: looking for first-time stories (normal mode)")
        normal_stories = jira.find_stories_to_process(normal_selection, max_results=max_stories)

        regen_stories = []
        if regen_selection:
            logger.info("Scan pass 2/2: looking for stories with ai-regenerate label")
            regen_stories = jira.find_stories_to_process(regen_selection, max_results=max_stories)
        else:
            logger.info(
                "No 'regenerate_selection' config — skipping regen pass. "
                "Add 'agents.agent2_coder.regenerate_selection' to enable."
            )

        total_count = len(normal_stories) + len(regen_stories)
        if total_count == 0:
            logger.info(
                f"No stories found. "
                f"Normal: required={normal_selection.get('required_labels', [])}, "
                f"excluded={normal_selection.get('excluded_labels', [])}. "
                f"Regen requires 'ai-regenerate'. "
                f"Tip: ensure parent story has 'ai-processed' AND 'human-approved' labels."
            )
            print("\n[OK] Agent 2 scan complete -- no stories to process.")
            sys.exit(0)

        logger.info(
            f"Found {len(normal_stories)} normal + {len(regen_stories)} regen "
            f"= {total_count} stories to process."
        )

        results = []
        for story in normal_stories:
            try:
                result = run(story["key"], dry_run=args.dry_run, is_regenerate=False)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']} (normal): {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "status": "failed",
                    "mode": "normal",
                    "error": str(e),
                })

        for story in regen_stories:
            if any(r.get("story_id") == story["key"] for r in results):
                logger.warning(
                    f"Skipping {story['key']} in regen pass — already processed in normal pass. "
                    "Check config: regenerate_selection should require ai-regenerate label."
                )
                continue
            try:
                result = run(story["key"], dry_run=args.dry_run, is_regenerate=True)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']} (regen): {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "status": "failed",
                    "mode": "regenerate",
                    "error": str(e),
                })

        _print_scan_summary(results)

    except Exception as e:
        logger.error(f"Agent 2 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
