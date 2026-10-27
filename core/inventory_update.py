"""Inventory update: turn the nightly drift report into one reviewed pull request.

WHY THIS EXISTS
---------------
Every agent writes and checks tests against the page inventory, but nothing in
the pipeline ever wrote the inventory back. The nightly drift job
(`check_inventory_staleness --compare`) already measures what is wrong:

  * selectors that resolve to nothing on the live page (STALE),
  * live elements no selector covers (a new field, a new button),
  * selectors matching several elements (AMBIGUOUS), pages that did not load.

Until now that report only reached a person as a Jira maintenance story and a
job summary; fixing the inventory meant running scripts by hand. So a new
feature's elements never reached the inventory (and Agent 2, which may use
inventory keys only, left those test cases out), and dead selectors stayed for
ever.

WHAT IT CHANGES (each rule errs toward leaving the inventory alone)
------------------------------------------------------------------
  * REPLACE  a stale key's selector when tonight's crawl found the element the
             generator names the same on that page, with a durable selector:
             the element is still there, its selector changed. The key, and
             every page object using it, stays valid.
  * REMOVE   a stale key no code names - no string literal in the code
             directories on `main`, and none added by an open pull request -
             that is not the page's row family. Its notes and its entries in
             multi_match / conditional go too. When the open pull requests
             could not be read, nothing is removed.
  * KEEP     a stale key code still names: removing it would break a page
             object, and a change story may be asserting it is gone (an
             absence test needs the key). Listed for a person.
  * ADD      live elements no selector covers, named and ranked by the
             generator's own rules (`introspect.uncovered_entry`), WITH the
             generator's declarations (a family -> multi_match, a hidden
             element -> conditional), checked by the same refusal rules as
             the manual proposals file, at most `max_additions_per_page` per
             page. Elements the generator flags for review (no durable
             handle: a css fallback, an index-pinned `>> nth=` member, an
             element hidden when crawled) are listed, never added.
  * HOLD     a page where more than `hold_ratio` of the selectors are stale is
             not changed at all: that is a page that did not render as itself
             (an error page, an outage, a redesign) - a person decides.
  * REPORT   ambiguous selectors, unreachable pages and untracked test-ids:
             listed, never changed.

Nothing is merged here. The pull request is the review, and the normal checks
run on it: Agent 4 runs the suite against the updated inventory, Agent 0 lists
the tests the change touches.

ONE PROPOSAL AT A TIME
----------------------
Each proposal gets its own branch (`<branch_prefix><date>`), so a new one
never needs an old branch deleted - a repository may forbid deletion. An
older untouched proposal is closed (`RepoHost.close_pull_request`) and its
branch deleted best-effort; a proposal a person committed to is never
touched.

Pure logic apart from `keys_named_in_code` (reads the code directories) and
the RepoHost calls in `keys_named_in_open_prs` and `open_or_refresh`. Nothing
here names an application, a page or an element.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.impact_settings import DEFAULTS as _IMPACT_DEFAULTS
from core.inventory_proposals import refusal_reason

logger = logging.getLogger(__name__)

MARKER = "[inventory-update]"
_RECORDED = re.compile(re.escape(MARKER) + r" content: ([0-9a-f]{12})")
_NOTED = re.compile(re.escape(MARKER) + r" kept-edited: ([0-9a-f]{12})")
_QUOTED = re.compile(r"[\"']([A-Za-z0-9_]+)[\"']")

# One source for the defaults: Agent 0's settings (core.impact_settings), whose
# shipped config.yaml block must equal them.
DEFAULTS = _IMPACT_DEFAULTS["inventory_update"]

# Page fields that list element keys. A removed key leaves every one of them.
_KEY_LISTS = ("multi_match", "conditional")

# GitHub refuses a pull request body over 65,536 characters; each table is
# capped well below it and the rest counted.
_MAX_ROWS = 60
_MAX_BODY = 60_000


@dataclass
class InventoryUpdate:
    inventory: dict
    added: list = field(default_factory=list)         # {page, element, selector}
    replaced: list = field(default_factory=list)      # {page, element, old, new}
    removed: list = field(default_factory=list)       # {page, element, selector}
    kept_missing: list = field(default_factory=list)  # {page, element, selector, why}
    over_cap: list = field(default_factory=list)      # {page, element, selector}
    refused: list = field(default_factory=list)       # {page, element, selector, refused}
    fragile: list = field(default_factory=list)       # {page, element, selector}
    held_pages: list = field(default_factory=list)    # {page, stale, total}
    ambiguous: list = field(default_factory=list)     # {page, element, selector, matches}
    unreachable: list = field(default_factory=list)   # [page]
    new_test_ids: list = field(default_factory=list)  # {page, value}

    @property
    def changed(self) -> bool:
        return bool(self.added or self.replaced or self.removed)


# ─────────────────────────────────────────────────────────────
# Which keys the code still names
# ─────────────────────────────────────────────────────────────

def keys_named_in_code(root: Path, code_dirs=("pages", "tests")) -> set:
    """Every string literal in the Python files under `code_dirs`.

    Deliberately wider than "keys passed to self.sel()": a key reached through
    a helper, a constant or a step definition is a string literal somewhere, and
    an over-wide set only means a stale key is KEPT, never wrongly removed. A
    file that cannot be parsed is read as plain text: every quoted token in it
    counts, for the same reason."""
    found: set = set()
    root = Path(root)
    for d in code_dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                found |= set(_QUOTED.findall(text))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    found.add(node.value)
    return found


def keys_in_patches(files: list, code_dirs=("pages", "tests")) -> set:
    """Quoted tokens on the ADDED lines of a pull request's Python files under
    `code_dirs` (RepoHost.get_pr_changed_files shape: filename, patch)."""
    found: set = set()
    prefixes = tuple(f"{d.rstrip('/')}/" for d in code_dirs)
    for f in files or []:
        name = (f.get("filename") or "").replace("\\", "/")
        if not (name.endswith(".py") and name.startswith(prefixes)):
            continue
        for line in (f.get("patch") or "").splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                found |= set(_QUOTED.findall(line))
    return found


def keys_named_in_open_prs(host, code_dirs=("pages", "tests"),
                           own_prefix: str = "") -> Optional[set]:
    """Keys named by code an open pull request adds - code not on `main` yet.

    A story pull request in flight may add a page object method using a key
    that is stale tonight; removing the key would break that story after both
    merge. Returns None when the open pull requests cannot be read, which the
    caller must take as "remove nothing"."""
    found: set = set()
    try:
        for pr in host.list_open_prs(strict=True):
            if own_prefix and (pr.get("head_ref") or "").startswith(own_prefix):
                continue
            found |= keys_in_patches(host.get_pr_changed_files(pr["number"]), code_dirs)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("open pull requests could not be read: %s", e)
        return None
    return found


# ─────────────────────────────────────────────────────────────
# The report's freshness
# ─────────────────────────────────────────────────────────────

def report_age_problem(drift: dict, max_hours: float, now: Optional[datetime] = None) -> str:
    """Why a drift report is too old (or undated) to act on, or ''."""
    stamp = drift.get("checked_at") or ""
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return "the report carries no checked_at time"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    hours = ((now or datetime.now(timezone.utc)) - when).total_seconds() / 3600
    if hours > max_hours:
        return f"the report is {hours:.0f} h old (limit {max_hours:g} h)"
    return ""


# ─────────────────────────────────────────────────────────────
# The update
# ─────────────────────────────────────────────────────────────

def _selectors(page: dict) -> dict:
    return {k: v for k, v in (page.get("elements") or {}).items()
            if isinstance(v, str) and not k.startswith("_")}


def _row_families(page: dict) -> set:
    value = page.get("row_family")
    if isinstance(value, str):
        return {value}
    return {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()


def _drop_key(page: dict, key: str) -> None:
    """Remove `key` and every reference to it from one inventory page."""
    (page.get("elements") or {}).pop(key, None)
    notes = page.get("elements_notes")
    if isinstance(notes, dict):
        notes.pop(key, None)
    for name in _KEY_LISTS:
        values = page.get(name)
        if isinstance(values, list) and key in values:
            page[name] = [v for v in values if v != key]


def _declare(page: dict, key: str, declared: dict) -> None:
    """Carry the generator's declarations for `key` onto the page."""
    for name in _KEY_LISTS:
        if key in (declared.get(name) or []):
            values = page.get(name)
            values = list(values) if isinstance(values, list) else []
            if key not in values:
                values.append(key)
            page[name] = values


