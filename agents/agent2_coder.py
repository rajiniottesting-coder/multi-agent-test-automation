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
from agents.import_validator import validate_imports_resolvable
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
from config.paths import PROMPTS_DIR, CONFIG_YAML, FEATURES_DIR, PROJECT_ROOT

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


def validate_paths_against_policy(plan: CodePlan, ctx: AppContext) -> None:
    """Enforce the two-tier file policy on the LLM's plan.

    Tier 1 — RESERVED: never touched. If the plan includes any reserved path,
        abort. These are the reference files the LLM uses as a style baseline.

    Tier 2 — EXTENDABLE: may be modified to add new methods. The plan must
        mark these with `is_new_file=False` so it's an explicit, conscious
        modification (not an accidental overwrite). If the LLM marks an
        extendable file as `is_new_file=True`, that means "create from
        scratch" which would wipe existing methods — also abort.

    Tier 3 — NEW: every other path. LLM creates fresh.

    Reserved/extendable lists come from `app_under_test.*` in config.yaml,
    so this check stays correct regardless of which app is being tested.
    """
    reserved = ctx.reserved_paths_normalized()
    extendable = ctx.extendable_paths_normalized()

    reserved_collisions: list[str] = []
    extendable_misclassified: list[str] = []  # marked is_new_file=True for an existing extendable file

    for fp in plan.files_to_create:
        normalized = _normalize_path(fp.file_path)
        if normalized in reserved:
            reserved_collisions.append(fp.file_path)
        elif normalized in extendable and fp.is_new_file:
            extendable_misclassified.append(fp.file_path)

    if reserved_collisions:
        raise ValueError(
            f"LLM tried to overwrite reserved reference files: "
            f"{reserved_collisions}. These files are protected by "
            f"app_under_test.reserved_paths in config.yaml — they're the "
            f"style baseline the LLM mimics, and must never be modified. "
            f"The LLM should have used different file paths for new tests, "
            f"or marked an extendable page object for modification instead."
        )

    if extendable_misclassified:
        raise ValueError(
            f"LLM marked existing extendable file(s) as new "
            f"(is_new_file=True): {extendable_misclassified}. These are "
            f"existing page objects listed in app_under_test.extendable_paths. "
            f"They may be MODIFIED (is_new_file=False) to add new methods, "
            f"but never CREATED from scratch — that would wipe existing "
            f"methods. Fix the plan to set is_new_file=False for these files."
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
    if not ctx.reserved_paths:
        return "(none — no reserved paths configured)"
    return "\n".join(f"- `{p}` -- RESERVED (must NOT be modified)" for p in ctx.reserved_paths)


def _build_extendable_paths_block(ctx: AppContext) -> str:
    """Render the extendable-paths list as a markdown bullet block for the
    Stage 1 plan prompt. Tells the LLM these existing files MAY be extended."""
    if not ctx.extendable_paths:
        return "(none — no extendable paths configured)"
    return "\n".join(
        f"- `{p}` -- EXTENDABLE (MAY add new methods; "
        f"set is_new_file=False; do NOT remove existing methods)"
        for p in ctx.extendable_paths
    )


def _read_extendable_file_content(file_path: str) -> str:
    """Read the current content of an extendable file so Stage 2 can preserve
    existing methods when adding new ones.

    Falls back to a placeholder if the file doesn't exist on disk —
    extendable files SHOULD exist already, but a missing file is non-fatal
    (the LLM will just create it fresh).
    """
    abs_path = PROJECT_ROOT / file_path
    if not abs_path.exists():
        logger.warning(
            f"Extendable file '{file_path}' not found on disk. The LLM will "
            f"have no existing-content reference; it may create new methods "
            f"without preserving anything. Configured under "
            f"app_under_test.extendable_paths in config.yaml."
        )
        return f"# (file '{file_path}' does not exist yet — generate fresh content)"
    return abs_path.read_text(encoding="utf-8")


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
        .replace("{extendable_paths_block}", _build_extendable_paths_block(ctx))
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

    # Defensive guard: enforce the two-tier reserved/extendable policy
    validate_paths_against_policy(plan, ctx)
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
    validator_feedback: list[str] | None = None,
    previous_attempt: str | None = None,
) -> str:
    """Stage 2: For ONE file in the plan, get its full content as raw text.

    For files marked as extending an existing path (is_new_file=False AND
    in extendable_paths), the current file content is injected into the
    prompt under a dedicated section so the LLM preserves existing methods.

    Repair mode (when validator_feedback is provided):
        After a validator finds problems, this function can be called again
        with the validator's error messages and the previous attempt's
        content. The prompt then includes a "Validator Feedback" section
        telling the LLM exactly what to fix. This is app-agnostic — the
        feedback strings come from the validator, which works on any
        feature/step pair.
    """
    related_test_cases = [
        tc for tc in test_cases if tc["key"] in file_plan.related_test_cases
    ]
    if not related_test_cases:
        related_test_cases = test_cases

    # If this file is being EXTENDED (not created fresh), give the LLM
    # the current content so it doesn't accidentally remove existing methods.
    extendable = ctx.extendable_paths_normalized()
    is_extending_existing = (
        not file_plan.is_new_file
        and _normalize_path(file_plan.file_path) in extendable
    )
    if is_extending_existing:
        existing_content = _read_extendable_file_content(file_plan.file_path)
        existing_block = (
            f"# EXTENDING EXISTING FILE — preserve all methods below\n\n"
            f"You are MODIFYING an existing file. The current content is shown\n"
            f"below. You MUST keep every existing method and its signature\n"
            f"intact. ADD new methods alongside them. Do NOT remove or rename\n"
            f"any existing code.\n\n"
            f"## Current content of `{file_plan.file_path}`:\n"
            f"```python\n{existing_content}\n```\n"
        )
        logger.info(
            f"Stage 2: extending existing file '{file_plan.file_path}' — "
            f"injecting {len(existing_content)} chars of current content."
        )
    else:
        existing_block = ""

    # If this is a REPAIR call, inject validator feedback so the LLM knows
    # exactly what to fix. The feedback strings are produced by the validator
    # and reference specific Gherkin steps that need decorators.
    feedback_block = ""
    if validator_feedback:
        feedback_lines = "\n".join(f"- {err}" for err in validator_feedback)
        prev_attempt_block = ""
        if previous_attempt:
            prev_attempt_block = (
                f"\n\n## Your previous attempt (which had the issues above):\n"
                f"```\n{previous_attempt}\n```\n"
                f"\nProduce a CORRECTED version of this file. Keep what was "
                f"right; fix what the validator flagged."
            )
        feedback_block = (
            f"\n\n# CRITICAL: Validator Feedback — fix these issues\n\n"
            f"Your previous attempt at this file was rejected by the automated "
            f"validator. The specific problems were:\n\n"
            f"{feedback_lines}\n\n"
            f"You MUST address every one of these issues in this regeneration. "
            f"Re-read the feature file's steps carefully — every Given / When / "
            f"Then / And / But line MUST have a matching @given / @when / @then "
            f"decorator. Pay attention to the And/But inheritance rule: an `And` "
            f"after a `Then` is itself a Then.{prev_attempt_block}\n"
        )
        logger.info(
            f"  Repair mode: injecting {len(validator_feedback)} validator "
            f"feedback item(s) into prompt for '{file_plan.file_path}'."
        )

    prompt_template = load_prompt("agent2_coder_generate.md")
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{file_path}", file_plan.file_path)
        .replace("{file_type}", file_plan.file_type)
        .replace("{file_purpose}", file_plan.purpose)
        .replace("{feature_name}", plan.feature_name)
        .replace("{existing_file_block}", existing_block)
        .replace("{validator_feedback_block}", feedback_block)
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
    """Run all final validators.

    Catches the failure modes Agent 2 has historically had:
      - PR #7: kebab-case feature filename vs snake_case feature_path() ref
      - PR #9: feature steps without matching @given/@when/@then decorators
      - SCRUM-13: imports referencing modules that don't exist

    Raises ValueError if any validator finds problems.

    NOTE: This is the FINAL validation, run after any retry attempts.
    By the time this raises, the LLM has already been given a chance
    to self-correct via _attempt_step_coverage_repair.
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
            f"{len(coverage_errors)} error(s) AFTER retry:"
        )
        for err in coverage_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Step definition coverage validation failed for {story_id}: "
            f"{len(coverage_errors)} feature step(s) without matching "
            f"@given/@when/@then decorator(s) — even after the LLM was "
            f"given the validator's feedback for self-correction. This "
            f"usually means the LLM model is too weak (try gemini-2.5-flash "
            f"instead of -lite) or the feature file has unusually complex "
            f"steps. See logs for details."
        )

    import_errors = validate_imports_resolvable(generated_files, PROJECT_ROOT)
    if import_errors:
        logger.error(
            f"Import resolution check FAILED with "
            f"{len(import_errors)} error(s) AFTER retry:"
        )
        for err in import_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Import resolution validation failed for {story_id}: "
            f"{len(import_errors)} import(s) reference module(s) that don't "
            f"exist in the repo, in this generation batch, or in "
            f"requirements.txt — even after the LLM was given the "
            f"validator's feedback for self-correction. The LLM likely "
            f"hallucinated a page object class import. See logs for details."
        )


# ---------------------------------------------------------------------------
# Self-correcting retry loop (handles weak-model step coverage failures)
# ---------------------------------------------------------------------------
def _group_validator_errors_by_file(
    validator_errors: list[str],
) -> dict[str, list[str]]:
    """Group validator error messages by the file they refer to.

    Validator errors follow the convention: `<error type> in '<file_path>':`
    so we extract the file path with a single regex that matches any error
    prefix. This works for:
      - `Step coverage error in '...':` (coverage validator)
      - `Import resolution error in '...':` (import validator)
      - any future validators that follow the same convention

    Returns: {file_path: [error_messages_for_that_file]}
    """
    grouped: dict[str, list[str]] = {}
    # Match `<words> error in '<path>':` regardless of which validator emitted it
    pattern = re.compile(r"error in '([^']+)':")
    for err in validator_errors:
        match = pattern.search(err)
        if not match:
            # Validator returned an error in an unexpected format — skip;
            # final validation will still raise it, just no targeted retry.
            continue
        path = match.group(1)
        grouped.setdefault(path, []).append(err)
    return grouped


# Backward-compat alias — older tests reference the old name
_group_coverage_errors_by_step_def = _group_validator_errors_by_file


def _collect_repairable_errors(generated_files: list[GeneratedFile]) -> list[str]:
    """Aggregate errors from all validators that the repair loop can act on.

    Currently combines:
      - Step-definition coverage validator (missing @given/@when/@then)
      - Import resolution validator (imports referencing non-existent modules)

    Both produce errors in the `<type> error in '<path>':` format so the
    repair loop's grouper can target the right file.

    Future validators can be plumbed here as long as they emit errors in
    the same format.
    """
    errors: list[str] = []
    errors.extend(validate_step_definitions_complete(generated_files))
    errors.extend(validate_imports_resolvable(generated_files, PROJECT_ROOT))
    return errors


def _attempt_step_coverage_repair(
    generated_files: list[GeneratedFile],
    llm: LLMClient,
    plan: CodePlan,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
    max_retries: int = 2,
) -> list[GeneratedFile]:
    """If validators find issues in the generated files, give the LLM up to
    `max_retries` chances to fix them with explicit feedback.

    Handles two failure modes today:
      - Missing step decorators (coverage validator)
      - Unresolvable imports (import validator)

    Both kinds of errors are app-agnostic: the validators work on any
    feature/step pair and any Python imports. The repair simply re-invokes
    Stage 2 for the broken file with a "Validator Feedback" section.

    Why retry instead of hard-fail:
        Weaker LLMs (gemini-2.5-flash-lite specifically) often slip up.
        Validators catch it, but the old behavior was to abort the whole
        run, wasting work already done on other files. Retrying ONLY the
        broken file is targeted, cheap, and usually succeeds.

    Cost: each retry = 1 LLM call per broken file. Capped at `max_retries`
    iterations. Worst case for a typical 1-broken-file run is 2 extra calls.
    """
    for attempt in range(1, max_retries + 1):
        all_errors = _collect_repairable_errors(generated_files)
        if not all_errors:
            if attempt > 1:
                logger.info(
                    f"Validator repair succeeded after {attempt - 1} "
                    f"retry attempt(s). All issues resolved."
                )
            return generated_files

        grouped = _group_validator_errors_by_file(all_errors)
        if not grouped:
            # Errors couldn't be parsed — let final validation handle it
            logger.warning(
                f"Validators produced {len(all_errors)} error(s) but no "
                f"targetable file was identified. Skipping repair."
            )
            return generated_files

        logger.warning(
            f"Validators found {len(all_errors)} issue(s) across "
            f"{len(grouped)} file(s). "
            f"Attempting repair (attempt {attempt}/{max_retries})..."
        )

        for step_def_path, errors_for_this_file in grouped.items():
            # Find the corresponding GeneratedFile to repair
            target_idx = next(
                (i for i, gf in enumerate(generated_files)
                 if _normalize_path(gf.file_path) == _normalize_path(step_def_path)),
                None,
            )
            if target_idx is None:
                logger.warning(
                    f"Validator flagged '{step_def_path}' but it's not in "
                    f"the generated batch. Cannot repair."
                )
                continue

            # Find the matching FilePlan for prompt context
            target_plan = next(
                (fp for fp in plan.files_to_create
                 if _normalize_path(fp.file_path) == _normalize_path(step_def_path)),
                None,
            )
            if target_plan is None:
                logger.warning(
                    f"No FilePlan found for '{step_def_path}'. Cannot repair."
                )
                continue

            logger.info(
                f"  Repairing '{step_def_path}' with "
                f"{len(errors_for_this_file)} feedback item(s)..."
            )
            try:
                repaired_content = generate_file_content(
                    llm,
                    target_plan,
                    plan,
                    test_cases,
                    references,
                    page_inventory,
                    ctx,
                    validator_feedback=errors_for_this_file,
                    previous_attempt=generated_files[target_idx].content,
                )
                generated_files[target_idx] = GeneratedFile(
                    file_path=generated_files[target_idx].file_path,
                    content=repaired_content,
                    is_new_file=generated_files[target_idx].is_new_file,
                    purpose=generated_files[target_idx].purpose,
                )
            except Exception as e:
                logger.error(
                    f"  Repair attempt for '{step_def_path}' failed: {e}. "
                    f"Will let final validation surface the issue."
                )

    # Hit max_retries without full success — final validator will raise.
    final_errors = _collect_repairable_errors(generated_files)
    if final_errors:
        logger.warning(
            f"Validator repair exhausted {max_retries} retry attempt(s); "
            f"{len(final_errors)} error(s) remain. Final validator will raise."
        )
    return generated_files


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

    # 4b. SELF-CORRECTING REPAIR (handles weak-model coverage misses)
    # If validator finds missing decorators, give the LLM up to 2 chances
    # to fix the broken step def file with explicit feedback. Only the
    # broken file is regenerated (cheap), and the cap bounds total cost.
    generated_files = _attempt_step_coverage_repair(
        generated_files,
        llm,
        plan,
        new_test_cases,
        references,
        page_inventory,
        ctx,
        max_retries=2,
    )
    output = CodeGenerationOutput(
        feature_name=plan.feature_name,
        branch_name=plan.branch_name,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        files=generated_files,
        notes=plan.notes,
    )

    # 4c. FINAL VALIDATION (after any repair attempts)
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