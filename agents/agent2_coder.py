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
    - Reserved-path guard: refuses to overwrite reference files even if
      the LLM plans to.
    - Dry-run mode: preview without touching GitHub.
    - Windows-safe printing: ASCII-only output (no emoji) to work in cp1252.

Usage:
    python -m agents.agent2_coder --story SCRUM-5 --dry-run
    python -m agents.agent2_coder --story SCRUM-5
"""
import argparse
import logging
import re
import sys
import yaml

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
from config.paths import PROMPTS_DIR, CONFIG_YAML, PROJECT_ROOT, FEATURES_DIR

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent2_coder")


# ---------------------------------------------------------------------------
# Reserved paths — these belong to the Day 2 reference test suite and must
# never be overwritten by Agent 2. If the LLM plans to touch them, we abort.
# ---------------------------------------------------------------------------
RESERVED_PATHS = {
    "features/login.feature",
    "tests/step_defs/test_login.py",
    "pages/login_page.py",
    "pages/inventory_page.py",
    "pages/base_page.py",
}


def normalize_path(p: str) -> str:
    """Convert backslashes to forward slashes and strip leading ./ for comparison."""
    p = p.replace("\\", "/").lstrip("./")
    return p


def validate_no_reserved_paths(plan: CodePlan) -> None:
    """Raise ValueError if the plan tries to modify reference files."""
    collisions = []
    for fp in plan.files_to_create:
        if normalize_path(fp.file_path) in RESERVED_PATHS:
            collisions.append(fp.file_path)
    if collisions:
        raise ValueError(
            f"LLM tried to overwrite reserved reference files: {collisions}. "
            f"These files are protected. The LLM should have used different "
            f"file paths (e.g., 'features/login-validation.feature' instead "
            f"of 'features/login.feature'). Consider tightening the prompt."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")


def load_reference_files() -> dict:
    """Read the Day 2 reference files that the LLM will mimic."""
    files = {
        "feature": PROJECT_ROOT / "features" / "login.feature",
        "step_def": PROJECT_ROOT / "tests" / "step_defs" / "test_login.py",
        "page_object": PROJECT_ROOT / "pages" / "login_page.py",
    }
    return {key: path.read_text(encoding="utf-8") for key, path in files.items()}


def load_page_inventory() -> str:
    inventory_path = PROJECT_ROOT / "app_inventory" / "saucedemo.json"
    return inventory_path.read_text(encoding="utf-8")


def load_test_cases_for_story(jira: JiraClient, story_key: str) -> list[dict]:
    jql = f'project = {jira.project_key} AND issuetype = "Test Case" AND issue in linkedIssues("{story_key}")'
    logger.info(f"Fetching test cases linked to {story_key}: {jql}")
    issues = jira.client.enhanced_search_issues(jql, maxResults=50)

    test_cases = []
    for issue in issues:
        test_cases.append({
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
        })
    logger.info(f"Found {len(test_cases)} test cases linked to {story_key}")
    return test_cases


def format_test_cases_for_prompt(test_cases: list[dict]) -> str:
    blocks = []
    for tc in test_cases:
        blocks.append(f"## {tc['key']}: {tc['summary']}\n\n{tc['description']}\n")
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


# ---------------------------------------------------------------------------
# STAGE 1: Build the plan
# ---------------------------------------------------------------------------
def build_plan(
    llm: LLMClient,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
) -> CodePlan:
    """Stage 1: Get a structured plan describing what files to create. NO code yet."""
    prompt_template = load_prompt("agent2_coder_plan.md")
    user_prompt = (
        prompt_template
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{test_cases_text}", format_test_cases_for_prompt(test_cases))
    )

    prompt_chars = len(user_prompt)
    logger.info(f"Stage 1 (plan) prompt size: {prompt_chars:,} chars (~{prompt_chars // 4:,} tokens)")

    plan: CodePlan = llm.invoke_structured(
        system_prompt="You are a Senior Test Automation Engineer (SDET).",
        user_prompt=user_prompt,
        output_schema=CodePlan,
    )

    logger.info(f"Stage 1 complete: {len(plan.files_to_create)} files planned")
    for fp in plan.files_to_create:
        logger.info(f"  - {fp.file_path} [{fp.file_type}] -- {fp.purpose}")

    # Defensive guard: refuse if the LLM planned to overwrite reference files
    validate_no_reserved_paths(plan)
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
) -> str:
    """Stage 2: For ONE file in the plan, get its full content as raw text."""
    related_test_cases = [tc for tc in test_cases if tc["key"] in file_plan.related_test_cases]
    if not related_test_cases:
        related_test_cases = test_cases

    prompt_template = load_prompt("agent2_coder_generate.md")
    user_prompt = (
        prompt_template
        .replace("{file_path}", file_plan.file_path)
        .replace("{file_type}", file_plan.file_type)
        .replace("{file_purpose}", file_plan.purpose)
        .replace("{feature_name}", plan.feature_name)
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
# Core agent workflow
# ---------------------------------------------------------------------------
def run(story_id: str, dry_run: bool = False, is_regenerate: bool = False) -> dict:
    """Main agent flow — Stage 1 plan, then Stage 2 per-file generation.

    Args:
        story_id: Jira story key (e.g., "SCRUM-5")
        dry_run: If True, don't create branch/commits/PR. Print preview.
        is_regenerate: If True, this is a REGENERATION run triggered by the
            `ai-regenerate` label. Behavior changes:
              - Dedup check is SKIPPED (LLM regenerates everything fresh)
              - Branch name gets a `-revN` suffix (preserves old PR)
              - On success: removes `ai-regenerate` label (one-shot signal)
              - On success: still adds `ai-coded` (back to normal state)
    """
    mode_label = "REGENERATE" if is_regenerate else "normal"
    logger.info(f"=== Agent 2 (Coder) starting for {story_id} (mode={mode_label}, dry_run={dry_run}) ===")

    # 1. INPUT
    jira = JiraClient()
    jira.get_story(story_id)
    test_cases = load_test_cases_for_story(jira, story_id)

    if not test_cases:
        logger.warning(f"No Test Cases linked to {story_id}. Run Agent 1 first.")
        return {"story_id": story_id, "status": "no_test_cases", "files_generated": 0}

    # 1b. DEDUPLICATION CHECK
    # Before spending LLM tokens, check if any test cases are already covered
    # by existing scenarios in features/. This solves the duplicate-coverage
    # problem we saw on PR #7 where Agent 2 generated `login-validation.feature`
    # alongside the existing `login.feature`.
    #
    # Three outcomes:
    #   - All test cases new → continue with full flow (no change from before)
    #   - Some duplicates    → log them, continue with only new cases
    #   - All duplicates     → skip PR creation entirely, mark ai-coded
    #
    # REGENERATE BYPASS:
    #   When is_regenerate=True, the user explicitly asked for fresh code
    #   even if scenarios already exist. We skip the inventory scan entirely
    #   and treat all test cases as "new". This is the simplest, safest
    #   implementation — no special-case branches in the filter logic.
    if is_regenerate:
        logger.info(
            f"Regeneration mode: bypassing dedup check. All {len(test_cases)} "
            "test cases will be regenerated from scratch."
        )
        new_test_cases = test_cases
        skipped_test_cases = []
    else:
        inventory = scan_features_dir(FEATURES_DIR)
        new_test_cases, skipped_test_cases = filter_duplicate_test_cases(test_cases, inventory)

    if skipped_test_cases:
        logger.info(
            f"Dedup: {len(skipped_test_cases)} of {len(test_cases)} test cases "
            f"already covered by existing scenarios. Skipping these."
        )
        for skip in skipped_test_cases:
            tc = skip["test_case"]
            logger.info(
                f"  - {tc.get('key', '?')}: '{tc.get('summary', '?')}' "
                f"already covered by '{skip['matched_scenario']}' "
                f"in {skip['matched_file']}"
            )

    if not new_test_cases:
        # Every approved test case is already covered. The honest thing is
        # to do nothing — no PR needed, no LLM cost wasted. We still mark
        # the parent story 'ai-coded' so it doesn't keep coming back in scans.
        logger.info(
            f"All {len(test_cases)} test cases for {story_id} are already covered "
            "by existing scenarios. No new code generation needed."
        )

        if not dry_run:
            config = load_agent_config()
            completion_label = config.get("completion_label", "ai-coded")
            jira.add_label(story_id, completion_label)
            logger.info(f"Marked {story_id} with label '{completion_label}' (no work needed)")

        return {
            "story_id": story_id,
            "status": "skipped_all_duplicates",
            "files_generated": 0,
            "skipped_count": len(skipped_test_cases),
        }

    # From here on, use new_test_cases instead of test_cases — the LLM only
    # needs to know about cases that need code. Sending duplicates would
    # waste tokens AND risk the LLM regenerating them anyway.
    if len(new_test_cases) < len(test_cases):
        logger.info(
            f"Generating code for {len(new_test_cases)} new case(s); "
            f"{len(skipped_test_cases)} skipped as duplicates."
        )

    # 2. CONTEXT
    references = load_reference_files()
    page_inventory = load_page_inventory()
    llm = LLMClient(temperature=0.2)

    # 3. STAGE 1
    plan = build_plan(llm, new_test_cases, references, page_inventory)

    # 4. STAGE 2
    generated_files: list[GeneratedFile] = []
    for file_plan in plan.files_to_create:
        try:
            content = generate_file_content(
                llm, file_plan, plan, new_test_cases, references, page_inventory
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

    # 4b. VALIDATE FILENAME CONSISTENCY
    # Catches the bug we hit on PR #7 where the LLM generated:
    #   features/login-validation.feature   (kebab-case)
    #   test_login_validation.py uses feature_path("login_validation") (snake_case)
    # which made pytest-bdd fail with FileNotFoundError at test collection.
    #
    # The prompt was updated in Phase 4 to enforce snake_case throughout,
    # but LLMs occasionally drift. Validating here is defense-in-depth —
    # we'd rather fail loudly NOW than ship a broken PR.
    consistency_errors = validate_filename_consistency(generated_files)
    if consistency_errors:
        logger.error(f"Filename consistency check FAILED with {len(consistency_errors)} error(s):")
        for err in consistency_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Filename consistency validation failed for {story_id}: "
            f"{len(consistency_errors)} mismatch(es) between feature files "
            f"and step definitions. See logs for details. The LLM produced "
            f"step defs that reference feature files not in this batch -- "
            f"opening this PR would create immediately-broken tests."
        )

    # PHASE 8: Step Definition Coverage Validator (ADR-010)
    # ----------------------------------------------------------------
    # The PR #9 incident: the LLM generated a feature file with step
    # phrases, but forgot to generate matching @given/@when/@then
    # decorators in the step def file. Tests then failed at collection
    # time with `StepDefinitionNotFoundError`.
    #
    # This validator pairs each generated .feature file with its
    # corresponding test_*.py and verifies every Gherkin step has a
    # matching decorator. Hard-fails if any step is uncovered.
    #
    # Reusable across projects -- understands pytest-bdd's grammar
    # (And/But inheritance, parsers.parse() placeholders, etc.) with
    # no domain-specific assumptions.
    coverage_errors = validate_step_definitions_complete(generated_files)
    if coverage_errors:
        logger.error(f"Step definition coverage check FAILED with {len(coverage_errors)} error(s):")
        for err in coverage_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Step definition coverage validation failed for {story_id}: "
            f"{len(coverage_errors)} feature step(s) without matching "
            f"@given/@when/@then decorator(s). See logs for details. "
            f"The LLM produced a feature file with step phrases that have "
            f"no corresponding step definitions -- opening this PR would "
            f"create tests that fail at collection time with "
            f"StepDefinitionNotFoundError."
        )

    # 5. ACT
    if dry_run:
        logger.warning("DRY RUN -- skipping branch/commit/PR creation")
        # NOTE: All print output below uses ASCII-only (no emoji) to be
        # compatible with Windows PowerShell's default cp1252 codepage.
        print("\n" + "=" * 60)
        print("DRY RUN -- Generated code preview")
        print("=" * 60)
        print(f"\n[Branch]    {output.branch_name}")
        print(f"[PR Title]  {output.pr_title}")
        print(f"[Feature]   {output.feature_name}")

        print(f"\n[PR Body]")
        print("-" * 60)
        # Strip any non-cp1252 chars from LLM output for safe printing
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
                # Replace any non-printable chars for safe terminal output
                safe_line = line.encode("ascii", "replace").decode("ascii")
                print(f"   {i:3} | {safe_line}")
            if len(lines) > 30:
                print(f"   ... (and {len(lines) - 30} more lines)")

        return {
            "story_id": story_id,
            "files_generated": len(output.files),
            "status": "code_generated_dry_run",
        }

    # Real run
    # Validate that the LLM generated a branch name with a Jira key in it.
    # Without a key in the branch, Agent 5 (Reporter) won't be able to
    # post results back to the right Jira story. Better to catch this
    # NOW (before pushing) than to have a silent gap downstream.
    from config import assert_valid_branch_for_pipeline
    assert_valid_branch_for_pipeline(output.branch_name)

    gh = GitHubClient()

    # REGENERATE: append -revN suffix so we don't reuse the existing branch.
    # This preserves the old PR as historical record (user closes manually).
    # We find the lowest unused N starting from 2 (rev1 = original).
    if is_regenerate:
        base_branch = output.branch_name
        rev_n = 2
        while gh.branch_exists(f"{base_branch}-rev{rev_n}"):
            rev_n += 1
        new_branch_name = f"{base_branch}-rev{rev_n}"
        logger.info(
            f"Regeneration: changed branch from '{base_branch}' to "
            f"'{new_branch_name}' to preserve old PR as historical record"
        )
        # Update output so all downstream uses match (commits, PR head)
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

    # Idempotency marker: tag the parent story so the next --scan run skips it.
    # Without this, every scheduled scan would re-process the same approved
    # story over and over (wasting LLM tokens and creating duplicate PRs).
    # Reads completion_label from config so it stays consistent with the
    # excluded_labels filter that find_stories_to_process() uses.
    config = load_agent_config()
    completion_label = config.get("completion_label", "ai-coded")
    jira.add_label(story_id, completion_label)
    logger.info(f"Marked {story_id} with label '{completion_label}' (idempotency)")

    # REGENERATE: clean up the ai-regenerate label so it acts as a one-shot
    # signal. Without this, the story would re-trigger regeneration on every
    # scan run. The user adds ai-regenerate to mean "redo this once" — we
    # honor that by removing it after we're done.
    if is_regenerate:
        regenerate_label = config.get("regenerate_label", "ai-regenerate")
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
def main():
    parser = argparse.ArgumentParser(description="Agent 2 (Coder): Generate test code from Jira test cases")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--story", help="Process all test cases of a specific story")
    group.add_argument("--scan", action="store_true", help="Scan mode (config-driven)")
    parser.add_argument("--dry-run", action="store_true", help="Don't create branch/PR, just preview")
    args = parser.parse_args()

    try:
        if args.story:
            # Single-story mode: process one specific story by key.
            # Used for development, debugging, and manual runs.
            result = run(args.story, dry_run=args.dry_run)
            print("\n" + "=" * 60)
            print(f"[OK] Agent 2 finished -- story: {result['story_id']}")
            print(f"   Files generated: {result.get('files_generated', 0)}")
            print(f"   Status: {result['status']}")
            if result.get("pr_url"):
                print(f"   PR: {result['pr_url']}")
            print("=" * 60)
        else:
            # Scan mode: read selection criteria from config.yaml, find all
            # eligible stories, and process each one. Used in CI for batch runs.
            #
            # Two passes (Phase 6):
            #   1. NORMAL pass — stories ready for first-time coding
            #      (ai-processed AND human-approved AND NOT ai-coded AND NOT ai-skip
            #       AND NOT ai-regenerate)
            #
            #   2. REGENERATE pass — stories where the user updated the test
            #      cases and labeled the story ai-regenerate to redo the code
            #      (ai-processed AND human-approved AND ai-regenerate AND NOT ai-skip)
            #
            # We deliberately keep the two configs separate (rather than OR-ing
            # them in JQL) because the runtime BEHAVIOR differs (regen bypasses
            # dedup, uses -revN branch). Two queries → two passes is cleaner
            # and more debuggable.
            config = load_agent_config()
            normal_selection = config.get("selection", {})
            regen_selection = config.get("regenerate_selection", {})
            max_stories = config.get("max_stories_per_run", 5)

            if not normal_selection:
                logger.error(
                    "No 'selection' config found for agent2_coder in config.yaml. "
                    "Add an 'agents.agent2_coder.selection' block or use --story KEY instead."
                )
                sys.exit(1)

            jira = JiraClient()

            # Pass 1: Normal-mode candidates
            logger.info("Scan pass 1/2: looking for first-time stories (normal mode)")
            normal_stories = jira.find_stories_to_process(normal_selection, max_results=max_stories)

            # Pass 2: Regenerate-mode candidates (only if regen_selection is configured)
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
                    f"No stories found in either pass. "
                    f"Normal mode: required={normal_selection.get('required_labels', [])}, "
                    f"excluded={normal_selection.get('excluded_labels', [])}. "
                    f"Regen mode: requires 'ai-regenerate' label. "
                    f"Tip: ensure parent story has 'ai-processed' (Agent 1 done) "
                    f"and 'human-approved' (you reviewed) labels."
                )
                print("\n[OK] Agent 2 scan complete -- no stories to process.")
                sys.exit(0)

            logger.info(
                f"Found {len(normal_stories)} normal + {len(regen_stories)} regen "
                f"= {total_count} stories to process. "
                f"Normal: {[s['key'] for s in normal_stories]}. "
                f"Regen: {[s['key'] for s in regen_stories]}."
            )

            results = []

            # Process normal-mode stories first
            for story in normal_stories:
                try:
                    result = run(story["key"], dry_run=args.dry_run, is_regenerate=False)
                    results.append(result)
                except Exception as e:
                    # One story failing should not abort the whole batch —
                    # log, record, and move on.
                    logger.error(f"Failed processing {story['key']} (normal): {e}", exc_info=True)
                    results.append({
                        "story_id": story["key"],
                        "status": "failed",
                        "mode": "normal",
                        "error": str(e),
                    })

            # Process regenerate-mode stories
            for story in regen_stories:
                # Defensive: skip if same story already appeared in normal pass.
                # Shouldn't happen given our exclusion lists, but if config is
                # misconfigured we don't want to double-process.
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

            # Summary across all stories processed in this scan
            print("\n" + "=" * 60)
            print(f"[OK] Agent 2 scan finished -- processed {len(results)} stories")
            for r in results:
                status = r.get("status", "unknown")
                if status == "pr_opened":
                    status_marker = "OK"
                elif status == "skipped_all_duplicates":
                    status_marker = "SKIP"
                elif status == "failed":
                    status_marker = "FAIL"
                else:
                    status_marker = "??"
                pr_info = f" -> {r.get('pr_url')}" if r.get("pr_url") else ""
                print(f"   [{status_marker}] {r.get('story_id')}: {status}{pr_info}")
            print("=" * 60)
    except Exception as e:
        logger.error(f"Agent 2 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()