"""Failure-to-defect triage: a test failing on main raises one defect (F-22).

WHY
    Agent 5 comments only on the story of a pull request. A test that failed
    on `main` - in the scheduled run (F-21), after a runtime change was pushed,
    or in a manual run on main - reached nobody: the diagnosis and the evidence
    existed, and nothing routed them to a person.

WHAT
    After a run on main (scripts/triage_failures.py), for each test that still
    fails after the retry:
      - one OPEN defect per TEST: a failure first finds the open defect of its
        test and cause (its fingerprint `<defects.label>-<hash>`), else any
        open defect of its test - the cause is a heuristic reading and the
        same problem can read differently from one night to the next (10 Nov
        2026: four duplicates in one run). A repeat updates the description
        (how often, first and last seen, the latest failure and run, and the
        causes seen) - no comment, so watchers are not emailed every night;
      - a new defect carries the test, its test case and owning story (from
        the scenario's `# JIRA:` marker), the diagnosed cause and fix, the
        failure and the run link. At most `max_new_per_run` per run: more is a
        broken build or an outage, and one health alert says so instead;
      - when its test passes in a later run on main, the defect gets
        `passing_label` and ONE comment suggesting it be closed - a person
        decides. Failing again removes the label, with one comment.
    Outages (F-7) and flakes (F-19) never raise a defect: the outage opens a
    health alert, the flake is recorded on the health issue.

    Traceability (`trace_links`, `copy_components`): every defect is LINKED to
    what its test verifies, so the test case and the story show it - not only
    named in the description:
      - "<defect> blocks <test case>" (link kind `defect_of`) and
        "<defect> relates to <story>" (`defect_story`); the link types are the
        tracker's, from `tracker.link_types`;
      - the defect takes the story's components;
      - where the test is traced from: its scenario's `# JIRA:` marker (test
        case and story); else the one story every marked scenario of its
        feature file shares; else `defects.trace_owners` (a feature file ->
        story, for files that must not carry markers, such as the reserved
        reference files); else it is NOT traced - label `unmapped_label` and
        one health alert, never silent;
      - kept current on every update: a missing link is added (defects raised
        before this existed included), a moved owner or test case moves its
        link, the unmapped label goes once the test is traced.

    Only after a rerun (`only_after_retry`, on by default): a defect is raised
    or updated only for a test that failed, was run again once the application
    was found up (core/app_probe.py), and failed again (`retried`). A failure
    that was not run again - more failures than the retry takes, or a retry
    that did not run - raises nothing and is listed in one health alert: a
    single failure is not yet evidence of a defect (30 Oct 2026: 17 of 17
    failed on an application that was not itself, and ten defects were raised
    from the first run alone).

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
    """The fingerprint of this test's defect for this cause: `<label>-<10 hex>`.

    It identifies the defect; it is no longer a LABEL on it. Every defect's
    triage data (its description) holds the test and the cause, so the
    fingerprint is computed from them again (fingerprint_of). As a label it
    filled the tracker's label suggestions with one meaningless code per test
    and cause, kept by closed defects too (3 Nov 2026). Defects raised before
    carry it as a label: read as a fallback, removed when the defect is next
    updated (scripts/tidy_defect_labels.py removes the rest)."""
    s = s or settings()
    digest = hashlib.sha1(f"{test_id}|{cause}".encode("utf-8")).hexdigest()[:10]
    return f"{s['label']}-{digest}"


def legacy_labels(labels, s: dict) -> list:
    """The fingerprint labels of a defect raised before they were dropped -
    only `<label>-<10 hex>`: the passing and unmapped labels share the prefix."""
    shape = re.compile(re.escape(s["label"]) + r"-[0-9a-f]{10}")
    return [lb for lb in labels or [] if shape.fullmatch(lb)]


def fingerprint_of(issue: dict, s: dict) -> str | None:
    """The defect's fingerprint: from its triage data, else (raised before the
    data held both, or the data was edited away) its fingerprint label."""
    state = state_of(issue.get("description", "")) or {}
    if state.get("test") and state.get("cause"):
        return defect_label(state["test"], state["cause"], s)
    old = legacy_labels(issue.get("labels"), s)
    return old[0] if old else None


# ── which story owns a failing test ──────────────────────────

def _feature_file(test_id: str) -> str:
    """The feature file a pytest-bdd test id comes from (`test_<name>` -> `<name>.feature`)."""
    module = test_id.partition("::")[0].rsplit(".", 1)[-1]
    return (module[len("test_"):] if module.startswith("test_") else module) + ".feature"


def trace_of(test_id: str, features_dir: Path, tracker=None, s: dict | None = None) -> dict:
    """What a failing test is traced to: {"test_case", "owner", "traced_by"}.

    In order: the scenario's marker; the one story every marked scenario of
    the feature file shares; `defects.trace_owners` for the feature file.
    All None when nothing traces it. Never raises."""
    s = s or settings()
    tc, owner = owner_of(test_id, features_dir, tracker)
    if tc:
        return {"test_case": tc, "owner": owner, "traced_by": "scenario marker"}
    file = _feature_file(test_id)
    try:
        from agents.agent2_coder import build_marker_index
        owners = set()
        for entry in build_marker_index(Path(features_dir)).by_key.values():
            if entry.file != file:
                continue
            o = getattr(entry, "owner", None)
            if not o and tracker is not None:
                o = tracker.get_parent_story_key(entry.key)
            owners.add(o)
        if len(owners) == 1 and None not in owners:
            return {"test_case": None, "owner": owners.pop(), "traced_by": "feature file"}
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Feature file of %s not read: %s", test_id, e)
    for path, story in (s.get("trace_owners") or {}).items():
        p = str(path).replace("\\", "/").strip("/")
        if story and (p == file or p.endswith("/" + file)):
            return {"test_case": None, "owner": str(story).upper(),
                    "traced_by": "defects.trace_owners"}
    return {"test_case": None, "owner": None, "traced_by": None}


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


def _traced_line(state: dict) -> str:
    if state.get("test_case"):
        return (f"{state['test_case']} (owning story: {state.get('owner') or 'not found'})")
    if state.get("owner"):
        return (f"none for this scenario - its story {state['owner']} is traced by the "
                f"{state.get('traced_by') or 'feature file'}")
    return ("NOT TRACED - no `# JIRA:` marker on the scenario, no story shared by the "
            "marked scenarios of its feature file, and no `defects.trace_owners` entry "
            "for the file. Add one; until then the defect is labelled "
            f"`{settings().get('unmapped_label')}`")


def render(tracker, state: dict) -> str:
    md = [
        "A test fails on `main`. Raised by the defect triage after a run on main "
        "(scheduled, or after a change that affects the tests). One open defect per test: "
        "a repeat updates this description; when the test passes again on main this "
        "defect gets a label and one comment suggesting it be closed - a person decides.",
        "",
        f"**Test:** `{state['test']}`",
        "**Test case:** " + _traced_line(state),
        f"**Cause ({state['cause']}):** {state['cause_text']}",
        f"**Fix:** {state['remedy']}",
        *([f"**Causes seen before:** {', '.join(state['earlier_causes'])} - the same test, "
           "read differently on another run"] if state.get("earlier_causes") else []),
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
    """{fingerprint: issue dict} for every open defect the triage raised.
    A defect whose fingerprint cannot be read is skipped and logged - it is
    not the triage's to update."""
    found = tracker.find_stories_to_process(
        {"issue_type": s["issue_type"], "required_labels": [s["label"]],
         "allowed_statuses": list(s["open_statuses"])}, max_results=200)
    out = {}
    for issue in found or []:
        fp = fingerprint_of(issue, s)
        if fp is None:
            logger.warning("Defect %s: no triage data and no fingerprint label - not "
                           "matched to a failure.", issue.get("key"))
            continue
        out.setdefault(fp, issue)
    return out


