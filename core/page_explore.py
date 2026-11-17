"""A page the inventory lacks, explored live and proposed - not a refusal (PW1).

WHY
    Agent 2 may use inventory keys only, and the inventory is curated. A story
    whose test cases need a page the inventory does not have was refused: the
    final gate (or the plan) named the page, the blocked comment told a person
    to add it by hand (scripts.plan_inventory), and nothing moved until
    someone did. Such a page is usually live already - linked from the
    application's own menu - and the nightly crawl reads only the pages the
    inventory lists, so it never finds it either.

WHAT
    When Agent 2 refuses a story for a page the inventory lacks, it records a
    request (core.blocked -> record_request) and the run's next step
    (scripts/explore_missing_pages.py), for each request:
      1. signs in as the nightly check does and collects the same-origin links
         on the inventory's pages that lead to no inventory page - never one
         whose path looks destructive (`explore_never_visit`: sign-out,
         delete ...), which is not visited, only listed;
      2. picks the link that opens the page: by name when the page Agent 2
         named matches exactly one link's path, else ONE light model call that
         reads the story, its test cases and the refusal against the links -
         and may answer that none fits;
      3. reads that page live with the nightly check itself
         (check_inventory_staleness --inventory <inventory + the page>
         --page <page> --compare): its elements, named and declared by the
         generator's own rules, signed in as the tests are;
      4. keeps them as the nightly inventory update keeps a new page's
         elements (core.inventory_update.build_update): the same refusal rules,
         no element without a durable handle, at most `explore_max_elements`;
      5. opens ONE pull request adding the page (never a second one for a
         story or page with one open, nor again for a story whose proposal a
         person closed without merging), and says so on the story.
    Merging that pull request starts Agent 2 on the story again
    (scripts/resume_explored_story.py, run by "Story Done on merge"). Nothing
    is merged by an agent: a person reviews the proposed page, as they review
    the nightly inventory update.

    Not explored: a page no link leads to (reached only by a form or a
    script) - the story comment says so, and the hand route stays.

Pure logic here; the browser, the tracker and the repository host are in the
scripts. Nothing here names an application, a page or an element.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MARKER = "[inventory-explore]"
_BODY = re.compile(re.escape(MARKER) + r" story: (\S+) page: ([a-z][a-z0-9_]*)")
REQUESTS_FILE = "reports/explore_requests.json"
_PAGE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_SKIP_HREF = ("#", "mailto:", "tel:", "javascript:")


# ── settings ────────────────────────────────────────────────────────────

def settings() -> dict:
    """`live_browser` in config.yaml over its defaults. A branch prefix holding
    an issue key is refused: merging it would move that story to Done."""
    from config import extract_jira_key
    from core.ops_settings import section
    s = section("live_browser")
    for key in ("explore_branch_prefix", "heal_branch_prefix"):
        if extract_jira_key(str(s.get(key) or "")):
            raise ValueError(f"live_browser.{key} {s[key]!r} contains an issue key: merging "
                             "it would close or report on that story")
    return s


# ── what a refusal asks for ─────────────────────────────────────────────

def _words(name: str) -> list:
    """A page name as a reason may write it: `order_history`, `order history`."""
    return [name, name.replace("_", " ")]


# The plan writes "needs <the element> on <page>, not in the app inventory".
_ON_PAGE = re.compile(r"\bneeds\b.*?\bon (?:the )?(.+?),? not in the app inventory", re.I | re.S)
# A page name the reason writes the code's way (`order_history`), which the link's
# path may carry: chosen by name, without a model call.
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def _names_known_page(text: str, pages) -> bool:
    """Does the reason place the missing thing on a page the inventory has?
    Read from the page it names ("... on <page>, not in the app inventory"):
    a known page at its start is a missing ELEMENT of that page. Without that
    phrase, any known page named anywhere counts - the cautious reading."""
    m = _ON_PAGE.search(text or "")
    if m:
        phrase = m.group(1).strip().lower()
        return any(re.match(rf"{re.escape(w)}(?![a-z0-9_])", phrase)
                   for p in pages for w in _words(str(p).lower()))
    low = (text or "").lower()
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(w)}(?![a-z0-9_])", low)
               for p in pages for w in _words(str(p).lower()))


def requested(errors, inventory: dict) -> dict | None:
    """{"pages": [names], "reasons": [texts]} when a refusal is for a page the
    inventory lacks, else None.

    `pages`: the page names generated code used that the inventory does not
    have (the method-resolution validator's own reading - not a misspelling of
    a page it has). `reasons`: the plan's "not in the app inventory" reasons
    that name no page the inventory has - a missing ELEMENT on a known page is
    the nightly update's to add, not a page to explore."""
    from core.blocked import says_not_in_inventory
    from validators.method_resolution_validator import pages_missing_from_inventory
    names = list(((inventory or {}).get("pages") or {}))
    errors = [str(e) for e in errors or []]
    wanted = pages_missing_from_inventory(errors, pages=names)
    reasons = [e[:400] for e in errors
               if says_not_in_inventory(e) and not _names_known_page(e, names)]
    if not wanted and not reasons:
        return None
    return {"pages": wanted, "reasons": reasons}


