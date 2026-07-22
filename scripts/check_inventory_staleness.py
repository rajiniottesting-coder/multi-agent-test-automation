#!/usr/bin/env python3
"""Check the committed inventory against the live app (backlog 3.1, Part B).

Loads the inventory configured in config.yaml, visits each page, and reports
drift: inventory selectors that no longer resolve (the dangerous kind — they
make generated tests fail as if the test were buggy), live data-test handles not
in the inventory (coverage gaps), and pages that are now unreachable. Also warns
about pages with no `elements_notes` (a machine can't author those, so a gap is
worth surfacing).

Exit code is 1 when drift is found AND --fail-on-drift is passed (for CI gating);
otherwise 0.

Examples:
    INVENTORY_USER=standard_user INVENTORY_PASS=secret_sauce \\
      python -m scripts.check_inventory_staleness

    # As a CI gate:
    ... python -m scripts.check_inventory_staleness --fail-on-drift --json report.json

Requires: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import browser_page, login_if_configured, resolve_selectors


# meta keys that are not element selectors
_NON_ELEMENT_KEYS = {"_selector_strategies"}


def _page_selectors(page: dict) -> dict[str, str]:
    """Return {element_name: selector} for a page, skipping non-selector values."""
    els = page.get("elements") or {}
    return {n: s for n, s in els.items()
            if isinstance(s, str) and n not in _NON_ELEMENT_KEYS}


def main() -> int:
    ap = argparse.ArgumentParser(description="Check inventory vs live app.")
    ap.add_argument("--username", default=os.getenv("INVENTORY_USER"))
    ap.add_argument("--password", default=os.getenv("INVENTORY_PASS"))
    ap.add_argument("--no-login", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--fail-on-drift", action="store_true",
                    help="Exit 1 if any drift is found (for CI gating).")
    ap.add_argument("--json", help="Also write the full drift report to this path.")
    args = ap.parse_args()

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")
    inventory = json.loads(ctx.inventory_path().read_text(encoding="utf-8"))
    pages = inventory.get("pages") or {}
    login_page = pages.get("login")

    per_page: dict[str, dict] = {}
    unreachable: list[str] = []

    with browser_page(headless=not args.headed) as page:
        if not args.no_login:
            login_if_configured(page, base_url, login_page, args.username, args.password)

        for name, entry in pages.items():
            if entry.get("always"):
                # shared overlay (menu) — no standalone URL to visit
                continue
            url_path = entry.get("url") or "/"
            if "<" in url_path:  # templated URL (e.g. ?id=<id>) — skip auto-visit
                continue
            selectors = _page_selectors(entry)
            counts, live_data_tests, reachable = resolve_selectors(
                page, base_url + url_path, list(selectors.values())
            )
            if not reachable:
                unreachable.append(name)
                continue
            per_page[name] = introspect.diff_page(name, selectors, counts, live_data_tests)

    report = introspect.summarize_drift(per_page, unreachable)
    report["pages_missing_notes"] = introspect.pages_missing_notes(inventory)

    # ── human-readable summary ──
    print(f"\nInventory staleness report for {ctx.name} ({base_url})")
    print(f"  pages checked      : {report['pages_checked']}")
    print(f"  stale selectors    : {report['stale_selectors']}")
    print(f"  new untracked tags : {report['new_untracked_data_tests']}")
    print(f"  unreachable pages  : {report['unreachable_pages'] or 'none'}")
    for pname, diff in per_page.items():
        if diff["missing"] or diff["new_data_tests"]:
            print(f"\n  [{pname}]")
            for m in diff["missing"]:
                print(f"    STALE   {m['element']}: {m['selector']} → 0 matches on live page")
            for nt in diff["new_data_tests"]:
                print(f"    NEW     data-test='{nt}' present live but not in inventory")
    if report["pages_missing_notes"]:
        print(f"\n  WARN: pages with no elements_notes (author them): "
              f"{', '.join(report['pages_missing_notes'])}")
    print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Full report written to {args.json}")

    if report["has_drift"] and args.fail_on_drift:
        print("DRIFT DETECTED — failing (--fail-on-drift).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())