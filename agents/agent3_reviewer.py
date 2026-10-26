"""
Agent 3 — Reviewer.

Role:
    Reads a GitHub Pull Request, performs an AI-driven code review using a
    rigorous checklist, and posts the review as a comment on the PR.

Position in pipeline:
    Agent 1 (Test Designer) → Agent 2 (Coder) → [Agent 3: Reviewer]
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
from dataclasses import dataclass

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


# A STOP NEEDS A FAILURE, NOT A LABEL.
#
# The waiver check above reads one phrase in one field, and exempts an
# explicit `blocking` severity. A review on SCRUM-111 then filed a
# `blocking` / `functional_bug` whose own description walked through the flow
# and ended "This flow is valid. No blocking bug - downgrading." The severity
# field was never changed, and the pull request went red while every test
# passed. Four incidents, four wordings: a phrase list does not converge.
#
# So blocking now requires positive evidence instead of the absence of a
# retraction: a non-empty `failure_scenario` - the step, the line, and what
# goes wrong. A model that concluded the code works has nothing to put there.
# A finding filed as blocking without one is lowered to `major` and shown,
# not dropped. Security is exempt, as everywhere in this module.
def _names_a_failure(issue) -> bool:
    return bool((getattr(issue, "failure_scenario", None) or "").strip())


def _require_failure_for_blocking(report: ReviewReport) -> ReviewReport:
    lowered = []
    issues = []
    for issue in report.issues:
        if (issue.severity == "blocking"
                and issue.issue_type not in _ALWAYS_BLOCKING_TYPES
                and not _names_a_failure(issue)):
            lowered.append(issue)
            issue = issue.model_copy(update={"severity": "major"})
        issues.append(issue)
    if lowered:
        logger.warning(
            "%d finding(s) filed as blocking LOWERED to major: none names a "
            "concrete failure (failure_scenario is empty), so nothing shows "
            "the code breaks: %s", len(lowered),
            "; ".join(f"{i.file_path}: {(i.description or '')[:120]}" for i in lowered))
        report = report.model_copy(update={"issues": issues})
    return report


def derive_verdict(report: ReviewReport) -> ReviewReport:
    """Recompute overall_verdict from the issues the review actually found.

    An issue counts as blocking when its SEVERITY says so, or when its TYPE is
    one whose own definition already asserts the code is broken: functional_bug
    ("test will fail") and security. A report that contains one of those and
    calls itself advisory has contradicted itself, and the issue is the more
    specific of the two statements.

    Derives in BOTH directions.

    It used to only raise, on the reasoning that a model wanting to block
    should be trusted to. But that makes the severity field meaningless in one
    direction: a review filed two `minor` / `best_practice` findings - both
    wording suggestions, its own summary calling the code "acceptable" - and
    still returned request_changes. The pull request went red on readability
    notes while Agent 4 was green.

    A gate that blocks on advisory findings is a gate people learn to
    override, and then it is not a gate. If a review wants to stop a pull
    request it has to file something that says so; that is what the severity
    and type fields are for.

    The lowering is logged loudly, because a verdict that disagrees with its
    own findings usually means the summary saw something the issue list did
    not capture - worth a human glance even though it no longer blocks.
    """
    report = _require_failure_for_blocking(report)
    blocking = [issue for issue in report.issues if _blocks(issue)]
    if not blocking:
        if report.overall_verdict == "request_changes":
            logger.warning(
                "Verdict LOWERED from 'request_changes' to 'comment': none of "
                "the %d finding(s) is blocking (%s). A review that wants to "
                "stop a pull request must file a finding that says so - "
                "blocking on advisory notes is how a gate gets overridden by "
                "habit. If the summary saw something the issue list did not, "
                "that is worth a human glance: %s",
                len(report.issues),
                ", ".join(sorted({f"{i.severity}/{i.issue_type}"
                                  for i in report.issues})) or "no findings",
                (report.summary or "")[:200],
            )
            return report.model_copy(update={"overall_verdict": "comment"})
        return report

    if report.overall_verdict == "request_changes":
        return report

    logger.warning(
        "Verdict raised from %r to 'request_changes': %d issue(s) assert the "
        "code is broken (%s). A review cannot report that a test will fail and "
        "call itself advisory.",
        report.overall_verdict, len(blocking),
        ", ".join(sorted({f"{i.severity}/{i.issue_type}" for i in blocking})),
    )
    return report.model_copy(update={"overall_verdict": "request_changes"})


# A PREDICTED FAILURE IS REFUTED BY A RUN.
#
# "This test will fail" is a prediction, and this repository runs the tests:
# Agent 4 executes every scenario on the same commit, in parallel with this
# review. PR #148 (SCRUM-111) was blocked by a major/functional_bug whose
# failure_scenario read "if the site renders two separate rows ... the
# assertion fails" and whose fix read "No code change needed if behaviour is
# confirmed". The runner had already confirmed it: all four scenarios passed
# on that commit. The review was blocking on a question the pipeline had
# answered.
#
# So when the ONLY thing stopping the pull request is a prediction that a
# test fails, the review waits for the runner on this exact commit. Green
# refutes the prediction: the finding is lowered to major and annotated, not
# dropped. Red, absent or still running at the deadline: the block stands -
# no evidence is never treated as good evidence. A finding that says the test
# PASSES WRONGLY is never refuted by a pass, and security never waits.
#
# PER SCENARIO, NOT PER RUN (SCRUM-206, PR #211). A red run used to keep every
# prediction blocking, however unrelated the red test. That run had one test
# fail on an HTTP 503 from the application, and a change story's PR is red
# BY DESIGN until the change is deployed (its absence test fails). The
# reviewer predicted the listing-card scenario would fail; that scenario
# passed, and the prediction still blocked. Now the finding names its
# scenario, the runner's junit report is read, and a prediction whose own
# scenario passed on this commit is refuted whatever else failed. A finding
# with no scenario, a scenario not in the report, or a report that cannot be
# read: judged on the whole run, exactly as before.
RUNNER_WORKFLOW = "agent4_runner.yml"
RUNNER_ARTIFACT_PREFIX = "pytest-report-"
RUNNER_REPORT_FILE = "junit.xml"
RUNNER_WAIT_SECONDS = 480
RUNNER_POLL_SECONDS = 20
_REFUTED_NOTE = ("Refuted by the runner: this commit's scenarios were executed "
                 "and passed, so the predicted failure did not happen.")


def _refutable_by_a_green_run(issue) -> bool:
    """A prediction that a test FAILS - whatever category it was filed under.

    Keyed on the claim, not the label: a `blocking` / `best_practice` finding
    whose failure_scenario predicts a failing test is the same prediction as
    a functional_bug, and a green run refutes it the same way. Security is
    never a prediction about a test result.
    """
    if issue.issue_type in _ALWAYS_BLOCKING_TYPES:
        return False
    outcome = getattr(issue, "test_outcome", None)
    if outcome == "fails":
        return _names_a_failure(issue)
    return issue.issue_type == "functional_bug" and outcome is None


def _blocks(issue) -> bool:
    """The one definition of a finding that stops a pull request."""
    return ((issue.severity in _BLOCKING_SEVERITIES
             or issue.issue_type in _ALWAYS_BLOCKING_TYPES
             or (issue.issue_type in _BLOCKING_ISSUE_TYPES
                 and issue.severity in _TYPE_BLOCKS_AT
                 and _names_a_failure(issue)))
            # A finding whose own fix opens with "no change required" has
            # withdrawn itself. Two exemptions: a security finding that shrugs
            # is still worth one look, and an explicit `blocking` severity is a
            # deliberate call that a waiver phrase does not get to overturn.
            and not (issue.issue_type not in _ALWAYS_BLOCKING_TYPES
                     and issue.severity not in _BLOCKING_SEVERITIES
                     and _waives_itself(issue)))


def _completed_runner_run(host, pr_number: int, head_branch: str, wait_seconds: int,
                          poll_seconds: int, sleep=None, clock=None) -> dict | None:
    """The runner's completed run on this PR's head commit, waiting for it, or
    None when there is none by the deadline or it cannot be read."""
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    head_sha = next((p.get("head_sha") for p in host.list_open_prs()
                     if p.get("number") == pr_number), None)
    if not head_sha:
        return None
    deadline = clock() + wait_seconds
    while True:
        runs = [r for r in host.get_workflow_runs(RUNNER_WORKFLOW, head_branch)
                if r.get("head_sha") == head_sha]
        done = [r for r in runs if r.get("status") == "completed"]
        if done:
            return done[0]
        if clock() >= deadline:
            return None
        sleep(poll_seconds)


def runner_result_for_head(host, pr_number: int, head_branch: str,
                           wait_seconds: int = RUNNER_WAIT_SECONDS,
                           poll_seconds: int = RUNNER_POLL_SECONDS,
                           sleep=None, clock=None) -> str | None:
    """'success' / 'failure' / ... for the runner on this PR's head commit, or
    None when it has not concluded by the deadline or cannot be read."""
    run = _completed_runner_run(host, pr_number, head_branch, wait_seconds,
                                poll_seconds, sleep, clock)
    return run.get("conclusion") if run else None


@dataclass(frozen=True)
class RunnerEvidence:
    """The runner's verdict on this commit, and - when its report could be
    read - each scenario's outcome ({scenario key: [outcomes]}, see
    scenario_key()). `scenarios` is None when the report is unavailable."""
    conclusion: str | None
    scenarios: dict | None = None


def scenario_key(title: str) -> str:
    """One spelling for a scenario title and the test pytest-bdd generates from
    it: lower case, letters and digits only, without a leading `test` and an
    outline's `[...]` parameters. 'Searching for a non-existent product' and
    `test_searching_for_a_nonexistent_product` give the same key."""
    text = re.sub(r"\[.*\]$", "", (title or "").strip())
    text = re.sub(r"^test_", "", text.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_junit_scenarios(xml_bytes: bytes | None) -> dict | None:
    """{scenario key: [outcome, ...]} from a junit report, None when unreadable.

    Outcome is 'passed', 'failed', 'error' or 'skipped'. A list, because two
    features may hold a scenario of the same title, and an outline runs once
    per example: a prediction is refuted only when EVERY run of its scenario
    passed.
    """
    if not xml_bytes:
        return None
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("Runner report unreadable (%s); judging the whole run.", e)
        return None
    out: dict = {}
    for case in root.iter("testcase"):
        tags = {child.tag for child in case}
        outcome = ("failed" if "failure" in tags else "error" if "error" in tags
                   else "skipped" if "skipped" in tags else "passed")
        out.setdefault(scenario_key(case.get("name", "")), []).append(outcome)
    return out


def runner_evidence_for_head(host, pr_number: int, head_branch: str,
                             wait_seconds: int = RUNNER_WAIT_SECONDS,
                             poll_seconds: int = RUNNER_POLL_SECONDS,
                             sleep=None, clock=None) -> RunnerEvidence:
    """The runner's conclusion on this commit, plus each scenario's outcome
    when the run is red and its report can be read. Never raises."""
    run = _completed_runner_run(host, pr_number, head_branch, wait_seconds,
                                poll_seconds, sleep, clock)
    if not run:
        return RunnerEvidence(None)
    conclusion = run.get("conclusion")
    if conclusion == "success" or run.get("id") is None:
        return RunnerEvidence(conclusion)
    try:
        report = host.get_run_artifact_file(run["id"], RUNNER_ARTIFACT_PREFIX,
                                            RUNNER_REPORT_FILE)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Runner report not read (%s); judging the whole run.", e)
        report = None
    return RunnerEvidence(conclusion, parse_junit_scenarios(report))


_SCENARIO_IN_TEXT = re.compile(r"\bscenario(?:\s+outline)?\s*:?\s*['\"\u2018\u201c]([^'\"\u2019\u201d\n]{3,})"
                               r"['\"\u2019\u201d]", re.IGNORECASE)


def _predicted_scenario(issue) -> str | None:
    """The scenario a prediction is about: its `scenario` field, else a quoted
    scenario title in its failure_scenario ("Scenario 'X': at the ... step")."""
    named = (getattr(issue, "scenario", None) or "").strip()
    if named:
        return re.sub(r"^\s*scenario(?:\s+outline)?\s*:\s*", "", named, flags=re.IGNORECASE)
    m = _SCENARIO_IN_TEXT.search(getattr(issue, "failure_scenario", None) or "")
    return m.group(1).strip() if m else None


def _scenario_passed(issue, scenarios: dict | None) -> str | None:
    """The scenario's title when every run of it passed in the report, else None."""
    title = _predicted_scenario(issue)
    if not title or not scenarios:
        return None
    outcomes = scenarios.get(scenario_key(title))
    return title if outcomes and all(o == "passed" for o in outcomes) else None


