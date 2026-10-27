#!/usr/bin/env python3
"""Apply reviewed inventory proposals (E1 follow-up).

Reads a proposals file written by `check_inventory_staleness --propose` and adds
the rows marked `"apply": true` to the inventory. Nothing else is changed.

The manual route, for a one-off. Nightly, the Agent 0 drift job proposes
additions (and replacements and removals) as a pull request instead:
scripts/propose_inventory_update.py, same refusal rules.

    python -m scripts.apply_inventory_proposals reports/inventory_proposals.json --dry-run
    python -m scripts.apply_inventory_proposals reports/inventory_proposals.json

Without --yes the script prints what it will add and asks. It never writes
without that confirmation, and it writes the inventory in the same format
promote_draft uses, so the diff in git shows only the added elements.

After applying, verify the new selectors against the live application:

    python -m scripts.check_inventory_staleness --no-login
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import inventory_proposals
from core.app_context import PROJECT_ROOT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply reviewed inventory proposals.")
    ap.add_argument("proposals", help="proposals file from check_inventory_staleness --propose")
    ap.add_argument("--inventory",
                    help="inventory file to change (default: the one the proposals were "
                         "made against, resolved from the project root)")
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("--yes", action="store_true", help="write without asking")
    args = ap.parse_args(argv)

    doc = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
    if doc.get("schema") != inventory_proposals.PROPOSALS_SCHEMA:
        print(f"Unsupported proposals schema {doc.get('schema')!r}; expected "
              f"{inventory_proposals.PROPOSALS_SCHEMA}.")
        return 1

    target = Path(args.inventory) if args.inventory else PROJECT_ROOT / doc["inventory"]
    inventory = json.loads(target.read_text(encoding="utf-8"))
    new_inventory, applied, refused = inventory_proposals.apply_proposals(
        inventory, doc.get("rows") or [])

    selected = sum(1 for r in doc.get("rows") or [] if r.get("apply") is True)
    print(f"Inventory: {target}")
    print(f"  marked to apply : {selected}")
    print(f"  will add        : {len(applied)}")
    for a in applied:
        print(f"    + {a['page']}.{a['element']}: {a['selector']}")
    for r in refused:
        print(f"  refused         : {r['page']}.{r['element']} - {r['refused']}")

    if not applied:
        print("Nothing to add.")
        return 0
    if args.dry_run:
        print("--dry-run: nothing written.")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("Refusing to write without --yes (no terminal to confirm on).")
            return 1
        if input(f"Add {len(applied)} element(s) to {target.name}? [y/N] ").strip().lower() != "y":
            print("Not written.")
            return 0

    target.write_text(json.dumps(new_inventory, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"Wrote {target}. Review the diff, then verify the selectors:")
    print("  python -m scripts.check_inventory_staleness --no-login")
    return 0


if __name__ == "__main__":
    sys.exit(main())
