"""No approved test case is dropped without a word (G5 / F-13).

WHAT WENT WRONG
    A person approves a story's test cases; Agent 2 automates them. When it
    could not automate one - an element missing from the inventory, a step the
    page cannot show, a title it could not pair with a marker - the plan prompt
    told the model to leave it out and say so in `notes`. Those notes were
    printed only in a dry run: not in the pull request, not on the story. Marker
    injection only logged a warning when scenarios and test cases did not pair.
    The story still got `ai-coded`, and the board said it was coded.

    Two quieter paths did the same: the duplicate check skipped a test case
    whose title matched ANOTHER test case's scenario ("title clash") - so it was
    never generated - and logged it; `ai-update` skipped a new test case whose
    title matched an unmarked scenario, and logged it.

THE RULE, FOR EVERY RUN THAT CODES A STORY
    Every approved test case ends in one of three states, decided from the
    files themselves, never from what the model says it did:

      covered       a scenario in this run's feature files carries its marker,
                    or one on main already does (unchanged);
      not covered   listed - with the reason the plan's notes give for it, or
                    the duplicate check's reason - in the pull request body and
                    in ONE comment on the story; the story gets the
                    `incomplete_label` (ai-incomplete) beside `ai-coded`, so a
                    board query finds it;
      needs action  covered but needing a person (its scenario is outdated, or
                    has no marker): listed the same way, without the label.

    A run that would automate NONE of the story's new test cases opens no pull
    request: the final gate refuses it (core.blocked says why, once).

    A later run that leaves nothing uncovered - `ai-update` after the cause is
    fixed, or `ai-regenerate` - removes the label.

Generic: nothing here names an application, a page or a rule of one.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

INCOMPLETE_MARKER = "[agent2:incomplete]"
DEFAULT_INCOMPLETE_LABEL = "ai-incomplete"
_MAX_NOTE_CHARS = 300


@dataclass(frozen=True)
class Gap:
    """An approved test case this run did not automate, or one that needs a person."""
    key: str
    summary: str
    reason: str
    blocking: bool          # True: no scenario of its own exists - the story is incomplete


# ── what the files say ───────────────────────────────────────────────────

def _feature_blocks(files):
    from agents.agent2_coder import parse_feature_file
    for f in files:
        if f.file_path.endswith(".feature"):
            _h, blocks = parse_feature_file(f.content or "")
            for b in blocks:
                if b.kind == "scenario":
                    yield f.file_path, b


def markered_keys(files) -> set:
    """Keys whose scenario carries a marker in these feature files."""
    return {b.jira_key for _p, b in _feature_blocks(files) if b.jira_key}


def unmarked_scenarios(files) -> list:
    """(path, title) of every scenario with no marker - one no approved test
    case could be paired with, so `ai-update` can never maintain it."""
    from agents.agent2_coder import _scenario_title
    return [(p, _scenario_title(b)) for p, b in _feature_blocks(files) if not b.jira_key]


def notes_about(notes: str, key: str) -> str:
    """The sentences of the model's notes that name this key, else ""."""
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(key)}(?![0-9])", re.IGNORECASE)
    picked = []
    for line in (notes or "").splitlines():
        for sentence in re.split(r"(?<=[.;])\s+", line.strip()):
            if sentence and pattern.search(sentence) and sentence not in picked:
                picked.append(sentence)
    text = " ".join(" ".join(picked).split()).lstrip("-*• ").strip()
    # The plan's own form, "Skipped: <KEY> -- <reason>": the key is already named.
    text = re.sub(rf"^(?:skipped:\s*)?{re.escape(key)}\s*(?:--|-|:|—)\s*", "", text,
                  flags=re.IGNORECASE)
    return text if len(text) <= _MAX_NOTE_CHARS else text[:_MAX_NOTE_CHARS - 3] + "..."


# ── the gaps ─────────────────────────────────────────────────────────────

def missing_from_batch(files, test_cases, notes: str = "") -> list:
    """Each test case this run was asked to automate with no markered scenario."""
    from agents.agent2_coder import _KEY
    have = markered_keys(files)
    gaps = []
    for tc in test_cases:
        if tc["key"] in have:
            continue
        said = notes_about(notes, tc["key"])
        if not re.fullmatch(_KEY, tc["key"], re.IGNORECASE):
            reason = ("its key cannot be carried by a scenario marker (a marker holds keys "
                      "shaped like PROJ-123), so no scenario can be traced to it")
        elif said:
            reason = "no scenario of its own in this pull request - the plan's notes: " + said
        else:
            reason = ("no scenario of its own in this pull request (a scenario holds one "
                      "test case's marker), and the model gave no reason")
        gaps.append(Gap(tc["key"], tc.get("summary", ""), reason, blocking=True))
    return gaps


