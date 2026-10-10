#!/usr/bin/env python3
"""Check the committed inventory against the live app (backlog 3.1, Part B).

Loads the inventory configured in config.yaml, visits each page, and reports
drift: inventory selectors that no longer resolve (the dangerous kind — they
make generated tests fail as if the test were buggy), live test-id handles not
in the inventory (coverage gaps), and pages that are now unreachable. Also warns
about pages with no `elements_notes` (a machine can't author those, so a gap is
worth surfacing).

App-agnostic: the app comes from config.yaml; login fields are auto-detected by
input type (override with --username-selector etc.); the test-id attributes come
from --test-attrs (defaults to the common conventions).

Exit code is 1 when drift is found AND --fail-on-drift is passed (for CI gating);
otherwise 0.

Examples:
    python -m scripts.check_inventory_staleness

    # As a CI gate:
    ... python -m scripts.check_inventory_staleness --fail-on-drift --json report.json

Requires: pip install playwright && playwright install chromium

Every example above is ONE line on purpose. A trailing backslash is
Unix-shell continuation and is NOT valid in PowerShell (which uses a
backtick), so a wrapped command silently joins its arguments — e.g.
'--urls / --output x.json' becomes '--urls /--output' and argparse
rejects it. Copy each command as a single line.

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.check_inventory_staleness --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so credentials resolve the same way as in smoke_test.py and the
# agents. Without this, INVENTORY_USER / INVENTORY_PASS set in .env are
# invisible here and login silently does nothing.
from dotenv import load_dotenv

load_dotenv()

from core import inventory_proposals
from core.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import (
    crawl_credentials,
    browser_page, do_login, resolve_selectors, collect_uncovered,
    DEFAULT_USERNAME_SELECTOR, DEFAULT_PASSWORD_SELECTOR, DEFAULT_SUBMIT_SELECTOR, resolve_page_url,
)


# Anything inside `elements` whose key starts with `_` is a note, not a
# selector. Naming one such key was fragile: the crawler has since grown
# several more, and each new one would have been measured as if it were a
# locator.


def _page_selectors(page: dict) -> dict[str, str]:
    """Return {element_name: selector} for a page, skipping non-selector values."""
    els = page.get("elements") or {}
    return {n: s for n, s in els.items()
            if isinstance(s, str) and not n.startswith("_")}


def _abs(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    return base_url + (path_or_url if path_or_url.startswith("/") else "/" + path_or_url)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check inventory vs live app.",
        epilog=("examples:\n  public site                 --no-login\n  login-gated app             (no flag - reads INVENTORY_USER/INVENTORY_PASS from .env)\n  watch the login happen      --headed\n  fail a CI job on drift      --fail-on-drift\n\nread-only: reports STALE (0 matches), AMBIG (>1), NEW test-ids and\nunreachable pages. It never edits the inventory."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test-attrs",
                    help="Comma-separated test-id attributes to track "
                         "(default: %s)." % ",".join(introspect.TEST_ID_ATTRS))
    # Login (all optional; auto-detected by input type unless overridden).
    # Credentials: prefer the tool-specific vars, fall back to the same
    # APP_* variables the test suite uses (tests/step_defs/conftest.py),
    # so a repo has ONE credential source rather than two.
    ap.add_argument("--username",
                    default=crawl_credentials()[0],
                    help="Login username. Defaults to INVENTORY_USER, else "
                         "INVENTORY_USER from .env.")
    ap.add_argument("--password",
                    default=crawl_credentials()[1],
                    help="Login password. Defaults to INVENTORY_PASS, else "
                         "APP_PASSWORD from .env.")
    ap.add_argument("--login-url", help="Login page URL/path (default: app root).")
    ap.add_argument("--username-selector", default=None,
                    help="Override auto-detection of the username field.")
    ap.add_argument("--password-selector", default=None,
                    help="Override auto-detection of the password field.")
    ap.add_argument("--submit-selector", default=None,
                    help="Override auto-detection of the submit control.")
    ap.add_argument("--no-login", action="store_true",
                    help="Skip login. Use for public sites.")
    ap.add_argument("--headed", action="store_true",
                    help="Show the browser window (useful when login is failing).")
    ap.add_argument("--fail-on-drift", action="store_true",
                    help="Exit 1 if any drift is found (for CI gating).")
    ap.add_argument("--json", help="Also write the full drift report to this path.")
    ap.add_argument("--compare", action="store_true",
                    help="Also report live elements NO inventory selector covers "
                         "(new elements with no test-id). Report only: it never "
                         "affects drift or the exit code.")
    ap.add_argument("--propose", metavar="PATH",
                    help="Write the uncovered elements as an inventory proposals "
                         "file for review (implies --compare). The inventory is "
                         "not changed; apply with scripts.apply_inventory_proposals.")
    args = ap.parse_args()
    if args.propose:
        args.compare = True

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")
    inventory = json.loads(ctx.inventory_path().read_text(encoding="utf-8"))
    pages = inventory.get("pages") or {}
    test_attrs = (tuple(a.strip() for a in args.test_attrs.split(",") if a.strip())
                  if args.test_attrs else introspect.TEST_ID_ATTRS)

    per_page: dict[str, dict] = {}
    unreachable: list[str] = []
    new_by_page: dict[str, dict] = {}   # --compare: {page: {element: selector}}
    # Pages marked `always` (a global menu, a cookie banner, a footer) are
    # rendered on EVERY page. Their elements are covered wherever they appear,
    # so compare marks their selectors on each page it visits. Without this,
    # every shared-overlay element was reported as uncovered on every page.
    always_selectors = [sel for entry in pages.values() if entry.get("always")
                        for sel in _page_selectors(entry).values()]

    with browser_page(headless=not args.headed) as page:
        if not args.no_login:
            login_url = _abs(base_url, args.login_url) if args.login_url else base_url + "/"
            do_login(page, login_url, args.username_selector,
                     args.password_selector, args.submit_selector,
                     args.username, args.password)

        for name, entry in pages.items():
            if entry.get("always"):
                # shared overlay (e.g. a global menu) — no standalone URL to visit
                continue
            url_path, skip = resolve_page_url(entry)
            if skip:
                # A templated page with no sample cannot be visited. Say so and
                # move on: reporting its selectors as drifted would be a lie.
                print(f"  [{name}] skipped - {skip}")
                continue
            if "<" in url_path:  # templated URL (e.g. ?id=<id>) — skip auto-visit
                continue
            selectors = _page_selectors(entry)
            counts, live_test_ids, reachable = resolve_selectors(
                page, base_url + url_path, list(selectors.values()), test_attrs
            )
            # A page that REDIRECTED was not measured - it was measured
            # somewhere else. /login sends an authenticated visitor to /, and
            # every selector unique to the sign-in form then reads as drift.
            # Compare paths only; a query string or trailing slash is not a
            # redirect.
            def _path_of(u: str) -> str:
                from urllib.parse import urlparse
                return (urlparse(u).path or "/").rstrip("/") or "/"

            if reachable and _path_of(page.url) != _path_of(base_url + url_path):
                print(f"  [{name}] skipped - requested {url_path} but landed on "
                      f"{_path_of(page.url)}. A page that exists only in the other "
                      f"auth state cannot be checked in this sweep; reporting its "
                      f"selectors as drift would be a false alarm.")
                continue

            if not reachable:
                unreachable.append(name)
                continue
            if args.compare:
                # Marks every node the inventory covers, then reports what the
                # generator would capture that is NOT marked. Read-only in the
                # sense that matters: no element is changed, clicked or saved.
                title, descriptors = collect_uncovered(
                    page, base_url + url_path,
                    list(selectors.values()) + always_selectors, test_attrs)
                new_by_page[name] = introspect.uncovered_elements(
                    base_url + url_path, title, descriptors,
                    base_url=base_url, test_attrs=test_attrs)
            per_page[name] = introspect.diff_page(
                name, selectors, counts, live_test_ids, test_attrs,
                # The inventory states which keys are meant to match several
                # elements and which cannot be reached without a click. Passing
                # them through stops the nightly report crying wolf.
                declared_family=set(entry.get("multi_match") or []),
                declared_conditional=set(entry.get("conditional") or []))

    report = introspect.summarize_drift(per_page, unreachable)
    report["pages_missing_notes"] = introspect.pages_missing_notes(inventory)
    if args.compare:
        # Informational: deliberately NOT folded into summarize_drift, so an
        # uncovered element can never fail --fail-on-drift.
        report["new_elements"] = {p: els for p, els in new_by_page.items() if els}

    # ── human-readable summary ──
    print(f"\nInventory staleness report for {ctx.name} ({base_url})")
    print(f"  pages checked      : {report['pages_checked']}")
    print(f"  stale selectors    : {report['stale_selectors']}")
    print(f"  new untracked tags : {report['new_untracked_data_tests']}")
    print(f"  ambiguous selectors: {report['ambiguous_selectors']}")
    print(f"  unreachable pages  : {report['unreachable_pages'] or 'none'}")
    for pname, diff in per_page.items():
        if diff["missing"] or diff["new_data_tests"] or diff.get("ambiguous"):
            print(f"\n  [{pname}]")
            for m in diff["missing"]:
                print(f"    STALE   {m['element']}: {m['selector']} -> 0 matches on live page")
            for amb in diff.get("ambiguous", []):
                print(f"    AMBIG   {amb['element']}: {amb['selector']} -> "
                      f"{amb['matches']} matches (Playwright strict mode will "
                      f"fail on this)")
            for nt in diff["new_data_tests"]:
                print(f"    NEW     test-id '{nt}' present live but not in inventory")
    if args.propose:
        proposals = inventory_proposals.build_proposals(
            {p: els for p, els in new_by_page.items() if els}, inventory,
            inventory_path=ctx.inventory_file, base_url=base_url)
        Path(args.propose).parent.mkdir(parents=True, exist_ok=True)
        Path(args.propose).write_text(
            json.dumps(proposals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Proposals written to {args.propose} "
              f"({len(proposals['rows'])} row(s)). The inventory is unchanged.")

    if args.compare:
        new_total = sum(len(els) for els in new_by_page.values())
        print(f"  uncovered elements : {new_total} (no selector in the inventory)")
        for pname, els in new_by_page.items():
            if els:
                print(f"\n  [{pname}] uncovered")
                for ename, sel in els.items():
                    print(f"    NEW-ELEMENT   {ename}: {sel}")
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