"""
Agent 2 - review fix: change an open pull request the way its reviewer asked.

Until this existed, a person's review comment on a pull request was read by no
agent: the reviewer made the fix by hand, or regenerated the whole story.

Trigger (.github/workflows/agent2_review_fix.yml): a person with write access
submits a "Request changes" review on an `auto/*` pull request, or comments
`/fix <what to change>` on it - that text plus every inline review comment not
handled yet (`/fix` alone: those inline comments). Bots never trigger it, so agents cannot loop on each other.

What it does, in order:
  1. Guard    the PR is open and on `<branch_prefix><STORY>-...`; this review
              or comment was not handled before (marker comment); the feature
              is enabled.
  2. Read     the review's inline comments (file, line, text) and the review
              or `/fix` text; every code file of the PR from its branch; the
              story and its approved test cases.
  3. Decide   one model call (ReviewFixPlan): fix / decline / no_change per
              comment. Code enforces that a fix names only editable files.
  4. Change   per file, Stage 2's generator in review mode: the current file
              and the comments that concern it. A feature file must keep its
              scenarios, titles and markers; a degraded answer is discarded.
  5. Gate     the repair loop, then the final gate, over every code file of
              the PR - the same checks a new pull request passes. Anything
              still failing, or a repair that reaches a file that is not
              editable: nothing is pushed, and the reviewer is told why.
  6. Push     each changed file to the SAME branch, so Agents 3, 4 and 5 run
              again; a reply in each comment's thread; one summary comment
              carrying the marker; the cost on the story's ledger.

Editable: the story's own files - those this PR ADDED, the feature files it
MODIFIED whose every scenario marker is one of this story's test cases (an
`ai-regenerate` or `ai-update` pull request rewrites files that already
existed), their step definitions, and page objects it adds or extends. A
feature or step-definition file holding any other story's scenario was only
spliced into (a change story) and is never regenerated here. Reserved
reference files and framework files never are.

The approved test cases are the specification. A comment about HOW the code
checks them is fixed; a comment asking to check something else is declined
with the way to get it: change the test case, then add `ai-regenerate`.

Usage:
    python -m agents.agent2_review_fix --pr 215 --review-id 123456
    python -m agents.agent2_review_fix --pr 215 --comment-id 7890   # a /fix comment
    python -m agents.agent2_review_fix --pr 215 --review-id 1 --dry-run
The review's or comment's own text comes from the REVIEW_FIX_TEXT environment
variable (the workflow passes the event's text there, never on a command line).
"""
from __future__ import annotations

import argparse
import ast
import logging
import os
import re
import sys
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MARKER = "[agent2:review-fix]"
AGENT_NAME = "Agent 2 (Coder, review fix)"
_CODE_DIRS = ("features/", "tests/step_defs/", "pages/")
_FRAMEWORK_FILES = {"pages/base_page.py", "tests/step_defs/conftest.py", "tests/conftest.py"}
_SCENARIO_LINE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+?)\s*$", re.M)
_HANDLED_IDS = re.compile(r"comments:\s*([\d,\s]+)")


@dataclass
class Item:
    """One thing the reviewer asked: an inline comment, or the review's text."""
    n: int
    body: str
    comment_id: int | None = None
    path: str | None = None
    line: int | None = None

    def where(self) -> str:
        if not self.path:
            return "the pull request"
        return f"{self.path}:{self.line}" if self.line else self.path


@dataclass
class Outcome:
    item: Item
    action: str
    reason: str
    files: list = field(default_factory=list)


def settings() -> dict:
    from agents.agent2_coder import load_agent_config
    cfg = load_agent_config().get("review_fix") or {}
    return {"enabled": bool(cfg.get("enabled", True)),
            "command": str(cfg.get("command") or "/fix"),
            "branch_prefix": str(cfg.get("branch_prefix") or "auto/"),
            "max_files": int(cfg.get("max_files") or 6)}