def build_update(drift: dict, inventory: dict, used: set, *,
                 max_additions_per_page: int = 20, hold_ratio: float = 0.5,
                 allow_removal: bool = True,
                 no_removal_reason: str = "") -> InventoryUpdate:
    """The inventory after tonight's drift report, and what changed (pure).

    `drift` is check_inventory_staleness's JSON report (with --compare for
    additions and replacements); `used` is every key code names (main and the
    open pull requests). `allow_removal=False` keeps every stale key, with
    `no_removal_reason`. The input inventory is not modified."""
    out = copy.deepcopy(inventory)
    upd = InventoryUpdate(inventory=out)
    pages = out.get("pages") or {}
    new_by_page = drift.get("new_elements") or {}
    declared_by_page = drift.get("new_element_declarations") or {}
    upd.unreachable = list(drift.get("unreachable_pages") or [])

    for name in sorted(drift.get("pages") or {}):
        diff = drift["pages"][name] or {}
        page = pages.get(name)
        if not isinstance(page, dict):
            continue
        current = _selectors(page)
        stale = [m for m in diff.get("missing") or []
                 if isinstance(m, dict) and m.get("element") in current]
        upd.ambiguous += [{"page": name, **a} for a in diff.get("ambiguous") or []]
        upd.new_test_ids += [{"page": name, "value": v} for v in diff.get("new_data_tests") or []]

        if current and len(stale) > 1 and len(stale) / len(current) > hold_ratio:
            upd.held_pages.append({"page": name, "stale": len(stale), "total": len(current)})
            continue

        declared = declared_by_page.get(name) or {}
        unstable = set(declared.get("unstable") or [])
        new = dict(new_by_page.get(name) or {})
        for element in sorted(set(new) & unstable):
            upd.fragile.append({"page": name, "element": element, "selector": new.pop(element)})

        for m in stale:
            key, old = m["element"], current[m["element"]]
            candidate = new.pop(key, None)
            if candidate and candidate in _selectors(page).values():
                upd.refused.append({"page": name, "element": key, "selector": candidate,
                                    "refused": "replacement selector already used by "
                                               "another element on the page"})
                candidate = None
            if candidate and candidate != old:
                page["elements"][key] = candidate
                _declare(page, key, declared)
                upd.replaced.append({"page": name, "element": key, "old": old, "new": candidate})
            elif key in used:
                upd.kept_missing.append({"page": name, "element": key, "selector": old,
                                         "why": "code still names it"})
            elif key in _row_families(page):
                upd.kept_missing.append({"page": name, "element": key, "selector": old,
                                         "why": "the page's row family"})
            elif not allow_removal:
                upd.kept_missing.append({"page": name, "element": key, "selector": old,
                                         "why": no_removal_reason or "removal is off"})
            else:
                _drop_key(page, key)
                upd.removed.append({"page": name, "element": key, "selector": old})

        added_here = 0
        for element, selector in sorted(new.items()):
            reason = refusal_reason(out, name, element, selector)
            row = {"page": name, "element": element, "selector": selector}
            if reason:
                upd.refused.append({**row, "refused": reason})
            elif added_here >= max_additions_per_page:
                upd.over_cap.append(row)
            else:
                page.setdefault("elements", {})[element] = selector
                _declare(page, element, declared)
                upd.added.append(row)
                added_here += 1
    return upd