def record_request(story_id: str, request: dict, path: str | Path = REQUESTS_FILE) -> None:
    """Add the story's request to the file the run's explore step reads (one
    entry per story; a later refusal of the same story in the run replaces it).
    Never raises: exploring is an offer, the refusal stands without it."""
    try:
        p = Path(path)
        try:
            entries = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = []
        entries = [e for e in entries if isinstance(e, dict) and e.get("story") != story_id]
        entries.append({"story": story_id, **request})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Exploration request for %s not recorded: %s", story_id, e)


def read_requests(path: str | Path = REQUESTS_FILE) -> list:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("story")]


# ── the links ───────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def never_visit(path: str, words) -> bool:
    """A path that would change the account or the session when opened."""
    low = _slug(path)
    return any(_slug(w) and _slug(w) in low for w in words or ())


def candidate_links(found: dict, inventory: dict, base_url: str, limit: int = 40,
                    never=()) -> tuple:
    """(candidates, not_visited): the same-origin pages the application links
    to that no inventory page's url (or `{template}`) matches, each
    {"path", "texts", "linked_from"}, most-linked first; and the paths left
    out because opening them would change the session or the account.

    `found`: {inventory page: [{"href", "text"}]} read live on each page."""
    from inventory_tools.introspect import _ASSET, _path_pattern
    host = urlparse(base_url).netloc
    patterns = [_path_pattern((p or {}).get("url") or "/")
                for p in ((inventory or {}).get("pages") or {}).values()
                if isinstance(p, dict) and (p.get("url") or "").startswith("/")]
    rows: dict = {}
    skipped: set = set()
    for page in sorted(found or {}):
        for link in found[page] or []:
            href = str((link or {}).get("href") or "").strip()
            if not href or href.startswith(_SKIP_HREF):
                continue
            parsed = urlparse(href if "://" in href or href.startswith("//")
                              else base_url.rstrip("/") + "/" + href.lstrip("/"))
            if parsed.netloc and parsed.netloc != host:
                continue
            path = (parsed.path or "/").rstrip("/") or "/"
            if _ASSET.search(path) or any(p.match(path) for p in patterns):
                continue
            if never_visit(path, never):
                skipped.add(path)
                continue
            row = rows.setdefault(path, {"path": path, "texts": [], "linked_from": []})
            text = " ".join(str((link or {}).get("text") or "").split())[:80]
            if text and text not in row["texts"] and len(row["texts"]) < 3:
                row["texts"].append(text)
            if page not in row["linked_from"]:
                row["linked_from"].append(page)
    out = sorted(rows.values(), key=lambda r: (-len(r["linked_from"]), r["path"]))
    return out[:limit], sorted(skipped)


def names_in(reasons) -> list:
    """snake_case names the reasons write (a page as the code would name it)."""
    out = []
    for r in reasons or []:
        for n in _SNAKE.findall(str(r)):
            if n not in out:
                out.append(n)
    return out


def by_name(wanted, candidates) -> str | None:
    """The one candidate path whose last segment (or whole path) is a page
    name the generated code used, letter case and separators ignored."""
    names = {_slug(w) for w in wanted or () if _slug(w)}
    if not names:
        return None
    hits = [c["path"] for c in candidates or []
            if _slug(c["path"].rstrip("/").rsplit("/", 1)[-1]) in names
            or _slug(c["path"]) in names]
    return hits[0] if len(hits) == 1 else None


