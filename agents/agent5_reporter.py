"""
Agent 5 — Reporter.

Role:
    Reads test results (JUnit XML) produced by Agent 4 (Runner), summarizes
    them with the LLM, and posts a friendly comment to the parent Jira story.

Position in pipeline:
    Agent 1 (Analyst) → Agent 2 (Coder) → Agent 3 (Reviewer) → Agent 4 (Runner) → [Agent 5: Reporter]

Triggering modes:
    1. Local CLI:
         python -m agents.agent5_reporter --story PROJ-123 --reports-dir reports/
    2. GitHub Actions:
         Auto-runs after Agent 4. Reads PR_NUMBER, GITHUB_RUN_ID, etc.
         from the workflow environment.

Inputs:
    - JUnit XML at <reports-dir>/junit.xml (default: ./reports/junit.xml)
    - Parent Jira story key (auto-detected from PR branch name or --story arg)
    - PR / workflow context from environment (best-effort; comment still
      generates without these, just with fewer links)

Outputs:
    - A markdown comment posted on the parent Jira story
    - Story labeled with `tests-run` for traceability

Idempotency:
    None enforced — Agent 5 is intended to be called once per CI run.
    If you re-run, you'll get a duplicate comment. This is acceptable
    because comments are timestamped and ordered.
"""
import argparse
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from agents.jira_client import JiraClient
from agents.llm_client import LLMClient
from agents.schemas import RunReport, TestResult, JiraCommentDraft
from config.paths import PROMPTS_DIR, PROJECT_ROOT

# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent5_reporter")


# ─────────────────────────────────────────────────────────────
# JUnit XML parsing
# ─────────────────────────────────────────────────────────────
def parse_junit_xml(junit_path: Path) -> RunReport:
    """Parse a pytest-generated JUnit XML file into a RunReport.

    Pytest's JUnit format uses one <testsuite> element per session
    (wrapped in <testsuites>), with <testcase> children for each test.
    Failures and errors are nested elements inside <testcase>.
    """
    if not junit_path.exists():
        raise FileNotFoundError(
            f"JUnit XML not found at {junit_path}. "
            f"Make sure Agent 4 (Runner) ran first and produced reports/junit.xml."
        )

    tree = ET.parse(junit_path)
    root = tree.getroot()

    # JUnit XML can have <testsuites> wrapper or be a single <testsuite>.
    # Pytest uses <testsuites><testsuite>...</testsuite></testsuites>.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    if not suites:
        raise ValueError(f"No <testsuite> found in {junit_path}")

    # For pytest there's exactly one suite per session — combine if more.
    total = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    duration = sum(float(s.get("time", 0.0)) for s in suites)
    passed = total - failures - errors - skipped

    results: list[TestResult] = []
    for suite in suites:
        for tc in suite.findall("testcase"):
            name = tc.get("name", "<unknown>")
            classname = tc.get("classname", "")
            tc_time = float(tc.get("time", 0.0))

            # Find which child element (failure/error/skipped) is present
            failure_el = tc.find("failure")
            error_el = tc.find("error")
            skipped_el = tc.find("skipped")

            if failure_el is not None:
                status = "failed"
                # Take first line of message; the full stack trace is noise here
                msg = failure_el.get("message", "") or (failure_el.text or "")
                failure_message = msg.strip().split("\n")[0][:200]
            elif error_el is not None:
                status = "error"
                msg = error_el.get("message", "") or (error_el.text or "")
                failure_message = msg.strip().split("\n")[0][:200]
            elif skipped_el is not None:
                status = "skipped"
                failure_message = None
            else:
                status = "passed"
                failure_message = None

            results.append(TestResult(
                name=name,
                classname=classname,
                status=status,
                duration_seconds=tc_time,
                failure_message=failure_message,
            ))

    return RunReport(
        total=total,
        passed=passed,
        failed=failures,
        errors=errors,
        skipped=skipped,
        duration_seconds=duration,
        results=results,
    )


