"""
Agent 3 — Reviewer.

Role:
    Reads a GitHub Pull Request, performs an AI-driven code review using a
    rigorous checklist, and posts the review as a comment on the PR.

Position in pipeline:
    Agent 1 (Analyst) → Agent 2 (Coder) → [Agent 3: Reviewer]
                      → Agent 4 (Runner) → Agent 5 (Reporter)

Triggering modes:
    1. Local CLI:        python -m agents.agent3_reviewer --pr 5 [--dry-run]
    2. GitHub Actions:   PR number auto-detected from $GITHUB_EVENT_PATH

Inputs:
    - PR number (via --pr CLI arg or auto-detected from CI environment)

Outputs:
    - A markdown comment posted on the PR with the structured review

Hardening notes:
    - Reference files and page inventory come from AppContext (config-driven),
      not hardcoded paths. Works for any app, not just SauceDemo.
    - Post-processing dedup+cap on issues list — LLMs can produce
      repetition loops on low-content PRs and `maxItems` can't be expressed
      in the structured-output schema.
"""
import argparse
import json
import logging
import os
import re
import sys

from agents.app_context import AppContext
from agents.github_client import GitHubClient
from agents.llm_client import LLMClient
from agents.schemas import ReviewReport, ReviewIssue
from config import (
    REQUIRED_GITHUB_ENV_VARS,
    REQUIRED_LLM_ENV_VARS,
    validate_required_env,
)
from config.paths import PROMPTS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent3_reviewer")

# Cap on the number of issues we keep. LLMs sometimes enter a "repetition
# loop" on low-content PRs and generate dozens of duplicate complaints.
# We cap and dedupe in post-processing rather than in the Pydantic schema
# because some providers' constrained-decoding can't handle maxItems on
# complex nested arrays.
MAX_ISSUES = 10


# ─────────────────────────────────────────────────────────────
# PR number resolution (CLI arg vs. CI environment)
# ─────────────────────────────────────────────────────────────
def resolve_pr_number(cli_arg_pr: int | None) -> int:
    """Determine which PR number to review.

    Priority:
      1. --pr CLI argument (highest priority — explicit overrides)
      2. GITHUB_EVENT_PATH (JSON event payload GitHub Actions writes)
      3. PR_NUMBER env var (manual override for testing)
    """
    if cli_arg_pr is not None:
        logger.info(f"PR number from --pr CLI arg: {cli_arg_pr}")
        return cli_arg_pr

    event_path = os.getenv("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path) as f:
                event = json.load(f)
            pr_num = event.get("number") or event.get("pull_request", {}).get("number")
            if pr_num:
                logger.info(f"PR number from GITHUB_EVENT_PATH: {pr_num}")
                return int(pr_num)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Could not parse GITHUB_EVENT_PATH: {e}")

    env_pr = os.getenv("PR_NUMBER")
    if env_pr:
        logger.info(f"PR number from PR_NUMBER env var: {env_pr}")
        return int(env_pr)

    raise ValueError(
        "Could not determine PR number. Provide one of: "
        "--pr <N> CLI arg, GITHUB_EVENT_PATH (CI), or PR_NUMBER env var."
    )


# ─────────────────────────────────────────────────────────────
# Post-processing: deduplicate and cap the issues list
# ─────────────────────────────────────────────────────────────
def _normalize_description(text: str) -> str:
    """Normalize a description to a stable fingerprint for dedup.

    Lowercases, collapses whitespace, strips trailing digits/punctuation
    (catches reworded "...variant 2" vs "...variant 11"), keeps first 40 chars.
    """
    s = text.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\d\W]+$", "", s)
    return s[:40]


