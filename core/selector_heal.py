"""A test failing because a selector changed: propose the new selector, not a defect (PW2).

WHY
    A test on main that failed because an inventory selector stopped matching -
    the application renamed a test-id or reworded a button, and the element is
    still there - was raised as a defect against the application ("element
    never appeared"). The nightly inventory update kept the key too ("code
    still names it - a person decides") unless the generator happened to name
    the live element exactly as the key. A person then found the element in
    DevTools and edited the inventory by hand.

WHAT
    After a run on main, before the triage raises defects
    (scripts/heal_selectors.py, in Agent 4's triage job):
      1. the failures worth checking: failed again after the retry, not an
         outage, and read by the failure diagnosis as an element that never
         appeared (`heal_failure_kinds`) - not a wrong value, not an element
         that was there but hidden;
      2. the inventory keys each one reaches (Agent 0's impact graph: steps ->
         page-object methods -> `self.sel` keys) and their pages, at most
         `heal_max_pages`, the page most failing tests reach first;
      3. each page read live with the nightly check itself
         (check_inventory_staleness --page <page> --compare): the keys that
         match nothing now, and the live elements no selector matches, named
         and declared by the generator's rules;
      4. for each stale key a failing test reaches: the live element the
         generator names the same (the nightly update's own rule), else ONE
         light model call choosing among the uncovered elements - or none.
         Never an element without a durable handle; a family key only for an
         element the generator declares a family, and the reverse;
      5. ONE pull request with every selector healed (a key an open pull
         request already changes is left to it; a heal a person closed
         without merging is never proposed again), a comment on each healed
         test's test case, and reports/heal.json, which the triage reads: no
         defect for a healed test - its fix is in review.
    A test reaching a stale key nothing matches is raised as a defect, as
    before: the element may really be gone. Nothing is merged by an agent;
    Agent 4 runs the tests the changed keys reach on the pull request.

Pure logic here; the browser, the model, the tracker and the repository host
are in the script. Nothing here names an application, a page or an element.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER = "[inventory-heal]"
_KEY_LINE = re.compile(re.escape(MARKER) + r" ([a-z][a-z0-9_]*)\.([A-Za-z0-9_]+):")
HEAL_FILE = "heal.json"


# ── which failures ──────────────────────────────────────────────────────

def _captured(case) -> str:
    return "\n".join((node.text or "") for tag in ("system-out", "system-err")
                     for node in case.findall(tag))


def healable(root, kinds, only_after_retry: bool = True) -> list:
    """[(test id, diagnosis label, failure text)] of the failures a changed
    selector may explain: failed (again, after the retry when the triage needs
    one), not an outage, and read as one of `kinds` by the failure diagnosis."""
    from core import junit_marks as jm
    from core.failure_diagnosis import diagnose_with_context
    out = []
    for case in jm.cases(root):
        if jm.outcome(case) not in ("failed", "error") or jm.is_outage(case):
            continue
        if only_after_retry and not jm.is_retried(case):
            continue
        text = jm.failure_text(case)
        label = diagnose_with_context(text, _captured(case)).label
        if label in set(kinds or ()):
            out.append((jm.case_id(case), label, f"{text}\n{_captured(case)}"))
    return out


def narrow(keys: set, text: str, selectors: dict) -> set:
    """The keys whose selector the failure quotes (Playwright names the locator
    it waited for), else all of them: then every page the test reaches is
    read."""
    text = text or ""
    hits = {k for k in keys if selectors.get(k)
            and (selectors[k] in text or selectors[k].replace('"', '\\"') in text)}
    return hits or set(keys)


# ── which keys ──────────────────────────────────────────────────────────

def _scenario_index(graph) -> dict:
    """{(module, function): scenario} - the pytest test each scenario runs as."""
    from core.impact_results import _test_name
    return {("test_" + Path(s.file).stem, _test_name(s.title)): s for s in graph.scenarios}


def scenario_of(graph, test_id: str, index: dict | None = None):
    classname, _, name = test_id.partition("::")
    module = classname.rsplit(".", 1)[-1]
    name = re.sub(r"\[.*\]$", "", name)
    return (index if index is not None else _scenario_index(graph)).get((module, name))


def keys_by_test(graph, test_ids) -> dict:
    """{test id: {(page, key)}} the test's steps reach; a test the graph
    cannot place reaches nothing (it is raised as before)."""
    index = _scenario_index(graph)
    out = {}
    for t in test_ids:
        s = scenario_of(graph, t, index)
        out[t] = set(s.elements) if s else set()
    return out


def pages_to_check(reached: dict, limit: int) -> list:
    """The pages the failing tests reach, the one most of them reach first."""
    count: dict = {}
    for keys in reached.values():
        for page in {p for p, _k in keys}:
            count[page] = count.get(page, 0) + 1
    return [p for p, _n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))][:limit]


# ── the reading of one page ─────────────────────────────────────────────

def stale_keys(report: dict, page: str) -> dict:
    """{key: selector} the nightly check found matching nothing on `page`."""
    diff = ((report or {}).get("pages") or {}).get(page) or {}
    return {m["element"]: m.get("selector", "") for m in diff.get("missing") or []
            if isinstance(m, dict) and m.get("element")}


def candidates(report: dict, page: str) -> tuple:
    """({name: selector} live elements no selector matches, with a durable
    handle; {name} the generator declares a family)."""
    elements = dict(((report or {}).get("new_elements") or {}).get(page) or {})
    declared = ((report or {}).get("new_element_declarations") or {}).get(page) or {}
    for name in declared.get("unstable") or []:
        elements.pop(name, None)
    return elements, set(declared.get("multi_match") or [])


def by_name(key: str, cands: dict) -> str | None:
    return key if key in cands else None


def fits(key: str, entry: dict, name: str, families: set) -> str:
    """'' when live element `name` can stand for `key`, else why not."""
    family_key = key in set((entry or {}).get("multi_match") or [])
    if family_key and name not in families:
        return "the key names a list of elements; the live element is one element"
    if not family_key and name in families:
        return "the key names one element; the live element is a list"
    return ""


def heal_prompt(template: str, page: str, url: str, key: str, old: str, note: str,
                steps, cands: dict) -> str:
    return (template.replace("{page}", page).replace("{url}", url or "")
            .replace("{key}", key).replace("{old_selector}", old)
            .replace("{note}", note or "(none)")
            .replace("{steps}", "\n".join(f"- {k} {p}" for k, p in steps or []) or "(unknown)")
            .replace("{candidates}", "\n".join(f"- {n}: {s}" for n, s in sorted(cands.items()))
                     or "(none)"))


def choose(llm, prompt: str, cands: dict) -> tuple:
    """(element name or '', why) from one structured call; a name not listed
    is no answer."""
    from core.schemas import SelectorChoice
    answer = llm.invoke_structured(
        system_prompt="You are a meticulous QA engineer maintaining a page inventory.",
        user_prompt=prompt, output_schema=SelectorChoice)
    name = (answer.element or "").strip()
    if name and name not in cands:
        return "", f"the answer named {name!r}, which is not one of the live elements"
    return name, (answer.why or "").strip()


# ── the change ──────────────────────────────────────────────────────────

def apply(inventory: dict, heals: list) -> tuple:
    """(inventory with each heal's selector, refused heals with why). A new
    selector another key of the page already uses is refused."""
    out = copy.deepcopy(inventory)
    refused = []
    for h in heals:
        page = ((out.get("pages") or {}).get(h["page"]) or {})
        elements = page.get("elements") or {}
        if h["key"] not in elements:
            refused.append({**h, "why": "the key is not on the page any more"})
            continue
        if h["new"] in {v for k, v in elements.items() if k != h["key"]}:
            refused.append({**h, "why": "another key of the page already uses that selector"})
            continue
        elements[h["key"]] = h["new"]
    return out, refused


def healed_tests(reached: dict, stale: set, fixed: dict, checked=None) -> tuple:
    """({test: [page.key fixed]}, {test: why not}) - a test is healed when every
    page it reaches was read (`checked`; None: all were), it reaches a stale
    key, and every stale key it reaches is fixed (here, or by an open pull
    request)."""
    healed, not_healed = {}, {}
    for test, keys in reached.items():
        unread = sorted({p for p, _k in keys} - set(checked)) if checked is not None else []
        if unread:
            not_healed[test] = f"page(s) {', '.join(unread)} not read live"
            continue
        hit = sorted(k for k in keys if k in stale)
        if not hit:
            not_healed[test] = "every inventory key it reaches matches on the live page"
            continue
        missing = [f"{p}.{k}" for p, k in hit if (p, k) not in fixed]
        if missing:
            not_healed[test] = f"no live element found for {', '.join(missing)}"
            continue
        healed[test] = [f"{p}.{k}" for p, k in hit]
    return healed, not_healed


def render_body(heals: list, tests: dict, *, inventory_path: str, run_url: str) -> str:
    from core.inventory_update import _table
    lines = [f"{MARKER} {h['page']}.{h['key']}: {h['old']} -> {h['new']}" for h in heals]
    lines += [
        "",
        "## 🤖 Selectors healed after a failure on main",
        "",
        f"Tests failed on main ({run_url}) because these inventory selectors match nothing "
        "on the live page any more. Each element is still there with another selector - "
        f"read live, signed in as the tests are - so `{inventory_path}` is updated instead "
        "of raising a defect against the application.",
        "",
        "**Before merging:** look at Agent 4's run on this pull request (it runs the tests "
        "these keys reach) and check each new selector names the same element. Close it if "
        "one does not: the next failure is then raised as a defect.",
        "",
    ]
    lines += _table("Selectors healed", heals, [
        ("Key", lambda r: f"`{r['page']}.{r['key']}`"),
        ("Old", lambda r: f"`{r['old']}`"), ("New", lambda r: f"`{r['new']}`"),
        ("How", lambda r: r["how"])])
    if tests:
        lines += ["**Failing tests it fixes:**", ""]
        lines += [f"- `{t}` ({', '.join(f'`{k}`' for k in keys)})"
                  for t, keys in sorted(tests.items())]
        lines.append("")
    lines += ["_Proposed by `scripts.heal_selectors` (PW2). Nothing is merged by an agent._"]
    return "\n".join(lines)


def pending_keys(body: str) -> set:
    """{(page, key)} an open heal pull request changes."""
    return set(_KEY_LINE.findall(body or ""))


def proposed_changes(body: str) -> set:
    """{(page, key, new selector)} a heal pull request's body proposes. One a
    person closed without merging is never proposed again: the next failure
    is raised as a defect, as its body promised."""
    out = set()
    for line in (body or "").splitlines():
        m = _KEY_LINE.match(line)
        if m and " -> " in line:
            out.add((m.group(1), m.group(2), line.rsplit(" -> ", 1)[1].strip()))
    return out


def test_case_comment(test: str, keys, pr_url: str, run_url: str) -> str:
    return (f"{MARKER} `{test}` failed on main ({run_url}) because the inventory "
            f"selector(s) of {', '.join(f'`{k}`' for k in keys)} match nothing on the live "
            f"page. The element is still there with another selector: the fix is proposed in "
            f"{pr_url}. No defect is raised for this failure while the fix is in review.")


def write_report(path: Path, healed: dict, not_healed: dict, prs: dict) -> None:
    """reports/heal.json: {"healed": {test: {"keys", "pr"}}, "not_healed": {test: why}}."""
    data = {"healed": {t: {"keys": keys, "pr": prs.get(t, "")} for t, keys in healed.items()},
            "not_healed": not_healed}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_report(path: Path) -> dict:
    """{test: {"keys", "pr"}} healed; {} when there is no report."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    healed = (data or {}).get("healed") if isinstance(data, dict) else None
    return healed if isinstance(healed, dict) else {}
