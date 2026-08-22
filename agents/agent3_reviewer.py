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
      not hardcoded paths. Works for any app under test.
    - Post-processing dedup+cap on issues list — LLMs can produce
      repetition loops on low-content PRs and `maxItems` can't be expressed
      in the structured-output schema.

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m agents.agent3_reviewer --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
import argparse
import json
import logging
import os
import re
import sys

from core.app_context import AppContext
from integrations.repo_host import get_repo_host
from core.llm_client import LLMClient
from core.schemas import ReviewReport, ReviewIssue
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


# The verdict must FOLLOW from the issues, not be chosen alongside them.
#
# A review reported a `major` / `functional_bug` issue - and the schema defines
# functional_bug as "test will fail" - while simultaneously returning the
# verdict `comment`, which renders as "Advisory comments". The finding was
# correct: the test failed on exactly the line the review named, in the run
# that followed. Nothing acted on it, because nothing connected the severity
# the model assigned to the verdict the model chose. Two fields, filled
# independently, free to disagree.
#
# So the verdict is DERIVED. The model reports what it found; what that means
# for the pull request is arithmetic, not a second judgement call.
_BLOCKING_SEVERITIES = frozenset({"blocking"})

# Types whose definition asserts the code is broken - but only when the model
# also judged the impact to be worth acting on.
#
# The first version blocked on the TYPE alone. A review then filed a
# `minor` / `functional_bug` whose own suggested fix read "No change required
# for current scenarios", and the pull request went red over it. Severity is
# the model's judgement of how much a finding matters; ignoring it turned every
# passing observation into a stop sign, and a gate that is red on advisory
# notes gets switched off.
# Security is categorically different: a "minor" security finding is still a
# security finding, and stopping for it costs one look.
_ALWAYS_BLOCKING_TYPES = frozenset({"security"})

# functional_bug means "test will fail" - true at major, and routinely used at
# minor for a passing observation. Both are useful; only one should stop a
# pull request.
_BLOCKING_ISSUE_TYPES = frozenset({"functional_bug"})
_TYPE_BLOCKS_AT = frozenset({"blocking", "major"})

# THE SAME CONTRADICTION, ONE SEVERITY UP.
#
# Raising the threshold from TYPE-alone to major-or-above did not stop the
# recurrence, it moved it. A review then filed a `major` / `functional_bug`
# whose description ended "the pattern is acceptable given actual scenario
# data" and whose suggested fix opened "No change required for current
# scenarios". The pull request went red over a finding that said, twice, in
# its own words, that nothing needed doing.
#
# Chasing this with the threshold cannot converge. The only step left is to
# block on `blocking` alone, which throws functional_bug detection away.
# The signal was never the severity - it is that the finding CONTRADICTS
# ITSELF, the same shape as the verdict/severity disagreement this whole
# module exists to resolve, so it is read the same way: the more specific
# statement wins, and "no change required" is more specific than a label.
#
# Deliberately narrow. The phrase must OPEN the suggested fix - the field
# whose entire job is to say what to do. "No change required to the selector,
# but the assertion must be rewritten" still blocks, because something IS
# being asked for.
_NO_CHANGE_REQUIRED = re.compile(
    r"^\W*(?:no|there\s+is\s+no)\s+"
    r"(?:change|changes|action|fix|edit|update|modification)s?\s+"
    r"(?:is\s+|are\s+)?(?:required|needed|necessary)\b",
    re.I,
)

# An adversative clause in the same sentence means something IS being asked
# for after all, so the opening waiver does not stand.
_RETRACTS_THE_WAIVER = re.compile(
    r"\b(?:but|however|although|though|except|unless|still|instead)\b", re.I)