def dedupe_and_cap_issues(report: ReviewReport, max_issues: int = MAX_ISSUES) -> ReviewReport:
    """De-duplicate near-identical issues and cap the list at max_issues."""
    if not report.issues:
        return report

    seen = set()
    deduped: list[ReviewIssue] = []
    for issue in report.issues:
        fingerprint = (
            issue.file_path,
            issue.issue_type,
            issue.severity,
            _normalize_description(issue.description),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(issue)
        if len(deduped) >= max_issues:
            break

    if len(deduped) < len(report.issues):
        logger.warning(
            f"Issues list reduced: {len(report.issues)} -> {len(deduped)} "
            f"(deduped/capped at {max_issues})"
        )

    return report.model_copy(update={"issues": deduped})


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def load_prompt() -> str:
    return (PROMPTS_DIR / "agent3_reviewer.md").read_text(encoding="utf-8")


def format_changed_files_for_prompt(files: list[dict]) -> str:
    """Format the list of changed files into a clear text block for the LLM."""
    if not files:
        return "(No files changed)"

    blocks = []
    for f in files:
        block = f"### File: `{f['filename']}`\n"
        block += f"Status: {f['status']} (+{f['additions']} -{f['deletions']})\n\n"
        if f.get("content"):
            block += f"**Full file content:**\n```\n{f['content']}\n```\n"
        elif f.get("patch"):
            block += f"**Diff (patch):**\n```diff\n{f['patch']}\n```\n"
        else:
            block += "(File content not available — possibly binary or too large)\n"
        blocks.append(block)
    return "\n---\n".join(blocks)


# ─────────────────────────────────────────────────────────────
# Markdown rendering for the PR comment
# ─────────────────────────────────────────────────────────────
def format_review_as_markdown(report: ReviewReport) -> str:
    """Convert a ReviewReport into a Markdown PR comment."""
    verdict_emoji = {
        "approve": "✅",
        "request_changes": "🛑",
        "comment": "💬",
    }
    verdict_label = {
        "approve": "Ready for human approval",
        "request_changes": "Issues found — changes requested",
        "comment": "Advisory comments",
    }

    md = []
    md.append("## 🤖 Agent 3 — Code Review")
    md.append("")
    md.append(f"### Verdict: {verdict_emoji[report.overall_verdict]} {verdict_label[report.overall_verdict]}")
    md.append("")
    md.append(report.summary)
    md.append("")

    if report.issues:
        groups = [
            ("Blocking 🛑", [i for i in report.issues if i.severity == "blocking"]),
            ("Major ⚠️", [i for i in report.issues if i.severity == "major"]),
            ("Minor 💡", [i for i in report.issues if i.severity == "minor"]),
            ("Info ℹ️", [i for i in report.issues if i.severity == "info"]),
        ]
        for label, group in groups:
            if not group:
                continue
            md.append(f"### {label}")
            md.append("")
            for i, issue in enumerate(group, 1):
                location = f"`{issue.file_path}`"
                if issue.line_number:
                    location += f" line {issue.line_number}"
                md.append(f"**{i}. [{issue.issue_type}]** {location}")
                md.append("")
                md.append(f"   {issue.description}")
                md.append("")
                md.append(f"   **Suggested fix:**")
                md.append(f"   {issue.suggested_fix}")
                md.append("")
    else:
        md.append("### No issues found 🎉")
        md.append("")

    md.append("### Compliance Checklist")
    md.append("")
    checks = [
        ("Style matches reference", report.style_compliance),
        ("Type hints present", report.type_hints_present),
        ("No hardcoded waits (time.sleep)", report.no_hardcoded_waits),
        ("POM compliant (selectors in page objects)", report.pom_compliant),
        ("Coverage complete (all test cases addressed)", report.coverage_complete),
    ]
    for label, passed in checks:
        emoji = "✅" if passed else "❌"
        md.append(f"- {emoji} {label}")
    md.append("")

    md.append("---")
    md.append("")
    md.append("_This review was generated by Agent 3 (Reviewer). The final merge decision remains with the human reviewer._")

    return "\n".join(md)


# ─────────────────────────────────────────────────────────────
# Core agent workflow
# ─────────────────────────────────────────────────────────────
def run(pr_number: int, dry_run: bool = False) -> dict:
    logger.info(f"=== Agent 3 (Reviewer) starting for PR #{pr_number} (dry_run={dry_run}) ===")

    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name}")

    # 1. INPUT: fetch PR data
    gh = GitHubClient()
    pr_metadata = gh.get_pr_metadata(pr_number)
    logger.info(
        f"PR #{pr_number}: '{pr_metadata['title']}' "
        f"on branch {pr_metadata['head_branch']}"
    )

    if pr_metadata["state"] != "open":
        logger.warning(f"PR #{pr_number} is {pr_metadata['state']} (not open). Reviewing anyway.")

    changed_files = gh.get_pr_changed_files(pr_number)
    if not changed_files:
        logger.warning("No changed files found in PR. Nothing to review.")
        return {"pr_number": pr_number, "status": "no_changes", "verdict": "comment"}

    # 2. CONTEXT — reference files and page inventory from AppContext
    references = ctx.load_reference_files()
    page_inventory = ctx.load_page_inventory_json()

    # 3. REASON: build prompt and call LLM
    prompt_template = load_prompt()
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{reference_feature_path}", ctx.reference_feature)
        .replace("{reference_step_def_path}", ctx.reference_step_def)
        .replace("{reference_page_object_path}", ctx.reference_page_object)
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{pr_number}", str(pr_metadata["number"]))
        .replace("{pr_title}", pr_metadata["title"])
        .replace("{pr_branch}", pr_metadata["head_branch"])
        .replace("{pr_author}", pr_metadata["author"])
        .replace("{pr_body}", pr_metadata["body"])
        .replace("{changed_files_section}", format_changed_files_for_prompt(changed_files))
    )

    prompt_chars = len(user_prompt)
    logger.info(f"Review prompt size: {prompt_chars:,} chars (~{prompt_chars // 4:,} tokens)")

    # max_output_tokens=8192 (not the default 4096): ReviewReport has 7
    # required scalar fields plus an `issues` list where each issue carries
    # 5 required fields (severity, file_path, line_number, issue_type,
    # description, suggested_fix). With 5+ issues the JSON exceeds 4K and
    # truncates mid-object — Pydantic then rejects it with "Field required"
    # validation errors. 8K leaves comfortable headroom.
    llm = LLMClient(temperature=0.1, max_output_tokens=8192)
    report: ReviewReport = llm.invoke_structured(
        system_prompt="You are a Senior SDET performing rigorous code review on automated test code.",
        user_prompt=user_prompt,
        output_schema=ReviewReport,
    )

    # 3b. POST-PROCESS: dedupe and cap (handles LLM repetition collapse)
    report = dedupe_and_cap_issues(report, max_issues=MAX_ISSUES)

    logger.info(f"Review verdict: {report.overall_verdict}")
    logger.info(f"Issues found: {len(report.issues)}")
    for issue in report.issues:
        logger.info(f"  - [{issue.severity}/{issue.issue_type}] {issue.file_path}: {issue.description}")

    # 4. FORMAT
    markdown = format_review_as_markdown(report)

    # 5. ACT
    if dry_run:
        logger.warning("DRY RUN — skipping comment post")
        print("\n" + "=" * 60)
        print("DRY RUN — Generated review preview")
        print("=" * 60)
        print(markdown.encode("ascii", "replace").decode("ascii"))
        print("=" * 60)
        return {
            "pr_number": pr_number,
            "verdict": report.overall_verdict,
            "issues_count": len(report.issues),
            "blocking_count": sum(1 for i in report.issues if i.severity == "blocking"),
            "status": "review_generated_dry_run",
        }

    comment_url = gh.post_pr_comment(pr_number, markdown)

    result = {
        "pr_number": pr_number,
        "verdict": report.overall_verdict,
        "issues_count": len(report.issues),
        "blocking_count": sum(1 for i in report.issues if i.severity == "blocking"),
        "comment_url": comment_url,
        "status": "review_posted",
    }

    logger.info(f"=== Agent 3 (Reviewer) complete. Comment: {comment_url} ===")
    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Agent 3 (Reviewer): AI code review on a PR")
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="PR number to review. If omitted, will try to detect from GitHub Actions environment.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't post comment, just preview")
    args = parser.parse_args()

    # Fast-fail on missing config
    validate_required_env(REQUIRED_LLM_ENV_VARS + REQUIRED_GITHUB_ENV_VARS)

    try:
        pr_number = resolve_pr_number(args.pr)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        result = run(pr_number, dry_run=args.dry_run)
        print("\n" + "=" * 60)
        print(f"[OK] Agent 3 finished -- PR #{result['pr_number']}")
        print(f"   Verdict: {result['verdict']}")
        print(f"   Issues found: {result.get('issues_count', 0)} ({result.get('blocking_count', 0)} blocking)")
        print(f"   Status: {result['status']}")
        if result.get("comment_url"):
            print(f"   Comment: {result['comment_url']}")
        print("=" * 60)
    except Exception as e:
        logger.error(f"Agent 3 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()