def link_prompt(template: str, story: dict, test_cases, wanted, reasons, candidates) -> str:
    def case(tc):
        return f"- {tc.get('key', '')} {tc.get('summary', '')}".rstrip()
    links = "\n".join(
        f"{i}. {c['path']} - link text: {', '.join(repr(t) for t in c['texts']) or '(none)'}"
        f" - on: {', '.join(c['linked_from'])}" for i, c in enumerate(candidates, 1))
    return (template
            .replace("{story_text}", f"Title: {story.get('summary', '')}\n\n"
                                     f"{(story.get('description') or '')[:3000]}")
            .replace("{test_cases}", "\n".join(case(t) for t in test_cases or []) or "(none)")
            .replace("{wanted}", ", ".join(wanted or []) or "(not named)")
            .replace("{reasons}", "\n".join(f"- {r}" for r in reasons or []) or "(none)")
            .replace("{links}", links or "(no link found)"))


def choose_link(llm, prompt: str, candidates) -> tuple:
    """(path, why) from one structured call; an answer naming no listed path
    is no answer."""
    from core.schemas import LinkChoice
    answer = llm.invoke_structured(
        system_prompt="You are a meticulous QA engineer mapping an application's pages.",
        user_prompt=prompt, output_schema=LinkChoice)
    path = (answer.path or "").strip()
    if path and path not in {c["path"] for c in candidates or []}:
        return "", f"the answer named {path!r}, which is not one of the links"
    return path, (answer.why or "").strip()


# ── the page ────────────────────────────────────────────────────────────

def page_name(wanted, path: str, inventory: dict) -> str:
    """The name Agent 2's code used when it named exactly one, else one made
    from the path's last segment; never a name the inventory has."""
    pages = set(((inventory or {}).get("pages") or {}))
    if len(wanted or []) == 1 and _PAGE_NAME.match(wanted[0]):
        base = wanted[0]
    else:
        base = _slug((path or "").rstrip("/").rsplit("/", 1)[-1]) or "page"
        if not base[0].isalpha():
            base = f"page_{base}"
    name, n = base, 2
    while name in pages:
        name, n = f"{base}_{n}", n + 1
    return name


def with_page(inventory: dict, name: str, path: str, components=()) -> tuple:
    """(inventory with an empty page `name` at `path`, refusal). The page is
    read live into it next; nothing else changes."""
    from core.inventory_planned import _url_taken
    if not _PAGE_NAME.match(name or ""):
        return inventory, "page name must be lowercase snake_case"
    if name in ((inventory or {}).get("pages") or {}):
        return inventory, f"page {name!r} already exists"
    if not (path or "").startswith("/"):
        return inventory, "url must be a path starting with '/'"
    taken = _url_taken(inventory, path)
    if taken:
        return inventory, f"url {path!r} is already page {taken!r}"
    out = copy.deepcopy(inventory)
    out.setdefault("pages", {})[name] = {"url": path, "components": list(components or []),
                                         "elements": {}}
    return out, ""


def template_content(drift: dict, name: str, inventory: dict) -> tuple:
    """(drift with the page's template content among its new elements, rows).

    The nightly check lists an element another page's key already covers as
    shared, never added (a footer on every page). For a page read for the first
    time that is wrong when the covering key is a FAMILY (`multi_match`) of a
    page not declared `always`: the new page is built from the same template
    as that page - the same list markup - and the element is its own content.
    A page object reaches only its own page's keys, so without them the page
    was proposed with nothing a test needs (17 Nov 2026: every item of a
    list page read as shared with another page's list). Such elements are
    added under the generator's own names and selectors; a single key that
    covers them (a header, a form field) still marks shared chrome."""
    import copy as _copy
    out = _copy.deepcopy(drift or {})
    pages = (inventory or {}).get("pages") or {}
    declared = ((out.get("new_element_declarations") or {}).get(name) or {})
    shared = dict(declared.get("shared") or {})
    new = (out.setdefault("new_elements", {})).setdefault(name, {})
    rows = []
    for element, row in sorted(shared.items()):
        owner_page, _, owner_key = str((row or {}).get("covered_by") or "").partition(".")
        owner = pages.get(owner_page) or {}
        if owner.get("always") or owner_key not in set(owner.get("multi_match") or []):
            continue
        if element in new or not row.get("selector"):
            continue
        new[element] = row["selector"]
        shared.pop(element)
        rows.append({"element": element, "selector": row["selector"],
                     "covered_by": row["covered_by"]})
    if rows:
        declared["shared"] = shared
    return out, rows


