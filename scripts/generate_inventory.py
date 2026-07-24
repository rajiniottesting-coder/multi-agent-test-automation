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
    python -m scripts.generate_inventory --no-login --urls / \
     --output app_inventory/saucedemo.login.draft.json --headed

    # Crawl the configured app (2 levels), logging in via env credentials:
    python -m scripts.generate_inventory --crawl --max-pages 25 \
      --output app_inventory/generated.draft.json

    #To inspect at deeper level, use --max-depth 3 or more (default: 2)
    python -m scripts.generate_inventory --crawl --max-depth 4 --max-pages 60 \
  --output app_inventory/app.draft.json

    # Specific paths, no login, app that tags elements with data-cy:
    python -m scripts.generate_inventory --urls /,/dashboard --no-login \
      --test-attrs data-cy,data-testid --output draft.json

Requires: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.app_context import AppContext
from inventory_tools import introspect
from inventory_tools.browser import (
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
    ap = argparse.ArgumentParser(description="Generate a draft inventory JSON.")
    ap.add_argument("--urls", help="Comma-separated paths/URLs to visit (skips crawl).")
    ap.add_argument("--crawl", action="store_true", help="BFS-crawl same-origin links.")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--test-attrs",
                    help="Comma-separated test-id attributes to prefer/track "
                         "(default: %s)." % ",".join(introspect.TEST_ID_ATTRS))
    # Login (all optional; auto-detected by input type unless overridden).
    # Credentials: prefer the tool-specific vars, fall back to the same
    # APP_* variables the test suite uses (tests/step_defs/conftest.py),
    # so a repo has ONE credential source rather than two.
    ap.add_argument("--username",
                    default=os.getenv("INVENTORY_USER")
                    or os.getenv("APP_USER_STANDARD"))
    ap.add_argument("--password",
                    default=os.getenv("INVENTORY_PASS")
                    or os.getenv("APP_PASSWORD"))
    ap.add_argument("--login-url", help="Login page URL/path (default: app root).")
    ap.add_argument("--username-selector", default=DEFAULT_USERNAME_SELECTOR)
    ap.add_argument("--password-selector", default=DEFAULT_PASSWORD_SELECTOR)
    ap.add_argument("--submit-selector", default=DEFAULT_SUBMIT_SELECTOR)
    ap.add_argument("--no-login", action="store_true")
    ap.add_argument("--headed", action="store_true", help="Show the browser.")
    ap.add_argument("--output", default="app_inventory/generated.draft.json")
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
            print("  logged in." if did else "  (no login — missing creds/selectors)")

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
            pages[page_name] = introspect.build_page_entry(
                url, title, descriptors, base_url, test_attrs)
            print(f"  captured {page_name}: {len(pages[page_name]['elements'])} elements ({path})")

            if args.crawl and depth < args.max_depth:
                for link in _links_from(descriptors, url, base_url):
                    if introspect.url_to_path(link, base_url) not in seen:
                        queue.append((link, depth + 1))

    inventory = {
        "app_name": ctx.name,
        "base_url": ctx.base_url,
        "description": "AUTO-GENERATED DRAFT — hand-review before committing.",
        "_inventory_conventions": {
            "generated": "Draft produced by scripts/generate_inventory.py (backlog 3.1). "
                         "Tag each page's `components`, add elements_notes/key_methods/errors, "
                         "delete `_selector_strategies`, `_unstable_selectors` and `title_seen` "
                         "after review, and verify every selector before this replaces the real "
                         "inventory.",
            "selectors": "Selectors may be: a css attribute selector ([data-test='x'], #id), "
                         "a Playwright role locator (role=combobox[name='Country']) for custom "
                         "widgets, a text locator (text=Submit), or an iframe-chained selector "
                         "using ' >>> ' (iframe#pay >>> [data-test='card']) meaning "
                         "page.frame_locator('iframe#pay').locator(\"[data-test='card']\"). "
                         "role=/text= locators pierce open shadow DOM automatically.",
            "_unstable_selectors": "If present on a page, these elements had no durable handle "
                         "(only a fragile css fallback). Add a data-test in the app or replace "
                         "with a role/label/text locator before relying on them.",
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