# ─────────────────────────────────────────────────────────────
# CI context detection — gather PR/workflow info from environment
# ─────────────────────────────────────────────────────────────
def gather_ci_context(report: RunReport, cli_pr: int | None = None) -> RunReport:
    """Enrich a RunReport with PR and workflow URLs from the environment.

    Sources (priority order):
      1. CLI args (--pr)
      2. GITHUB_EVENT_PATH JSON (when triggered by pull_request event)
      3. PR_NUMBER env var (manual override)
      4. GITHUB_REPOSITORY / GITHUB_RUN_ID / GITHUB_SHA (always set in CI)

    All fields are optional — Agent 5 still works without any of these
    (the comment just won't have links).
    """
    repo = os.getenv("GITHUB_REPOSITORY")  # e.g. "user/repo"
    run_id = os.getenv("GITHUB_RUN_ID")
    sha = os.getenv("GITHUB_SHA")

    pr_number = cli_pr
    if pr_number is None:
        event_path = os.getenv("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path) as f:
                    event = json.load(f)
                pr_number = (event.get("pull_request", {}).get("number")
                             or event.get("number"))
            except (json.JSONDecodeError, KeyError):
                pass
    if pr_number is None:
        env_pr = os.getenv("PR_NUMBER")
        if env_pr:
            try:
                pr_number = int(env_pr)
            except ValueError:
                pass

    pr_url = f"https://github.com/{repo}/pull/{pr_number}" if (repo and pr_number) else None
    workflow_run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if (repo and run_id) else None
    # The HTML report is uploaded as an artifact attached to the workflow run.
    # GitHub doesn't expose a direct "download artifact" URL without an API call,
    # but the run page has an Artifacts section at the bottom — anchoring with
    # #artifacts auto-scrolls the user there. One extra click vs. a direct link,
    # but no GitHub API call needed (which would require auth + run-id mapping).
    html_report_url = f"{workflow_run_url}#artifacts" if workflow_run_url else None

    return report.model_copy(update={
        "pr_number": pr_number,
        "pr_url": pr_url,
        "workflow_run_url": workflow_run_url,
        "html_report_url": html_report_url,
        "commit_sha": sha,
    })


# ─────────────────────────────────────────────────────────────
# Final comment assembly — Python builds the deterministic parts
# (links, commit hash, "posted by" footer) so the LLM doesn't
# accidentally write "View PR (None)" when fields are unavailable.
#
# This is a deliberate split:
#   - LLM writes the PROSE (friendly, contextual summary)
#   - Python writes the FACTS (links, hashes, footer)
# Lesson learned: don't ask the LLM to do conditional logic on
# nullable fields — it will follow the template even when told
# to omit. Determinism belongs in code.
# ─────────────────────────────────────────────────────────────
def build_final_comment(prose_body: str, report: RunReport) -> str:
    """Assemble the final Jira comment from LLM prose + deterministic links.

    Args:
        prose_body: The LLM-generated summary (just the verdict + failures, no links)
        report: The RunReport (which knows whether PR/commit/workflow links exist)

    Returns:
        Final markdown string ready to post to Jira.
    """
    parts: list[str] = [prose_body.rstrip()]

    # Build the "Run details" section ONLY with fields that are actually set.
    # Each line is conditional — no field, no line.
    detail_lines: list[str] = []
    if report.commit_sha:
        short_sha = report.commit_sha[:8]
        detail_lines.append(f"- Commit: `{short_sha}`")
    if report.pr_url:
        detail_lines.append(f"- [View PR]({report.pr_url})")
    if report.workflow_run_url:
        detail_lines.append(f"- [View Actions run]({report.workflow_run_url})")
    if report.html_report_url and report.html_report_url != report.workflow_run_url:
        # The link goes to the run page's #artifacts anchor — user clicks the
        # artifact zip there to download the HTML report. One extra click vs.
        # a direct download URL, but no API/auth needed.
        detail_lines.append(f"- [Download HTML report]({report.html_report_url}) (scroll to Artifacts section)")

    if detail_lines:
        parts.append("")  # blank line
        parts.append("**Run details:**")
        parts.extend(detail_lines)

    # Footer (always added, identifies this as agent-generated)
    parts.append("")
    parts.append("—")
    parts.append("_Posted automatically by Agent 5 (Reporter)._")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Story key resolution — figure out which Jira story to comment on
# ─────────────────────────────────────────────────────────────
def resolve_story_key(cli_arg: str | None, pr_branch: str | None = None) -> str:
    """Determine which Jira story to comment on.

    Priority:
      1. --story CLI argument (explicit, always wins)
      2. JIRA_STORY_KEY env var
      3. Parsed from PR branch name (any branch containing a Jira key
         like PROJ-123, e.g., 'auto/PROJ-123-feature' or 'feature/PROJ-99-foo')
      4. Raise — we can't guess

    See docs/BRANCH_NAMING.md for the full branch convention.
    """
    if cli_arg:
        return cli_arg.upper()

    env_key = os.getenv("JIRA_STORY_KEY")
    if env_key:
        return env_key.upper()

    if pr_branch:
        # Use the centralized extractor from config — works for any
        # Jira project prefix (SCRUM, PROD, MOBILE, BACKEND, etc.).
        from config import extract_jira_key
        key = extract_jira_key(pr_branch)
        if key:
            return key

    raise ValueError(
        "Could not determine Jira story key. Provide one of: "
        "--story <KEY> CLI arg, JIRA_STORY_KEY env var, or run on a "
        "PR branch with a Jira key (e.g., 'auto/PROJ-123-feature'). "
        "See docs/BRANCH_NAMING.md."
    )


def get_pr_branch_from_env() -> str | None:
    """Best-effort attempt to read the PR head branch from CI environment."""
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path) as f:
                event = json.load(f)
            return event.get("pull_request", {}).get("head", {}).get("ref")
        except (json.JSONDecodeError, KeyError):
            pass
    return os.getenv("GITHUB_HEAD_REF")  # set by GHA on pull_request events