def proposed(inventory: dict, updated: dict, name: str) -> dict:
    """The committed inventory with the explored page added - and nothing else
    changed, whatever else the read found."""
    out = copy.deepcopy(inventory)
    page = copy.deepcopy(((updated or {}).get("pages") or {}).get(name) or {})
    for key in ("multi_match", "conditional"):
        if not page.get(key):
            page.pop(key, None)
    out.setdefault("pages", {})[name] = page
    return out


def parse_body(body: str) -> tuple | None:
    """(story, page) from an exploration pull request's body, or None."""
    m = _BODY.search(body or "")
    return (m.group(1), m.group(2)) if m else None


def render_body(story_id: str, name: str, path: str, how: str, upd, *,
                inventory_path: str, not_visited=(), template=()) -> str:
    """The pull request's description: what was explored, why that page, and
    what was left out."""
    from core.inventory_update import _table
    el = ("Element", lambda r: f"`{r['element']}`")
    sel = ("Selector", lambda r: f"`{r['selector']}`")
    lines = [
        f"{MARKER} story: {story_id} page: {name}",
        "",
        f"## 🤖 A page the inventory lacked, explored live for {story_id}",
        "",
        f"Agent 2 could not code {story_id}: its test cases need a page `{inventory_path}` "
        f"does not have. The application links to it, so it was read live, signed in as "
        f"the tests are, and is proposed here as page `{name}` (`{path}`).",
        "",
        f"**Why this page:** {how}",
        "",
        "**Before merging:** open the page and check the names and selectors below "
        "(rename a key in this branch if a better name exists; add `components`, notes "
        "or `conditional` elements a crawler cannot see). Merging starts Agent 2 on "
        f"{story_id} again. Close this pull request if it is the wrong page - it is then not "
        "proposed again for this story - and add the page by hand "
        "(`python -m scripts.plan_inventory page ...`).",
        "",
    ]
    lines += _table("Elements added", upd.added, [el, sel])
    if template:
        owners = sorted({r["covered_by"] for r in template})
        lines += [f"**Same template as** {', '.join(f'`{o}`' for o in owners)}: "
                  f"{len(template)} element(s) above are this page's items of the list that "
                  "key covers on its own page. Declare one family key for them if a test "
                  "reads the list as a whole (the family's selector, in `multi_match`).", ""]
    lines += _table("Not added - no durable selector", upd.fragile, [el, sel],
                    "Only a fragile handle (a css fallback, one member pinned by `>> nth=`, "
                    "hidden when read). Add a test-id in the application or write the entry "
                    "by hand.")
    lines += _table("Not added - already covered on another page", upd.shared,
                    [el, sel, ("Covered by", lambda r: f"`{r['covered_by']}`")])
    lines += _table("Not added - over the limit (`live_browser.explore_max_elements`)",
                    upd.over_cap, [el, sel])
    lines += _table("Not added - refused", upd.refused,
                    [el, sel, ("Reason", lambda r: r["refused"])])
    if not_visited:
        lines += ["**Links never opened** (they would change the session or the account, "
                  "`live_browser.explore_never_visit`): "
                  + ", ".join(f"`{p}`" for p in list(not_visited)[:20]), ""]
    lines += ["_Proposed by `scripts.explore_missing_pages` (PW1). Nothing is merged by an "
              "agent._"]
    return "\n".join(lines)


def story_comment(story_id: str, name: str, path: str, pr_url: str, added: int) -> str:
    return (f"{MARKER} Agent 2 explored the page this story needs on the live application: "
            f"`{path}`, with {added} element(s), is proposed as inventory page `{name}` in "
            f"{pr_url}. Check it and merge it: merging starts Agent 2 on {story_id} again. "
            "If it is the wrong page, close the pull request and add the page by hand.")


def not_found_comment(why: str) -> str:
    return (f"{MARKER} Agent 2 looked for the page this story needs on the live "
            f"application and proposes nothing: {why}. Add the page by hand "
            "(`python -m scripts.plan_inventory page --page <page> --url /<path> "
            "--component \"<Component>\" --element <key>=\"<selector>\"`), then run Agent 2 "
            "with this story's key.")
