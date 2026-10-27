"""Add a planned inventory entry from the design, before deployment (F-12).

    python -m scripts.plan_inventory element --page <page> --key <key> --selector "<selector>"
    python -m scripts.plan_inventory page --page <page> --url /<path> \\
        --component "<Component>" --element <key>="<selector>" [--element ...]

`element` adds one element to an existing page and declares it `planned`.
`page` adds a page not deployed yet (`planned_page: true`) with at least one
planned element the design names - finding one live is what confirms the page.

The same refusal rules as every other inventory writer apply (a free
snake_case name, a selector not already used on the page). The file keeps its
own format, so the diff shows only the addition. Commit it in the story's
branch or its own pull request. `--dry-run` prints the result and writes
nothing.

Nothing here names an application: the inventory is read from AppContext.
"""
from __future__ import annotations

import argparse
import json
import sys

from core.app_context import AppContext
from core.inventory_planned import add_planned_element, add_planned_page
from core.inventory_update import dump_like


def _pairs(values) -> dict:
    out = {}
    for item in values or []:
        key, sep, selector = item.partition("=")
        if not sep or not key.strip() or not selector.strip():
            raise SystemExit(f"--element {item!r}: expected <key>=<selector>")
        out[key.strip()] = selector.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="what", required=True)
    el = sub.add_parser("element", help="a planned element on an existing page")
    el.add_argument("--page", required=True)
    el.add_argument("--key", required=True)
    el.add_argument("--selector", required=True)
    pg = sub.add_parser("page", help="a planned page with its planned elements")
    pg.add_argument("--page", required=True)
    pg.add_argument("--url", required=True)
    pg.add_argument("--component", action="append", default=[])
    pg.add_argument("--element", action="append", default=[], metavar="KEY=SELECTOR")
    for p in (el, pg):
        p.add_argument("--dry-run", action="store_true", help="print; write nothing")
    args = ap.parse_args(argv)

    ctx = AppContext.load()
    path = ctx.inventory_path()
    original = path.read_text(encoding="utf-8")
    inventory = json.loads(original)
    if args.what == "element":
        new, refused = add_planned_element(inventory, args.page, args.key, args.selector)
        what = f"{args.page}.{args.key}"
    else:
        new, refused = add_planned_page(inventory, args.page, args.url,
                                        _pairs(args.element), args.component)
        what = f"page {args.page} ({args.url})"
    if refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 1
    text = dump_like(original, new)
    if args.dry_run:
        print(json.dumps(new["pages"][args.page], indent=2, ensure_ascii=False))
        print(f"\n--dry-run: {what} not written.")
        return 0
    path.write_text(text, encoding="utf-8")
    print(f"Added {what} as planned to {ctx.inventory_file}. Agent 2 may use it now; "
          "the nightly inventory update confirms it once it is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
