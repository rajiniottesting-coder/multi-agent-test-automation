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
from config.paths import PROMPTS_DIR, CONFIG_YAML, PROJECT_ROOT

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
def run(story_id: str, dry_run: bool = False) -> dict:
    """Main agent flow — Stage 1 plan, then Stage 2 per-file generation."""
    logger.info(f"=== Agent 2 (Coder) starting for {story_id} (dry_run={dry_run}) ===")

    # 1. INPUT
    jira = JiraClient()
    jira.get_story(story_id)
    test_cases = load_test_cases_for_story(jira, story_id)

    if not test_cases:
        logger.warning(f"No Test Cases linked to {story_id}. Run Agent 1 first.")
        return {"story_id": story_id, "status": "no_test_cases", "files_generated": 0}

    # 2. CONTEXT
    references = load_reference_files()
    page_inventory = load_page_inventory()
    llm = LLMClient(temperature=0.2)

    # 3. STAGE 1
    plan = build_plan(llm, test_cases, references, page_inventory)

    # 4. STAGE 2
    generated_files: list[GeneratedFile] = []
    for file_plan in plan.files_to_create:
        try:
            content = generate_file_content(
                llm, file_plan, plan, test_cases, references, page_inventory
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
    gh = GitHubClient()
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
            result = run(args.story, dry_run=args.dry_run)
            print("\n" + "=" * 60)
            print(f"[OK] Agent 2 finished -- story: {result['story_id']}")
            print(f"   Files generated: {result.get('files_generated', 0)}")
            print(f"   Status: {result['status']}")
            if result.get("pr_url"):
                print(f"   PR: {result['pr_url']}")
            print("=" * 60)
        else:
            logger.error("Scan mode for Agent 2 not yet implemented -- use --story KEY for now")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Agent 2 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()