def apply_runner_evidence(report: ReviewReport, runner_result) -> ReviewReport:
    """Lower every blocking prediction of a failing test that the run refuted.

    runner_result is the run's conclusion ('success', ...) or a RunnerEvidence.
    A green run refutes every prediction. A red run refutes a prediction whose
    own scenario passed on this commit (RunnerEvidence.scenarios); the others
    keep blocking.

    Each finding is judged on its own: a refuted prediction stops blocking even
    when another, unrelated finding still stops the pull request - otherwise it
    is shown as Blocking beside the real one and the reader fixes the wrong
    thing. The verdict is re-derived by align_labels_with_verdict.
    """
    candidates = [i for i in report.issues if _blocks(i) and _refutable_by_a_green_run(i)]
    if not candidates:
        return report
    if isinstance(runner_result, RunnerEvidence):
        conclusion, scenarios = runner_result.conclusion, runner_result.scenarios
    else:
        conclusion, scenarios = runner_result, None
    if conclusion == "success":
        notes = {id(i): _REFUTED_NOTE for i in candidates}
    else:
        notes = {}
        for issue in candidates:
            title = _scenario_passed(issue, scenarios)
            if title:
                notes[id(issue)] = (f"Refuted by the runner: scenario '{title}' was executed "
                                    f"on this commit and passed, so the predicted failure "
                                    f"did not happen.")
        if not notes:
            logger.info("Runner result for this commit: %s - predicted failure(s) "
                        "keep blocking%s.", conclusion or "not concluded",
                        "" if scenarios else " (no per-scenario report)")
            return report
    issues = []
    for issue in report.issues:
        note = notes.get(id(issue))
        if note:
            # Shown as a note, without its failure scenario: a "Fails when"
            # line under a finding the run just disproved reads as a failure.
            issue = issue.model_copy(update={
                "severity": "info",
                "issue_type": "best_practice",
                "failure_scenario": None,
                "test_outcome": None,
                "description": f"{issue.description} ({note})",
            })
        issues.append(issue)
    logger.warning("%d of %d predicted test failure(s) REFUTED by the runner on this "
                   "commit (%s). Lowered, not dropped.", len(notes), len(candidates),
                   "the run passed" if conclusion == "success" else "their scenarios passed")
    return report.model_copy(update={"issues": issues})