def by_test(existing: dict) -> dict:
    """{test id: (fingerprint, issue)} - one open defect per test: the newest
    one not flagged passing, else the newest (several only for defects raised
    before one per test)."""
    s = settings()
    out: dict = {}
    def rank(issue):
        key = str(issue.get("key", ""))
        num = int(key.rsplit("-", 1)[-1]) if key.rsplit("-", 1)[-1].isdigit() else 0
        return (s["passing_label"] not in (issue.get("labels") or []), num)
    for fp, issue in existing.items():
        test = (state_of(issue.get("description", "")) or {}).get("test")
        if not test:
            continue
        if test not in out or rank(issue) > rank(out[test][1]):
            out[test] = (fp, issue)
    return out


def _gone(tracker, key: str) -> bool:
    """True when the issue `key` cannot be read. Asked after a refused link, so
    a link type the tracker lacks (Jira answers that with a 404 too) stays a
    refused write, and only a deleted or moved issue reads as a stale trace."""
    try:
        tracker.get_story(key)
        return False
    except Exception:                                              # noqa: BLE001
        return True


def _trace(tracker, key: str, state: dict, before: dict, labels: list, s: dict,
           result: dict, dry_run: bool) -> None:
    """Link the defect to its test case and story, give it the story's
    components, and keep the unmapped label true. Best-effort per write: a
    refused write is recorded in result["errors"], never stops the triage."""
    tc, owner = state.get("test_case"), state.get("owner")
    if not (tc or owner):
        result["unmapped"].append(key)
    if dry_run:
        return
    unmapped = s.get("unmapped_label")

    def attempt(what, call, *args, target=None):
        try:
            call(*args)
        except Exception as e:                                     # noqa: BLE001
            if target and _gone(tracker, target):
                # The marker (or trace_owners) names an issue that is gone:
                # a traceability problem for a person, not a refused write.
                logger.warning("Defect %s: %s no longer exists", key, target)
                result["stale_trace"].append(f"{key} -> {target}")
                return
            logger.warning("Defect %s: %s not done: %s", key, what, e)
            result["errors"].append((f"{key} {what}", f"{type(e).__name__}: {e}"))

    if unmapped:
        if not (tc or owner) and unmapped not in labels:
            attempt("unmapped label", tracker.add_label, key, unmapped)
        elif (tc or owner) and unmapped in labels:
            attempt("unmapped label removal", tracker.remove_label, key, unmapped)
    if s.get("trace_links", True):
        for kind, old, new in (("defect_of", before.get("test_case"), tc),
                               ("defect_story", before.get("owner"), owner)):
            if old and old != new:
                attempt(f"link to {old} removed", tracker.unlink_issues, key, old, kind)
            if new:
                attempt(f"link to {new}", tracker.link_issues, key, new, kind, target=new)
    set_components = capability(tracker, "set_components")
    if owner and s.get("copy_components", True) and set_components is not None:
        try:
            wanted = list(tracker.get_story(owner).get("components") or [])
            have = list(tracker.get_story(key).get("components") or [])
            if wanted and sorted(wanted) != sorted(have):
                set_components(key, wanted)
        except Exception as e:                                     # noqa: BLE001
            # A nicety, never a failure: a project whose defect screen has no
            # components field refuses it on every defect, every night.
            logger.warning("Defect %s: components not copied: %s", key, e)


