"""Notice what changed under the pipeline's feet, and say so once (Group B).

Run by the pipeline health workflow (scripts/watch_tracker.py). Every finding
is a COMMENT or a label - nothing is regenerated, deleted or pushed - and each
is said once: what was said is remembered in a hidden issue property
(`pipeline.watch`), so the next run stays quiet until something changes again.

  R2  A story edited after its test cases were drafted, or after its tests
      were coded (the tracker's history: a summary or description change
      after the drafting / coding label was added) -> one comment on the
      story: check the test cases (drafted), or add `impact-check` (coded).
      Only edits within `watch.story_edit_days`; older ones are history.

  R3  A test case edited or deleted in the tracker after its scenario was
      coded (the scenario marker's hash differs from the test case's text, or
      the test case is gone) -> one comment on its owning story: add
      `ai-update`, or remove / re-point the scenario.

  R4  A story cancelled or deleted while its scenarios still run (marker
      owners; cancelled = a done status or resolution in `watch.cancelled`)
      -> its test cases get the retired label and one comment naming the
      scenario to remove; the open defects traced to it get one comment.

  X5  An agent pull request (`auto/`) in conflict with main, or behind main
      on a file it changes -> one comment on the pull request: the cause and
      `ai-regenerate` (conflict) or `ai-update` (behind). Never a push.

Generic: labels, statuses and prefixes come from config; nothing here names
an application, project or person.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROPERTY = "pipeline.watch"


# ── settings and memory ─────────────────────────────────────────────────

def settings() -> dict:
    from core.ops_settings import section
    return section("watch")


def _memory(tracker, key: str) -> dict:
    from integrations.tracker import capability
    get = capability(tracker, "get_property")
    try:
        value = get(key, PROPERTY) if get else None
    except Exception:                                              # noqa: BLE001
        value = None
    return value if isinstance(value, dict) else {}


def _say_once(tracker, key: str, slot: str, value: str, body: str, result: dict,
              finding: str, dry_run: bool) -> bool:
    """Comment `body` on `key` unless `slot` already holds `value`."""
    memory = _memory(tracker, key) if not dry_run else {}
    if memory.get(slot) == value:
        return False
    result[finding].append(key)
    if dry_run:
        return True
    from integrations.tracker import capability
    try:
        tracker.add_comment(key, body)
        put = capability(tracker, "set_property")
        if put is not None:
            memory[slot] = value
            put(key, PROPERTY, memory)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("%s: %s not said: %s", key, finding, e)
        _write_failed(result, f"{key} {finding}", e)
    return True


def _iso(value) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:            # Jira: 2026-11-14T05:00:00.000+0530
            t = _dt.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S.%f%z")
        except (TypeError, ValueError):
            return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def _label_added_at(history, label: str) -> _dt.datetime | None:
    found = None
    for change in history or []:
        for item in change.get("items") or []:
            if item.get("field") == "labels" and label in (item.get("to") or "").split() \
                    and label not in (item.get("from") or "").split():
                found = _iso(change.get("at")) or found
    return found


def _last_edit(history, after: _dt.datetime) -> dict | None:
    """The last summary or description change after `after`."""
    last = None
    for change in history or []:
        at = _iso(change.get("at"))
        if at is None or at <= after:
            continue
        if any(i.get("field") in ("summary", "description") for i in change.get("items") or []):
            last = {"at": at, "by": change.get("by") or {}}
    return last


# ── R2 ──────────────────────────────────────────────────────────────────

def stories_edited(tracker, result: dict, s: dict, now: _dt.datetime, dry_run: bool) -> None:
    from integrations.tracker import capability
    read = capability(tracker, "changelog")
    if read is None:
        return
    drafted_label, coded_label = s["drafted_label"], s["coded_label"]
    stories = tracker.find_stories_to_process(
        {"issue_type": s["story_type"], "required_labels": [drafted_label],
         "allowed_statuses": list(s["story_statuses"])}, max_results=200) or []
    since = now - _dt.timedelta(days=int(s["story_edit_days"]))
    for story in stories:
        history = read(story["key"])
        drafted = _label_added_at(history, drafted_label)
        if drafted is None:
            continue
        coded = _label_added_at(history, coded_label)
        edit = _last_edit(history, drafted)
        if edit is None or edit["at"] < since:
            continue
        who = edit["by"].get("name") or "someone"
        when = edit["at"].strftime("%Y-%m-%d %H:%M UTC")
        if coded and edit["at"] > coded:
            body = (f"[watch:story-edited] This story was edited on {when} by {who}, after "
                    f"its tests were coded. Add `{s['impact_label']}` so the impact check "
                    f"finds what the edit affects (or revise the test cases and add "
                    f"`{s['update_label']}`). Nothing was changed automatically.")
        else:
            body = (f"[watch:story-edited] This story was edited on {when} by {who}, after "
                    f"its test cases were drafted. Check they still match the story: edit "
                    f"them in the tracker, or - to draft again - delete them, remove "
                    f"`{drafted_label}` and add `{s['draft_label']}`. Nothing was changed "
                    f"automatically.")
        _say_once(tracker, story["key"], "story_edited", edit["at"].isoformat(), body,
                  result, "story_edited", dry_run)


# ── R3 and R4 read the scenario markers ─────────────────────────────────

def _markers(features_dir: Path) -> list:
    from agents.agent2_coder import build_marker_index
    return list(build_marker_index(Path(features_dir)).by_key.values())


def test_cases_changed(tracker, markers: list, cases: dict, result: dict, s: dict,
                       dry_run: bool) -> None:
    """R3. `cases` is {key: test case} for every live test case."""
    from agents.agent2_coder import compute_description_hash
    from integrations.tracker import capability
    state = capability(tracker, "issue_state")
    retired = getattr(tracker, "retired_label", None)
    for m in markers:
        owner = getattr(m, "owner", None) or (cases.get(m.key) or {}).get("owner")
        where = f"`{m.file}` (scenario \"{m.title}\")"
        if m.key in cases:
            now_hash = compute_description_hash(cases[m.key].get("description", ""))
            if now_hash == (m.hash or "").lower() or not owner:
                continue
            body = (f"[watch:test-case-changed] Test case {m.key} was edited in the tracker "
                    f"after its scenario was coded ({where}): the scenario no longer matches "
                    f"it. Add `{s['update_label']}` to this story to update the scenario.")
            _say_once(tracker, owner, f"tc:{m.key}", now_hash, body, result,
                      "test_case_changed", dry_run)
            continue
        info = None
        try:
            info = state(m.key) if state else {}
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s not read: %s", m.key, e)
            continue
        if info and (retired in (info.get("labels") or []) or info.get("type") != s["test_case_type"]):
            continue                     # retired (R4) or not a test case
        if info is None and owner:
            body = (f"[watch:test-case-deleted] Test case {m.key} no longer exists in the "
                    f"tracker, but its scenario {where} still runs. Remove the scenario in a "
                    f"pull request, or point its marker at another test case.")
            _say_once(tracker, owner, f"tc:{m.key}", "deleted", body, result,
                      "test_case_deleted", dry_run)


def _cancelled(info: dict | None, s: dict) -> str:
    """'deleted', 'cancelled' or '' for a story."""
    if info is None:
        return "deleted"
    names = {str(x).lower() for x in s["cancelled"]}
    if info.get("category") == "done" and (str(info.get("status") or "").lower() in names
                                           or str(info.get("resolution") or "").lower() in names):
        return "cancelled"
    return ""


def stories_retired(tracker, markers: list, result: dict, s: dict, dry_run: bool) -> None:
    """R4."""
    from integrations.tracker import capability
    state = capability(tracker, "issue_state")
    if state is None:
        return
    by_owner: dict = {}
    for m in markers:
        if getattr(m, "owner", None):
            by_owner.setdefault(m.owner, []).append(m)
    retired = getattr(tracker, "retired_label", None) or "ai-retired"
    report = capability(tracker, "issues_for_report")
    from core.defects import settings as defect_settings
    d = defect_settings()
    open_defects = None
    for owner, ms in sorted(by_owner.items()):
        try:
            why = _cancelled(state(owner), s)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s not read: %s", owner, e)
            continue
        if not why:
            continue
        for m in ms:
            try:
                info = state(m.key)
            except Exception:                                      # noqa: BLE001
                info = None
            if info is None or retired in (info.get("labels") or []):
                continue
            result["retired"].append(m.key)
            if dry_run:
                continue
            try:
                tracker.add_label(m.key, retired)
                tracker.add_comment(
                    m.key, f"[watch:retired] Its story {owner} was {why}, so this test case is "
                           f"retired. Its scenario in `{m.file}` (\"{m.title}\") still runs: "
                           f"remove it in a pull request.")
            except Exception as e:                                 # noqa: BLE001
                _write_failed(result, f"{m.key} retire", e)
        if open_defects is None:
            open_defects = report(d["issue_type"], open_only=True) if report else []
        keys = {owner} | {m.key for m in ms}
        for defect in open_defects or []:
            if keys & set(defect.get("links") or []):
                _say_once(tracker, defect["key"], f"retired:{owner}", why,
                          f"[watch:retired] Its story {owner} was {why}; the test cases it "
                          f"traces to are retired. Close this defect unless it still matters.",
                          result, "defects_flagged", dry_run)


# ── X5 ──────────────────────────────────────────────────────────────────

def prs_out_of_sync(host, result: dict, s: dict, dry_run: bool) -> None:
    from integrations.tracker import capability
    read = capability(host, "pr_sync_state")
    if read is None:
        return
    for pr in host.list_open_prs(s["pr_prefix"]) or []:
        try:
            sync = read(pr["number"])
        except Exception as e:                                     # noqa: BLE001
            logger.warning("PR #%s not checked: %s", pr["number"], e)
            continue
        if sync.get("conflict"):
            kind, body = "conflict", (
                f"[watch:pr-out-of-sync] This pull request has merge conflicts with "
                f"`{sync.get('base')}`" + (f" in {', '.join(sync['conflict_files'][:5])}"
                                           if sync.get("conflict_files") else "")
                + f". It cannot be merged as it is. Add `{s['regenerate_label']}` to its story "
                  f"to generate it again on a fresh branch. Nothing was pushed.")
        elif sync.get("overlap"):
            kind, body = "behind", (
                f"[watch:pr-out-of-sync] `{sync.get('base')}` moved on by {sync['behind_by']} "
                f"commit(s) since this pull request's branch, changing files it also changes: "
                f"{', '.join(sync['overlap'][:5])}. Its tests ran against the older version. "
                f"Add `{s['update_label']}` to its story to bring it up to date. Nothing was "
                f"pushed.")
        else:
            continue
        marker = f"<!-- watch:pr-sync {pr.get('head_sha')} {kind} -->"
        result[_PR_FINDING[kind]].append(pr["number"])
        if dry_run:
            continue
        try:
            if any(marker in c for c in host.get_pr_comments(pr["number"]) or []):
                continue
            host.post_pr_comment(pr["number"], body + "\n\n" + marker)
        except Exception as e:                                     # noqa: BLE001
            _write_failed(result, f"PR #{pr['number']}", e)


_PR_FINDING = {"conflict": "prs_conflict", "behind": "prs_behind"}


def _write_failed(result: dict, what: str, error: Exception) -> None:
    """A refused write: listed in errors AND write_errors (the script's exit
    code reads write_errors; a step that could not read is a warning)."""
    entry = (what, str(error)[:300])
    result["errors"].append(entry)
    result["write_errors"].append(entry)


# ── one run ─────────────────────────────────────────────────────────────

def run(tracker, host, features_dir: Path, now: _dt.datetime | None = None,
        dry_run: bool = False) -> dict:
    s = settings()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    result = {"story_edited": [], "test_case_changed": [], "test_case_deleted": [],
              "retired": [], "defects_flagged": [], "prs_conflict": [], "prs_behind": [],
              "errors": [], "write_errors": []}
    if not s.get("enabled", True):
        return result
    steps = []
    if tracker is not None:
        if s.get("story_edits", True):
            steps.append(("R2", lambda: stories_edited(tracker, result, s, now, dry_run)))
        markers = None

        def _m():
            nonlocal markers
            if markers is None:
                markers = _markers(features_dir)
            return markers
        if s.get("test_case_changes", True):
            def r3():
                cases = {c["key"]: c for c in tracker.get_all_test_cases() or []}
                test_cases_changed(tracker, _m(), cases, result, s, dry_run)
            steps.append(("R3", r3))
        if s.get("retire_cancelled", True):
            steps.append(("R4", lambda: stories_retired(tracker, _m(), result, s, dry_run)))
    if host is not None and s.get("pr_sync", True):
        steps.append(("X5", lambda: prs_out_of_sync(host, result, s, dry_run)))
    for name, step in steps:
        try:
            step()
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s not checked: %s", name, e)
            result["errors"].append((name, str(e)[:300]))
    return result