def _needs_runner_evidence(report: ReviewReport) -> bool:
    """Any blocking finding that only predicts a failing test: worth the wait."""
    return any(_blocks(i) and _refutable_by_a_green_run(i) for i in report.issues)


# THE REPORT MUST SAY ONE THING.
#
# The gate fixes made the VERDICT follow the findings, but the comment a human
# reads kept contradicting itself. The final review of PR #148 (SCRUM-111)
# was advisory - correct - yet its summary still announced "SCRUM-215 has a
# functional bug", and it listed a major/functional_bug whose own fix read
# "No change required ... Leaving as advisory." A reader trusts the summary
# and the label, not the fine print, so the gate was right and the page was
# wrong.
#
# So findings are reconciled before anything is rendered:
#   - a finding whose own fix asks for nothing is WITHDRAWN, even if it names
#     a failure: not listed, counted in a footnote, logged in full
#   - a functional_bug that names no failure is not a functional bug: it is
#     shown as an unverified info note
# and when that, or any later step, changed what the model filed, the model's
# summary describes findings that no longer exist and is replaced with one
# built from the final list. Security findings are never touched.
def reconcile_findings(report: ReviewReport) -> tuple[ReviewReport, list]:
    """(report with substantiated findings only, withdrawn findings)."""
    kept, withdrawn = [], []
    for issue in report.issues:
        if issue.issue_type in _ALWAYS_BLOCKING_TYPES:
            kept.append(issue)
            continue
        # Its own fix asks for nothing, so there is nothing for anyone to do -
        # even when it names a failure. PR #148's fifth review filed one that
        # did both: "Fails when: ... this is the test doing its job, not a
        # bug - downgrading" / "No code change required". A finding that
        # still wants something says so in the same sentence ("but ...",
        # "however ..."), which _waives_itself already honours.
        if _waives_itself(issue):
            withdrawn.append(issue)
            continue
        if issue.issue_type == "functional_bug" and not _names_a_failure(issue):
            issue = issue.model_copy(update={
                "issue_type": "best_practice", "severity": "info",
                "description": f"Unverified - no failing scenario was named. {issue.description}",
            })
        kept.append(issue)
    if withdrawn:
        logger.info("%d finding(s) WITHDRAWN - their own suggested fix asks for "
                    "no change: %s", len(withdrawn),
                    "; ".join(f"{i.file_path}: {(i.description or '')[:120]}" for i in withdrawn))
    return report.model_copy(update={"issues": kept}), withdrawn


