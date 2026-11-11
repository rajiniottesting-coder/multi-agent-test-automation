"""Work already in flight in other open pull requests.

Every story branches from `main`, and Agent 2 writes WHOLE files. Two stories
whose pull requests are open at the same time therefore cannot see each
other's work:

- both rewrite the same page object from main's copy -> a merge conflict, or
  the PR merged second silently drops the methods the first one added;
- both create the same new file -> an add/add conflict;
- both generate the same scenario -> a duplicate test once both merge
  (duplicate detection reads main, where neither is yet).

The rule here is simple and generic: a story run must not write a file that
another open pull request is changing, nor add a scenario another open pull
request already adds. Such a run WAITS - nothing is generated or committed,
its labels are untouched, and the next scan retries it. Once the other pull
request merges, main holds its work and the usual checks apply (the page
object is extended, the duplicate scenario is skipped); once it is closed
unmerged, nothing stands in the way.

Fails open: if the open pull requests cannot be read, the run proceeds as it
always did. The guard prevents a conflict; it must never become the reason
work stops on an API hiccup.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

WAITING_MARKER = "[agent2:waiting]"


@dataclass
class InFlight:
    """Files changed by OTHER open pull requests: {path: [(number, url)]},
    plus the content of their feature files (for scenario titles)."""
    by_path: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)        # {(number, url, path): content}

    def __bool__(self) -> bool:
        return bool(self.by_path)


def _own_branch(head_ref: str, story_id: str) -> bool:
    """A branch belongs to the story when the story key is a whole token in
    it (auto/PROJ-5-x, auto/PROJ-5-x-update2, context-update/proj-5).
    PROJ-5 must not match PROJ-50."""
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(story_id)}(?![0-9])",
                     head_ref or "", re.IGNORECASE) is not None


def snapshot(host, story_id: str) -> InFlight:
    """What other open pull requests are changing. Empty on any error."""
    state = InFlight()
    try:
        prs = [p for p in host.list_open_prs()
               if not _own_branch(p.get("head_ref", ""), story_id)]
        for pr in prs:
            ref = (pr["number"], pr.get("url", ""))
            for f in host.get_pr_changed_files(pr["number"]) or []:
                path = f.get("filename") or ""
                if not path:
                    continue
                state.by_path.setdefault(path, []).append(ref)
                if path.endswith(".feature") and f.get("content"):
                    state.features[(*ref, path)] = f["content"]
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Could not read the open pull requests (%s) - proceeding "
                       "without the in-flight check.", e)
        return InFlight()
    return state


def _norm(path: str) -> str:
    return (path or "").replace("\\", "/").removeprefix("./")


def file_conflicts(paths, state: InFlight) -> list[dict]:
    """Files this run would write that another open PR is changing."""
    changing = {_norm(p): refs for p, refs in state.by_path.items()}
    out = []
    for path in sorted({_norm(p) for p in paths if p}):
        for number, url in changing.get(path, []):
            out.append({"path": path, "pr": number, "url": url})
    return out


def duplicate_scenarios(test_cases, state: InFlight, titles_of,
                        case_title=lambda summary: summary) -> list[dict]:
    """Test cases whose title is already a scenario another open PR adds.

    `titles_of(feature_content) -> [scenario title]` and
    `case_title(summary) -> title` are the caller's own parser and summary
    rule (a summary may carry tags a scenario title does not), so this module
    depends on no agent. Titles compare with the same rule as duplicate
    detection on main (normalize_scenario_name)."""
    from validators.gherkin_analyzer import normalize_scenario_name
    in_prs: dict = {}
    for (number, url, path), content in state.features.items():
        try:
            titles = titles_of(content)
        except Exception as e:                                 # noqa: BLE001
            logger.warning("Could not read scenarios of %s in PR #%s: %s", path, number, e)
            continue
        for title in titles:
            if title:
                in_prs.setdefault(normalize_scenario_name(title),
                                  {"pr": number, "url": url, "path": path, "scenario": title})
    out = []
    for tc in test_cases or []:
        hit = in_prs.get(normalize_scenario_name(case_title(tc.get("summary", "") or "")))
        if hit:
            out.append({"key": tc.get("key"), **hit})
    return out


def wait_comment(story_id: str, files: list[dict], scenarios: list[dict],
                 inputs: str = "") -> str:
    """The Jira comment. Its first line is a stable signature of WHY the story
    waits, so a scan every 30 minutes posts it once, not every time. `inputs`
    (the story's input fingerprint, core.blocked) lets the next scan wait again
    without a new plan while nothing has changed (still_waiting)."""
    prs = sorted({c["pr"] for c in files} | {s["pr"] for s in scenarios})
    signature = (f"{WAITING_MARKER} prs: {','.join(map(str, prs))} "
                 f"files: {','.join(sorted({c['path'] for c in files})) or '-'} "
                 f"scenarios: {','.join(sorted(str(s['key']) for s in scenarios)) or '-'}"
                 + (f" inputs: {inputs}" if inputs else ""))
    lines = [signature,
             (f"Agent 2 is waiting before coding {story_id}: another open pull request "
              "is already changing what this story needs."), ""]
    for c in files:
        lines.append(f"- `{c['path']}` is being changed by PR #{c['pr']} {c['url']}".rstrip())
    for s in scenarios:
        lines.append(f"- {s['key']}: scenario \"{s['scenario']}\" is already added by "
                     f"PR #{s['pr']} ({s['path']})")
    lines += ["", ("Nothing was generated and the labels are unchanged. The next scan "
                   "retries automatically once that pull request is merged or closed. "
                   "If it is abandoned, close it.")]
    return "\n".join(lines)


def post_wait_once(tracker, story_id: str, files: list[dict], scenarios: list[dict],
                   inputs: str = "") -> bool:
    """Post the waiting comment unless the same one is already on the story.
    Best-effort: returns whether a comment was posted, never raises."""
    body = wait_comment(story_id, files, scenarios, inputs)
    signature = body.splitlines()[0]
    try:
        if any(signature in (c or "") for c in tracker.get_comments(story_id)):
            return False
        from integrations.tracker import add_markdown_comment
        add_markdown_comment(tracker, story_id, body)
        return True
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Could not post the waiting note on %s: %s", story_id, e)
        return False


_FILE_WAIT = re.compile(rf"^{re.escape(WAITING_MARKER)} prs: ([0-9,]+) files: (\S+) "
                        r"scenarios: - inputs: ([0-9a-f]+)$", re.M)


def still_waiting(comments, state: InFlight, inputs: str) -> list[dict]:
    """The file clashes of an earlier wait that still hold, else [].

    A story waiting on a file another open pull request changes was planned
    again on every scan - a model call each time, to reach the same wait (4 Nov
    2026: about $0.11 a scan while it waited). When a waiting comment for THESE
    inputs names files that the same pull requests still change, the story
    waits again before the plan. Any change - the story or a test case edited,
    the pull request merged or closed, the file no longer in it - and the
    story is planned as usual."""
    if not inputs or not state:
        return []
    changing = {_norm(p): refs for p, refs in state.by_path.items()}
    for comment in reversed(list(comments or [])):
        for prs, files, fp in _FILE_WAIT.findall(comment or ""):
            if fp != inputs:
                continue
            numbers = {int(n) for n in prs.split(",") if n}
            clashes = []
            for path in files.split(","):
                refs = [r for r in changing.get(_norm(path), []) if r[0] in numbers]
                if not refs:
                    clashes = []
                    break
                clashes += [{"path": _norm(path), "pr": n, "url": u} for n, u in refs]
            if clashes:
                return clashes
    return []