# ─────────────────────────────────────────────────────────────
# Text, hash, pull request body
# ─────────────────────────────────────────────────────────────

def dump_like(original: str, inventory: dict) -> str:
    """The inventory as JSON in the committed file's own format (indent 2,
    non-ASCII kept, the same final newline or none), so the diff shows only
    what changed."""
    text = json.dumps(inventory, indent=2, ensure_ascii=False)
    return text + "\n" if original.endswith("\n") else text


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _cell(text, limit: int = 90) -> str:
    text = str(text).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _table(title: str, rows: list, cols: list, note: str = "") -> list:
    if not rows:
        return []
    out = [f"### {title} ({len(rows)})", ""]
    if note:
        out += [note, ""]
    out += ["| " + " | ".join(c for c, _ in cols) + " |",
            "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(_cell(f(r)) for _, f in cols) + " |" for r in rows[:_MAX_ROWS]]
    if len(rows) > _MAX_ROWS:
        out.append(f"\n… and {len(rows) - _MAX_ROWS} more (see the drift report artifact).")
    return out + [""]


def render_body(upd: InventoryUpdate, inventory_path: str, digest: str,
                checked_at: str = "") -> str:
    el = ("Element", lambda r: f"`{r['page']}.{r['element']}`")
    sel = ("Selector", lambda r: f"`{r['selector']}`")
    lines = [
        f"{MARKER} content: {digest}",
        "",
        "## 🤖 Inventory update from the nightly check",
        "",
        f"The nightly crawl{f' ({checked_at})' if checked_at else ''} compared "
        f"`{inventory_path}` with the live application. This pull request applies "
        "what can be applied safely; the rest is listed for a person.",
        "",
        "**Before merging:** check each added name and selector (rename a key in this "
        "branch if a better name exists), and look at Agent 4's run on this PR - it "
        "runs the suite against the updated inventory. Merge when the application is "
        "deployed as crawled. Nothing is merged by an agent.",
        "",
    ]
    lines += _table("Selectors replaced - the element is still there, its selector changed",
                    upd.replaced, [el, ("Old", lambda r: f"`{r['old']}`"),
                                   ("New", lambda r: f"`{r['new']}`")])
    lines += _table("Added - live elements no selector covered", upd.added, [el, sel])
    lines += _table("Removed - no longer on the page, and no code names them",
                    upd.removed, [el, sel],
                    "Check each is really gone. An element shown only after a click, or "
                    "only in the other sign-in state, should be declared `conditional` "
                    "instead: restore it in this branch and add it to the page's "
                    "`conditional` list.")
    lines += _table("Kept although not found - a person decides", upd.kept_missing,
                    [el, sel, ("Why kept", lambda r: r["why"])],
                    "Each is missing on the live page. If the feature was removed on "
                    "purpose, a change story's absence test may need the key; otherwise "
                    "the page object needs a new selector.")
    lines += _table("Pages not changed - most selectors did not resolve", upd.held_pages,
                    [("Page", lambda r: f"`{r['page']}`"),
                     ("Stale", lambda r: f"{r['stale']} of {r['total']}")],
                    "A page that did not render as itself (error page, outage, redesign) "
                    "is never edited automatically.")
    lines += _table("Not added - no durable selector", upd.fragile, [el, sel],
                    "The generator flagged each for review: only a fragile handle (a css "
                    "fallback), one member of a repeated widget pinned by `>> nth=`, or "
                    "an element hidden when crawled. Add a test-id in the application, "
                    "declare a family, or write the entry by hand.")
    lines += _table("Not added - over the per-page limit", upd.over_cap, [el, sel])
    lines += _table("Not applied - refused", upd.refused,
                    [el, sel, ("Reason", lambda r: r["refused"])])
    lines += _table("Ambiguous selectors - match several elements", upd.ambiguous,
                    [el, sel, ("Matches", lambda r: r.get("matches", ""))])
    if upd.unreachable:
        lines += [f"**Unreachable pages** (not checked): "
                  f"{', '.join(f'`{p}`' for p in upd.unreachable)}", ""]
    lines += ["_Generated by `scripts.propose_inventory_update` from the nightly drift "
              "report. A newer check closes this pull request while nobody has edited "
              "it; once a person commits to the branch, it is left alone._"]
    body = "\n".join(lines)
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY] + "\n\n… (truncated: the drift report artifact has the rest)"
    return body