def triage(tracker, root, run_url: str, features_dir: Path, now: _dt.datetime | None = None,
           dry_run: bool = False) -> dict:
    """Raise, update and flag defects for one run on main. Returns what it did:
    {"raised", "updated", "passing", "failing_again", "capped", "outages", "flaky",
    "not_retried", "unmapped", "stale_trace", "errors"} - `not_retried` lists
    failures that were not run again (no defect, see only_after_retry);
    `unmapped` defects nothing traces; `stale_trace` "defect -> key" where the
    trace names an issue that no longer exists; `errors` is [(what, why)] for every
    write the tracker refused
    (a required field on the defect's create screen, a permission), so the
    caller can say so instead of a run that looks clean."""
    s = settings()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    today = now.date().isoformat()
    cases = jm.cases(root)
    failing = [c for c in cases if jm.outcome(c) in ("failed", "error") and not jm.is_outage(c)]
    not_retried = []
    if s.get("only_after_retry", True):
        not_retried = [c for c in failing if not jm.is_retried(c)]
        failing = [c for c in failing if jm.is_retried(c)]
    result = {"raised": [], "updated": [], "passing": [], "failing_again": [], "capped": [],
              "outages": [jm.case_id(c) for c in cases if jm.is_outage(c)],
              "flaky": [jm.case_id(c) for c in cases if jm.is_flaky(c)],
              "not_retried": [jm.case_id(c) for c in not_retried], "unmapped": [],
              "stale_trace": [], "errors": []}
    if not s.get("enabled", True):
        logger.info("defects.enabled is false - no defect is raised.")
        return result
    create = capability(tracker, "create_issue")
    try:
        existing = open_defects(tracker, s)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Open defects not read (%s); none raised this run.", e)
        result["errors"].append(("the open defects", f"{type(e).__name__}: {e}"))
        return result
    failing_labels = set()
    failing_tests: dict = {}             # test -> its defect this run (None: none)
    per_test = by_test(existing)
    for case in failing:
        test = jm.case_id(case)
        d = _diagnosis(case)
        label = defect_label(test, d.label, s)
        failing_labels.add(label)
        failing_tests.setdefault(test, None)
        issue = existing.get(label)
        if issue is None and test in per_test:
            # The open defect of this test, recorded under another cause.
            old_fp, issue = per_test[test]
            failing_labels.add(old_fp)
        try:
            if issue is not None:
                state = state_of(issue.get("description", "")) or {}
                before = {"test_case": state.get("test_case"), "owner": state.get("owner")}
                if state.get("cause") and state["cause"] != d.label:
                    seen = list(state.get("earlier_causes") or [])
                    if state["cause"] not in seen:
                        seen.append(state["cause"])
                    state["earlier_causes"] = [c for c in seen if c != d.label]
                state.update(test=test, cause=d.label, cause_text=d.cause, remedy=d.remedy,
                             failure=_failure_excerpt(case), last_seen=today, last_run=run_url,
                             times=int(state.get("times", 1)) + 1,
                             **trace_of(test, features_dir, tracker, s))
                state.setdefault("first_seen", today)
                if not dry_run:
                    tracker.set_description(issue["key"], render(tracker, state))
                result["updated"].append(issue["key"])
                failing_tests[test] = issue["key"]
                _trace(tracker, issue["key"], state, before, list(issue.get("labels") or []),
                       s, result, dry_run)
                for old in legacy_labels(issue.get("labels"), s):
                    # Raised before fingerprints left the labels: its triage
                    # data now identifies it, so the code label goes.
                    try:
                        if not dry_run:
                            tracker.remove_label(issue["key"], old)
                    except Exception as e:                         # noqa: BLE001
                        result["errors"].append((issue["key"], f"label {old} not removed: "
                                                               f"{type(e).__name__}: {e}"))
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
            traced = trace_of(test, features_dir, tracker, s)
            state = {"test": test, **traced, "cause": d.label,
                     "cause_text": d.cause, "remedy": d.remedy,
                     "failure": _failure_excerpt(case), "first_seen": today,
                     "last_seen": today, "last_run": run_url, "times": 1}
            summary = f"[Auto] {test.rsplit('.', 1)[-1][:150]} fails on main: {d.label}"
            if dry_run:
                result["raised"].append(f"(dry run) {summary}")
                if not (traced["test_case"] or traced["owner"]):
                    result["unmapped"].append(f"(dry run) {summary}")
                continue
            labels = [s["label"]]
            if not (traced["test_case"] or traced["owner"]) and s.get("unmapped_label"):
                labels.append(s["unmapped_label"])
            key = create(s["issue_type"], summary, render(tracker, state), labels)
            result["raised"].append(key)
            failing_tests[test] = key
            logger.warning("Defect %s raised: %s", key, summary)
            _trace(tracker, key, state, {}, labels, s, result, dry_run)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Defect for %s not written: %s", test, e)
            result["errors"].append((test, f"{type(e).__name__}: {e}"))

    # A test failing now for ANOTHER cause than an older defect of it records
    # (two open defects of one test, raised before one open defect per test):
    # that defect is not passing any more.
    # Left flagged, it would suggest closing while its test fails on main
    # (10 Nov 2026: a defect 'unclassified' stayed 'passing - suggest closing'
    # while its test failed for another cause under a new defect).
    for label, issue in existing.items():
        if label in failing_labels or s["passing_label"] not in (issue.get("labels") or []):
            continue
        test = (state_of(issue.get("description", "")) or {}).get("test")
        if test not in failing_tests:
            continue
        now = failing_tests[test]
        try:
            if not dry_run:
                tracker.remove_label(issue["key"], s["passing_label"])
                tracker.add_comment(
                    issue["key"],
                    f"Its test fails on main again, now for another cause"
                    f"{f' - see {now}' if now else ''}: {run_url}. Not passing any more; "
                    "if both describe one problem, close one of them.")
            result["failing_again"].append(issue["key"])
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Defect %s not unflagged: %s", issue.get("key"), e)
            result["errors"].append((issue.get("key"), f"{type(e).__name__}: {e}"))

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
            result["errors"].append((issue.get("key"), f"{type(e).__name__}: {e}"))
    return result
