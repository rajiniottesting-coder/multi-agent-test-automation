"""
Agent 5 — Reporter.

Role:
    Reads test results (JUnit XML) produced by Agent 4 (Runner), summarizes
    them with the LLM, and posts a friendly comment to the parent Jira story.

Position in pipeline:
    Agent 1 (Test Designer) → Agent 2 (Coder) → Agent 3 (Reviewer) → Agent 4 (Runner) → [Agent 5: Reporter]

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

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m agents.agent5_reporter --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from core import junit_marks
from integrations.repo_host import get_repo_host
from integrations.tracker import get_tracker
from core.llm_client import LLMClient
from core.schemas import RunReport, TestResult, JiraCommentDraft
from config import (
    REQUIRED_JIRA_ENV_VARS,
    REQUIRED_LLM_ENV_VARS,
    validate_required_env,
)
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

    try:
        tree = ET.parse(junit_path)
    except ET.ParseError as e:
        # An empty or truncated junit.xml means the test RUN broke, not the
        # report. Pytest killed mid-write, a cancelled runner, or a truncated
        # artifact download all land here. The raw ParseError
        # ("no element found: line 1, column 0") tells the reader nothing, so
        # say what actually happened and what to look at.
        size = junit_path.stat().st_size if junit_path.exists() else 0
        raise ValueError(
            f"Could not parse {junit_path} ({size} bytes): {e}\n"
            f"  The file exists but is not valid XML - usually pytest was "
            f"killed before it finished writing, or the artifact download was "
            f"truncated.\n"
            f"  Check Agent 4's run: if the test job was cancelled or timed "
            f"out, re-run it rather than trusting this report."
        ) from e
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
                # Agent 4's marks: the application was unavailable (F-7); passed
                # only when retried once (F-19).
                outage=junit_marks.is_outage(tc),
                flaky=junit_marks.is_flaky(tc),
                first_failure=junit_marks.props(tc).get("first_failure") or None,
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
    if pr_number is None:
        # Keep what the report already knows rather than erase it.
        pr_number = report.pr_number

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
def build_final_comment(prose_body: str, report: RunReport,
                        outside: list = (), unscoped_total: int | None = None,
                        outages: list = ()) -> str:
    """Assemble the final Jira comment from LLM prose + deterministic links.

    Args:
        prose_body: The LLM-generated summary (just the verdict + failures, no links)
        report: The RunReport (which knows whether PR/commit/workflow links exist)
        outside: failures in tests the story does not own (see
            _failures_outside_scope). Listed by code, after the prose, with a
            one-line warning above it, so a reader cannot miss them.

        unscoped_total: set when the report could NOT be narrowed to the
            story's own tests. The comment then says so in plain words, so a
            whole-session count is never read as the story's own.

        outages: tests that failed because the application was unavailable
            (F-7), the story's or not. Listed apart, with a warning above the
            prose: they are neither passes nor failures of the change.

    Returns:
        Final markdown string ready to post to Jira.
    """
    parts: list[str] = []
    if unscoped_total is not None:
        parts.append(f"_Scope: all {unscoped_total} tests in this run - the run "
                     f"could not be narrowed to this story's own tests._")
        parts.append("")
    if outages:
        n = len(outages)
        parts.append(f"> ⚠ **Not judged:** {n} test{'' if n == 1 else 's'} could not "
                     f"run {'its' if n == 1 else 'their'} checks - the application was "
                     f"unavailable. See below; re-run once it is up.")
        parts.append("")
    if outside:
        parts.append(f"> ⚠ **Not green:** {len(outside)} test"
                     f"{'' if len(outside) == 1 else 's'} outside this story "
                     f"fail{'s' if len(outside) == 1 else ''} on this branch - see below.")
        parts.append("")
    parts.append(prose_body.rstrip())
    section = _outside_failures_section(outside)
    if section:
        parts.append("")
        parts.extend(section)
    section = _outage_section(outages)
    if section:
        parts.append("")
        parts.extend(section)
    section = _flaky_section([r for r in report.results if r.flaky])
    if section:
        parts.append("")
        parts.extend(section)

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


# How many outside failures the comment lists by name before summarising.
_OUTSIDE_LISTED = 15


def _failures_outside_scope(full: "RunReport", scoped: "RunReport") -> list:
    """Failed or errored tests in the whole session that the story does not own.

    Scoping keeps another story's failure out of THIS story's counts - a login
    failure listed under an unrelated key is noise. But scoping alone made the
    failure invisible: the PR check is red because the whole suite runs, and
    the Jira comment, computed from the scoped report, said "passed". A story
    that broke twenty committed tests reported itself green.

    So the story's own counts stay scoped, and what was dropped is kept here
    to be shown separately. When scoping did not happen, `scoped` IS `full`
    and this is empty - nothing is reported twice.
    """
    mine = {(r.classname, r.name) for r in scoped.results}
    return [r for r in full.results
            if r.status in ("failed", "error") and not r.outage
            and (r.classname, r.name) not in mine]


def _overall_verdict(scoped: "RunReport", outside: list, outages: list = ()) -> str:
    """'passed' only when the story's tests AND everything else on the branch pass.

    Must agree with the PR check, which runs the whole suite: a Jira comment
    saying "passed" next to a red check is the contradiction this exists to end.
    'unavailable' when nothing failed but some tests could not be judged
    because the application was unavailable (F-7) - not green, not a failure.
    """
    real = [r for r in scoped.results if r.status in ("failed", "error") and not r.outage]
    if (real if scoped.results else (scoped.failed or scoped.errors)) or outside:
        return "failed"
    if outages:
        return "unavailable"
    return "passed"


def _outside_failures_section(outside: list) -> list:
    """Markdown lines naming the failures outside the story. Built by code, not
    by the model, so it cannot be softened, summarised away or omitted."""
    if not outside:
        return []
    n = len(outside)
    lines = [
        f"**⚠ {n} other test{'' if n == 1 else 's'} failing on this branch**",
        "",
        "Not this story's tests, but they fail with this pull request's code, and "
        "the PR check is red because of them. Either this change broke them, or "
        "they already fail on `main` - this run cannot tell which. Compare with "
        "the latest run on `main` before merging.",
        "",
    ]
    for r in outside[:_OUTSIDE_LISTED]:
        module = r.classname.rsplit(".", 1)[-1]
        reason = (r.failure_message or "").strip().splitlines()
        lines.append(f"- `{module}::{r.name}` ({r.status})"
                     + (f" - {reason[0][:160]}" if reason else ""))
    if n > _OUTSIDE_LISTED:
        lines.append(f"- ...and {n - _OUTSIDE_LISTED} more - see the HTML report.")
    return lines


def _outage_section(outages: list) -> list:
    """Markdown naming the tests the application's unavailability stopped (F-7).
    Built by code: an outage must never read as a defect in the change."""
    if not outages:
        return []
    n = len(outages)
    lines = [f"**🌐 {n} test{'' if n == 1 else 's'} not judged: the application was "
             f"unavailable**", "",
             "The application refused or never answered these tests' requests, even "
             "after the retries. They are neither passes nor failures of this change.", ""]
    for r in outages[:_OUTSIDE_LISTED]:
        module = r.classname.rsplit(".", 1)[-1]
        reason = (r.failure_message or "").strip().splitlines()
        lines.append(f"- `{module}::{r.name}`" + (f" - {reason[0][:160]}" if reason else ""))
    if n > _OUTSIDE_LISTED:
        lines.append(f"- ...and {n - _OUTSIDE_LISTED} more - see the HTML report.")
    return lines


def fallback_draft(report: "RunReport", reason: BaseException) -> JiraCommentDraft:
    """The prose the model would write, written by code: used when the model
    cannot be called (the spend budget, F-24). Same shape as the prompt asks."""
    bad = [r for r in report.results if r.status in ("failed", "error")]
    if report.total and not bad and not report.failed and not report.errors:
        head = f"✅ **All {report.total} tests passed** in {report.duration_seconds:.2f}s"
        title = f"All {report.total} tests passed"
    else:
        n = len(bad) or (report.failed + report.errors)
        head = f"❌ **{n} of {report.total} tests failed** in {report.duration_seconds:.2f}s"
        title = f"{n} of {report.total} tests failed"
    lines = [head]
    if bad:
        lines += ["", "The following tests need attention:", ""]
        for r in bad[:_OUTSIDE_LISTED]:
            module = r.classname.rsplit(".", 1)[-1]
            msg = (r.failure_message or "").strip().splitlines()
            lines.append(f"- `{module}::{r.name}` — "
                         + ("**ERRORED**" if r.status == "error" else (msg[0][:160] if msg else "failed")))
    lines += ["", f"_Summary written without the model: {reason}_"]
    return JiraCommentDraft(title=title, body_markdown="\n".join(lines))


def _flaky_section(flaky: list) -> list:
    """Markdown naming the story's tests that passed only on the retry (F-19).
    They count as passed; a flake that is never named is never fixed."""
    if not flaky:
        return []
    lines = [f"**♻ Passed only on the retry (flaky):** {len(flaky)} test"
             f"{'' if len(flaky) == 1 else 's'} failed, then passed when run once more. "
             "Counted as passed and recorded on the pipeline health issue.", ""]
    for r in flaky[:_OUTSIDE_LISTED]:
        module = r.classname.rsplit(".", 1)[-1]
        lines.append(f"- `{module}::{r.name}`"
                     + (f" - first failure: {r.first_failure[:160]}" if r.first_failure else ""))
    if len(flaky) > _OUTSIDE_LISTED:
        lines.append(f"- ...and {len(flaky) - _OUTSIDE_LISTED} more - see the run summary.")
    return lines


# F-31 (D4): the report of the last run posted on the story, as a hidden issue
# property - a re-run of Agent 5 on the same commit with the same results posts
# nothing new (and costs no model call).
REPORT_PROPERTY = "agent5.report"


def report_fingerprint(story_key: str, full_report: "RunReport", verdict: str) -> str | None:
    """What a person reads in the report, as one hash: the story, the pull
    request, the commit, the verdict and every test's outcome. None without a
    commit - a run that cannot be told apart is always reported."""
    if not full_report.commit_sha:
        return None
    rows = sorted((r.classname, r.name, r.status, bool(r.outage), bool(r.flaky))
                  for r in full_report.results)
    payload = json.dumps([story_key, full_report.pr_number, full_report.commit_sha, verdict, rows])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _last_report(tracker, story_key: str) -> dict:
    """The stored fingerprint of the last report (properties ledger only)."""
    from core.usage_ledger import mode
    from integrations.tracker import capability
    get = capability(tracker, "get_property")
    if get is None or mode(tracker) != "properties":
        return {}
    try:
        return get(story_key, REPORT_PROPERTY) or {}
    except Exception as e:                                         # noqa: BLE001
        logger.info(f"Last report of {story_key} not read ({e}) - reporting.")
        return {}


def _remember_report(tracker, story_key: str, fingerprint: str | None, comment_url,
                     report: "RunReport") -> None:
    from core.usage_ledger import mode
    from integrations.tracker import capability
    setter = capability(tracker, "set_property")
    if not fingerprint or setter is None or mode(tracker) != "properties":
        return
    try:
        setter(story_key, REPORT_PROPERTY, {"fp": fingerprint, "ref": comment_url,
                                            "commit": report.commit_sha,
                                            "run": report.workflow_run_url})
    except Exception as e:                                         # noqa: BLE001
        logger.warning(f"Report fingerprint of {story_key} not kept: {e}")


def record_flakes(tracker, results: list, run_url: str | None) -> int:
    """Every flaky test of the run on the pipeline health issue - the whole
    run, not only the story's: a flake is the suite's problem. Never raises."""
    try:
        from core import flaky_tests
        return flaky_tests.record(tracker, [(f"{r.classname}::{r.name}", r.first_failure)
                                            for r in results if r.flaky], run_url)
    except Exception as e:                                         # noqa: BLE001
        logger.warning(f"Flaky tests not recorded (non-fatal): {e}")
        return 0


def _without_outages(report: "RunReport") -> "RunReport":
    """The report with outage results left out and the counts made to match:
    what the model summarises is only what the run could judge."""
    kept = [r for r in report.results if not r.outage]
    if len(kept) == len(report.results):
        return report
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for r in kept:
        counts[r.status] = counts.get(r.status, 0) + 1
    return report.model_copy(update={
        "results": kept, "total": len(kept), "passed": counts["passed"],
        "failed": counts["failed"], "errors": counts["error"], "skipped": counts["skipped"],
        "duration_seconds": round(sum(r.duration_seconds for r in kept), 3)})


def _classname_of(path: str) -> str:
    """'tests/step_defs/test_x.py' -> 'tests.step_defs.test_x' (junit style)."""
    return (path or "").replace("\\", "/").removesuffix(".py").replace("/", ".")


def _scope_to_story(report: "RunReport", cli_pr: int | None = None) -> "RunReport":
    """Narrow a whole-session report to the step-def modules the PR touched.

    Returns the report UNCHANGED - deliberately - when the scope cannot be
    established: no PR number, the API call fails, or the PR touched no
    step-def file at all. Over-reporting is a cosmetic defect; silently
    dropping a story's own failures because a lookup blipped would be a
    correctness one, and it would read as a green story.
    """
    pr_number = cli_pr or report.pr_number
    if not pr_number:
        logger.info("No PR number - reporting the whole session, unscoped.")
        return report
    try:
        changed = get_repo_host().get_pr_changed_files(int(pr_number))
        owned = {
            _classname_of(f.get("filename", ""))
            for f in (changed or [])
            if (f.get("filename", "") or "").replace("\\", "/")
               .startswith("tests/step_defs/")
            and (f.get("filename", "") or "").endswith(".py")
            and not (f.get("filename", "") or "").endswith("conftest.py")
        }
    except Exception as exc:                              # noqa: BLE001
        logger.warning("Could not scope to the story's own tests (%s); "
                       "reporting the whole session.", exc)
        return report
    if not owned:
        logger.info("PR #%s touched no step-def module - reporting unscoped.",
                    pr_number)
        return report

    mine = [r for r in report.results
            if any(r.classname == c or r.classname.startswith(c + ".")
                   for c in owned)]
    if not mine:
        # The PR added step defs but the junit holds none of them: the run
        # never reached them. Saying "0 tests" would be a lie of omission.
        logger.warning("None of the story's tests appear in junit.xml "
                       "(owned=%s) - reporting the whole session.",
                       sorted(owned))
        return report

    dropped = len(report.results) - len(mine)
    if dropped:
        logger.info("Scoped report to %s: kept %d test(s), dropped %d "
                    "belonging to other stories.",
                    ", ".join(sorted(owned)), len(mine), dropped)

    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for r in mine:
        counts[r.status] = counts.get(r.status, 0) + 1
    return report.model_copy(update={
        "results": mine,
        "total": len(mine),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "duration_seconds": round(sum(r.duration_seconds for r in mine), 3),
    })


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

    Branch names like 'auto/SCRUM-23-...' embed the *test case* key, not the
    user story. After the initial resolution we ask Jira whether that key is
    a Test Case linked to a parent Story; if so we escalate to the Story so
    run-summary comments land where humans expect to read them.

    See docs/GUIDE.md (§ Branch naming) for the full branch convention.
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
            # Escalate to parent Story when the branch encoded a Test Case key.
            # Best-effort: any failure here keeps the original key.
            try:
                from integrations.tracker import get_tracker
                parent = get_tracker().get_parent_story_key(key)
                if parent:
                    return parent
            except Exception as e:
                logger.warning(
                    f"Parent-story lookup failed for {key}; commenting on it directly. ({e})"
                )
            return key

    raise ValueError(
        "Could not determine Jira story key. Provide one of: "
        "--story <KEY> CLI arg, JIRA_STORY_KEY env var, or run on a "
        "PR branch with a Jira key (e.g., 'auto/PROJ-123-feature'). "
        "See docs/GUIDE.md (§ Branch naming)."
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

    # 1b. SCOPE: keep only the tests this STORY owns.
    #
    # reports/junit.xml is the whole `pytest tests/step_defs/` session - every
    # step-def module in the repo, not just the one this story generated. So a
    # three-scenario story was reported to Jira as "3 of 8 tests failed", with
    # a login failure it had nothing to do with listed under its own key. The
    # PR tells us which step-def files the story actually added or changed.
    #
    # The CI context comes FIRST: scoping needs the PR number, and the PR
    # number is resolved here (event payload, PR_NUMBER). It used to run
    # after scoping, so in CI the scope always saw "no PR number" and every
    # story's comment counted the whole session - "All 12 tests passed" on a
    # three-scenario story, and failures outside it never listed.
    report = gather_ci_context(report, cli_pr=cli_pr)
    full_report = report
    report = _scope_to_story(full_report, cli_pr=cli_pr)
    scoped_whole = report is full_report
    outside = _failures_outside_scope(full_report, report)
    outages = [r for r in full_report.results if r.outage]
    if outages:
        logger.warning("%d test(s) not judged: the application was unavailable - "
                       "reported apart from failures: %s", len(outages),
                       ", ".join(f"{r.classname}::{r.name}" for r in outages[:10]))
    if outside:
        logger.warning(
            "%d test(s) outside this story fail on this branch - reported "
            "separately, and the verdict is 'failed': %s",
            len(outside), ", ".join(f"{r.classname}::{r.name}" for r in outside[:10]))
    verdict = _overall_verdict(report, outside, outages)
    # What the model summarises is what the run could judge; the outages are
    # listed by code (build_final_comment).
    report = _without_outages(report)

    # 2. CONTEXT: already gathered above, before scoping.
    if report.pr_number:
        logger.info(f"PR context: #{report.pr_number} ({report.pr_url})")
    if report.workflow_run_url:
        logger.info(f"Workflow run: {report.workflow_run_url}")

    # 2b. F-31 (D4): the same commit with the same results is already on the
    # story (a re-run of this job, or of the tests with the same outcome).
    tracker = None if dry_run else get_tracker()
    fingerprint = report_fingerprint(story_key, full_report, verdict)
    last = _last_report(tracker, story_key) if tracker is not None and fingerprint else {}
    if fingerprint and last.get("fp") == fingerprint:
        logger.info(f"Same commit and the same results as the report already on {story_key} "
                    f"({last.get('ref')}) - not posted again, no model call.")
        if report.workflow_run_url and report.workflow_run_url != last.get("run"):
            # Another run of the tests that happened to agree: its flakes are new.
            record_flakes(tracker, full_report.results, report.workflow_run_url)
        return {"story_key": story_key, "title": "", "verdict": verdict,
                "failing_outside_story": len(outside), "total": report.total,
                "passed": report.passed, "failed": report.failed,
                "comment_url": last.get("ref"), "status": "unchanged_not_reposted"}

    # 3. REASON: ask LLM to draft the comment
    prompt_template = load_prompt()
    user_prompt = prompt_template.replace(
        "{run_report_json}",
        report.model_dump_json(indent=2),
    )

    from core import spend_budget
    if not dry_run:
        spend_budget.begin_story(story_key)          # F-24: within the story's budget
    llm = LLMClient(temperature=0.3)  # slight creativity for friendly tone
    try:
        if outages and report.total == 0:
            # F-7: none of the story's tests could be judged. Nothing for the
            # model to summarise - code says so (the outage section follows).
            draft = JiraCommentDraft(
                title="Not judged: the application was unavailable",
                body_markdown="⚠ **None of this story's tests could be judged** - the "
                              "application was unavailable during the run.")
        else:
            draft = llm.invoke_structured(
                system_prompt="You are a QA Lead summarizing automated test results for a "
                              "Jira story.",
                user_prompt=user_prompt,
                output_schema=JiraCommentDraft,
            )
    except spend_budget.BudgetExceeded as stop:
        # The results are still reported - the model only writes the prose,
        # so code writes it instead. A story over its budget is held.
        logger.warning(f"[BUDGET] {stop} - the summary is written without the model.")
        if not dry_run:
            spend_budget.hold_story(spend_budget.current_tracker(), stop)
        draft = fallback_draft(report, stop)

    logger.info(f"LLM draft title: {draft.title}")

    # 3b. ASSEMBLE: Python builds the final comment from LLM prose + deterministic links.
    # This avoids the LLM rendering "View PR (None)" when fields are unavailable.
    final_body = build_final_comment(draft.body_markdown, report, outside,
                                     unscoped_total=(full_report.total
                                                     if scoped_whole else None),
                                     outages=outages)

    # 3c. USAGE LEDGER: this agent's own usage, and the story's cost so far.
    # Property ledger (F-31): one line pointing to the story's cost comment,
    # which holds the table - not a copy of it in every report. Comment
    # ledger: the end-to-end table appended here, as before.
    from core.llm_client import log_usage_summary, reset_usage
    from core import usage_ledger as ul
    own_usage = log_usage_summary(f"story {story_key} (reporter)")
    reset_usage()
    own_entry = dict(own_usage)
    own_entry["agent"] = "Agent 5 (Reporter)"
    properties_ledger = tracker is not None and ul.mode(tracker) == "properties"
    try:
        if properties_ledger:
            line = ul.cost_line(story_key, tracker, extra_entries=[own_entry])
            if line:
                final_body = final_body + "\n\n---\n" + line
        else:
            ledger = ul.story_ledger(story_key, tracker) if tracker is not None else \
                {"entries": [], "holds": []}
            agg = ul.aggregate_entries(ledger["entries"], extra_entries=[own_entry])
            budget = spend_budget.settings()
            allowed = (ul._allowance(story_key, tracker, ledger, budget)
                       if tracker is not None else None)
            e2e_section = ul.format_e2e_section(agg, budget=budget, allowance=allowed)
            if e2e_section:
                final_body = final_body + "\n" + e2e_section
                logger.info(
                    "E2E story usage: %d agent runs, %s tokens, cost %s",
                    agg["agent_runs"], f"{agg['total_tokens']:,}",
                    f"${agg['total_cost_usd']:.4f}" if agg["total_cost_usd"] is not None else "n/a",
                )
    except Exception as e:
        logger.warning(f"Usage ledger aggregation failed (non-fatal): {e}")

    # 3d. Agent 0, stage 10, with the property ledger (F-31, D3): the
    # prediction's outcome is measured now and shown as a line of this report,
    # instead of a second comment posted at the same moment.
    outcome = None
    if properties_ledger:
        try:
            from config.paths import FEATURES_DIR
            from core.impact_results import record_prediction_outcome
            outcome = record_prediction_outcome(tracker, get_repo_host(), story_key,
                                                report.pr_number, report.pr_url,
                                                full_report.results, FEATURES_DIR, save=False)
            if outcome:
                from agents.agent0_impact import outcome_line
                final_body = final_body + "\n\n" + outcome_line(outcome)
        except Exception as e:                                     # noqa: BLE001
            logger.warning(f"Impact outcome skipped (non-fatal): {e}")
            outcome = None

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
            "verdict": verdict,
            "failing_outside_story": len(outside),
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "status": "draft_generated_dry_run",
        }

    jira = tracker
    # The comment is authored in Markdown. A tracker whose comments use another
    # markup converts it (Jira's REST v2 renders wiki markup, where a Markdown
    # table separator becomes a row of dashes and **bold** keeps its stars);
    # a tracker without the capability gets the Markdown as written.
    render = getattr(jira, "render_markdown", None)
    comment_url = jira.add_comment(story_key, render(final_body) if callable(render)
                                   else final_body)
    jira.add_label(story_key, "tests-run")  # idempotent — won't dup-add

    # A change story that revised tests OTHER stories own (Agent 0, stage 9):
    # one result line on each owner. Nothing for an ordinary story. Never
    # fails the report - the story's own comment is already posted.
    try:
        from config.paths import FEATURES_DIR
        from core.impact_results import post_owner_results
        post_owner_results(jira, story_key, report.pr_url, full_report.results, FEATURES_DIR)
    except Exception as e:                                     # noqa: BLE001
        logger.warning(f"Owner result lines skipped (non-fatal): {e}")
    # Agent 0, stage 10: when Agent 0 predicted this story's impact (shadow or
    # live), record recall and precision against what this run showed. Does
    # nothing otherwise, and never fails the report. With the property ledger
    # it was measured above and is in the report; here it is only kept.
    try:
        if outcome:
            from agents.agent0_impact import save_outcome
            save_outcome(jira, story_key, report.pr_url or f"#{report.pr_number}", outcome)
        elif not properties_ledger:
            from config.paths import FEATURES_DIR
            from core.impact_results import record_prediction_outcome
            record_prediction_outcome(jira, get_repo_host(), story_key, report.pr_number,
                                      report.pr_url, full_report.results, FEATURES_DIR)
    except Exception as e:                                     # noqa: BLE001
        logger.warning(f"Impact outcome skipped (non-fatal): {e}")
    # F-19: flakes go on the pipeline health issue (never a defect).
    record_flakes(jira, full_report.results, report.workflow_run_url)
    # Record this agent's usage on the ledger too, so any later re-run or
    # re-aggregation sees the full picture (and the cost comment shows it).
    ul.post_usage_to_story(story_key, "Agent 5 (Reporter)", own_usage, jira=jira)
    _remember_report(jira, story_key, fingerprint, comment_url, full_report)

    result = {
        "story_key": story_key,
        "title": draft.title,
        "verdict": verdict,
        "failing_outside_story": len(outside),
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
    parser = argparse.ArgumentParser(description="Agent 5 (Reporter): post test results to Jira",
        epilog=("example:\n  --story SCRUM-5"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
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

    # Fast-fail on missing config
    validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)

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
        if result.get("failing_outside_story"):
            print(f"            plus {result['failing_outside_story']} failing test(s) "
                  f"outside this story - listed in the comment")
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