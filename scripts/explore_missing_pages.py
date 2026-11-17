#!/usr/bin/env python3
"""Explore the pages refused stories need, and propose each one (PW1).

    python -m scripts.explore_missing_pages [--requests reports/explore_requests.json] [--dry-run]

Run by Agent 2's workflow right after Agent 2, when Agent 2 refused a story for
a page the inventory lacks and recorded a request (core.blocked ->
core.page_explore.record_request). For each request: find the link that opens
the page, read the page live with the nightly check, and open one pull request
adding it - core/page_explore.py says what is proposed and what is left alone.

--dry-run prints what would be proposed and writes nothing (no pull request,
no comment). Settings: `live_browser` in config.yaml.

Exit code 0 whatever was found - the outcome is on the story; 1 only when the
tracker or the repository host cannot be used.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from core import inventory_update as iu
from core import page_explore as pe
from core.app_context import PROJECT_ROOT, AppContext

logger = logging.getLogger("explore_missing_pages")

AGENT_NAME = "Agent 2 (Coder, page exploration)"
_LINKS_JS = ("els => els.map(e => ({href: e.getAttribute('href') || '', "
             "text: (e.innerText || e.getAttribute('aria-label') || e.title || '').trim()}))")


def collect_links(inventory: dict, base_url: str, max_pages: int) -> tuple:
    """({inventory page: [{"href", "text"}]}, problem) read live, signed in as
    the nightly check signs in. problem is "" on success."""
    from inventory_tools.browser import (_goto_spa_tolerant, browser_page, crawl_credentials,
                                         do_login, find_login_path, resolve_page_url)
    found: dict = {}
    pages = (inventory.get("pages") or {})
    targets = [("(root)", "/")]
    for name, entry in pages.items():
        path, skip = resolve_page_url(entry)
        if not skip and path.startswith("/") and (name, path) not in targets:
            targets.append((name, path))
    with browser_page() as page:
        login = find_login_path(inventory)
        user, password = crawl_credentials()
        if login and user and password:
            if not do_login(page, base_url + login, None, None, None, user, password):
                return {}, f"sign-in at {login} failed"
        for name, path in targets[:max_pages]:
            try:
                _goto_spa_tolerant(page, base_url + path)
                found[name] = page.eval_on_selector_all("a[href]", _LINKS_JS)
            except Exception as e:                                 # noqa: BLE001
                logger.warning("links of %s not read: %s", name, e)
    return found, ""


def read_page(stub: dict, name: str) -> tuple:
    """(drift report of the one page, problem): the nightly check run on the
    inventory with the page added, so the page is read exactly as the nightly
    crawl reads a page - signed in, rendered, its elements named and declared
    by the generator's rules."""
    with tempfile.TemporaryDirectory() as tmp:
        inv = Path(tmp) / "inventory.json"
        out = Path(tmp) / "page.json"
        inv.write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-m", "scripts.check_inventory_staleness", "--inventory", str(inv),
             "--page", name, "--compare", "--headings", "--json", str(out)],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600)
        print(run.stdout[-4000:])
        if run.returncode == 2:
            return None, "the sign-in failed"
        try:
            drift = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, f"the page check wrote no report (exit {run.returncode})"
    if name in (drift.get("unreachable_pages") or []):
        why = ((drift.get("unreachable_reasons") or {}).get(name) or {}).get("reason")
        return None, f"it did not load ({why or 'unreachable'})"
    if name not in (drift.get("pages") or {}):
        return None, "it sent the browser to another page (signed in), so it was not read"
    return drift, ""


def _open_explore_prs(host, prefix: str) -> list:
    out = []
    for pr in host.list_open_prs(prefix, strict=True):
        if not (pr.get("head_ref") or "").startswith(prefix):
            continue
        body = host.get_pr_metadata(pr["number"]).get("body") or ""
        parsed = pe.parse_body(body)
        if parsed:
            out.append({"number": pr["number"], "story": parsed[0], "page": parsed[1],
                        "url": pr.get("url") or f"#{pr['number']}"})
    return out