def _norm(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def _file_type(path: str) -> str:
    if path.endswith(".feature"):
        return "feature"
    if path.startswith("tests/step_defs/"):
        return "step_definitions"
    if path.startswith("pages/"):
        return "page_object"
    return "other"


def feature_owned_by(content: str, story_key: str, test_case_keys: set) -> bool:
    """True when every scenario marker in a feature file is this story's.

    A marker is this story's when its key is one of the story's test cases and
    it names no other story as owner. A file with no marker, or with one
    marker of another story (a file this story only spliced into), is not.
    """
    from agents.agent2_coder import parse_marker_fields
    markers = [m for m in (parse_marker_fields(line) for line in (content or "").splitlines()) if m]
    keys = {k.upper() for k in test_case_keys}
    return bool(markers) and all(
        m["key"] in keys and (m["owner"] is None or m["owner"] == story_key.upper())
        for m in markers)


def owned_by_story(changed: list[dict], read, story_key: str, test_case_keys: set) -> set:
    """The PR's modified feature and step files that belong to this story alone.

    An `ai-regenerate` or `ai-update` pull request rewrites the story's own
    existing files, so they arrive as "modified", not "added". Ownership is
    read from the scenario markers on the PR's branch (`read(path)`); a step
    file `tests/step_defs/test_<stem>.py` follows its feature `<stem>.feature`
    (the pairing Agent 2 writes).
    """
    statuses = {_norm(f.get("filename", "")): f.get("status", "") for f in changed or []}

    def owns(path: str) -> bool:
        try:
            return feature_owned_by(read(path), story_key, test_case_keys)
        except Exception:                                          # noqa: BLE001
            return False

    features = {p for p, s in statuses.items() if p.endswith(".feature") and s != "removed"}
    owned = {p for p in features if statuses[p] == "added" or owns(p)}
    by_stem = {p.rsplit("/", 1)[-1][: -len(".feature")]: p for p in features}
    for path, status in statuses.items():
        if status != "modified" or _file_type(path) != "step_definitions":
            continue
        name = path.rsplit("/", 1)[-1]
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        stem = name[len("test_"):-len(".py")]
        feature = by_stem.get(stem)
        if feature in owned or (feature is None and owns(f"features/{stem}.feature")):
            owned.add(path)
    return {p for p in owned if statuses.get(p) == "modified"}


def classify_files(changed: list[dict], reserved: set, owned: set = frozenset()) -> tuple[dict, dict]:
    """(editable, protected): {path: status} and {path: reason} for the PR's code files.

    `owned`: modified files that are this story's own (`owned_by_story`).
    """
    editable, protected = {}, {}
    for f in changed or []:
        path, status = _norm(f.get("filename", "")), f.get("status", "")
        if status == "removed" or not path.endswith((".feature", ".py")) \
                or not path.startswith(_CODE_DIRS) or path.endswith("__init__.py"):
            continue
        if path in reserved:
            protected[path] = "a reserved reference file"
        elif path in _FRAMEWORK_FILES:
            protected[path] = "a framework file"
        elif _file_type(path) == "page_object" or status == "added" or path in owned:
            editable[path] = status
        else:
            protected[path] = ("another story's file - this pull request changes it only "
                               "by splicing approved scenarios")
    return editable, protected


def review_key(review_id: int | None, comment_id: int | None) -> str:
    return f"review {review_id}" if review_id else f"comment {comment_id}"


def handled(comments: list[str], key: str) -> bool:
    """True when a summary comment for this review or comment already exists."""
    return any(f"{MARKER} {key} comments:" in (c or "") for c in comments)


def handled_comment_ids(comments: list[str]) -> set:
    ids: set = set()
    for c in comments:
        if MARKER not in (c or ""):
            continue
        m = _HANDLED_IDS.search(c)
        if m:
            ids |= {int(x) for x in re.findall(r"\d+", m.group(1))}
    return ids


def strip_command(text: str, command: str) -> str:
    text = (text or "").strip()
    if text.lower().startswith(command.lower()):
        text = text[len(command):]
    return text.strip()


def collect_items(host, pr_number: int, review_id: int | None, text: str,
                  already: set) -> list[Item]:
    """A review: its inline comments, then its own text. A `/fix` comment: every
    inline comment not handled before, then the comment's own text, if any.

    A reviewer leaves comments on the lines and then writes `/fix please address
    these`: the text must not hide the comments it refers to.
    """
    inline = host.get_review_comments(pr_number, review_id)
    items: list[Item] = []
    for c in inline:
        if (c.get("author") or "").endswith("[bot]") or not (c.get("body") or "").strip():
            continue
        if review_id is None and c.get("id") in already:
            continue
        items.append(Item(len(items) + 1, c["body"].strip(), c.get("id"),
                          _norm(c.get("path") or "") or None, c.get("line")))
    if text.strip():
        items.append(Item(len(items) + 1, text.strip()))
    return items


def scenario_identity(content: str) -> list:
    """(marker key, marker hash, title) of each scenario, in order."""
    from agents.agent2_coder import parse_feature_file
    _h, blocks = parse_feature_file(content or "")
    out = []
    for b in blocks:
        if b.kind != "scenario":
            continue
        m = _SCENARIO_LINE.search(b.text())
        out.append((b.jira_key, b.jira_hash, m.group(1) if m else ""))
    return out


def degraded(new: str, prior: str, path: str) -> bool:
    """Stage 2's degraded-output test, without its absolute size floor for a
    file that was already below it: a short page object is not a stub."""
    from agents import agent2_coder as a2
    if len(prior or "") >= a2._DEGRADED_OUTPUT_CHAR_THRESHOLD:
        return a2._is_degraded_regeneration(new, prior, path)
    if not new or len(new) < 0.3 * len(prior or ""):
        return True
    if path.endswith(".feature"):
        return "Feature:" not in new or not re.search(r"Scenario( Outline)?:", new)
    try:
        ast.parse(new)
    except SyntaxError:
        return True
    return False


def decide(llm, items: list[Item], story: dict, test_cases: list, editable: dict,
           protected: dict):
    from agents.agent2_coder import format_test_cases_for_prompt, load_prompt
    from core.schemas import ReviewFixPlan
    prompt = (load_prompt("agent2_review_triage.md")
              .replace("{story_text}", f"{story.get('summary', '')}\n\n{story.get('description') or ''}")
              .replace("{test_cases_text}", format_test_cases_for_prompt(test_cases) or "(none)")
              .replace("{editable_files}", "\n".join(f"- {p} ({_file_type(p)})" for p in editable) or "(none)")
              .replace("{protected_files}", "\n".join(f"- {p} - {why}" for p, why in protected.items())
                       or "(none)")
              .replace("{comments}", "\n\n".join(f"{i.n}. On {i.where()}:\n{i.body}" for i in items)))
    return llm.invoke_structured(
        system_prompt="You are the coder who wrote this pull request, deciding how to answer its review.",
        user_prompt=prompt, output_schema=ReviewFixPlan)


def enforce(plan, items: list[Item], editable: dict, protected: dict) -> list[Outcome]:
    """The model's decisions, held to what code can check."""
    by_n = {d.comment: d for d in getattr(plan, "decisions", []) or []}
    out = []
    for item in items:
        d = by_n.get(item.n)
        if d is None:
            out.append(Outcome(item, "decline", "No decision was returned for this comment; "
                                                "nothing was changed for it."))
            continue
        if item.path and item.path in protected and d.action == "fix":
            out.append(Outcome(item, "decline", f"{item.path} is {protected[item.path]}, so it is "
                                                "not regenerated here."))
            continue
        if d.action != "fix":
            out.append(Outcome(item, d.action, d.reason))
            continue
        files = [p for p in (_norm(f) for f in d.files) if p in editable]
        if item.path and item.path in editable and item.path not in files:
            files.insert(0, item.path)
        if not files:
            out.append(Outcome(item, "decline", "The change needs a file this pull request may not "
                                                f"change here. {d.reason}"))
            continue
        out.append(Outcome(item, "fix", d.reason, files))
    return out


def _plan_for(head: str, title: str, contents: dict, statuses: dict, story_key: str,
              test_cases: list):
    from core.schemas import CodePlan, FilePlan
    keys = [tc["key"] for tc in test_cases]
    files = [FilePlan(file_path=p, file_type=_file_type(p), is_new_file=statuses.get(p) == "added",
                      purpose=f"Review fix for {story_key}", related_test_cases=keys)
             for p in contents]
    return CodePlan(feature_name=head.split("/", 1)[-1], branch_name=head, pr_title=title,
                    pr_body="", files_to_create=files, notes="")


def _reply(host, pr_number: int, outcome: Outcome, pushed: bool) -> None:
    if outcome.item.comment_id is None:
        return
    if outcome.action == "fix":
        text = (f"Agent 2: changed {', '.join(outcome.files)} - {outcome.reason}" if pushed else
                f"Agent 2: not changed - the fix did not pass the checks; see the summary comment. "
                f"{outcome.reason}")
    else:
        text = f"Agent 2: not changed - {outcome.reason}"
    try:
        host.reply_to_review_comment(pr_number, outcome.item.comment_id, text)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Could not reply to review comment %s: %s", outcome.item.comment_id, e)


def summary_comment(key: str, outcomes: list[Outcome], pushed: list, problem: str = "") -> str:
    ids = ",".join(str(o.item.comment_id) for o in outcomes if o.item.comment_id is not None)
    lines = [f"{MARKER} {key} comments: {ids or '-'}", "", "## 🤖 Agent 2 - review fix", ""]
    if pushed:
        lines.append(f"Pushed {len(pushed)} file(s) to this branch: {', '.join(pushed)}. "
                     "Agents 3, 4 and 5 run again on the new commit.")
    elif problem:
        lines.append(f"Nothing was pushed. {problem}")
    else:
        lines.append("Nothing needed a code change.")
    lines += ["", "| # | On | Action | Reason |", "|---|---|---|---|"]
    for o in outcomes:
        reason = o.reason.replace("|", "/").replace("\n", " ")
        lines.append(f"| {o.item.n} | {o.item.where()} | {o.action} | {reason} |")
    lines += ["", "_A comment that asks the tests to check something the approved test cases "
                  "do not state is declined: update the test case, then add `ai-regenerate`._"]
    return "\n".join(lines)


def run(pr_number: int, review_id: int | None = None, comment_id: int | None = None,
        text: str = "", dry_run: bool = False, host=None, tracker=None, llm=None,
        ctx=None) -> dict:
    """Handle one review (or one `/fix` comment) on one pull request."""
    from agents import agent2_coder as a2
    from config import extract_jira_key
    from core.llm_client import LLMClient, log_usage_summary, reset_usage
    from core.schemas import GeneratedFile

    cfg = settings()
    key = review_key(review_id, comment_id)
    result = {"pr": pr_number, "key": key}
    if not cfg["enabled"]:
        return {**result, "status": "disabled"}

    if host is None:
        from integrations.repo_host import get_repo_host
        host = get_repo_host()
    if tracker is None:
        from integrations.tracker import get_tracker
        tracker = get_tracker()
    recorders: list = []
    if dry_run:
        from core import dry_run as dry
        host, tracker = dry.repo_host(host), dry.tracker(tracker)
        recorders = [host, tracker]

    meta = host.get_pr_metadata(pr_number)
    head = meta.get("head_branch") or ""
    if (meta.get("state") or "open") != "open":
        return {**result, "status": "skipped", "reason": "pull request is not open"}
    if not head.startswith(cfg["branch_prefix"]):
        return {**result, "status": "skipped",
                "reason": f"branch {head!r} is not one Agent 2 opened ({cfg['branch_prefix']}*)"}
    story_key = extract_jira_key(head)
    if not story_key:
        return {**result, "status": "skipped", "reason": f"no story key in branch {head!r}"}

    earlier = host.get_pr_comments(pr_number)
    if handled(earlier, key):
        return {**result, "status": "skipped", "reason": f"{key} was handled before"}

    items = collect_items(host, pr_number, review_id, strip_command(text, cfg["command"]),
                          handled_comment_ids(earlier))
    if not items:
        return {**result, "status": "skipped", "reason": "nothing to act on"}

    if ctx is None:
        from core.app_context import AppContext
        ctx = AppContext.load()
    story = tracker.get_story(story_key)
    test_cases = a2.load_test_cases_for_story(tracker, story_key)
    changed_files = host.get_pr_changed_files(pr_number)
    owned = owned_by_story(changed_files, lambda p: host.get_file_content(p, branch=head),
                           story_key, {tc["key"] for tc in test_cases})
    editable, protected = classify_files(changed_files,
                                         {_norm(p) for p in ctx.reserved_paths_normalized()},
                                         owned)
    contents = {p: host.get_file_content(p, branch=head) for p in [*editable, *protected]}
    llm = llm or LLMClient(temperature=0.2)

    outcomes = enforce(decide(llm, items, story, test_cases, editable, protected),
                       items, editable, protected)
    to_fix: dict = {}
    for o in outcomes:
        if o.action == "fix":
            for p in o.files:
                to_fix.setdefault(p, []).append(o)

    pushed: list = []
    problem = ""
    if len(to_fix) > cfg["max_files"]:
        problem = (f"The review asks for changes in {len(to_fix)} files; review fix handles at most "
                   f"{cfg['max_files']} at once (`review_fix.max_files`). Split the review.")
        for o in outcomes:
            if o.action == "fix":
                o.action, o.reason = "decline", f"Not attempted: {problem}"
        to_fix = {}

    if to_fix:
        statuses = {**editable, **{p: "modified" for p in protected}}
        plan = _plan_for(head, meta.get("title") or "", contents, statuses, story_key, test_cases)
        references = ctx.load_reference_files()
        page_inventory = ctx.load_page_inventory_json(story.get("components"))
        files = {p: GeneratedFile(file_path=p, content=c, is_new_file=statuses.get(p) == "added",
                                  purpose=f"Review fix for {story_key}")
                 for p, c in contents.items()}
        for path, about in to_fix.items():
            feedback = [f"On {o.item.where()}: {o.item.body}" for o in about]
            prior = contents[path]
            fp = next(f for f in plan.files_to_create if f.file_path == path)
            new = a2.generate_file_content(
                llm, fp, plan, test_cases, references, page_inventory, ctx,
                previous_attempt=prior, review_feedback=feedback,
                already_generated=[f for p, f in files.items() if p != path])
            why_not = ""
            if degraded(new, prior, path):
                why_not = "the regenerated file was degraded (much shorter or malformed)"
            elif path.endswith(".feature") and scenario_identity(new) != scenario_identity(prior):
                why_not = ("the change would alter the scenarios, titles or markers, which come "
                           "from the approved test cases")
            if why_not:
                for o in about:
                    o.action, o.reason = "decline", f"Not changed: {why_not}."
                continue
            files[path] = files[path].model_copy(update={"content": new})

        # A file is pushed only for a comment still being fixed: when one file of
        # a comment's change was refused, its other files are put back too.
        wanted = {p for o in outcomes if o.action == "fix" for p in o.files}
        for p in files:
            if p not in wanted:
                files[p] = files[p].model_copy(update={"content": contents[p]})
        changed = [p for p in files if files[p].content != contents[p]]
        for o in outcomes:
            if o.action == "fix" and not any(p in changed for p in o.files):
                o.action, o.reason = "no_change", ("The regenerated file came back unchanged, "
                                                   "so nothing was changed for this comment.")
        if changed:
            batch = list(files.values())
            try:
                batch = a2._attempt_step_coverage_repair(
                    batch, llm, plan, test_cases, references, page_inventory, ctx)
                reached = [f.file_path for f in batch
                           if f.content != contents.get(f.file_path) and f.file_path not in editable]
                if reached:
                    raise ValueError(f"the repair would change files that are not editable here: "
                                     f"{reached}")
                a2._validate_generated_files(batch, story_key, test_cases)
            except Exception as e:                                 # noqa: BLE001
                problem = f"The changed files did not pass the checks every pull request passes: {e}"
                errors = getattr(e, "errors", None) or []
                if errors:
                    problem += "\n" + "\n".join(f"- {err}" for err in errors[:10])
                    if len(errors) > 10:
                        problem += f"\n- ... and {len(errors) - 10} more"
                logger.error("Review fix for PR #%s refused: %s", pr_number, e)
            else:
                for f in batch:
                    if f.content != contents.get(f.file_path):
                        host.create_or_update_file(
                            f.file_path, f.content,
                            f"fix(review): {f.file_path} - {key} on PR #{pr_number}", head)
                        pushed.append(f.file_path)

    for o in outcomes:
        _reply(host, pr_number, o, bool(pushed))
    host.post_pr_comment(pr_number, summary_comment(key, outcomes, pushed, problem))

    usage = log_usage_summary(f"PR #{pr_number} review fix")
    reset_usage()
    if not dry_run:
        from core.usage_ledger import post_usage_to_story
        post_usage_to_story(story_key, AGENT_NAME, usage, jira=tracker)

    status = "fixed" if pushed else ("refused" if problem else "nothing_to_fix")
    out = {**result, "status": status, "story": story_key, "pushed": pushed,
           "outcomes": [(o.item.n, o.action) for o in outcomes]}
    for recorder in recorders:
        for line in recorder.describe():
            print(line)
    return out


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="python -m agents.agent2_review_fix",
                                 description="Agent 2 - fix what a pull request's reviewer asked for")
    ap.add_argument("--pr", type=int, required=True, help="pull request number")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--review-id", type=int, help="a submitted review (its inline comments and text)")
    who.add_argument("--comment-id", type=int, help="a `/fix` conversation comment")
    ap.add_argument("--dry-run", action="store_true", help="decide and generate, print the writes, make none")
    args = ap.parse_args(argv)
    try:
        result = run(pr_number=args.pr, review_id=args.review_id,
                     comment_id=args.comment_id,
                     text=os.getenv("REVIEW_FIX_TEXT", ""),
                     dry_run=args.dry_run)
    except Exception as e:                                         # noqa: BLE001
        logger.error("Review fix failed on PR #%s: %s", args.pr, e, exc_info=True)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
