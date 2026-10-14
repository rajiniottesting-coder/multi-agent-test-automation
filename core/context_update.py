"""Context update: keep the agents' reference material in step with a change story.

Agent 1 and Agent 2 read two kinds of reference material that no agent
writes: the page inventory (every selector, plus notes about each page) and
the app context notes (prompts/app_context/*.md, or prompts/app_context.md).
When a story changes user-visible wording, both go stale. A selector that
matches on the old text stops resolving after deployment, and notes quoting
the old text keep teaching the agents the old wording, story after story.

When Agent 0 hands a change story over (or finds nothing to review), it
proposes the update as a pull request for a person to review. Two kinds of
change make the material stale, and each has its own step:

  * WORDING the story replaces (a label, a message): an exact replacement,
    below (steps 1-3).
  * BEHAVIOUR, a rule or an element the story changes or removes: one more
    model call reads the notes and the inventory's note text and rewrites
    each passage the story makes untrue (extract_note_rewrites). A passage
    not found verbatim is dropped and reported; a selector is never touched
    (the element is live until the change is deployed). Found in validation:
    a story removing a dialog left every note that described the dialog.

For wording:

1. One model call lists the text the story replaces: old -> new, as the
   story states it. A change whose old text appears in none of the sources
   is dropped and reported, the same rule as invented element keys.
2. The replacement is applied to the inventory's string values and to the
   context notes, exactly and case-sensitively. Each hit is classified as a
   selector (verify after deployment), an inventory note or a context note.
3. Code that mentions the old text (features, step definitions, page
   objects) is listed but not edited: code changes go through the story's
   own pull request.
4. The pull request is never merged here. Its branch carries no issue key,
   so merging it neither closes the story nor reports on it. The nightly
   inventory check confirms the selectors after deployment.

Everything comes from the story, the configured inventory file and the
configured context notes, so nothing here is specific to one application.
Idempotent: a marker comment on the story means the proposal was made - for
the story as it reads now (the marker carries its content hash) and for the
current attempt (a marker before the latest reconcile undo does not count).
An edited story, or a retry after an undo, is checked again.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MARKER = "[agent0:context-update]"
_STORY_HASH = re.compile(r"\(story: ([0-9a-f]+)\)")
_UNDONE = "[agent0:reconcile] reverted"
_CODE_GLOBS = ("features/**/*.feature", "tests/step_defs/**/*.py", "pages/**/*.py")


@dataclass
class Proposal:
    edits: dict = field(default_factory=dict)       # relpath -> new full text
    findings: list = field(default_factory=list)    # {"path","where","kind","before","after"}
    code_mentions: list = field(default_factory=list)  # {"path","line","text"}
    applied: list = field(default_factory=list)     # [(old, new)] that matched something
    dropped: list = field(default_factory=list)     # [(old, new, why)]
    rewrites: list = field(default_factory=list)    # {"path","before","after","reason"}

    @property
    def empty(self) -> bool:
        return not self.edits


# ─────────────────────────────────────────────────────────────
# Sources
# ─────────────────────────────────────────────────────────────

def context_sources(root: Path) -> dict:
    """{relpath: text} of the files this proposal may edit: the configured
    inventory and the app context notes. Missing files are simply absent."""
    root = Path(root)
    out: dict = {}
    try:
        from core.app_context import AppContext
        inv = AppContext.load().inventory_file
    except Exception:                                   # noqa: BLE001 - no app config
        inv = None
    if inv and (root / inv).is_file():
        out[Path(inv).as_posix()] = (root / inv).read_text(encoding="utf-8")
    folder = root / "prompts" / "app_context"
    files = sorted(folder.glob("*.md")) if folder.is_dir() else []
    single = root / "prompts" / "app_context.md"
    if not files and single.is_file():
        files = [single]
    for f in files:
        out[f.relative_to(root).as_posix()] = f.read_text(encoding="utf-8")
    return out


def code_sources(root: Path) -> dict:
    """{relpath: text} of code that may mention the wording - listed, never edited."""
    root = Path(root)
    out: dict = {}
    for pattern in _CODE_GLOBS:
        for f in sorted(root.glob(pattern)):
            if f.is_file() and "__pycache__" not in f.parts:
                out[f.relative_to(root).as_posix()] = f.read_text(encoding="utf-8")
    return out


# ─────────────────────────────────────────────────────────────
# The replacement
# ─────────────────────────────────────────────────────────────

def _walk(node, path=()):
    """(path, string) for every string VALUE in a JSON document."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (str(i),))
    elif isinstance(node, str):
        yield path, node


def _replace_values(node, old: str, new: str):
    if isinstance(node, dict):
        return {k: _replace_values(v, old, new) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_values(v, old, new) for v in node]
    if isinstance(node, str):
        return node.replace(old, new)
    return node