def _signature(issues) -> list:
    return [(i.file_path, i.line_number, i.severity, i.issue_type, i.description)
            for i in issues]


def finalize_summary(original: ReviewReport, final: ReviewReport,
                     withdrawn_count: int = 0) -> ReviewReport:
    """Keep the model's summary only if the findings it describes survived."""
    if _signature(original.issues) == _signature(final.issues) and not withdrawn_count:
        return final
    counts = {}
    for issue in final.issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    listed = ", ".join(f"{counts[k]} {k}" for k in ("blocking", "major", "minor", "info")
                       if counts.get(k)) or "none"
    stops = ("Nothing here blocks this pull request."
             if final.overall_verdict != "request_changes"
             else "The blocking finding(s) below must be fixed before merge.")
    summary = (f"Findings after verification: {listed}. {stops} Findings the reviewer "
               f"filed without a concrete failure, or withdrew in its own fix, were "
               f"lowered or left out, so the reviewer's original summary was replaced.")
    return final.model_copy(update={"summary": summary})


# A PULL REQUEST IS JUDGED ON WHAT IT CHANGES.
#
# PR #160 changed one line of a test file. The review blocked it on a
# different, pre-existing line of that file - a vacuous assertion that had
# been on main for weeks - and the same code had been "ready" on the
# previous run. Pre-existing defects are worth reporting, but blocking on
# them makes the gate depend on which old line the model happens to read,
# and stops a correct change for something it did not do.
#
# So a finding located on a line the pull request did not touch is lowered
# to an info note marked pre-existing. "Touched" is generous: every line
# inside a changed hunk (context included) plus a small margin, because the
# model's line numbers drift by a few lines. A finding with no line, in a
# file the PR added, or with no patch to read is left alone - no evidence,
# no change. Security is never lowered.
_LINE_MARGIN = 3
_PRE_EXISTING = "Pre-existing - not on a line this pull request changed."
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_line_map(changed_files) -> dict:
    """{path: set of head-side line numbers inside changed hunks}, or the
    string "all" for an added file. Files without a patch are omitted."""
    out: dict = {}
    for f in changed_files or []:
        path = (f.get("filename") or "").replace("\\", "/")
        if not path:
            continue
        if f.get("status") == "added":
            out[path] = "all"
            continue
        patch = f.get("patch")
        if not patch:
            continue
        lines: set = set()
        for row in patch.splitlines():
            m = _HUNK.match(row)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                lines.update(range(start - _LINE_MARGIN, start + count + _LINE_MARGIN))
        out[path] = lines
    return out