# ─────────────────────────────────────────────────────────────
# The pull request (RepoHost)
# ─────────────────────────────────────────────────────────────

def settings(raw: Optional[dict] = None) -> dict:
    """The effective settings (`raw` over DEFAULTS); refuses an issue key in the prefix."""
    merged = {**copy.deepcopy(DEFAULTS), **(raw or {})}
    from config import extract_jira_key
    if extract_jira_key(merged["branch_prefix"]):
        raise ValueError(f"inventory_update.branch_prefix {merged['branch_prefix']!r} "
                         "contains an issue key: merging it would close or report on that "
                         "story")
    return merged


def _unused_branch(host, prefix: str, today: str) -> str:
    branch, n = f"{prefix}{today}", 1
    while host.branch_exists(branch):
        n += 1
        branch = f"{prefix}{today}-{n}"
    return branch


def _retire(host, pr: dict, reason: str) -> None:
    """Close a superseded proposal; its branch is deleted best-effort (a
    repository may forbid deletion - the next proposal uses a new branch)."""
    host.post_pr_comment(pr["number"], reason)
    host.close_pull_request(pr["number"])
    try:
        host.delete_branch(pr["head_ref"])
    except Exception as e:                                         # noqa: BLE001
        logger.warning("branch %s not deleted: %s", pr["head_ref"], e)