def skipped_gaps(skipped, labels=None) -> list:
    """The duplicate check's skips that a person must act on.

    `unchanged` is covered and says nothing. `title_clash` is NOT covered: the
    scenario with that title belongs to another test case. `modified` and
    `legacy` are covered, but need a person."""
    update = (labels or {}).get("update_label", "ai-update")
    gaps = []
    for s in skipped or ():
        tc, why = s["test_case"], s.get("reason")
        where = f"`{s.get('matched_file')}`" if s.get("matched_file") else "an existing file"
        if why == "title_clash":
            other = s.get("other_key") or "another test case"
            reason = (f"not generated - the scenario \"{s.get('matched_scenario')}\" in {where} "
                      f"has the same title and belongs to {other}. If this test case "
                      "duplicates that one, retire it; otherwise give it a distinct summary")
            gaps.append(Gap(tc["key"], tc.get("summary", ""), reason, blocking=True))
        elif why == "modified":
            reason = (f"its scenario in {where} was written from an older version of the "
                      f"test case and was not changed by this run: add `{update}` to the "
                      "story to revise it in place")
            gaps.append(Gap(tc["key"], tc.get("summary", ""), reason, blocking=False))
        elif why == "legacy":
            reason = (f"an unmarked scenario with the same title is in {where}: give it its "
                      "marker (`python scripts/backfill_markers.py propose`)")
            gaps.append(Gap(tc["key"], tc.get("summary", ""), reason, blocking=False))
    return gaps


def blocking(gaps) -> list:
    return [g for g in gaps if g.blocking]


# ── what a person reads ──────────────────────────────────────────────────

def _remedy(labels: dict) -> str:
    update = labels.get("update_label", "ai-update")
    return (f"To automate a test case listed as not automated: fix the cause - usually an "
            f"element missing from the inventory, or a test case asking for something the "
            f"page cannot show (edit it) - then, once this story's scenarios are on main, "
            f"add `{update}` to the story: it generates only what is missing, and removes "
            f"`{labels.get('incomplete_label', DEFAULT_INCOMPLETE_LABEL)}` when nothing is. "
            f"A test case that only repeats an existing scenario is retired instead.")


def _lines(gaps, unmarked) -> list:
    out = []
    for g in blocking(gaps):
        out.append(f"- **{g.key}** {g.summary} - {g.reason}")
    needs = [g for g in gaps if not g.blocking]
    if needs:
        out.append("")
        out.append("Covered, but needing a person:")
        out += [f"- **{g.key}** {g.summary} - {g.reason}" for g in needs]
    if unmarked:
        out.append("")
        out.append("Scenarios with no test-case marker (no approved test case could be "
                   "paired with the title; `ai-update` cannot maintain them):")
        out += [f"- `{p}`: \"{t}\"" for p, t in unmarked]
    return out


def pr_section(gaps, unmarked, labels: dict) -> str:
    """The pull-request body section; "" when there is nothing to say."""
    if not gaps and not unmarked:
        return ""
    head = (f"\n\n---\n## Approved test cases not automated ({len(blocking(gaps))})\n\n"
            if blocking(gaps) else "\n\n---\n## Approved test cases to check\n\n")
    body = "\n".join(_lines(gaps, unmarked)) + "\n"
    tail = f"\n{_remedy(labels)}\n" if blocking(gaps) else ""
    return head + body + tail


def comment(story_id: str, gaps, unmarked, where: str, labels: dict) -> str:
    """The one story comment for a run (`where`: the pull request, or "")."""
    n = len(blocking(gaps))
    first = (f"{INCOMPLETE_MARKER} Agent 2 automated {story_id} only in part: {n} approved "
             f"test case(s) have no scenario" if n else
             f"{INCOMPLETE_MARKER} Agent 2 coded {story_id}; the items below need a person")
    lines = [first + (f" ({where})." if where else "."), ""]
    lines += _lines(gaps, unmarked)
    if n:
        lines += ["", _remedy(labels)]
    return "\n".join(lines)


def labels_from(config: dict) -> dict:
    return {"update_label": config.get("update_label", "ai-update"),
            "incomplete_label": config.get("incomplete_label", DEFAULT_INCOMPLETE_LABEL)}


def record(tracker, story_id: str, gaps, unmarked, where: str, labels: dict,
           story_labels=None) -> None:
    """Say it on the story and set or clear the incomplete label. Never raises:
    the pull request already says it, and the work it reports has landed.

    `story_labels` (the story's labels as read at the start of the run) saves
    the tracker call when there is no label to clear; None always clears."""
    label = labels.get("incomplete_label", DEFAULT_INCOMPLETE_LABEL)
    # Separately: a comment that fails must not cost the label, nor the reverse.
    if gaps or unmarked:
        try:
            tracker.add_comment(story_id, comment(story_id, gaps, unmarked, where, labels))
        except Exception as e:                                 # noqa: BLE001
            logger.warning("Could not comment the coverage of %s: %s", story_id, e)
    try:
        if blocking(gaps):
            tracker.add_label(story_id, label)
        elif story_labels is None or label in story_labels:
            tracker.remove_label(story_id, label)
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Could not set or clear %s on %s: %s", label, story_id, e)


def log_gaps(story_id: str, gaps, unmarked) -> None:
    for line in _lines(gaps, unmarked):
        if line.strip():
            logger.warning("%s coverage: %s", story_id, line.strip())