def lower_findings_on_unchanged_lines(report: ReviewReport, changed: dict | None) -> ReviewReport:
    if not changed:
        return report
    issues, lowered = [], 0
    for issue in report.issues:
        where = changed.get((issue.file_path or "").replace("\\", "/"))
        on_unchanged_line = (issue.issue_type not in _ALWAYS_BLOCKING_TYPES
                             and issue.line_number is not None
                             and isinstance(where, set)
                             and issue.line_number not in where)
        if on_unchanged_line:
            lowered += 1
            issue = issue.model_copy(update={
                "severity": "info", "issue_type": "best_practice",
                "failure_scenario": None, "test_outcome": None,
                "description": f"{_PRE_EXISTING} {issue.description}"})
        issues.append(issue)
    if lowered:
        logger.info("%d finding(s) on lines this PR did not change were lowered "
                    "to pre-existing notes.", lowered)
    return report.model_copy(update={"issues": issues})


def postprocess_review(report: ReviewReport, get_runner_result=None,
                       changed_lines: dict | None = None) -> tuple[ReviewReport, list]:
    """Everything between the model's answer and the posted comment, in order.

    One function so the whole chain can be replayed on a real review: dedupe,
    reconcile findings, derive the verdict, consult the runner when only
    predicted failures block (`get_runner_result` is a zero-argument callable, or
    None to skip), then make the summary match what is left.
    """
    report = dedupe_and_cap_issues(report, max_issues=MAX_ISSUES)
    as_filed = report
    report, withdrawn = reconcile_findings(report)
    report = lower_findings_on_unchanged_lines(report, changed_lines)
    report = derive_verdict(report)
    if _needs_runner_evidence(report) and get_runner_result is not None:
        logger.info("Only predicted test failures block this review - waiting "
                    "up to %ds for the runner on this commit.", RUNNER_WAIT_SECONDS)
        report = apply_runner_evidence(report, get_runner_result())
    report = align_labels_with_verdict(report)
    return finalize_summary(as_filed, report, len(withdrawn)), withdrawn


