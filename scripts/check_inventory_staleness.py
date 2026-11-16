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

THE NIGHTLY CHECK (X10, 14 Nov 2026). The Inventory Health workflow runs this
once a night and hands its report to Agent 0's drift analysis and the
inventory update - one crawl, where there were two (this one, signed out, and
verify_locators). It reads the application as the tests use it:

  signed in      it signs in at the login page the inventory records (not the
                 root) and stops with exit 2 when that fails - every page would
                 otherwise read as stale. Pages served at the login path are
                 read first, signed out (the only state they render in).
  every page     including `always` pages that have a url (a menu on every
                 page); their keys are read there, never compared.
  rendered       a page whose expected keys never resolve within 15 s did not
                 render: listed apart, never reported as stale.
  invalid        a selector the browser rejects is INVALID, never stale - a
                 stale key is proposed for removal, an invalid one needs fixing.
  ambiguous      each one lists what it matched, and the exact `text="..."`
                 form when that matches exactly one.

verify_locators stays the tool a person runs to SEE a page's selectors.

Exit codes: 2 when the login failed (no report is written); 3 for an unknown
--page; 1 with --fail-on-drift when anything was found (drift, an invalid
selector, a page that did not render), or with --fail-on-breakage when
something would break a test (all but a new element); otherwise 0.

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
from datetime import datetime, timezone
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
    count_on_page, ambiguity_advice, exact_fix, find_login_path, signed_out_pages, INVALID,
)

