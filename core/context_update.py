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
ADD_MARKER = "[agent0:context-addition]"
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
    declared_removed: list = field(default_factory=list)  # ["page.key"] added to `removed`

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


def scoped_sources(sources: dict, components, root: Path) -> tuple[dict, set]:
    """(sources, inventory pages) the story's Components select - what the
    note-rewrite call reads (F-10). The notes modules follow Agent 1's rule
    (core.app_context.select_note_modules): core.md plus the story's modules,
    or all of them when none match; a single prompts/app_context.md is kept.
    The inventory is kept whole here; the page names returned limit which of
    its notes are offered (filter_inventory_by_components' rule)."""
    from core.app_context import select_note_modules, selected_page_names
    root = Path(root)
    folder = root / "prompts" / "app_context"
    wanted = ({p.relative_to(root).as_posix() for p in select_note_modules(folder, components)}
              if folder.is_dir() else set())
    out, pages = {}, None
    for relpath, text in sources.items():
        if relpath.endswith(".json"):
            out[relpath] = text
            try:
                pages = selected_page_names(json.loads(text), components)
            except ValueError:
                pages = None
        elif relpath.startswith("prompts/app_context/"):
            if relpath in wanted:
                out[relpath] = text
        else:
            out[relpath] = text
    return out, pages


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


def _apply_rewrites(current: dict, rewrites, prop: Proposal, offered=None) -> None:
    """Apply each rewrite; `offered` (when given) is the set of files the model
    was shown - a rewrite of any other file is dropped, never applied blind."""
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
        if offered is not None and path not in offered:
            prop.dropped.append((old[:60], new[:60],
                                 f"{path} was not among the notes the story's Components select"))
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


def _declare_removed(current: dict, removed, pages, prop: Proposal) -> None:
    """Add each `page.key` the story removes to that page's `removed` list in
    the inventory: after deployment the nightly check then reads the missing
    element as expected, and the inventory update deletes the key once no
    test names it (F-11). A reference that is not an element of a page the
    story's Components select is dropped and reported."""
    refs = [r.strip() for r in removed or () if r and r.strip()]
    if not refs:
        return
    paths = [p for p in current if p.endswith(".json")]
    if len(paths) != 1:
        prop.dropped += [(ref, "", "no single inventory file to declare it in") for ref in refs]
        return
    path = paths[0]
    try:
        data = json.loads(current[path])
    except ValueError:
        prop.dropped += [(ref, "", "the inventory could not be read") for ref in refs]
        return
    page_map = data.get("pages") or {}
    for ref in dict.fromkeys(refs):
        page, _, key = ref.partition(".")
        spec = page_map.get(page)
        if not key:
            prop.dropped.append((ref, "", "not written as page.key"))
        elif pages is not None and page not in pages:
            prop.dropped.append((ref, "", "not a page the story's Components select"))
        elif not isinstance(spec, dict) or key not in (spec.get("elements") or {}):
            prop.dropped.append((ref, "", "no such element in the inventory"))
        elif key not in (spec.get("removed") or []):
            spec["removed"] = list(spec.get("removed") or []) + [key]
            prop.declared_removed.append(ref)
    if prop.declared_removed:
        from core.inventory_update import dump_like
        current[path] = dump_like(current[path], data)