def _closed_explore_prs(host, prefix: str) -> list:
    """Exploration proposals a person closed without merging."""
    out = []
    for pr in (host.list_closed_prs(prefix) if hasattr(host, "list_closed_prs") else []):
        parsed = pe.parse_body(pr.get("body") or "")
        if parsed and not pr.get("merged"):
            out.append({"number": pr["number"], "story": parsed[0], "page": parsed[1]})
    return out


def _unused_branch(host, base: str) -> str:
    branch, n = base, 1
    while host.branch_exists(branch):
        n += 1
        branch = f"{base}-{n}"
    return branch


def _comment(tracker, story_id: str, text: str, dry_run: bool) -> None:
    print(f"[{story_id}] {text}")
    if dry_run:
        return
    try:
        from integrations.tracker import add_markdown_comment
        add_markdown_comment(tracker, story_id, text)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("comment on %s not posted: %s", story_id, e)


def explore(req: dict, *, tracker, host, inventory: dict, original: str, ctx, s: dict,
            links: dict, open_prs: list, dry_run: bool, llm_factory,
            closed_prs: Sequence[dict] = ()) -> dict:
    """One request. Returns {"story", "status", ...}; never raises for a
    finding - only for a tracker or host failure."""
    story_id, wanted = req["story"], list(req.get("pages") or [])
    known = dict(req.get("known_pages") or {})
    for pr in open_prs:
        if pr["story"] == story_id or pr["page"] in wanted + list(known):
            print(f"[{story_id}] an exploration pull request is open already: #{pr['number']}")
            return {"story": story_id, "status": "open", "pr": pr["number"]}
    for pr in closed_prs or ():
        if pr["story"] == story_id:
            # A person said no to the page proposed for this story: never again.
            print(f"[{story_id}] its proposal #{pr['number']} was closed without merging")
            return {"story": story_id, "status": "closed_before", "pr": pr["number"]}
    if not wanted and not req.get("reasons"):
        if known:
            return explore_elements(req, tracker=tracker, host=host, inventory=inventory,
                                    original=original, ctx=ctx, s=s, dry_run=dry_run)
        return {"story": story_id, "status": "nothing_asked"}
    candidates, not_visited = pe.candidate_links(
        links, inventory, ctx.base_url.rstrip("/"), int(s["explore_max_links"]),
        s.get("explore_never_visit") or ())
    if not candidates:
        _comment(tracker, story_id, pe.not_found_comment(
            "no link on the application's pages leads to a page the inventory lacks"), dry_run)
        return {"story": story_id, "status": "no_link"}
    path = pe.by_name(wanted, candidates)
    how = (f"the generated code named page `{wanted[0] if len(wanted) == 1 else wanted}`, and "
           f"exactly one link on the application leads to `{path}`") if path else ""
    if not path:
        named = pe.names_in(req.get("reasons"))
        path = pe.by_name(named, candidates)
        how = (f"the refusal names `{'`, `'.join(named)}`, and exactly one link on the "
               f"application leads to `{path}`") if path else ""
    if not path:
        from core.usage_ledger import post_usage_to_story, story_usage
        from core.llm_client import log_usage_summary, reset_usage
        story = tracker.get_story(story_id) or {}
        cases = tracker.get_linked_test_cases(story_id) or []
        from config.paths import PROMPTS_DIR
        template = (PROMPTS_DIR / "explore_page_link.md").read_text(encoding="utf-8")
        prompt = pe.link_prompt(template, story, cases, wanted, req.get("reasons"), candidates)
        with story_usage(story_id, AGENT_NAME, jira=tracker, dry_run=dry_run):
            path, why = pe.choose_link(llm_factory(), prompt, candidates)
            usage = log_usage_summary(f"story {story_id} (page exploration)")
            reset_usage()
            if not dry_run and (usage or {}).get("llm_calls"):
                post_usage_to_story(story_id, AGENT_NAME, usage, jira=tracker)
        if not path:
            _comment(tracker, story_id, pe.not_found_comment(
                f"none of the {len(candidates)} link(s) to pages the inventory lacks fits "
                f"({why or 'no reason given'})"), dry_run)
            return {"story": story_id, "status": "no_fit", "why": why}
        how = f"{why} (chosen among {len(candidates)} link(s) by one model call)"
    story = tracker.get_story(story_id) or {}
    name = pe.page_name(wanted, path, inventory)
    # Named as the inventory's other pages are: the story's Components, else
    # the words of the link that opened the page (pe.components_for).
    texts = next((c["texts"] for c in candidates if c["path"] == path), [])
    components = pe.components_for(story.get("components"), texts, name)
    stub, refused = pe.with_page(inventory, name, path, components)
    if refused:
        _comment(tracker, story_id, pe.not_found_comment(f"`{path}` cannot be added: {refused}"),
                 dry_run)
        return {"story": story_id, "status": "refused", "why": refused}
    drift, problem = read_page(stub, name)
    if drift is None:
        _comment(tracker, story_id, pe.not_found_comment(f"`{path}` was chosen but {problem}"),
                 dry_run)
        return {"story": story_id, "status": "not_read", "why": problem}
    drift, template = pe.template_content(drift, name, stub)
    cfg = _cfg()
    upd = iu.build_update(drift, stub, set(),
                          max_additions_per_page=int(s["explore_max_elements"]),
                          hold_ratio=float(cfg["hold_ratio"]),
                          layout_min_pages=int(cfg["layout_min_pages"]), allow_removal=False,
                          no_removal_reason="a new page")
    if not upd.added:
        _comment(tracker, story_id, pe.not_found_comment(
            f"`{path}` was read, but no element on it has a durable selector"), dry_run)
        return {"story": story_id, "status": "empty"}
    new = pe.proposed(inventory, upd.inventory, name)
    body = pe.render_body(story_id, name, path, how, upd, inventory_path=ctx.inventory_file,
                          not_visited=not_visited, template=template)
    if dry_run:
        print(f"\n--dry-run: page {name} ({path}), {len(upd.added)} element(s). The pull "
              f"request body would be:\n\n{body}\n")
        return {"story": story_id, "status": "dry_run", "page": name, "path": path,
                "added": len(upd.added)}
    branch = _unused_branch(host, f"{s['explore_branch_prefix']}{name.replace('_', '-')}")
    host.create_branch(branch, "main")
    try:
        host.create_or_update_file(ctx.inventory_file, iu.dump_like(original, new),
                                   f"chore(inventory): add page {name}, explored live", branch)
        url = host.open_pull_request(f"chore(inventory): add page {name}, explored live",
                                     body, branch, "main")
    except Exception:
        host.delete_branch(branch)        # never leave a half-written branch
        raise
    _comment(tracker, story_id, pe.story_comment(story_id, name, path, url, len(upd.added)),
             dry_run)
    return {"story": story_id, "status": "proposed", "page": name, "path": path, "pr": url}