# How long a page may take to render before it is reported as not rendered.
RENDER_WAIT_MS = 15000
RENDER_POLL_MS = 500


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
                    help="Login username. Defaults to INVENTORY_USER, else the "
                         "single APP_USER_<ROLE> variable set in .env.")
    ap.add_argument("--password",
                    default=crawl_credentials()[1],
                    help="Login password. Defaults to INVENTORY_PASS, else "
                         "APP_PASSWORD from .env.")
    ap.add_argument("--login-url",
                    help="Login page URL/path. Defaults to the login page recorded in "
                         "the inventory, else the app root.")
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
    ap.add_argument("--fail-on-breakage", action="store_true",
                    help="Exit 1 if anything would break a test: a stale, ambiguous, "
                         "invalid or returned selector, a page unreachable or not "
                         "rendered (a new element alone does not). The nightly "
                         "Inventory Health check.")
    ap.add_argument("--page", help="Check only this page key from the inventory.")
    ap.add_argument("--json", help="Also write the full drift report to this path.")
    ap.add_argument("--compare", action="store_true",
                    help="Also report live elements NO inventory selector covers "
                         "(new elements with no test-id). Report only: it never "
                         "affects drift or the exit code.")
    ap.add_argument("--propose", metavar="PATH",
                    help="Write the uncovered elements as an inventory proposals "
                         "file for review (implies --compare). The inventory is "
                         "not changed; apply with scripts.apply_inventory_proposals. "
                         "(The nightly drift job proposes the same additions, and "
                         "removals and replacements, as a pull request: "
                         "scripts.propose_inventory_update.)")
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
    unreachable_reasons: dict[str, dict] = {}   # why each one was not read
    new_by_page: dict[str, dict] = {}   # --compare: {page: {element: selector}}
    new_declared: dict[str, dict] = {}  # --compare: {page: {"multi_match", "conditional", "unstable"}}
    # Pages marked `always` (a global menu, a cookie banner, a footer) are
    # rendered on EVERY page. Their elements are covered wherever they appear,
    # so compare marks their selectors on each page it visits. Without this,
    # every shared-overlay element was reported as uncovered on every page.
    always_selectors = [sel for entry in pages.values() if entry.get("always")
                        for sel in _page_selectors(entry).values()]
    # Every other page's live keys, by owner (G14): an element another page's key
    # already covers - a footer on every page - is reported there, never added
    # again here. A key declared `removed` or `planned` covers nothing live.
    owners = {}
    for pname_, entry_ in pages.items():
        if entry_.get("always"):
            continue
        skip = set(entry_.get("removed") or []) | set(entry_.get("planned") or [])
        for key, sel in _page_selectors(entry_).items():
            if key not in skip:
                owners.setdefault(pname_, {})[sel] = f"{pname_}.{key}"
    planned_pages_waiting: list[str] = []   # planned pages not deployed yet (F-12)
    hrefs: dict[str, list] = {}             # --compare: links on each page (L25)

    if args.page and args.page not in pages:
        print(f"  no page named {args.page!r} in the inventory. "
              f"Available: {', '.join(sorted(pages))}")
        return 3
    not_rendered: list[str] = []
    invalid_by_page: dict[str, list] = {}

    def _path_of(u: str) -> str:
        from urllib.parse import urlparse
        return (urlparse(u).path or "/").rstrip("/") or "/"

    def _measure(page, name: str, entry: dict, state: str = "") -> None:
        """Read one page into per_page (or one of the lists beside it)."""
        always = bool(entry.get("always"))
        url_path, skip = resolve_page_url(entry)
        if always and not (url_path.startswith("/") or url_path.startswith("http")):
            # A shared overlay with no address of its own: its keys are read
            # on the pages that carry it, never on their own.
            return
        if skip:
            # A templated page with no sample cannot be visited. Say so and
            # move on: reporting its selectors as drifted would be a lie.
            print(f"  [{name}] skipped - {skip}")
            return
        if "<" in url_path:  # templated URL (e.g. ?id=<id>) — skip auto-visit
            return
        selectors = _page_selectors(entry)
        url = _abs(base_url, url_path)
        declared = dict(
            declared_conditional=set(entry.get("conditional") or []),
            declared_removed=set(entry.get("removed") or []),
            declared_planned=set(entry.get("planned") or []))
        reach: dict = {}
        counts, live_test_ids, reachable = resolve_selectors(
            page, url, list(selectors.values()), test_attrs, detail=reach
        )

        def _redirected() -> bool:
            # A page that REDIRECTED was not measured - it was measured
            # somewhere else. /login sends an authenticated visitor to /, and
            # every selector unique to the sign-in form then reads as drift.
            # Compare paths only; a query string or trailing slash is not a
            # redirect.
            return _path_of(page.url) != _path_of(url)

        def _planned_waiting() -> bool:
            # Declared from the design (F-12): not deployed yet is expected,
            # not an unreachable page and not drift.
            if entry.get("planned_page"):
                print(f"  [{name}] planned page - not live yet ({url_path})")
                planned_pages_waiting.append(name)
                return True
            return False

        if (not reachable or _redirected()) and _planned_waiting():
            return
        if reachable and _redirected():
            print(f"  [{name}] skipped - requested {url_path} but landed on "
                  f"{_path_of(page.url)}. A page that exists only in the other "
                  f"auth state cannot be checked in this sweep; reporting its "
                  f"selectors as drift would be a false alarm.")
            return
        if not reachable:
            unreachable.append(name)
            unreachable_reasons[name] = reach
            print(f"  [{name}] not read - {reach.get('reason') or 'unreachable'}")
            return
        if not introspect.rendered(selectors, counts, **declared):
            # Read again until it renders (X10): `load` fires before a
            # single-page app paints, so a first reading may be an empty shell.
            waited = 0
            while waited < RENDER_WAIT_MS and not introspect.rendered(
                    selectors, counts, **declared):
                page.wait_for_timeout(RENDER_POLL_MS)
                waited += RENDER_POLL_MS
                counts, live_test_ids = count_on_page(page, list(selectors.values()),
                                                      test_attrs)
            if not introspect.rendered(selectors, counts, **declared):
                if _planned_waiting():
                    return
                print(f"  [{name}] NOT RENDERED - none of its expected keys appeared "
                      f"within {RENDER_WAIT_MS // 1000}s at {page.url}. Not reported "
                      f"as stale: check the application, the login and redirects.")
                not_rendered.append(name)
                return
            if _redirected():
                print(f"  [{name}] skipped - landed on {_path_of(page.url)} once "
                      f"rendered; reporting its selectors as drift would be a false "
                      f"alarm.")
                return
        if args.compare and not always:
            # Marks every node the inventory covers, then reports what the
            # generator would capture that is NOT marked. Read-only in the
            # sense that matters: no element is changed, clicked or saved.
            shared = {sel: owner for other, sels in owners.items() if other != name
                      for sel, owner in sels.items() if sel not in selectors.values()}
            title, descriptors = collect_uncovered(
                page, url,
                list(selectors.values()) + always_selectors, test_attrs,
                shared=shared)
            hrefs[name] = [(d.get("attrs") or {}).get("href") for d in descriptors
                           if (d.get("attrs") or {}).get("href")]
            found = introspect.uncovered_entry(
                url, title, descriptors,
                base_url=base_url, test_attrs=test_attrs)
            new_by_page[name] = found["elements"]
            if (found["multi_match"] or found["conditional"] or found["unstable"]
                    or found["shared"]):
                new_declared[name] = {k: found[k] for k in
                                      ("multi_match", "conditional", "unstable", "shared")}
        diff = introspect.diff_page(
            name, selectors, counts,
            # An `always` page's keys are read where it is shown; the other
            # test-ids there belong to that page, not to it.
            set() if always else live_test_ids, test_attrs,
            # The inventory states which keys are meant to match several
            # elements and which cannot be reached without a click. Passing
            # them through stops the nightly report crying wolf.
            declared_family=set(entry.get("multi_match") or []), **declared)
        # A selector the browser rejects is neither stale nor fine (X10).
        diff["invalid"] = [{"element": n, "selector": sel} for n, sel in selectors.items()
                           if counts.get(sel) == INVALID]
        if diff["invalid"]:
            invalid_by_page[name] = diff["invalid"]
        # What each ambiguous key caught, and its exact text form when that
        # matches one: the nightly report is then enough to fix it.
        for amb in diff.get("ambiguous", []):
            amb.update(ambiguity_advice(page, amb["selector"]))
        # Keys that resolve to one today through a contains-match `text=`
        # selector whose exact form is also one: safe to tighten (a note).
        skip_tighten = declared["declared_removed"] | declared["declared_planned"]
        diff["tighten"] = {}
        for n, sel in selectors.items():
            if counts.get(sel) == 1 and n not in skip_tighten:
                fix = exact_fix(page, sel)
                if fix:
                    diff["tighten"][n] = fix
        # Keys declared removed and measured gone: as expected, and named, so
        # the summary of a healthy night still shows a change story's removal.
        diff["gone"] = [n for n in sorted(declared["declared_removed"])
                        if n in selectors and counts.get(selectors[n]) == 0]
        if state:
            diff["state"] = state
        per_page[name] = diff

    with browser_page(headless=not args.headed) as page:
        checked_first: set = set()
        if not args.no_login:
            # Where to SIGN IN: --login-url, else the login page the inventory
            # records, else the root. Before X10 this was always the root: on
            # an application whose root is a public home page there is no
            # login form there, and the nightly crawl ran signed out.
            known_login = args.login_url or find_login_path(inventory)
            login_url = _abs(base_url, known_login) if known_login else base_url + "/"
            # The login page as a signed-out visitor sees it - the only state
            # it renders in - read before signing in.
            for name, entry in signed_out_pages(inventory, known_login, args.page).items():
                _measure(page, name, entry, state="signed out")
                checked_first.add(name)
            logged_in = do_login(page, login_url, args.username_selector,
                                 args.password_selector, args.submit_selector,
                                 args.username, args.password)
            if logged_in:
                print(f"  signed in at {_path_of(login_url)}.")
            elif not (args.username and args.password):
                print("  no credentials supplied - continuing WITHOUT login. Pages "
                      "behind it are skipped or read as signed out.")
            else:
                # Every page would redirect to the login screen and read as
                # stale - a login problem, not drift. No report is written, so
                # nothing downstream acts on a false one.
                print(f"  LOGIN FAILED at {_path_of(login_url)} (still on the login "
                      f"form). No report written: every selector would read as "
                      f"stale. Check the credentials and the login form's selectors.")
                return 2

        for name, entry in pages.items():
            if name in checked_first or args.page not in (None, name):
                continue
            _measure(page, name, entry)

    report = introspect.summarize_drift(per_page, unreachable, unreachable_reasons)
    report["pages_missing_notes"] = introspect.pages_missing_notes(inventory)
    # When the live application was looked at. A reader of this file later
    # (Agent 0's uncovered-element hint) uses it to refuse a stale report.
    report["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["planned_pages_waiting"] = planned_pages_waiting
    # X10: found, but neither drift nor proposed for removal - a person fixes them.
    report["invalid_selectors"] = sum(len(v) for v in invalid_by_page.values())
    report["pages_not_rendered"] = not_rendered
    report["breaking"] = bool(report["stale_selectors"] or report["ambiguous_selectors"]
                              or report["reappeared_selectors"] or report["unreachable_pages"]
                              or report["invalid_selectors"] or not_rendered)
    if args.page:
        report["only_page"] = args.page
    if args.compare:
        # Informational: deliberately NOT folded into summarize_drift, so an
        # uncovered element can never fail --fail-on-drift.
        report["new_elements"] = {p: els for p, els in new_by_page.items() if els}
        # The generator's declarations about those elements (families, hidden
        # ones, ones with no durable handle). The nightly inventory update adds
        # the declarations with the element - or a hidden element reads as
        # stale the next night and is removed again - and never adds an
        # element with no durable handle.
        report["new_element_declarations"] = new_declared
        # Pages the application links to that the inventory has no entry for.
        report["unlisted_paths"] = introspect.unlisted_paths(hrefs, inventory, base_url)

    # ── human-readable summary ──
    print(f"\nInventory staleness report for {ctx.name} ({base_url})")
    print(f"  pages checked      : {report['pages_checked']}")
    print(f"  stale selectors    : {report['stale_selectors']}")
    print(f"  new untracked tags : {report['new_untracked_data_tests']}")
    print(f"  ambiguous selectors: {report['ambiguous_selectors']}")
    print(f"  removed, but back  : {report['reappeared_selectors']}")
    print(f"  invalid selectors  : {report['invalid_selectors']}")
    gone, not_read = introspect.split_unreachable(report)
    print(f"  unreachable pages  : {report['unreachable_pages'] or 'none'}")
    if report["unreachable_pages"]:
        print(f"    gone (not found) : {gone or 'none'}")
        print(f"    not read just now: {not_read or 'none'} - a timeout, refusal or "
              f"server error; not drift")
    print(f"  pages not rendered : {not_rendered or 'none'}")
    print(f"  planned, now live  : {report['planned_live']}")
    print(f"  planned, waiting   : {report['planned_waiting']} element(s); "
          f"pages: {planned_pages_waiting or 'none'}")
    for pname, diff in per_page.items():
        if (diff["missing"] or diff["new_data_tests"] or diff.get("ambiguous")
                or diff.get("reappeared") or diff.get("invalid")):
            print(f"\n  [{pname}]" + (f" ({diff['state']})" if diff.get("state") else ""))
            for bad in diff.get("invalid", []):
                print(f"    INVALID {bad['element']}: {bad['selector']} -> the browser "
                      f"rejects this selector; fix it (it is not proposed for removal)")
            for m in diff["missing"]:
                print(f"    STALE   {m['element']}: {m['selector']} -> 0 matches on live page")
            for back in diff.get("reappeared", []):
                print(f"    BACK    {back['element']}: {back['selector']} -> declared "
                      f"removed, but {back['matches']} match(es) on the live page")
            for amb in diff.get("ambiguous", []):
                print(f"    AMBIG   {amb['element']}: {amb['selector']} -> "
                      f"{amb['matches']} matches (Playwright strict mode will "
                      f"fail on this)")
                described = amb.get("described") or []
                for i, line in enumerate(described, 1):
                    print(f"              {i}. {line}")
                if described and amb["matches"] > len(described):
                    print(f"              ... and {amb['matches'] - len(described)} more")
                if amb.get("exact_fix"):
                    print(f"              fix: {amb['exact_fix']} matches exactly one "
                          f"(the whole text, exact) - use it for this key")
            for nt in diff["new_data_tests"]:
                print(f"    NEW     test-id '{nt}' present live but not in inventory")
    gone = [f"{pname}.{n}" for pname, diff in per_page.items() for n in diff.get("gone", [])]
    if gone:
        print(f"    GONE    {len(gone)} key(s) gone, as declared removed: {', '.join(gone)}")
    for pname, diff in per_page.items():
        if diff.get("tighten"):
            print(f"    note: [{pname}] resolve today through a contains-match `text=` "
                  f"selector whose exact form is also one - tighten before the site adds "
                  f"similar words (not a failure): "
                  + ", ".join(f"{n} -> {fix}" for n, fix in diff["tighten"].items()))
    for pname, diff in per_page.items():
        for live in diff.get("planned_live", []):
            print(f"    LIVE    {pname}.{live['element']}: planned, now on the page "
                  f"({live['matches']} match(es)) - the inventory update confirms it")
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
        for pname, dec in new_declared.items():
            for ename, row in (dec.get("shared") or {}).items():
                print(f"    SHARED        {pname}.{ename}: already in the inventory as "
                      f"{row['covered_by']}")
        for row in report.get("unlisted_paths") or []:
            print(f"    UNLISTED-PAGE {row['group']} ({row['count']} path(s), e.g. "
                  f"{row['example']}) - linked from {', '.join(row['linked_from'])}")
    if report["pages_missing_notes"]:
        print(f"\n  WARN: pages with no elements_notes (author them): "
              f"{', '.join(report['pages_missing_notes'])}")
    print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Full report written to {args.json}")

    if args.fail_on_breakage and report["breaking"]:
        print("BREAKING DRIFT — failing (--fail-on-breakage): a test reading these "
              "keys or pages would fail.")
        return 1
    if args.fail_on_drift and (report["has_drift"] or report["breaking"]):
        print("DRIFT DETECTED — failing (--fail-on-drift).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())