def open_or_refresh(host, upd: InventoryUpdate, *, inventory_path: str, original: str,
                    prefix: str, checked_at: str = "", today: str = "") -> dict:
    """Keep at most one inventory-update pull request, and only a current one.

    * An open proposal a person committed to (or one without our marker) ->
      never touched; one comment per new finding, no second proposal.
    * An untouched proposal with tonight's content -> left as it is.
    * An untouched proposal with other content -> closed with a comment; a
      fresh proposal on a new branch when there is a change.
    * No change and no proposal -> nothing.
    """
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = dump_like(original, upd.inventory)
    digest = content_hash(text)
    ours = [p for p in host.list_open_prs(prefix, strict=True)
            if (p.get("head_ref") or "").startswith(prefix)]

    edited, same, stale = [], [], []
    for pr in ours:
        body = host.get_pr_metadata(pr["number"]).get("body") or ""
        match = _RECORDED.search(body)
        try:
            on_branch = host.get_file_content(inventory_path, pr["head_ref"])
        except Exception:                                      # noqa: BLE001
            on_branch = None
        if match is None or on_branch is None or content_hash(on_branch) != match.group(1):
            edited.append(pr)
        elif match.group(1) == digest:
            same.append(pr)
        else:
            stale.append(pr)

    if edited:
        for pr in edited:
            noted = {m for c in host.get_pr_comments(pr["number"]) for m in _NOTED.findall(c or "")}
            if upd.changed and digest not in noted:
                host.post_pr_comment(pr["number"], (
                    f"{MARKER} kept-edited: {digest}\n\nThe {today} check found inventory "
                    "changes, but this branch was edited by a person, so it is left as it "
                    "is and no second proposal is opened. Merge or close it; the next "
                    "check proposes again from `main`."))
        return {"status": "kept_edited", "prs": [p["number"] for p in edited]}

    for pr in stale + same[1:]:
        _retire(host, pr, f"Superseded by the {today} check: " + (
            "a fresh pull request replaces this one." if upd.changed and not same
            else "the inventory needs no change now." if not upd.changed
            else "an identical proposal is already open."))
    if same:
        return {"status": "unchanged", "pr": same[0]["number"]}
    if not upd.changed:
        return {"status": "closed" if stale else "nothing_to_change"}

    branch = _unused_branch(host, prefix, today)
    host.create_branch(branch, "main")
    try:
        host.create_or_update_file(inventory_path, text,
                                   f"chore(inventory): nightly update ({today})", branch)
        url = host.open_pull_request(
            f"chore(inventory): nightly inventory update ({today})",
            render_body(upd, inventory_path, digest, checked_at), branch, "main")
    except Exception:
        host.delete_branch(branch)          # never leave a half-written branch
        raise
    return {"status": "opened", "url": url, "branch": branch}
