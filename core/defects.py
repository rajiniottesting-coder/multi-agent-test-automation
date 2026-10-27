"""Failure-to-defect triage: a test failing on main raises one defect (F-22).

WHY
    Agent 5 comments only on the story of a pull request. A test that failed
    on `main` - in the scheduled run (F-21), after a runtime change was pushed,
    or in a manual run on main - reached nobody: the diagnosis and the evidence
    existed, and nothing routed them to a person.

WHAT
    After a run on main (scripts/triage_failures.py), for each test that still
    fails after the retry:
      - one defect per TEST AND CAUSE (the diagnosis label), found again by a
        label `<defects.label>-<hash>`. A repeat updates its description (how
        often, first and last seen, the latest failure and run) - no comment,
        so watchers are not emailed every night for the same failure;
      - a new defect carries the test, its test case and owning story (from
        the scenario's `# JIRA:` marker), the diagnosed cause and fix, the
        failure and the run link. At most `max_new_per_run` per run: more is a
        broken build or an outage, and one health alert says so instead;
      - when its test passes in a later run on main, the defect gets
        `passing_label` and ONE comment suggesting it be closed - a person
        decides. Failing again removes the label, with one comment.
    Outages (F-7) and flakes (F-19) never raise a defect: the outage opens a
    health alert, the flake is recorded on the health issue.

Generic: no application, test or tracker name lives here. Every write is
best-effort per defect - one failing write never stops the others.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import re
from pathlib import Path

from core import junit_marks as jm
from core.json_block import read_json_block
from core.ops_settings import section
from integrations.tracker import capability

logger = logging.getLogger(__name__)

DATA_OPEN, DATA_CLOSE = "{code:json}", "{code}"


def settings() -> dict:
    return section("defects")


def defect_label(test_id: str, cause: str, s: dict | None = None) -> str:
    """The label that finds this test's defect for this cause again."""
    s = s or settings()
    digest = hashlib.sha1(f"{test_id}|{cause}".encode("utf-8")).hexdigest()[:10]
    return f"{s['label']}-{digest}"


# ── which story owns a failing test ──────────────────────────

def owner_of(test_id: str, features_dir: Path, tracker=None) -> tuple:
    """(test case key, owning story key) of a test from its scenario's marker,
    (None, None) when the scenario is not marked or cannot be found."""
    try:
        from agents.agent2_coder import build_marker_index
        from core.impact_results import _test_name
        classname, _, name = test_id.partition("::")
        module = classname.rsplit(".", 1)[-1]
        name = re.sub(r"\[.*\]$", "", name)
        for entry in build_marker_index(Path(features_dir)).by_key.values():
            if "test_" + entry.file.rsplit(".", 1)[0] == module and _test_name(entry.title) == name:
                owner = getattr(entry, "owner", None)
                if not owner and tracker is not None:
                    owner = tracker.get_parent_story_key(entry.key)
                return entry.key, owner
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Owner of %s not found: %s", test_id, e)
    return None, None


# ── the description: a page for people, a block for the triage ──

def _safe(text: str) -> str:
    """Failure text that cannot end the code block it is shown in."""
    return (text or "").replace("```", "'''").replace("{code", "{ code")


def render(tracker, state: dict) -> str:
    md = [
        "A test fails on `main`. Raised by the defect triage after a run on main "
        "(scheduled, or after a change that affects the tests). One defect per test and "
        "cause: a repeat updates this description; when the test passes again on main this "
        "defect gets a label and one comment suggesting it be closed - a person decides.",
        "",
        f"**Test:** `{state['test']}`",
        "**Test case:** " + (f"{state['test_case']} (owning story: "
                             f"{state.get('owner') or 'not found'})"
                             if state.get("test_case") else "not marked - no `# JIRA:` marker"),
        f"**Cause ({state['cause']}):** {state['cause_text']}",
        f"**Fix:** {state['remedy']}",
        "",
        "**Latest failure:**",
        "",
        "```",
        _safe(state["failure"]),
        "```",
        "",
        f"**Seen:** {state['times']} time(s) - first {state['first_seen']}, last "
        f"{state['last_seen']}" + (f" - [latest run]({state['last_run']})"
                                   if state.get("last_run") else ""),
        "",
        "Evidence (screenshot, video, trace) is in the run's `pytest-report-*` artifact, "
        "under `reports/failure-evidence/`.",
    ]
    text = "\n".join(md)
    render_md = capability(tracker, "render_markdown")
    try:
        text = render_md(text) if render_md else text
    except Exception:                                              # noqa: BLE001
        pass
    return (text + "\n\nTriage data - read back by the pipeline, leave it as it is:\n"
            + DATA_OPEN + "\n" + json.dumps(state, indent=1) + "\n" + DATA_CLOSE)


def state_of(description: str) -> dict | None:
    data = read_json_block(description or "")
    return data if isinstance(data, dict) and data.get("test") else None