def _cfg() -> dict:
    from core.impact_settings import impact_settings
    return iu.settings(impact_settings().get("inventory_update"))


def _claimed(host, inventory_path: str, inventory: dict, s: dict) -> dict:
    """{(page, selector): "page.key (pull request)"} an open nightly update or
    heal pull request already gives a key - not proposed a second time."""
    if host is None:
        return {}
    out = iu.additions_in_open_prs(host, _cfg()["branch_prefix"], inventory_path, inventory)
    for (page, key), v in iu.claims_in_open_prs(host, s["heal_branch_prefix"], inventory_path,
                                                 inventory).items():
        out.setdefault((page, v["selector"]), f"{page}.{key} ({v['url']})")
    return out


def explore_elements(req: dict, *, tracker, host, inventory: dict, original: str, ctx,
                     s: dict, dry_run: bool) -> dict:
    """Elements a refusal needs on pages the inventory HAS: each page read live
    with the nightly check, and only what the nightly update would add to it
    (with its headings and its template's list items) proposed - its other
    keys and fields untouched. No model call."""
    story_id, needs = req["story"], dict(req.get("known_pages") or {})
    cfg = _cfg()
    used = {k for entry in (inventory.get("pages") or {}).values()
            for k in ((entry or {}).get("elements") or {})}
    claimed = _claimed(host, ctx.inventory_file, inventory, s)
    upds, templates, problems = {}, {}, []
    new = inventory
    for page in sorted(needs)[:3]:
        drift, problem = read_page(inventory, page)
        if drift is None:
            problems.append(f"`{page}` {problem}")
            continue
        drift, template = pe.template_content(drift, page, inventory)
        upd = iu.build_update(drift, inventory, used,
                              max_additions_per_page=int(s["explore_max_elements"]),
                              hold_ratio=float(cfg["hold_ratio"]),
                              layout_min_pages=int(cfg["layout_min_pages"]),
                              allow_removal=False, no_removal_reason="an element read",
                              claimed=claimed)
        if upd.added:
            upds[page], templates[page] = upd, template
            new = pe.with_added(new, upd.inventory, page, upd.added)
        else:
            problems.append(f"`{page}` has no new element with a durable selector")
    if not upds:
        _comment(tracker, story_id, pe.elements_not_found_comment("; ".join(problems)), dry_run)
        return {"story": story_id, "status": "empty", "why": "; ".join(problems)}
    added = sum(len(u.added) for u in upds.values())
    body = pe.render_elements_body(story_id, upds, inventory_path=ctx.inventory_file,
                                   needs=needs, templates=templates)
    pages = sorted(upds)
    if dry_run:
        print(f"\n--dry-run: {added} element(s) for {', '.join(pages)}. The pull request "
              f"body would be:\n\n{body}\n")
        return {"story": story_id, "status": "dry_run", "pages": pages, "added": added}
    branch = _unused_branch(host, f"{s['explore_branch_prefix']}{pages[0].replace('_', '-')}"
                                  "-elements")
    title = f"chore(inventory): add elements to {', '.join(pages)}, read live"
    host.create_branch(branch, "main")
    try:
        host.create_or_update_file(ctx.inventory_file, iu.dump_like(original, new), title, branch)
        url = host.open_pull_request(title, body, branch, "main")
    except Exception:
        host.delete_branch(branch)        # never leave a half-written branch
        raise
    _comment(tracker, story_id, pe.elements_comment(story_id, pages, url, added), dry_run)
    return {"story": story_id, "status": "proposed", "pages": pages, "added": added, "pr": url}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--requests", default=pe.REQUESTS_FILE)
    ap.add_argument("--dry-run", action="store_true", help="print; open and post nothing")
    args = ap.parse_args(argv)
    s = pe.settings()
    if not s.get("explore_missing_pages"):
        print("live_browser.explore_missing_pages is false - nothing explored.")
        return 0
    requests = pe.read_requests(args.requests)
    if not requests:
        print("No story was refused for a page the inventory lacks - nothing to explore.")
        return 0
    try:
        from integrations.tracker import get_tracker
        tracker = get_tracker()
        host = None
        if not args.dry_run:
            from integrations.repo_host import get_repo_host
            host = get_repo_host()
    except Exception as e:                                         # noqa: BLE001
        print(f"[FAIL] the tracker or the repository host cannot be used: {e}")
        return 1
    ctx = AppContext.load()
    original = ctx.inventory_path().read_text(encoding="utf-8")
    inventory = json.loads(original)
    open_prs = _open_explore_prs(host, s["explore_branch_prefix"]) if host else []
    closed_prs = _closed_explore_prs(host, s["explore_branch_prefix"]) if host else []
    links, problem = {}, ""
    if any(r.get("pages") or r.get("reasons") for r in requests):
        # Links are read only for a missing PAGE; elements of a known page
        # are read on that page itself.
        links, problem = collect_links(inventory, ctx.base_url.rstrip("/"),
                                       int(s["explore_max_pages"]))
    from core.llm_client import LLMClient

    def llm_factory():
        return LLMClient(temperature=0.0, max_output_tokens=800)

    results = []
    for req in requests:
        if problem:
            _comment(tracker, req["story"], pe.not_found_comment(
                f"the application could not be read ({problem})"), args.dry_run)
            results.append({"story": req["story"], "status": "not_read", "why": problem})
            continue
        try:
            results.append(explore(req, tracker=tracker, host=host, inventory=inventory,
                                   original=original, ctx=ctx, s=s, links=links,
                                   open_prs=open_prs, dry_run=args.dry_run,
                                   llm_factory=llm_factory, closed_prs=closed_prs))
        except Exception as e:                                     # noqa: BLE001
            logger.error("exploration for %s failed: %s", req["story"], e)
            results.append({"story": req["story"], "status": "error", "why": str(e)[:300]})
    for r in results:
        print(f"explored: {r}")
    return 1 if any(r["status"] == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