def _json_kind(path: tuple) -> str:
    return "selector" if "elements" in path else "inventory note"


def _apply_json(text: str, old: str, new: str, relpath: str, prop: Proposal) -> Optional[str]:
    try:
        data = json.loads(text)
    except ValueError:
        logger.warning("context update: %s is not valid JSON - left alone", relpath)
        return None
    hits = [(p, s) for p, s in _walk(data) if old in s]
    if not hits:
        return None
    for p, s in hits:
        prop.findings.append({"path": relpath, "where": ".".join(p), "kind": _json_kind(p),
                              "before": s, "after": s.replace(old, new)})
    expected = _replace_values(data, old, new)
    # Replace in the raw text so the file keeps its own formatting; accept it
    # only if it parses to exactly the value-only replacement (no key touched).
    enc_old, enc_new = json.dumps(old)[1:-1], json.dumps(new)[1:-1]
    candidate = text.replace(enc_old, enc_new)
    try:
        if json.loads(candidate) == expected:
            return candidate
    except ValueError:
        pass
    return json.dumps(expected, indent=2, ensure_ascii=False) + "\n"


def _apply_text(text: str, old: str, new: str, relpath: str, prop: Proposal) -> Optional[str]:
    if old not in text:
        return None
    for n, line in enumerate(text.splitlines(), 1):
        if old in line:
            prop.findings.append({"path": relpath, "where": f"line {n}", "kind": "context note",
                                  "before": line.strip(), "after": line.replace(old, new).strip()})
    return text.replace(old, new)


def _apply_json_notes(text: str, old: str, new: str) -> str | None:
    """Replace `old` inside the inventory's NOTE values only - never a selector
    (a value under an `elements` map). None when no note holds it."""
    try:
        data = json.loads(text)
    except ValueError:
        return None

    def walk(node, path):
        if isinstance(node, dict):
            return {k: walk(v, path + (str(k),)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, path + (str(i),)) for i, v in enumerate(node)]
        if isinstance(node, str) and "elements" not in path and old in node:
            hits.append(path)
            return node.replace(old, new)
        return node
    hits: list = []
    expected = walk(data, ())
    if not hits:
        return None
    # Keep the file's own formatting where a raw replacement gives exactly the
    # note-only result (as _apply_json does for wording).
    candidate = text.replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1])
    try:
        if json.loads(candidate) == expected:
            return candidate
    except ValueError:
        pass
    return json.dumps(expected, indent=2, ensure_ascii=False) + "\n"


def _apply_rewrites(current: dict, rewrites, prop: Proposal) -> None:
    for rw in rewrites or []:
        path = (getattr(rw, "path", "") or "").strip()
        old = (getattr(rw, "old", "") or "").strip()
        new = (getattr(rw, "new", "") or "").strip()
        reason = (getattr(rw, "reason", "") or "").strip()
        if not old or not new or old == new:
            prop.dropped.append((old[:60], new[:60], "empty or unchanged rewrite"))
            continue
        if path not in current:
            prop.dropped.append((old[:60], new[:60], f"{path or '(no path)'} is not a note file"))
            continue
        text = current[path]
        if path.endswith(".json"):
            updated = _apply_json_notes(text, old, new)
        else:
            updated = text.replace(old, new) if old in text else None
        if updated is None:
            prop.dropped.append((old[:60], new[:60], f"the passage is not in {path} verbatim"))
            continue
        current[path] = updated
        prop.rewrites.append({"path": path, "before": old, "after": new, "reason": reason})


def propose(sources: dict, changes, code: dict | None = None, rewrites=()) -> Proposal:
    """Apply each old -> new, then each passage rewrite, to the sources.
    Pure: nothing is written."""
    prop = Proposal()
    current = dict(sources)
    seen: set = set()
    for ch in changes:
        old, new = (getattr(ch, "old", None) or "").strip(), (getattr(ch, "new", None) or "").strip()
        if not old or not new or old == new:
            prop.dropped.append((old, new, "empty or unchanged"))
            continue
        if old in seen:
            continue
        seen.add(old)
        matched = False
        for relpath, text in current.items():
            apply = _apply_json if relpath.endswith(".json") else _apply_text
            updated = apply(text, old, new, relpath, prop)
            if updated is not None and updated != text:
                current[relpath] = updated
                matched = True
        if not matched:
            prop.dropped.append((old, new, "the old text appears in none of the context files"))
            continue
        prop.applied.append((old, new))
        for relpath, text in (code or {}).items():
            for n, line in enumerate(text.splitlines(), 1):
                if old in line:
                    prop.code_mentions.append({"path": relpath, "line": n, "text": line.strip()})
    _apply_rewrites(current, rewrites, prop)
    prop.edits = {p: t for p, t in current.items() if t != sources.get(p)}
    return prop