def propose(sources: dict, changes, code: dict | None = None, rewrites=(),
            offered=None, removed=(), pages=None) -> Proposal:
    """Apply each old -> new, then each passage rewrite, then each removed
    element's declaration, to the sources. `offered`: the files the rewrite
    call was shown (None: all); `pages`: the inventory pages it was shown.
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
    _apply_rewrites(current, rewrites, prop, offered)
    _declare_removed(current, removed, pages, prop)
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
    if prop.declared_removed:
        lines += ["", "Elements the story removes, declared `removed` in the inventory - after "
                      "deployment the nightly check reads each missing element as expected "
                      "(present again: drift), and the nightly inventory update deletes the key "
                      "once no test names it:"]
        lines += [f"- `{ref}`" for ref in prop.declared_removed]
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


def _open_branch_pr(host, branch: str, edits: dict, message: str, title: str,
                    body: str) -> Optional[str]:
    """Branch from main, commit each edited file, open the PR. Returns its URL,
    or None when the branch already exists (proposed before)."""
    if host.branch_exists(branch):
        logger.info("context update: branch %s exists - not proposed again", branch)
        return None
    host.create_branch(branch, "main")
    try:
        for relpath, text in sorted(edits.items()):
            host.create_or_update_file(relpath, text, f"{message} in {relpath}", branch)
        return host.open_pull_request(title, body, branch, "main")
    except Exception:
        host.delete_branch(branch)            # never leave a half-written branch
        raise


def open_pull_request(host, story_key: str, prop: Proposal, prefix: str) -> Optional[str]:
    """The change story's context-update PR (wording and untrue passages)."""
    return _open_branch_pr(
        host, branch_for(story_key, prefix), prop.edits,
        f"chore(context): wording from {story_key}",
        f"chore(context): reference wording from {story_key} - merge after deploy",
        render_body(story_key, prop))


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


def _notes_block(sources: dict, pages=None) -> str:
    """The notes as the model sees them: each notes file whole, and the
    inventory as its NOTE values only, so a selector is never offered.
    `pages` (when given) limits the inventory's page notes to those pages;
    notes outside `pages` (test users, common errors) are always offered."""
    parts = []
    for relpath, text in sorted(sources.items()):
        if relpath.endswith(".json"):
            try:
                notes = [(".".join(p), s) for p, s in _walk(json.loads(text))
                         if "elements" not in p
                         and (pages is None or len(p) < 2 or p[0] != "pages" or p[1] in pages)]
            except ValueError:
                continue
            if notes:
                parts.append(f"## FILE {relpath} (inventory - note text only)\n"
                             + "\n".join(f"- {where}: {value}" for where, value in notes))
            try:
                page_map = (json.loads(text).get("pages") or {})
            except (ValueError, AttributeError):
                page_map = {}
            keys = [(name, sorted(k for k, v in (spec.get("elements") or {}).items()
                                  if isinstance(v, str) and not k.startswith("_")))
                    for name, spec in sorted(page_map.items())
                    if isinstance(spec, dict) and (pages is None or name in pages)]
            if any(k for _n, k in keys):
                parts.append(f"## Elements of {relpath} (keys only - for `removed`)\n"
                             + "\n".join(f"- {name}: {', '.join(k)}" for name, k in keys if k))
        else:
            parts.append(f"## FILE {relpath}\n{text}")
    return "\n\n".join(parts)