def align_labels_with_verdict(report: ReviewReport) -> ReviewReport:
    """A reader sees the verdict and the section headings, so they must agree.

    `request_changes` exactly when a finding stops the pull request, and every
    finding that stops it is shown under Blocking - a major/functional_bug that
    blocks used to sit under "Major" beneath a red verdict. Anything that does
    not block is never shown as Blocking.
    """
    issues = []
    for issue in report.issues:
        blocks = _blocks(issue)
        if blocks and issue.severity != "blocking":
            issue = issue.model_copy(update={"severity": "blocking"})
        elif not blocks and issue.severity == "blocking":
            issue = issue.model_copy(update={"severity": "major"})
        issues.append(issue)
    verdict = ("request_changes" if any(i.severity == "blocking" for i in issues)
               else ("comment" if report.overall_verdict == "request_changes"
                     else report.overall_verdict))
    return report.model_copy(update={"issues": issues, "overall_verdict": verdict})


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def load_prompt() -> str:
    return (PROMPTS_DIR / "agent3_reviewer.md").read_text(encoding="utf-8")


# WHAT A BASEPAGE HELPER DOES IS WRITTEN DOWN - SHOW IT.
#
# The prompt tells the reviewer not to speculate about pages/base_page.py, a
# file outside the diff. It speculated anyway when a finding turned on what a
# helper DOES: PR #211 was blocked on "click_in_row will hit two Add to cart
# controls in one card", which the helper's docstring describes and handles
# (it clicks the visible one) - and the scenario passed. Each helper the
# changed page objects call is now shown with its signature and docstring, read
# from the real file, so a claim about it can be checked against it.
_MAX_HELPER_DOC = 1600


