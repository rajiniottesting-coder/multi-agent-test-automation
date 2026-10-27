"""Inventory proposals: turn `--compare` findings into reviewable additions.

WHY THIS EXISTS
---------------
`check_inventory_staleness --compare` reports live elements no inventory
selector covers. A new field with no selector means the generator cannot write
a test for it, and Agent 0 has nothing to link it to. The fix is to add the
element to the inventory, and that is a human decision: a name and a selector
are a claim about the application.

So this module follows the marker backfill's pattern. Nothing is written until
a person has marked a row for application:

    1. propose   writes a proposals file. The inventory is not touched.
    2. review    the person sets "apply": true on the rows they accept, and
                 may rename "element" where the generated name is poor.
    3. apply     adds only rows marked "apply": true, and only where the page
                 exists and the name is free. Everything else is refused, with
                 the reason recorded.

PURE LOGIC ONLY. Reading and writing files is in scripts/.
"""
from __future__ import annotations

import copy
import re
from typing import Any

PROPOSALS_SCHEMA = 1

# Element names are the inventory's keys. Keep them lowercase snake_case and
# never start with "_": that prefix is reserved for notes (see _page_selectors).
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _page_elements(inventory: dict, page: str) -> dict:
    return ((inventory.get("pages") or {}).get(page) or {}).get("elements") or {}


def _refusal(inventory: dict, page: str, element: str, selector: str) -> str:
    """Why a proposed element cannot be added, or '' when it can."""
    if not (inventory.get("pages") or {}).get(page):
        return "page is not in the inventory"
    if not _NAME_RE.match(element or ""):
        return "element name must be lowercase snake_case and not start with '_'"
    if not isinstance(selector, str) or not selector.strip():
        return "selector is empty"
    existing = _page_elements(inventory, page)
    if element in existing:
        return f"name {element!r} already exists on this page"
    if selector in existing.values():
        return "this selector is already used by another element on the page"
    return ""


def refusal_reason(inventory: dict, page: str, element: str, selector: str) -> str:
    """Why `element` / `selector` cannot be added to `page`, or '' when it can.

    The one rule set for every writer of new elements: the reviewed proposals
    file (apply_proposals) and the nightly inventory update
    (core.inventory_update)."""
    return _refusal(inventory, page, element, selector)


def build_proposals(new_by_page: dict[str, dict[str, str]], inventory: dict,
                    *, inventory_path: str, base_url: str = "") -> dict[str, Any]:
    """The proposals document for `new_by_page` ({page: {element: selector}}).

    Rows that cannot be applied carry a `refused` reason from the start, so the
    reviewer sees the conflict rather than discovering it at apply time.
    Every row starts with `"apply": false`.
    """
    rows = []
    for page in sorted(new_by_page):
        for element, selector in sorted(new_by_page[page].items()):
            rows.append({
                "page": page,
                "element": element,
                "selector": selector,
                "apply": False,
                "refused": _refusal(inventory, page, element, selector),
            })
    return {
        "schema": PROPOSALS_SCHEMA,
        "inventory": inventory_path,
        "base_url": base_url,
        "rows": rows,
    }


def apply_proposals(inventory: dict, rows: list[dict]
                    ) -> tuple[dict, list[dict], list[dict]]:
    """Return (new_inventory, applied, refused). The input is not modified.

    Only rows with "apply": true are considered. Each is checked again against
    the inventory as it stands now - a row proposed last week may conflict with
    something added since - so a stale proposal cannot overwrite a name.
    """
    out = copy.deepcopy(inventory)
    applied, refused = [], []
    for row in rows:
        if row.get("apply") is not True:
            continue
        page = row.get("page", "")
        element = row.get("element", "")
        selector = row.get("selector", "")
        # Judged against the inventory as it is now, not the note written at
        # propose time: the note may be stale.
        reason = _refusal(out, page, element, selector)
        if reason:
            refused.append({**row, "refused": reason})
            continue
        out["pages"][page].setdefault("elements", {})[element] = selector
        applied.append({"page": page, "element": element, "selector": selector})
    return out, applied, refused