# ─────────────────────────────────────────────────────────────
# Main agent workflow
# ─────────────────────────────────────────────────────────────
def load_prompt() -> str:
    return (PROMPTS_DIR / "agent5_reporter.md").read_text(encoding="utf-8")


def run(story_key: str, reports_dir: Path, dry_run: bool = False, cli_pr: int | None = None) -> dict:
    logger.info(f"=== Agent 5 (Reporter) starting for {story_key} (dry_run={dry_run}) ===")

    # 1. INPUT: parse JUnit XML
    junit_path = reports_dir / "junit.xml"
    logger.info(f"Reading JUnit XML from: {junit_path}")
    report = parse_junit_xml(junit_path)
    logger.info(
        f"Parsed: total={report.total}, passed={report.passed}, "
        f"failed={report.failed}, errors={report.errors}, skipped={report.skipped} "
        f"({report.duration_seconds:.1f}s)"
    )

    # 2. CONTEXT: enrich with CI info
    report = gather_ci_context(report, cli_pr=cli_pr)
    if report.pr_number:
        logger.info(f"PR context: #{report.pr_number} ({report.pr_url})")
    if report.workflow_run_url:
        logger.info(f"Workflow run: {report.workflow_run_url}")

    # 3. REASON: ask LLM to draft the comment
    prompt_template = load_prompt()
    user_prompt = prompt_template.replace(
        "{run_report_json}",
        report.model_dump_json(indent=2),
    )

    llm = LLMClient(temperature=0.3)  # slight creativity for friendly tone
    draft: JiraCommentDraft = llm.invoke_structured(
        system_prompt="You are a QA Lead summarizing automated test results for a Jira story.",
        user_prompt=user_prompt,
        output_schema=JiraCommentDraft,
    )

    logger.info(f"LLM draft title: {draft.title}")

    # 3b. ASSEMBLE: Python builds the final comment from LLM prose + deterministic links.
    # This avoids the LLM rendering "View PR (None)" when fields are unavailable.
    final_body = build_final_comment(draft.body_markdown, report)

    # 4. ACT: post to Jira (or preview)
    if dry_run:
        logger.warning("DRY RUN — not posting to Jira")
        print("\n" + "=" * 60)
        print(f"DRY RUN — would post to {story_key}")
        print("=" * 60)
        print(f"Title: {draft.title}")
        print()
        print(final_body.encode("ascii", "replace").decode("ascii"))
        print("=" * 60)
        return {
            "story_key": story_key,
            "title": draft.title,
            "verdict": "passed" if report.failed == 0 and report.errors == 0 else "failed",
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "status": "draft_generated_dry_run",
        }

    jira = JiraClient()
    comment_url = jira.add_comment(story_key, final_body)
    jira.add_label(story_key, "tests-run")  # idempotent — won't dup-add

    result = {
        "story_key": story_key,
        "title": draft.title,
        "verdict": "passed" if report.failed == 0 and report.errors == 0 else "failed",
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "comment_url": comment_url,
        "status": "comment_posted",
    }

    logger.info(f"=== Agent 5 (Reporter) complete. Comment: {comment_url} ===")
    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Agent 5 (Reporter): post test results to Jira")
    parser.add_argument(
        "--story",
        default=None,
        help="Jira story key to comment on (e.g., PROJ-123). "
             "If omitted, will try to detect from JIRA_STORY_KEY or PR branch name.",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing junit.xml (default: ./reports)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="PR number for context (default: auto-detect from CI environment)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't post comment, just preview")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir).resolve()

    try:
        pr_branch = get_pr_branch_from_env()
        story_key = resolve_story_key(args.story, pr_branch)
    except ValueError as e:
        # No story key detected. This is normal for manual / non-AI PRs
        # (e.g., a hand-written branch like `feature/foo` with no Jira key).
        # Agent 5 is designed to close the loop for AI-generated PRs that
        # follow Agent 2's `auto/<KEY>-<feature>` naming. Skipping is the
        # correct behavior here — exit 0 so the workflow doesn't fail.
        logger.warning(
            f"Skipping Agent 5: {e} "
            f"(this is expected for non-AI PRs without a Jira key in the branch name)"
        )
        sys.exit(0)

    try:
        result = run(story_key, reports_dir, dry_run=args.dry_run, cli_pr=args.pr)
        print("\n" + "=" * 60)
        print(f"[OK] Agent 5 finished -- {result['story_key']}")
        print(f"   Title: {result['title']}")
        print(f"   Verdict: {result['verdict']} ({result['passed']}/{result['total']} passed)")
        print(f"   Status: {result['status']}")
        if result.get("comment_url"):
            print(f"   Comment: {result['comment_url']}")
        print("=" * 60)
    except FileNotFoundError as e:
        # No junit.xml. This means Agent 4 (the test job) didn't produce a
        # report. Possible causes:
        #   - Agent 4 was skipped (e.g., upstream job failed/skipped)
        #   - Agent 4 crashed before pytest ran (env error, install failure)
        #   - Branch was checked out but tests/ dir missing
        #
        # We don't want Agent 5 to fail the whole workflow when it has nothing
        # to report — a human can already see Agent 4's failure on the PR.
        # Exit 0 with a clear log so the PR shows green for Agent 5's check.
        logger.warning(
            f"Skipping Agent 5: no test report available ({e}). "
            f"This typically means Agent 4 (Runner) didn't produce junit.xml -- "
            f"check the Agent 4 job for the underlying failure. "
            f"Exiting cleanly so this Agent 5 check doesn't double-report the failure."
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Agent 5 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()