def base_page_helpers_called(changed_files: list[dict], project_root=None) -> str:
    """Signature and docstring of every BasePage helper the changed page objects
    call on the lines this pull request added (the whole file when no diff is
    known), as a prompt section; "" when there are none or BasePage is unreadable."""
    import ast
    from pathlib import Path

    from config.paths import PROJECT_ROOT
    root = Path(project_root) if project_root else PROJECT_ROOT
    try:
        tree = ast.parse((root / "pages" / "base_page.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    base = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BasePage"), None)
    if base is None:
        return ""
    helpers = {n.name: n for n in base.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    called: list[str] = []
    for f in changed_files or []:
        name = (f.get("filename") or "").replace("\\", "/")
        if not (name.startswith("pages/") and name.endswith(".py")) or name.endswith("base_page.py"):
            continue
        # The lines this pull request added, when the diff is known: a helper
        # the file called before the change is not what is under review.
        added = "\n".join(line[1:] for line in (f.get("patch") or "").splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        text = added or f.get("content") or ""
        for m in re.finditer(r"\bself\.([A-Za-z_]\w*)\s*\(", text):
            if m.group(1) in helpers and m.group(1) not in called:
                called.append(m.group(1))
    if not called:
        return ""

    blocks = []
    for helper in sorted(called):
        node = helpers[helper]
        args = ast.unparse(node.args).replace("self, ", "").replace("self", "").strip()
        returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
        doc = (ast.get_docstring(node) or "(no docstring)").strip()
        if len(doc) > _MAX_HELPER_DOC:
            doc = doc[:_MAX_HELPER_DOC].rsplit(" ", 1)[0] + " ..."
        blocks.append(f"### `self.{helper}({args}){returns}`\n```\n{doc}\n```")
    return ("These are the `pages/base_page.py` helpers the changed page objects call, "
            "read from the real file. A finding about what one of them does must agree "
            "with its docstring here.\n\n" + "\n\n".join(blocks))


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
def format_review_as_markdown(report: ReviewReport, withdrawn_count: int = 0) -> str:
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
                if (issue.failure_scenario or "").strip():
                    md.append(f"   **Fails when:** {issue.failure_scenario.strip()}")
                    md.append("")
                md.append(f"   **Suggested fix:**")
                md.append(f"   {issue.suggested_fix}")
                md.append("")
    else:
        md.append("### No issues found 🎉")
        md.append("")
    if withdrawn_count:
        md.append(f"_{withdrawn_count} further finding(s) were withdrawn by the "
                  f"reviewer's own suggested fix (no change requested) and are "
                  f"listed only in the workflow log._")
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
        .replace("{base_page_helpers_section}",
                 base_page_helpers_called(changed_files) or "(The changed page objects call no BasePage helper.)")
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
    # A green runner is evidence about app tests only if it ran them. Agent 4
    # skips the browser when this PR changes nothing a test reads (same rule,
    # core/test_runtime.py); its green then says nothing about a predicted
    # failure, so no runner result is offered.
    from core.test_runtime import runs_app_tests
    runner_ran_app_tests = runs_app_tests([f.get("filename", "") for f in changed_files])
    report, withdrawn = postprocess_review(
        report,
        None if dry_run or not runner_ran_app_tests else
        (lambda: runner_evidence_for_head(gh, pr_number, pr_metadata["head_branch"])),
        changed_lines=changed_line_map(changed_files))

    logger.info(f"Review verdict: {report.overall_verdict}")
    logger.info(f"Issues found: {len(report.issues)}")
    for issue in report.issues:
        logger.info(f"  - [{issue.severity}/{issue.issue_type}] {issue.file_path}: {issue.description}")

    # 4. FORMAT
    markdown = format_review_as_markdown(report, withdrawn_count=len(withdrawn))

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