def _waives_itself(issue) -> bool:
    """True when the finding's own suggested fix opens by asking for nothing.

    Only the FIRST sentence is read. A fix that begins by waiving the finding
    and then describes a hypothetical - "...If empty search is ever added,
    switch to parsers.re" - is still a waiver: the conditional is advice for
    a change nobody has requested.
    """
    text = (getattr(issue, "suggested_fix", "") or "").strip()
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0] if text else ""
    if not _NO_CHANGE_REQUIRED.match(first):
        return False
    # An adversative in the SAME sentence takes the waiver back: "No change
    # required to the selector, BUT the assertion must be rewritten" asks for
    # a change. Only an unqualified waiver counts.
    return not _RETRACTS_THE_WAIVER.search(first)


def derive_verdict(report: ReviewReport) -> ReviewReport:
    """Recompute overall_verdict from the issues the review actually found.

    An issue counts as blocking when its SEVERITY says so, or when its TYPE is
    one whose own definition already asserts the code is broken: functional_bug
    ("test will fail") and security. A report that contains one of those and
    calls itself advisory has contradicted itself, and the issue is the more
    specific of the two statements.

    Only ever raises. A model that returned request_changes keeps it, whatever
    the severities look like.
    """
    blocking = [
        issue for issue in report.issues
        if (issue.severity in _BLOCKING_SEVERITIES
            or issue.issue_type in _ALWAYS_BLOCKING_TYPES
            or (issue.issue_type in _BLOCKING_ISSUE_TYPES
                and issue.severity in _TYPE_BLOCKS_AT))
        # A finding whose own fix opens with "no change required" has
        # withdrawn itself. Two exemptions: a security finding that shrugs is
        # still worth one look, and an explicit `blocking` severity is a
        # deliberate call that a waiver phrase does not get to overturn.
        and not (issue.issue_type not in _ALWAYS_BLOCKING_TYPES
                 and issue.severity not in _BLOCKING_SEVERITIES
                 and _waives_itself(issue))
    ]
    if not blocking or report.overall_verdict == "request_changes":
        return report

    logger.warning(
        "Verdict raised from %r to 'request_changes': %d issue(s) assert the "
        "code is broken (%s). A review cannot report that a test will fail and "
        "call itself advisory.",
        report.overall_verdict, len(blocking),
        ", ".join(sorted({f"{i.severity}/{i.issue_type}" for i in blocking})),
    )
    return report.model_copy(update={"overall_verdict": "request_changes"})


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
    gh = get_repo_host()
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
    report = derive_verdict(report)

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

    # ── LLM usage: log summary and post to the story's usage ledger ──
    # Story key is derived from the auto/<KEY>-... branch convention.
    from core.llm_client import log_usage_summary, reset_usage
    usage = log_usage_summary(f"PR #{pr_number} (reviewer)")
    reset_usage()
    import re as _re
    _m = _re.match(r"auto/([A-Z][A-Z0-9_]*-\d+)-", pr_metadata.get("head_branch", "") or "")
    if _m:
        from core.usage_ledger import post_usage_to_story
        post_usage_to_story(_m.group(1), "Agent 3 (Reviewer)", usage)
    else:
        import logging as _logging
        _logging.getLogger(__name__).info(
            "Usage ledger: branch %r does not match auto/<KEY>- convention — "
            "skipping story usage comment.", pr_metadata.get("head_branch"))

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
    parser = argparse.ArgumentParser(description="Agent 3 (Reviewer): AI code review on a PR",
        epilog=("example:\n  --pr 42"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
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

        # A review that requests changes must FAIL THE JOB.
        #
        # Agent 3 used to post its comment and exit 0 whatever it found, so a
        # correct "this test will fail" finding sat in a PR comment while the
        # runner went ahead and proved it right. A red check is the cheapest
        # thing that makes the finding impossible to walk past.
        #
        # This turns the check red; it does not by itself prevent a merge.
        # Add "Agent 3 - Reviewer" to the branch's required status checks to
        # make it binding.
        if result.get("verdict") == "request_changes":
            print("REVIEW GATE: changes requested - see the PR comment above.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Agent 3 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()