# ─────────────────────────────────────────────────────────────
# The pull request
# ─────────────────────────────────────────────────────────────

def branch_for(story_key: str, prefix: str) -> str:
    """A branch with NO issue key in it: merging a context update must not
    close the story or report on it, and both find the story by its key in
    the branch name."""
    from config import extract_jira_key
    branch = f"{prefix}{story_key.lower()}"
    if extract_jira_key(branch):
        branch = f"{prefix}{hashlib.sha1(story_key.encode()).hexdigest()[:10]}"
    return branch


def _cell(text: str, limit: int = 120) -> str:
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_body(story_key: str, prop: Proposal) -> str:
    lines = [f"Context update proposed by Agent 0 for **{story_key}**.", "",
             "**Merge only after the change is deployed.** Before that, a selector below "
             "no longer matches the live application. Re-run this PR's checks after "
             "deployment; the nightly inventory check also confirms the selectors.", "",
             ]
    if prop.applied:
        lines += ["Wording changes taken from the story:"]
        lines += [f"- `{old}` → `{new}`" for old, new in prop.applied]
        lines += ["", "| File | Where | Kind | Before | After |", "|---|---|---|---|---|"]
        for f in prop.findings:
            lines.append(f"| `{f['path']}` | {_cell(f['where'], 60)} | {f['kind']} | "
                         f"{_cell(f['before'])} | {_cell(f['after'])} |")
    if prop.rewrites:
        lines += ["", ("Passages the story makes untrue - rewritten for the changed "
                       "application. Check each against the story before merging:"),
                  "", "| File | Before | After | Why |", "|---|---|---|---|"]
        for r in prop.rewrites:
            lines.append(f"| `{r['path']}` | {_cell(r['before'], 200)} | "
                         f"{_cell(r['after'], 200)} | {_cell(r['reason'], 160)} |")
    if any(f["kind"] == "selector" for f in prop.findings):
        lines += ["", "Selectors: verify after deployment that each matches exactly the "
                      "element it should (`python -m scripts.verify_locators`)."]
    if prop.code_mentions:
        lines += ["", "Also mentions the old text - **not edited here**; code changes go "
                      "through the story's own pull request:"]
        lines += [f"- `{m['path']}:{m['line']}` {_cell(m['text'], 100)}"
                  for m in prop.code_mentions[:40]]
    if prop.dropped:
        lines += ["", "Not applied:"]
        lines += [f"- `{o}` → `{n}`: {why}" for o, n, why in prop.dropped]
    lines += ["", "Review every row: an exact text match can also hit a sentence that "
                  "means something else. Edit or revert such rows before merging."]
    return "\n".join(lines)


def open_pull_request(host, story_key: str, prop: Proposal, prefix: str) -> Optional[str]:
    """Branch, commit each edited file, open the PR. Returns its URL, or None
    when the branch already exists (proposed before)."""
    branch = branch_for(story_key, prefix)
    if host.branch_exists(branch):
        logger.info("context update for %s: branch %s exists - not proposed again",
                    story_key, branch)
        return None
    host.create_branch(branch, "main")
    try:
        for relpath, text in sorted(prop.edits.items()):
            host.create_or_update_file(relpath, text,
                                       f"chore(context): wording from {story_key} in {relpath}",
                                       branch)
        return host.open_pull_request(
            f"chore(context): reference wording from {story_key} - merge after deploy",
            render_body(story_key, prop), branch, "main")
    except Exception:
        host.delete_branch(branch)            # never leave a half-written branch
        raise


# ─────────────────────────────────────────────────────────────
# Entry point (Agent 0)
# ─────────────────────────────────────────────────────────────

def extract_changes(llm, story: dict):
    from config.paths import PROMPTS_DIR
    from core.schemas import WordingChanges
    text = f"Title: {story['summary']}\n\nDescription:\n{story.get('description') or ''}"
    prompt = (PROMPTS_DIR / "agent0_wording.md").read_text(encoding="utf-8").replace(
        "{story_text}", text)
    return llm.invoke_structured(system_prompt="You are a senior QA analyst.",
                                 user_prompt=prompt, output_schema=WordingChanges).changes


def _notes_block(sources: dict) -> str:
    """The notes as the model sees them: each notes file whole, and the
    inventory as its NOTE values only, so a selector is never offered."""
    parts = []
    for relpath, text in sorted(sources.items()):
        if relpath.endswith(".json"):
            try:
                notes = [(".".join(p), s) for p, s in _walk(json.loads(text))
                         if "elements" not in p]
            except ValueError:
                continue
            if notes:
                parts.append(f"## FILE {relpath} (inventory - note text only)\n"
                             + "\n".join(f"- {where}: {value}" for where, value in notes))
        else:
            parts.append(f"## FILE {relpath}\n{text}")
    return "\n\n".join(parts)


