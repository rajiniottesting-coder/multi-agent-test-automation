#!/usr/bin/env python3
"""Generate a DRAFT inventory JSON from the live app (backlog 3.1, Part A).

Crawls the app (or a supplied URL list), snapshots each page's interactable /
test-tagged elements, and emits a first-draft inventory in the standard schema.
The draft fills the machine-knowable fields (url, elements, page-object guess)
and leaves human-only fields as visible stubs (`elements_notes`, `key_methods`,
page-level `errors`, `components`). ALWAYS hand-review before committing.

App-agnostic: the app under test comes from config.yaml (base_url); login fields
are auto-detected by input type (override with --username-selector etc.); the
test-id attributes to prefer come from --test-attrs (defaults to the common
conventions: data-test, data-testid, data-cy, ...).

Examples:
    # Login and Logout screens
    python -m scripts.generate_inventory --no-login --urls /  --output app_inventory/<app>.login.draft.json --headed

    # Crawl the configured app (2 levels), logging in via env credentials:
    python -m scripts.generate_inventory --crawl --max-pages 25  --output app_inventory/generated.draft.json

    #To inspect at deeper level, use --max-depth 3 or more (default: 2) #lisiting all pages 
    python -m scripts.generate_inventory --crawl --max-depth 4 --max-pages 60  --output app_inventory/app.draft.json
    python -m scripts.generate_inventory --urls "/path/one,/path/two,/path/three" --output app_inventory/app.draft.json --headed
    python -m scripts.generate_inventory --no-login --urls "/login" `
   --output app_inventory/login.draft.json
 
 python -m scripts.generate_inventory --login-url /login `
   --urls "/,/<listing>,/<cart>,/<record>/1" `
   --output app_inventory/full_auth.draft.json

    # Specific paths, no login, app that tags elements with data-cy:
    python -m scripts.generate_inventory --urls /,/dashboard --no-login  --test-attrs data-cy,data-testid --output draft.json

Requires: pip install playwright && playwright install chromium

Every example above is ONE line on purpose. A trailing backslash is
Unix-shell continuation and is NOT valid in PowerShell (which uses a
backtick), so a wrapped command silently joins its arguments — e.g.
'--urls / --output x.json' becomes '--urls /--output' and argparse
rejects it. Copy each command as a single line.

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.generate_inventory --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so credentials resolve the same way as in smoke_test.py and the
# agents. Without this, INVENTORY_USER / INVENTORY_PASS set in .env are
# invisible here and login silently does nothing.
from dotenv import load_dotenv

load_dotenv()

from core.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import (
    crawl_credentials,
    browser_page, do_login, collect_descriptors,
    DEFAULT_USERNAME_SELECTOR, DEFAULT_PASSWORD_SELECTOR, DEFAULT_SUBMIT_SELECTOR,
)


def _same_origin(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _links_from(descriptors: list[dict], current_url: str, base: str) -> list[str]:
    out = []
    for d in descriptors:
        if d.get("tag") == "a":
            href = (d.get("attrs") or {}).get("href")
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            absolute = urljoin(current_url, href)
            if _same_origin(absolute, base):
                out.append(absolute.split("#")[0])
    return out


def _abs(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    return base_url + (path_or_url if path_or_url.startswith("/") else "/" + path_or_url)



def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a draft inventory JSON.",
        epilog=("examples:\n  login page (logged OUT - you never see it once authenticated)\n    --no-login --urls / --output app_inventory/<app>.login.draft.json --headed\n  everything else, logged in, following links\n    --crawl --urls /dashboard --max-depth 3 --max-pages 40 --headed\n  exact pages only (most reliable - no crawl guesswork)\n    --urls /products,/cart,/checkout --output app_inventory/app.draft.json\n  app that tags elements with something other than data-test\n    --no-login --urls / --test-attrs data-cy,data-qa\n\nwrite each command on ONE line - a trailing backslash is Unix-shell\ncontinuation and is NOT valid in PowerShell, which silently joins the args."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", help="Comma-separated paths/URLs to visit (skips crawl).")
    ap.add_argument("--crawl", action="store_true", help="BFS-crawl same-origin links.")
    ap.add_argument("--max-pages", type=int, default=20,
                    help="Stop after N pages. The usual limiting factor - a crawl hits this long before --max-depth (default 20).")
    ap.add_argument("--max-depth", type=int, default=2,
                    help="How many link-hops from the seed to follow. A CEILING, not a target: the crawl stops early when the link graph runs out (default 2).")
    ap.add_argument("--test-attrs",
                    help="Comma-separated test-id attributes to prefer/track "
                         "(default: %s)." % ",".join(introspect.TEST_ID_ATTRS))
    # Login (all optional; auto-detected by input type unless overridden).
    # Credentials: prefer the tool-specific vars, fall back to the same
    # APP_* variables the test suite uses (tests/step_defs/conftest.py),
    # so a repo has ONE credential source rather than two.
    ap.add_argument("--username",
                    default=crawl_credentials()[0],
                    help="Login username for the crawl. Defaults to INVENTORY_USER, else the "
                         "single APP_USER_<ROLE> in .env / GitHub Secrets.")
    ap.add_argument("--password",
                    default=crawl_credentials()[1],
                    help="Login password. Defaults to INVENTORY_PASS, else "
                         "APP_PASSWORD, from .env / GitHub Secrets.")
    ap.add_argument("--login-url", help="Login page URL/path (default: app root).")
    ap.add_argument("--username-selector", default=None,
                    help="Override auto-detection of the username field (SSO, multi-step forms).")
    ap.add_argument("--password-selector", default=None,
                    help="Override auto-detection of the password field.")
    ap.add_argument("--submit-selector", default=None,
                    help="Override auto-detection of the submit control.")
    ap.add_argument("--no-login", action="store_true",
                    help="Skip login. Required for public sites AND for capturing the login page itself.")
    ap.add_argument("--headed", action="store_true", help="Show the browser.")
    ap.add_argument("--output", default="app_inventory/generated.draft.json",
                    help="Where to write the draft JSON (default app_inventory/generated.draft.json).")
    args = ap.parse_args()

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")
    test_attrs = (tuple(a.strip() for a in args.test_attrs.split(",") if a.strip())
                  if args.test_attrs else introspect.TEST_ID_ATTRS)

    seeds = []
    if args.urls:
        seeds = [_abs(base_url, u.strip()) for u in args.urls.split(",")]
    else:
        seeds = [base_url + "/"]

    pages: dict[str, dict] = {}
    with browser_page(headless=not args.headed) as page:
        if not args.no_login:
            login_url = _abs(base_url, args.login_url) if args.login_url else base_url + "/"
            did = do_login(page, login_url, args.username_selector,
                           args.password_selector, args.submit_selector,
                           args.username, args.password)
            if did:
                print("  logged in.")
            elif not (args.username and args.password):
                print("  (no login — missing creds/selectors)")
            else:
                # Credentials WERE supplied but we still look logged out. Say so
                # loudly: otherwise every page captured below is the login form
                # and the draft looks plausible but is useless.
                print("  WARNING: login appears to have FAILED (still on the "
                      "login page). Check credentials, or pass "
                      "--username-selector/--password-selector/--submit-selector "
                      "if the form is not auto-detected. Re-run with --headed "
                      "to watch it.")

        queue = deque((s, 0) for s in seeds)
        seen: set[str] = set()
        while queue and len(pages) < args.max_pages:
            url, depth = queue.popleft()
            path = introspect.url_to_path(url, base_url)
            if path in seen:
                continue
            seen.add(path)
            try:
                title, descriptors = collect_descriptors(page, url, test_attrs)
            except Exception as e:
                print(f"  ! skip {url}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            page_name = introspect._slug_to_name(
                path.strip("/").split("?")[0].replace(".html", "") or "home"
            )
            entry = introspect.build_page_entry(
                url, title, descriptors, base_url, test_attrs)

            # ── MEASURE, DO NOT PREDICT ─────────────────────────────────
            # Every selector is now tested against the page it was derived
            # from, while that page is still open. Ranking has to GUESS what
            # Playwright will do - what the accessible name resolves to, what
            # the a11y tree contains - and each wrong guess shipped a locator
            # that matched nothing. Guessing produced four separate bug
            # classes; asking the browser produces a fact.
            #
            # A selector that does not resolve here is recorded rather than
            # silently kept, so a human sees it in the draft instead of
            # discovering it in a staleness sweep days later.
            entry = introspect.verify_entry_against_page(page, entry)
            pages[page_name] = entry

            unresolved = entry.get("_unresolved_selectors", {}).get("elements", [])
            note = f", {len(unresolved)} UNRESOLVED" if unresolved else ""
            print(f"  captured {page_name}: {len(entry['elements'])} elements{note} ({path})")

            if args.crawl and depth < args.max_depth:
                for link in _links_from(descriptors, url, base_url):
                    if introspect.url_to_path(link, base_url) not in seen:
                        queue.append((link, depth + 1))

    inventory = {
        "app_name": ctx.name,
        "base_url": ctx.base_url,
        "description": "AUTO-GENERATED DRAFT — hand-review before committing.",
        "_inventory_conventions": {
            "generated":
                "Draft produced by scripts/generate_inventory.py. NOT ready to "
                "commit. Work through the checklist below - the machine filled "
                "what it can measure; everything here is what it cannot know.",
            "review_checklist": {
                "1_WRITE": {
                    "components": "Jira Component name(s) this page serves, e.g. "
                                  "['Products']. Left EMPTY by the crawler. Without "
                                  "it Agent 2 receives the whole inventory for every "
                                  "story instead of just this page.",
                    "elements_notes": "Per-key traps: what breaks, what to do "
                                      "instead. The highest-value field in the file, "
                                      "and the one a crawler can never produce.",
                    "key_methods": "The methods this page object should expose, as "
                                   "business verbs - login_as(email, password), not "
                                   "type_then_click(). OPTIONAL once the page object "
                                   "exists: Agent 2 reads its real signatures from "
                                   "the repo. Write it for a page not yet built.",
                    "errors": "Exact validation message text, if the page has any.",
                    "url + url_sample": "A page crawled at one RECORD's address "
                        "arrives pinned to it, e.g. '/records/1'. Rewrite the url "
                        "as a template - '/records/{record_id}' - and add "
                        "url_sample: '/records/1' so the browser tools still have "
                        "a concrete address to visit. Rename the page too: "
                        "'records_1' should become 'record_detail'.",
                    "always": "Set true on shared chrome (the navigation bar) and "
                        "move its elements there. A crawler cannot tell chrome from "
                        "page content, so every page arrives carrying its own copy "
                        "of the nav - five copies to keep in step, and five page "
                        "objects each with their own click_cart().",
                },
                "2_VERIFY_AND_CORRECT_never_delete": {
                    "elements": "Trim to what tests actually need. A content-heavy "
                                "page can yield 150+ keys where a story uses ten, "
                                "and every one costs prompt tokens on every "
                                "generated file.",
                    "multi_match": "Keys matching SEVERAL elements. ENFORCED at "
                                   "generation time - it is what rejects code that "
                                   "clicks a 68-match family. Measured at crawl "
                                   "time; confirm it, never remove it.",
                    "conditional": "Elements that exist only after an interaction. "
                                   "AUTO-DETECTED for anything hidden at crawl time, "
                                   "but a modal absent from the DOM entirely cannot "
                                   "be detected - add those by hand.",
                    "multi_match_note / conditional_note": "Permanent guidance sent "
                                   "to the LLM, not review artefacts. Keep them.",
                },
                "3_FIX_THEN_DELETE_THE_BLOCK": {
                    "_selectors_to_improve": "Real elements located by a STRUCTURAL "
                        "PATH. They resolve today and break when anything above them "
                        "re-renders. Replace each with an id, name, href or a "
                        "data-test added to the app, remove the key from the list, "
                        "then delete the block when it is empty.",
                    "_families_without_a_shared_handle": "A repeated widget whose "
                        "instances had NO selector in common, so only one was kept. "
                        "Find the shared class in DevTools (usually there is one), "
                        "set it as the family selector and add the key to "
                        "multi_match - or avoid the family entirely by acting on one "
                        "record's own page, where the control is unique.",
                    "_third_party_elements": "Ad and widget embeds. Delete the "
                        "elements AND the block; their text rotates per impression.",
                    "_unresolved_selectors": "Measured ZERO against the live page. "
                        "The element exists - the locator does not work. Fix each.",
                },
                "4_DELETE_OUTRIGHT": [
                    "implementation_status",
                    "title_seen",
                    "any remaining PAGE-LEVEL key beginning with '_'. NOT the "
                    "ones inside elements_notes - `_url`, `_naming`, `_shared` "
                    "there are page-wide notes rather than element names, they "
                    "ARE sent to the agents, and they carry the guidance that "
                    "stops the generator inventing a record id or asserting on "
                    "shared data. Keep those.",
                    "the ' (AUTO-DRAFT — verify)' suffix on page_object_file",
                    "this _inventory_conventions block itself",
                ],
                "5_THEN_MEASURE": "python -m scripts.verify_locators --inventory "
                                  "<file> --only-problems   (add --no-login for "
                                  "sign-in and sign-up pages: with a session they "
                                  "redirect and nothing can be measured)",
            },
            "selectors": "Every selector maps to a first-class Playwright locator, in priority order: [data-test='x'] / #id / [name='x'] (css), role=combobox[name='Country'] (getByRole), label=Email (getByLabel), placeholder=... , alt=Search (getByAltText), title=Close (getByTitle), text=Submit (getByText). XPath is never emitted. An iframe-chained selector uses ' >>> ', e.g. iframe#pay >>> [data-test='card']. label=/alt=/title= need page.get_by_label/get_by_alt_text/get_by_title (they are NOT page.locator() engine syntax); role= and text= work with page.locator() directly.",
            "_unstable_selectors": "If present on a page, these elements had no durable handle "
                         "(only a fragile css fallback). Add a data-test in the app or replace "
                         "with a role/label/text locator before relying on them.",
            "_ambiguous_selectors": "If present, these selectors were produced for MORE THAN ONE element on the page. Playwright locators are strict by default, so each one raises 'strict mode violation: locator resolved to N elements' at runtime. Give each element a distinct handle (add a data-test) or disambiguate with .nth()/.filter() in the page object.",
        },
        "pages": pages,
    }

    out_path = args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    missing_notes = introspect.pages_missing_notes(inventory)
    print(f"\nWrote {out_path}: {len(pages)} pages.")
    if missing_notes:
        print(f"REVIEW: {len(missing_notes)} page(s) have no elements_notes yet "
              f"(expected for a draft): {', '.join(missing_notes)}")
    print("This is a DRAFT. Review every selector and fill the human fields before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())