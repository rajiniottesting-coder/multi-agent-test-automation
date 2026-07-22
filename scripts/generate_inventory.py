#!/usr/bin/env python3
"""Generate a DRAFT inventory JSON from the live app (backlog 3.1, Part A).

Crawls the app (or a supplied URL list), snapshots each page's interactable /
test-tagged elements, and emits a first-draft inventory in the standard schema.
The draft fills the machine-knowable fields (url, elements, page-object guess)
and leaves human-only fields as visible stubs (`elements_notes`, `key_methods`,
page-level `errors`, `components`). ALWAYS hand-review before committing.

Examples:
    # Crawl SauceDemo (2 levels), logging in with standard_user:
    INVENTORY_USER=standard_user INVENTORY_PASS=secret_sauce \\
      python -m scripts.generate_inventory --crawl --max-pages 15 \\
      --output app_inventory/saucedemo.draft.json

    # Only specific paths, no login:
    python -m scripts.generate_inventory --urls /,/inventory.html --no-login \\
      --output draft.json

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
    browser_page, login_if_configured, collect_descriptors,
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a draft inventory JSON.")
    ap.add_argument("--urls", help="Comma-separated paths/URLs to visit (skips crawl).")
    ap.add_argument("--crawl", action="store_true", help="BFS-crawl same-origin links.")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--username", default=os.getenv("INVENTORY_USER"))
    ap.add_argument("--password", default=os.getenv("INVENTORY_PASS"))
    ap.add_argument("--no-login", action="store_true")
    ap.add_argument("--headed", action="store_true", help="Show the browser.")
    ap.add_argument("--output", default="app_inventory/generated.draft.json")
    args = ap.parse_args()

    ctx = AppContext.load()
    base_url = ctx.base_url.rstrip("/")

    # Reuse the committed login page selectors for login, if an inventory exists.
    login_page = None
    try:
        existing = json.loads(ctx.inventory_path().read_text(encoding="utf-8"))
        login_page = (existing.get("pages") or {}).get("login")
    except Exception:
        pass

    seeds = []
    if args.urls:
        for u in args.urls.split(","):
            u = u.strip()
            seeds.append(u if u.startswith("http") else base_url + (u if u.startswith("/") else "/" + u))
    else:
        seeds = [base_url + "/"]

    pages: dict[str, dict] = {}
    with browser_page(headless=not args.headed) as page:
        if not args.no_login:
            login_if_configured(page, base_url, login_page, args.username, args.password)

        queue = deque((s, 0) for s in seeds)
        seen: set[str] = set()
        while queue and len(pages) < args.max_pages:
            url, depth = queue.popleft()
            path = introspect.url_to_path(url, base_url)
            if path in seen:
                continue
            seen.add(path)
            try:
                title, descriptors = collect_descriptors(page, url)
            except Exception as e:
                print(f"  ! skip {url}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            page_name = introspect._slug_to_name(
                path.strip("/").split("?")[0].replace(".html", "") or "home"
            )
            pages[page_name] = introspect.build_page_entry(url, title, descriptors, base_url)
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
                         "delete `_selector_strategies` and `title_seen` after review, and "
                         "verify every selector before this replaces the real inventory.",
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