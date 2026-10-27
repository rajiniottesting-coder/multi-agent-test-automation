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
  * REPLACE  a stale key's selector when tonight's crawl found exactly the
             element the generator names the same on that page: the element
             is still there, its selector changed. The key, and every page
             object using it, stays valid.
  * REMOVE   a stale key no code refers to (no string literal in the code
             directories names it) and that is not the page's row family.
             Its notes and its entries in multi_match / conditional go too.
  * KEEP     a stale key code still uses: removing it would break a page
             object, and a change story may be asserting it is gone (an
             absence test needs the key). Listed for a person.
  * ADD      live elements no selector covers, named and ranked by the
             generator's own rules (`introspect.uncovered_elements`), checked
             by the same refusal rules as the manual proposals file, at most
             `max_additions_per_page` per page; the rest are listed.
  * HOLD     a page where more than `hold_ratio` of the selectors are stale is
             not changed at all: that is a page that did not render as itself
             (an error page, an outage, a redesign) - a person decides.
  * REPORT   ambiguous selectors, unreachable pages and pages that were not
             measured: listed, never changed.

Nothing is merged here. The pull request is the review, and the normal checks
run on it: Agent 4 runs the suite against the updated inventory, Agent 0 lists
the tests the change touches.

PURE LOGIC apart from `keys_named_in_code`, which reads the code directories.
The repository writes are in `open_or_refresh`, through the RepoHost protocol.
Nothing here names an application, a page or an element.
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

# One source for the defaults: Agent 0's settings (core.impact_settings), whose
# shipped config.yaml block must equal them.
DEFAULTS = _IMPACT_DEFAULTS["inventory_update"]

# Page fields that list element keys. A removed key leaves every one of them.
_KEY_LISTS = ("multi_match", "conditional")


@dataclass
class InventoryUpdate:
    inventory: dict
    added: list = field(default_factory=list)         # {page, element, selector}
    replaced: list = field(default_factory=list)      # {page, element, old, new}
    removed: list = field(default_factory=list)       # {page, element, selector}
    kept_missing: list = field(default_factory=list)  # {page, element, selector, why}
    over_cap: list = field(default_factory=list)      # {page, element, selector}
    refused: list = field(default_factory=list)       # {page, element, selector, refused}
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
                found |= set(re.findall(r"[\"']([A-Za-z0-9_]+)[\"']", text))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    found.add(node.value)
    return found


# ─────────────────────────────────────────────────────────────
# The update
# ─────────────────────────────────────────────────────────────

def _selectors(page: dict) -> dict:
    return {k: v for k, v in (page.get("elements") or {}).items()
            if isinstance(v, str) and not k.startswith("_")}


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


def build_update(drift: dict, inventory: dict, used: set, *,
                 max_additions_per_page: int = 20, hold_ratio: float = 0.5) -> InventoryUpdate:
    """The inventory after tonight's drift report, and what changed (pure).

    `drift` is check_inventory_staleness's JSON report (with --compare for
    additions and replacements); `used` is keys_named_in_code(). The input
    inventory is not modified."""
    out = copy.deepcopy(inventory)
    upd = InventoryUpdate(inventory=out)
    pages = out.get("pages") or {}
    new_by_page = drift.get("new_elements") or {}
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

        new = dict(new_by_page.get(name) or {})
        for m in stale:
            key, old = m["element"], current[m["element"]]
            candidate = new.pop(key, None)
            if candidate and candidate != old and candidate not in _selectors(page).values():
                page["elements"][key] = candidate
                upd.replaced.append({"page": name, "element": key, "old": old, "new": candidate})
            elif key in used:
                upd.kept_missing.append({"page": name, "element": key, "selector": old,
                                         "why": "code still names it"})
            elif page.get("row_family") == key:
                upd.kept_missing.append({"page": name, "element": key, "selector": old,
                                         "why": "the page's row family"})
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
    out += ["| " + " | ".join(_cell(f(r)) for _, f in cols) + " |" for r in rows]
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
                    upd.removed, [el, sel])
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
    lines += _table("Not added - over the per-page limit", upd.over_cap, [el, sel])
    lines += _table("Not added - refused", upd.refused,
                    [el, sel, ("Reason", lambda r: r["refused"])])
    lines += _table("Ambiguous selectors - match several elements", upd.ambiguous,
                    [el, sel, ("Matches", lambda r: r.get("matches", ""))])
    if upd.unreachable:
        lines += [f"**Unreachable pages** (not checked): "
                  f"{', '.join(f'`{p}`' for p in upd.unreachable)}", ""]
    lines += ["_Generated by `scripts.propose_inventory_update` from the nightly drift "
              "report. A fresh check replaces this pull request while nobody has edited "
              "it; once a person commits to the branch, it is left alone._"]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# The pull request (RepoHost)
# ─────────────────────────────────────────────────────────────

def settings(raw: Optional[dict] = None) -> dict:
    """The effective settings (`raw` over DEFAULTS); refuses an issue key in the branch."""
    merged = {**copy.deepcopy(DEFAULTS), **(raw or {})}
    from config import extract_jira_key
    if extract_jira_key(merged["branch"]):
        raise ValueError(f"inventory_update.branch {merged['branch']!r} contains an issue "
                         "key: merging it would close or report on that story")
    return merged


def _open_pr(host, branch: str) -> Optional[dict]:
    return next((p for p in host.list_open_prs(branch) if p.get("head_ref") == branch), None)


def open_or_refresh(host, upd: InventoryUpdate, *, inventory_path: str, original: str,
                    branch: str, checked_at: str = "", today: str = "") -> dict:
    """Open, replace or close the one inventory-update pull request.

    * Open PR untouched since we wrote it, same content tonight -> left as is.
    * Open PR untouched, different content -> superseded: a comment, the
      branch deleted (which closes it), and a fresh PR when there is a change.
    * Open PR a person committed to -> never touched; one comment per new
      finding, so the nightly run does not repeat itself.
    * No change tonight and no open PR -> nothing.
    """
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = dump_like(original, upd.inventory)
    digest = content_hash(text)
    existing = _open_pr(host, branch)

    if existing:
        number = existing["number"]
        body = host.get_pr_metadata(number).get("body") or ""
        recorded = (_RECORDED.search(body) or [None, None])[1]
        try:
            on_branch = host.get_file_content(inventory_path, branch)
        except Exception:                                      # noqa: BLE001
            on_branch = None
        if recorded is None or on_branch is None or content_hash(on_branch) != recorded:
            noted = {m for c in host.get_pr_comments(number) for m in _NOTED.findall(c or "")}
            if upd.changed and digest not in noted:
                host.post_pr_comment(number, (
                    f"{MARKER} kept-edited: {digest}\n\nThe {today} check found inventory "
                    "changes, but this branch was edited by a person, so it is left as it "
                    "is. Merge or close it; the next check proposes again from `main`."))
            return {"status": "kept_edited", "pr": number}
        if recorded == digest:
            return {"status": "unchanged", "pr": number}
        host.post_pr_comment(number, (
            f"Superseded by the {today} check: "
            + ("a fresh pull request replaces this one." if upd.changed
               else "the inventory needs no change now, so this one is closed.")))
        host.delete_branch(branch)          # deleting the head branch closes the PR
    elif host.branch_exists(branch):
        host.delete_branch(branch)          # left over without a PR: start clean

    if not upd.changed:
        return {"status": "closed" if existing else "nothing_to_change"}

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
    return {"status": "opened", "url": url}