def extract_note_rewrites(llm, story: dict, story_key: str, sources: dict) -> list:
    """One model call: each reference passage the story makes untrue, rewritten."""
    from config.paths import PROMPTS_DIR
    from core.schemas import NoteRewrites
    block = _notes_block(sources)
    if not block:
        return []
    text = f"Title: {story['summary']}\n\nDescription:\n{story.get('description') or ''}"
    prompt = ((PROMPTS_DIR / "agent0_context_notes.md").read_text(encoding="utf-8")
              .replace("{story_key}", story_key).replace("{story_text}", text)
              .replace("{notes_block}", block))
    result = llm.invoke_structured(system_prompt="You are a senior QA analyst.",
                                   user_prompt=prompt, output_schema=NoteRewrites)
    return list(getattr(result, "rewrites", None) or [])


def propose_for_story(tracker, host, llm, story_key: str, settings: dict, root: Path) -> dict:
    """Propose the context update for one change story, once."""
    cfg = settings.get("context_update") or {}
    if not cfg.get("enabled", False):
        return {"story": story_key, "context": "disabled"}
    story = tracker.get_story(story_key)
    chash = _story_hash(story)
    if _already_proposed(tracker.get_comments(story_key), chash, _pr_is_open(host)):
        return {"story": story_key, "context": "already-proposed"}
    sources = context_sources(root)
    changes = extract_changes(llm, story)
    try:
        rewrites = extract_note_rewrites(llm, story, story_key, sources)
        unchecked = ""
    except Exception as e:                                         # noqa: BLE001
        # The wording update must not be lost to a failure of this step.
        logger.warning("context update for %s: behaviour notes not checked: %s", story_key, e)
        rewrites, unchecked = [], f"\nBehaviour notes were not checked ({type(e).__name__})."
    prop = propose(sources, changes, code_sources(root), rewrites)
    if prop.empty:
        tracker.add_comment(story_key, f"{MARKER} No context update needed: the story replaces "
                            "no wording, and makes no passage untrue, in the inventory or the "
                            "context notes."
                            + ("".join(f"\nNot applied: {o} -> {n} ({why})"
                                       for o, n, why in prop.dropped)) + unchecked
                            + f"\n(story: {chash})")
        return {"story": story_key, "context": "none"}
    url = open_pull_request(host, story_key, prop, cfg.get("branch_prefix", "context-update/"))
    if url:
        tracker.add_comment(story_key, f"{MARKER} Context update proposed: {url} - "
                            f"{len(prop.findings) + len(prop.rewrites)} change(s) to the inventory "
                            "and context notes. "
                            "Merge it after this change is deployed."
                            f"\n(story: {chash})")
    return {"story": story_key, "context": "proposed" if url else "branch-exists", "url": url}


def _story_hash(story: dict) -> str:
    from core.impact_analysis import content_hash
    return content_hash(story.get("summary") or "", story.get("description") or "",
                        sorted(story.get("components") or []))


_PR_NUMBER = re.compile(r"/pull/(\d+)")


def _pr_is_open(host):
    """is_open(number) -> bool for markers that link a pull request.

    A failed lookup answers True: proposing a second PR because the repo host
    was unreachable would be worse than skipping one scan."""
    def is_open(number: int) -> bool:
        if host is None:
            return True
        try:
            return (host.get_pr_metadata(number) or {}).get("state") == "open"
        except Exception as e:                                     # noqa: BLE001
            logger.warning("context update: could not read PR #%s (%s) - "
                           "treating it as still open", number, e)
            return True
    return is_open


def _already_proposed(comments: list, chash: str, pr_is_open=None) -> bool:
    """A proposal stands only for this attempt, this text of the story, and -
    when it opened a pull request - only while that pull request is open.

    Comments are oldest first. A marker before the latest undo belonged to a
    change that never shipped; a marker for other story text (or one written
    before markers carried the hash) cannot say the current text was checked.

    The pull request's own state is the authority, not comment history: in
    validation story A3 the undo comment was deleted during a manual clean-up
    while the marker of the closed PR stayed, and the retry's context update
    was skipped silently. A closed PR - rejected, or merged so the notes no
    longer hold the old text - no longer stands; proposing again yields a new
    PR or a 'no context update needed' marker. A marker without a PR (no update
    needed) stands on the hash and the undo rule alone."""
    last_undo = max((i for i, c in enumerate(comments) if (c or "").startswith(_UNDONE)),
                    default=-1)
    for c in comments[last_undo + 1:]:
        if (c or "").startswith(MARKER):
            m = _STORY_HASH.search(c)
            if not (m and m.group(1) == chash):
                continue
            pr = _PR_NUMBER.search(c)
            if pr and pr_is_open is not None and not pr_is_open(int(pr.group(1))):
                continue
            return True
    return False