def extract_note_rewrites(llm, story: dict, story_key: str, sources: dict, pages=None):
    """One model call: each reference passage the story makes untrue, rewritten,
    and the elements it removes. Returns (rewrites, removed).
    `sources` and `pages` are what the story's Components select (scoped_sources)."""
    from config.paths import PROMPTS_DIR
    from core.schemas import NoteRewrites
    block = _notes_block(sources, pages)
    if not block:
        return [], []
    text = f"Title: {story['summary']}\n\nDescription:\n{story.get('description') or ''}"
    prompt = ((PROMPTS_DIR / "agent0_context_notes.md").read_text(encoding="utf-8")
              .replace("{story_key}", story_key).replace("{story_text}", text)
              .replace("{notes_block}", block))
    result = llm.invoke_structured(system_prompt="You are a senior QA analyst.",
                                   user_prompt=prompt, output_schema=NoteRewrites)
    return (list(getattr(result, "rewrites", None) or []),
            list(getattr(result, "removed", None) or []))


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
    offered, pages = scoped_sources(sources, story.get("components") or [], root)
    changes = extract_changes(llm, story)
    try:
        rewrites, removed = extract_note_rewrites(llm, story, story_key, offered, pages)
        unchecked = ""
    except Exception as e:                                         # noqa: BLE001
        # The wording update must not be lost to a failure of this step.
        logger.warning("context update for %s: behaviour notes not checked: %s", story_key, e)
        rewrites, removed = [], []
        unchecked = f"\nBehaviour notes were not checked ({type(e).__name__})."
    prop = propose(sources, changes, code_sources(root), rewrites, set(offered), removed, pages)
    if prop.empty:
        tracker.add_comment(story_key, f"{MARKER} No context update needed: the story replaces "
                            "no wording, makes no passage untrue and removes no element, in the "
                            "inventory or the context notes."
                            + ("".join(f"\nNot applied: {o} -> {n} ({why})"
                                       for o, n, why in prop.dropped)) + unchecked
                            + f"\n(story: {chash})")
        return {"story": story_key, "context": "none"}
    url = open_pull_request(host, story_key, prop, cfg.get("branch_prefix", "context-update/"))
    if url:
        tracker.add_comment(story_key, f"{MARKER} Context update proposed: {url} - "
                            f"{len(prop.findings) + len(prop.rewrites) + len(prop.declared_removed)} "
                            "change(s) to the inventory "
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


# ─────────────────────────────────────────────────────────────
# Additions when a story's pull request merges (F-8)
# ─────────────────────────────────────────────────────────────
#
# The hand-over update above can only REPLACE wording and REWRITE passages the
# story makes untrue; it never adds. A new feature - or a change story that
# adds a rule - therefore never reached the notes, and the next story on that
# feature was drafted from its own text alone. When a story's pull request
# merges (its tests passed against the live application), one model call
# proposes the facts the notes do not hold yet: rules, limits, messages, flow,
# test data. They go into the story's Component modules - a new module for a
# Component that has none - and every line already said, in any wording, is
# dropped deterministically. A reviewed pull request, like every other.

_WORD = re.compile(r"[a-z0-9]+")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass
class Additions:
    edits: dict = field(default_factory=dict)       # relpath -> new full text
    added: list = field(default_factory=list)       # {"path","heading","text","reason","new_file"}
    dropped: list = field(default_factory=list)     # (path, snippet, why)
    repeated: list = field(default_factory=list)    # (path, line) dropped as already said

    @property
    def empty(self) -> bool:
        return not self.edits


def _tokens(line: str) -> set:
    return set(_WORD.findall(_BULLET.sub("", line).lower()))


def _paragraphs(text: str) -> list:
    """Paragraphs and bullets of a notes text, hard-wrapped lines joined:
    a heading or a blank line ends one, a bullet starts a new one."""
    out, cur = [], []
    for line in (text or "").splitlines():
        if not line.strip() or _HEADING.match(line):
            if cur:
                out.append(" ".join(cur))
            cur = []
            continue
        if _BULLET.match(line) and cur:
            out.append(" ".join(cur))
            cur = []
        cur.append(_BULLET.sub("", line).strip() if not cur else line.strip())
    if cur:
        out.append(" ".join(cur))
    return out


def _units(text: str) -> list:
    """The sentences of a notes text (headings excluded, wrapped lines
    joined): what a new line is compared against."""
    return [u for p in _paragraphs(text) for u in re.split(r"(?<=[.!?])\s+", p) if u.strip()]


def near_duplicate(line: str, existing: list, threshold: float = 0.8) -> bool:
    """True when `line` says what one existing unit already says: its words
    are (almost) the same set, or it is contained in one. Deterministic, so a
    reviewer sees exactly why a line was left out."""
    words = _tokens(line)
    if not words:
        return True
    flat = re.sub(r"\s+", " ", _BULLET.sub("", line).strip().lower())
    for unit in existing:
        other = _tokens(unit)
        if not other:
            continue
        if flat and flat in re.sub(r"\s+", " ", unit.lower()):
            return True
        if len(words & other) / len(words | other) >= threshold:
            return True
    return False


def _insert_under(text: str, heading: str, block: str) -> Optional[str]:
    """`block` placed at the end of the section titled `heading` (any level),
    before the next heading of the same or a higher level. None when no such
    heading exists."""
    lines = text.splitlines()
    want = heading.strip().lstrip("#").strip().lower()
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().lower() == want:
            level = len(m.group(1))
            end = len(lines)
            for j in range(i + 1, len(lines)):
                n = _HEADING.match(lines[j])
                if n and len(n.group(1)) <= level:
                    end = j
                    break
            last = end
            while last > i + 1 and not lines[last - 1].strip():
                last -= 1
            rest = lines[end:]
            new = block.splitlines()
            # A bullet list continues as one list; anything else is a paragraph.
            joined = bool(_BULLET.match(lines[last - 1]) and new and _BULLET.match(new[0]))
            out = lines[:last] + ([] if joined else [""]) + new + ([""] + rest if rest else [])
            return "\n".join(out).rstrip("\n") + "\n"
    return None


def _append_section(text: str, block: str) -> str:
    return (text.rstrip("\n") + "\n\n" if text.strip() else "") + block.strip() + "\n"


def notes_report(texts: dict, budget: int, min_words: int = 6) -> dict:
    """Size and repetition of the notes modules (F-9), on {relpath: text}:

        {"over": [(path, chars)], "duplicates": [(path, sentence, path, sentence)]}

    `over`: modules longer than `budget` characters - every one of them goes
    into the prompt of each story it is selected for. `duplicates`: sentence
    pairs (at least `min_words` words) saying the same thing, within a module
    or across two. Deterministic; the inventory is not a notes module."""
    md = {p: t for p, t in sorted(texts.items()) if p.endswith(".md")}
    over = [(p, len(t)) for p, t in md.items() if len(t) > budget]
    items = [(p, u, _tokens(u)) for p, t in md.items() for u in _units(t)]
    items = [i for i in items if len(i[2]) >= min_words]
    dup = []
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            pa, ua, ta = items[a]
            pb, ub, tb = items[b]
            if len(ta & tb) / len(ta | tb) >= 0.8:
                dup.append((pa, ua, pb, ub))
    return {"over": over, "duplicates": dup}


def render_notes_report(report: dict, budget: int, limit: int = 10) -> str:
    """The notes-size section of a pull request body ('' when all is well)."""
    lines = []
    if report["over"]:
        lines += [f"**Notes over the {budget}-character budget** - each goes into the prompt "
                  "of every story it is selected for. Condense before merging (the unit "
                  "suite fails on a module over budget):"]
        lines += [f"- `{p}`: {n} characters" for p, n in report["over"]]
    if report["duplicates"]:
        lines += ["", "Sentences that say the same thing - consider keeping one:"]
        lines += [f"- `{pa}`: {_cell(ua, 90)} ↔ `{pb}`: {_cell(ub, 90)}"
                  for pa, ua, pb, ub in report["duplicates"][:limit]]
        if len(report["duplicates"]) > limit:
            lines.append(f"- … and {len(report['duplicates']) - limit} more")
    return "\n".join(lines).strip()


def new_module_paths(components, root: Path) -> dict:
    """{relpath: Component} for each story Component with no module yet - the
    only new files an addition may create (and only in the module layout)."""
    from core.app_context import _norm_component
    folder = Path(root) / "prompts" / "app_context"
    if not folder.is_dir():
        return {}
    have = {_norm_component(p.stem) for p in folder.glob("*.md")}
    out = {}
    for c in components or []:
        key = _norm_component(c or "")
        if key and key not in have:
            out[f"prompts/app_context/{key}.md"] = c.strip()
    return out


def propose_additions(sources: dict, additions, offered: set, new_modules: dict,
                      max_chars: int = 1500) -> Additions:
    """Place each addition (pure). Refused, and reported: a file the story's
    Components do not select (or the inventory - not a notes module), an
    empty or over-long addition, and every line the notes already state."""
    res = Additions()
    current = {p: t for p, t in sources.items() if not p.endswith(".json")}
    for add in additions or []:
        path = (getattr(add, "path", "") or "").strip()
        text = (getattr(add, "text", "") or "").strip()
        heading = (getattr(add, "heading", "") or "").strip().lstrip("#").strip()
        reason = (getattr(add, "reason", "") or "").strip()
        snippet = text[:60]
        if not text:
            res.dropped.append((path, snippet, "empty addition"))
            continue
        if path.endswith(".json") or not (path in offered or path in new_modules):
            res.dropped.append((path, snippet, "not a notes module the story's Components select"))
            continue
        if len(text) > max_chars:
            res.dropped.append((path, snippet, f"longer than {max_chars} characters"))
            continue
        existing = [u for t in current.values() for u in _units(t)]
        kept = []
        for line in text.splitlines():
            if not line.strip() or _HEADING.match(line):
                kept.append(line)
            elif near_duplicate(line, existing):
                res.repeated.append((path, line.strip()))
            else:
                kept.append(line)
        if not any(l.strip() and not _HEADING.match(l) for l in kept):
            res.dropped.append((path, snippet, "the notes already state it"))
            continue
        block = "\n".join(kept).strip()
        first = _HEADING.match(block.splitlines()[0])
        if first and heading and first.group(2).strip().lower() == heading.lower():
            # The text repeats the heading it is placed under: keep one.
            block = "\n".join(block.splitlines()[1:]).strip()
            first = None
        new_file = path not in current
        if new_file:
            current[path] = f"# {new_modules[path]}\n\n{block}\n"
        elif heading:
            placed = _insert_under(current[path], heading, block)
            current[path] = placed if placed is not None else _append_section(
                current[path], block if first else f"## {heading}\n\n{block}")
        else:
            current[path] = _append_section(current[path], block)
        res.added.append({"path": path, "heading": heading, "text": block, "reason": reason,
                          "new_file": new_file})
    res.edits = {p: t for p, t in current.items() if t != sources.get(p)}
    return res


def story_scenarios(root: Path, keys) -> str:
    """The merged scenarios of these test cases (by their `# JIRA:` markers),
    as written in the feature files on the checked-out branch."""
    from agents.agent2_coder import parse_feature_file
    keys = {k.upper() for k in keys or []}
    parts = []
    for path in sorted(Path(root).glob("features/**/*.feature")):
        try:
            _header, blocks = parse_feature_file(path.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            continue
        for b in blocks:
            if getattr(b, "kind", "") == "scenario" and (b.jira_key or "").upper() in keys:
                parts.append(f"## {path.relative_to(root).as_posix()}\n{b.text().strip()}")
    return "\n\n".join(parts)


def extract_note_additions(llm, story: dict, story_key: str, test_cases: list, scenarios: str,
                           sources: dict, pages, new_modules: dict) -> list:
    """One model call: the facts the merged story adds to the notes."""
    from config.paths import PROMPTS_DIR
    from core.schemas import NoteAdditions
    notes = {p: t for p, t in sources.items() if not p.endswith(".json")}
    text = f"Title: {story['summary']}\n\nDescription:\n{story.get('description') or ''}"
    cases = "\n\n".join(f"### {tc.get('key')}: {tc.get('summary', '')}\n{tc.get('description') or ''}"
                         for tc in test_cases or []) or "(none)"
    new = "\n".join(f"- {p} (Component: {c})" for p, c in new_modules.items()) or "(none)"
    prompt = ((PROMPTS_DIR / "agent0_context_additions.md").read_text(encoding="utf-8")
              .replace("{story_key}", story_key).replace("{story_text}", text)
              .replace("{test_cases}", cases).replace("{scenarios}", scenarios or "(none)")
              .replace("{new_modules}", new).replace("{notes_block}", _notes_block(notes, pages)))
    result = llm.invoke_structured(system_prompt="You are a senior QA analyst.",
                                   user_prompt=prompt, output_schema=NoteAdditions)
    return list(getattr(result, "additions", None) or [])


def render_addition_body(story_key: str, res: Additions, notes_report: str = "") -> str:
    lines = [f"Notes addition proposed by Agent 0 for **{story_key}**, whose pull request "
             "merged: its feature is live and its tests passed.", "",
             "Each addition is a fact a future story on this feature needs and the notes did "
             "not state. **Check every line against the story and its test cases**, edit or "
             "drop any you do not want, then merge.", ""]
    for a in res.added:
        where = "a new module" if a["new_file"] else (
            f"under `{a['heading']}`" if a["heading"] else "a new section at the end")
        lines += [f"### `{a['path']}` - {where}", "", a["text"], "",
                  f"_From: {_cell(a['reason'], 300)}_", ""]
    if res.repeated:
        lines += ["Left out - the notes already state it:"]
        lines += [f"- `{p}`: {_cell(l, 140)}" for p, l in res.repeated[:40]]
        lines += [""]
    if res.dropped:
        lines += ["Not applied:"]
        lines += [f"- `{p or '(no path)'}`: {_cell(s, 60)} - {why}" for p, s, why in res.dropped]
        lines += [""]
    if notes_report:
        lines += [notes_report, ""]
    return "\n".join(lines).rstrip() + "\n"


def addition_hash(story: dict, test_cases: list) -> str:
    """What a notes addition was proposed for: the story's text AND its test
    cases. An `ai-update` or `ai-regenerate` that changes the test cases (the
    story unchanged) brings new facts, so it is proposed again; the same
    content never is."""
    cases = sorted(f"{tc.get('key', '')}|{tc.get('summary', '')}|{tc.get('description') or ''}"
                   for tc in test_cases or [])
    return hashlib.sha256((_story_hash(story) + "\n" + "\n".join(cases))
                          .encode("utf-8")).hexdigest()[:12]


def addition_branch(story_key: str, prefix: str, digest: str = "") -> str:
    """`<prefix><key>-notes[-<digest[:8]>]`, lower case: no issue key, so
    merging it moves no card; one branch per content proposed."""
    return branch_for(f"{story_key}-notes" + (f"-{digest[:8]}" if digest else ""), prefix)


def propose_addition_for_story(tracker, host, llm, story_key: str, settings: dict, root: Path,
                               dry_run: bool = False) -> dict:
    """Propose the notes addition for a story whose pull request merged, once."""
    cfg = settings.get("context_update") or {}
    if not cfg.get("enabled", False) or not cfg.get("additions", True):
        return {"story": story_key, "addition": "disabled"}
    story = tracker.get_story(story_key)
    cases = list(tracker.get_linked_test_cases(story_key) or [])
    chash = addition_hash(story, cases)
    branch = addition_branch(story_key, cfg.get("branch_prefix", "context-update/"), chash)
    if any(f"{ADD_MARKER}" in (c or "") and f"(story: {chash})" in (c or "")
           for c in tracker.get_comments(story_key)) or host.branch_exists(branch):
        return {"story": story_key, "addition": "already-proposed"}
    sources = context_sources(root)
    components = story.get("components") or []
    offered, pages = scoped_sources(sources, components, root)
    new_modules = new_module_paths(components, root)
    scenarios = story_scenarios(root, [tc.get("key", "") for tc in cases])
    additions = extract_note_additions(llm, story, story_key, cases, scenarios, offered,
                                       pages, new_modules)
    res = propose_additions(sources, additions, set(offered), new_modules,
                            int(cfg.get("max_addition_chars", 1500)))
    budget = int(cfg.get("module_budget_chars", 8000))
    after = {**{p: t for p, t in sources.items() if p.endswith(".md")}, **res.edits}
    report = notes_report(after, budget)
    touched = set(res.edits)
    report = {"over": [o for o in report["over"] if o[0] in touched],
              "duplicates": [d for d in report["duplicates"] if d[0] in touched or d[2] in touched]}
    body = render_addition_body(story_key, res, render_notes_report(report, budget))
    if dry_run:
        return {"story": story_key, "addition": "dry-run", "body": body,
                "files": sorted(res.edits)}
    if res.empty:
        tracker.add_comment(story_key, f"{ADD_MARKER} No notes addition needed: the notes "
                            "already hold what this story's feature adds."
                            + "".join(f"\nNot applied: {p} - {why}" for p, _s, why in res.dropped)
                            + f"\n(story: {chash})")
        return {"story": story_key, "addition": "none"}
    url = _open_branch_pr(host, branch, res.edits, f"docs(context): notes from {story_key}",
                          f"docs(context): notes for {story_key}'s feature", body)
    if url:
        tracker.add_comment(story_key, f"{ADD_MARKER} Notes addition proposed: {url} - "
                            f"{len(res.added)} addition(s) to the app notes. Review and merge."
                            f"\n(story: {chash})")
    return {"story": story_key, "addition": "proposed" if url else "branch-exists", "url": url}