def _failure_excerpt(case) -> str:
    lines = jm.failure_text(case).strip().splitlines()
    return "\n".join(lines[:15])[:1500] or "(no message)"


def _diagnosis(case):
    from core.failure_diagnosis import diagnose_with_context
    captured = "\n".join((n.text or "") for tag in ("system-out", "system-err")
                         for n in case.findall(tag))
    return diagnose_with_context(jm.failure_text(case), captured)


# ── the triage ───────────────────────────────────────────────

def open_defects(tracker, s: dict) -> dict:
    """{defect label: issue dict} for every open defect the triage raised."""
    found = tracker.find_stories_to_process(
        {"issue_type": s["issue_type"], "required_labels": [s["label"]],
         "allowed_statuses": list(s["open_statuses"])}, max_results=200)
    out = {}
    prefix = s["label"] + "-"
    for issue in found or []:
        for label in issue.get("labels") or []:
            if label.startswith(prefix) and label != s["passing_label"]:
                out[label] = issue
    return out


def triage(tracker, root, run_url: str, features_dir: Path, now: _dt.datetime | None = None,
           dry_run: bool = False) -> dict:
    """Raise, update and flag defects for one run on main. Returns what it did:
    {"raised", "updated", "passing", "failing_again", "capped", "outages", "flaky"}."""
    s = settings()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    today = now.date().isoformat()
    cases = jm.cases(root)
    failing = [c for c in cases if jm.outcome(c) in ("failed", "error") and not jm.is_outage(c)]
    result = {"raised": [], "updated": [], "passing": [], "failing_again": [], "capped": [],
              "outages": [jm.case_id(c) for c in cases if jm.is_outage(c)],
              "flaky": [jm.case_id(c) for c in cases if jm.is_flaky(c)]}
    if not s.get("enabled", True):
        logger.info("defects.enabled is false - no defect is raised.")
        return result
    create = capability(tracker, "create_issue")
    try:
        existing = open_defects(tracker, s)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Open defects not read (%s); none raised this run.", e)
        return result
    failing_labels = set()
    for case in failing:
        test = jm.case_id(case)
        d = _diagnosis(case)
        label = defect_label(test, d.label, s)
        failing_labels.add(label)
        issue = existing.get(label)
        try:
            if issue is not None:
                state = state_of(issue.get("description", "")) or {}
                state.update(test=test, cause=d.label, cause_text=d.cause, remedy=d.remedy,
                             failure=_failure_excerpt(case), last_seen=today, last_run=run_url,
                             times=int(state.get("times", 1)) + 1)
                state.setdefault("first_seen", today)
                if not dry_run:
                    tracker.set_description(issue["key"], render(tracker, state))
                result["updated"].append(issue["key"])
                if s["passing_label"] in (issue.get("labels") or []):
                    if not dry_run:
                        tracker.remove_label(issue["key"], s["passing_label"])
                        tracker.add_comment(issue["key"], f"Failing again on main: {run_url}")
                    result["failing_again"].append(issue["key"])
                continue
            if len(result["raised"]) >= int(s["max_new_per_run"]):
                result["capped"].append(test)
                continue
            if create is None:
                logger.warning("The tracker cannot create issues - no defect for %s.", test)
                result["capped"].append(test)
                continue
            tc_key, owner = owner_of(test, features_dir, tracker)
            state = {"test": test, "test_case": tc_key, "owner": owner, "cause": d.label,
                     "cause_text": d.cause, "remedy": d.remedy,
                     "failure": _failure_excerpt(case), "first_seen": today,
                     "last_seen": today, "last_run": run_url, "times": 1}
            summary = f"[Auto] {test.rsplit('.', 1)[-1][:150]} fails on main: {d.label}"
            if dry_run:
                result["raised"].append(f"(dry run) {summary}")
                continue
            key = create(s["issue_type"], summary, render(tracker, state), [s["label"], label])
            result["raised"].append(key)
            logger.warning("Defect %s raised: %s", key, summary)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Defect for %s not written: %s", test, e)

    # A pass only on the retry is no sign the defect is gone (F-19).
    passed = {jm.case_id(c) for c in cases if jm.outcome(c) == "passed" and not jm.is_flaky(c)}
    for label, issue in existing.items():
        if label in failing_labels:
            continue
        state = state_of(issue.get("description", "")) or {}
        if state.get("test") not in passed or s["passing_label"] in (issue.get("labels") or []):
            continue                     # not run this time, or already flagged
        try:
            if not dry_run:
                tracker.add_label(issue["key"], s["passing_label"])
                tracker.add_comment(issue["key"],
                                    f"Passed on main: {run_url}. Suggest closing this defect "
                                    "if it stays green; it is not closed automatically.")
            result["passing"].append(issue["key"])
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Defect %s not flagged as passing: %s", issue.get("key"), e)
    return result
