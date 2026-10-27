"""Planned inventory entries: tests written before a feature is deployed (F-12).

WHY THIS EXISTS
    The inventory comes from crawling the live application, and Agent 2 may use
    inventory keys only. So a test case for an element - or a page - that is not
    deployed yet could not be automated: the element was not in the inventory,
    and nothing could add it before the crawl saw it (L19, L25).

THE RULE
    A person adds the element from the design - its key and the selector the
    design promises (a test-id, a label, a heading's text) - and declares it
    `planned` on its page. A whole page not deployed yet is declared
    `planned_page: true` with at least one planned element, which is how the
    nightly check later recognises it.

    * Agent 2 may use a planned key like any other; its pull request names the
      planned keys its code uses, so the reviewer knows those tests fail until
      the deployment (agents/agent2_coder.py).
    * Every checker reads a planned key's absence as "not live yet", never as
      drift; the nightly inventory update never removes one.
    * Once the crawl finds it, the nightly inventory update CONFIRMS it (it
      leaves `planned`). A planned page is not touched until one of its planned
      keys is found; then it is crawled and updated like any other page, so
      its other live elements are proposed too.

Pure logic: reading and writing files is in scripts/plan_inventory.py.
Nothing here names an application.
"""
from __future__ import annotations

import ast
import copy
import re

from core.inventory_proposals import refusal_reason

_PAGE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def add_planned_element(inventory: dict, page: str, key: str, selector: str) -> tuple:
    """(new_inventory, refusal) - the element added to `page` and declared
    `planned`, or the input unchanged with the reason it cannot be."""
    reason = refusal_reason(inventory, page, key, selector)
    if reason:
        return inventory, reason
    out = copy.deepcopy(inventory)
    entry = out["pages"][page]
    entry.setdefault("elements", {})[key] = selector
    entry["planned"] = list(entry.get("planned") or []) + [key]
    return out, ""


def _url_taken(inventory: dict, url: str) -> str:
    want = (url or "").rstrip("/") or "/"
    for name, entry in ((inventory or {}).get("pages") or {}).items():
        if ((entry or {}).get("url") or "").rstrip("/") == want and not entry.get("always"):
            return name
    return ""


def add_planned_page(inventory: dict, page: str, url: str, elements: dict,
                     components=()) -> tuple:
    """(new_inventory, refusal) - a page declared `planned_page` with its
    elements, every one `planned`. At least one element is required: finding
    one live is the only evidence the page is deployed (a 404 or a redirect may
    still answer at its url)."""
    if not _PAGE_NAME.match(page or ""):
        return inventory, "page name must be lowercase snake_case"
    if page in ((inventory or {}).get("pages") or {}):
        return inventory, f"page {page!r} already exists - add planned elements to it instead"
    if not (url or "").startswith("/"):
        return inventory, "url must be a path starting with '/'"
    taken = _url_taken(inventory, url)
    if taken:
        return inventory, f"url {url!r} is already page {taken!r}"
    if not elements:
        return inventory, ("a planned page needs at least one element the design names - "
                           "finding it live is what confirms the page is deployed")
    out = copy.deepcopy(inventory)
    out.setdefault("pages", {})[page] = {"url": url, "components": list(components),
                                         "planned_page": True, "elements": {}, "planned": []}
    for key, selector in elements.items():
        out, reason = add_planned_element(out, page, key, selector)
        if reason:
            return inventory, f"{key}: {reason}"
    return out, ""


# ── what Agent 2's code uses ────────────────────────────────────────────

_SEL_CALL = re.compile(r"""\bsel\(\s*["']([A-Za-z0-9_]+)["']""")


def _inventory_pages_of(text: str) -> set:
    """Values of every `INVENTORY_PAGE = "..."` class attribute in a module."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set(re.findall(r"""INVENTORY_PAGE\s*=\s*["']([^"']+)["']""", text))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str) \
                and any(isinstance(t, ast.Name) and t.id == "INVENTORY_PAGE" for t in node.targets):
            found.add(node.value.value)
    return found


def planned_keys_used(files, inventory: dict) -> list:
    """`page.key` for every planned key a generated page object reaches through
    `sel("<key>")` on its own INVENTORY_PAGE. Sorted, distinct."""
    pages = (inventory or {}).get("pages") or {}
    used = set()
    for f in files or ():
        path = getattr(f, "file_path", "") or ""
        text = getattr(f, "content", "") or ""
        if not path.endswith(".py"):
            continue
        keys = set(_SEL_CALL.findall(text))
        for page in _inventory_pages_of(text):
            planned = set((pages.get(page) or {}).get("planned") or [])
            used |= {f"{page}.{k}" for k in keys & planned}
    return sorted(used)


def pr_section(used: list) -> str:
    """The pull-request body section naming the planned keys used; "" if none."""
    if not used:
        return ""
    return ("\n\n---\n## Uses planned elements - not deployed yet\n\n"
            + "\n".join(f"- `{k}`" for k in used)
            + "\n\nThese keys were added to the inventory from the design (`planned`). The "
              "tests that reach them fail until the feature is deployed; the nightly "
              "inventory update confirms each one once it is live. Merge after the "
              "deployment, or expect those tests to be red.\n")


def load_inventory(ctx) -> dict:
    """The whole committed inventory (every page, every declaration), or {}."""
    import json
    try:
        return json.loads(ctx.inventory_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return {}
