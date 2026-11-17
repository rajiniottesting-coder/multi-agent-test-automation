#!/usr/bin/env python3
"""Heal the selectors behind failures on main, before the triage raises defects (PW2).

    python -m scripts.heal_selectors --reports-dir reports --plan
    python -m scripts.heal_selectors --reports-dir reports --run-url <url> [--dry-run]

Run by Agent 4's triage job after a run on main, on the junit.xml Agent 4
finalised. `--plan` only reads the report - no browser, no model - and says
whether any failure is worth checking live (`needed=true|false` to
$GITHUB_OUTPUT), so the job installs a browser only then. Without it: read the
pages live, heal what can be healed in one pull request, and write
<reports-dir>/heal.json for scripts.triage_failures. What is healed and what is
left alone: core/selector_heal.py.

--dry-run prints the pull request it would open and writes heal.json with no
test healed (the triage then raises as before). Settings: `live_browser`.

Exit code 0 whatever was found - an unhealed failure is raised by the triage;
1 only when the repository host refused the pull request.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from core import selector_heal as sh
from core.app_context import PROJECT_ROOT, AppContext

logger = logging.getLogger("heal_selectors")


def _output(name: str, value: str) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def read_page(page: str) -> dict | None:
    """The nightly check's report of one page (signed in, --compare), or None."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page.json"
        run = subprocess.run(
            [sys.executable, "-m", "scripts.check_inventory_staleness", "--page", page,
             "--compare", "--json", str(out)],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600)
        print(run.stdout[-3000:])
        try:
            report = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("page %s not read (exit %s)", page, run.returncode)
            return None
    return report if page in (report.get("pages") or {}) else None


def _unused_branch(host, base: str) -> str:
    branch, n = base, 1
    while host.branch_exists(branch):
        n += 1
        branch = f"{base}-{n}"
    return branch


def heal(root, *, s: dict, run_url: str, dry_run: bool, host=None,
         tracker=None, llm_factory=None, read=read_page) -> dict:
    """Heal what can be healed. Returns {"healed", "not_healed", "pr", "heals"}."""
    from core.defects import settings as defect_settings
    from core.impact_graph import build_impact_graph
    from core.inventory_update import dump_like, keys_in_open_prs
    failing = sh.healable(root, s.get("heal_failure_kinds") or [],
                          bool(defect_settings().get("only_after_retry", True)))
    tests = [t for t, _label, _text in failing]
    out = {"healed": {}, "not_healed": {}, "pr": "", "heals": []}
    if not tests:
        return out
    ctx = AppContext.load()
    original = ctx.inventory_path().read_text(encoding="utf-8")
    inventory = json.loads(original)
    graph = build_impact_graph(PROJECT_ROOT)
    reached = sh.keys_by_test(graph, tests)
    # Only the keys a failure quotes, when it quotes one: fewer pages to read.
    texts = {t: text for t, _label, text in failing}
    reached = {t: sh.narrow(keys, texts.get(t, ""), graph.selectors)
               for t, keys in reached.items()}
    steps = {}
    index = sh._scenario_index(graph)
    for t in tests:
        sc = sh.scenario_of(graph, t, index)
        steps[t] = list(sc.steps) if sc else []
    # Keys an open heal or nightly inventory pull request already changes.
    pending: dict = {}
    if host is not None:
        from core.impact_settings import impact_settings
        from core.inventory_update import settings as iu_settings
        nightly = iu_settings(impact_settings().get("inventory_update"))["branch_prefix"]
        for prefix in (s["heal_branch_prefix"], nightly):
            for k, url in keys_in_open_prs(host, prefix, ctx.inventory_file, inventory).items():
                pending.setdefault(k, url)
    # A heal a person closed without merging is not proposed again.
    rejected: set = set()
    if host is not None and hasattr(host, "list_closed_prs"):
        for pr in host.list_closed_prs(s["heal_branch_prefix"]):
            if not pr.get("merged"):
                rejected |= sh.proposed_changes(pr.get("body") or "")
    template = (PROJECT_ROOT / "prompts" / "heal_selector.md").read_text(encoding="utf-8")
    stale_all: set = set()
    fixed: dict = {}
    heals: list = []
    wanted = {k for keys in reached.values() for k in keys}
    checked: set = set()
    for page in sh.pages_to_check(reached, int(s["heal_max_pages"])):
        entry = (inventory.get("pages") or {}).get(page) or {}
        targets = {k for p, k in wanted if p == page}
        report = read(page)
        if report is None:
            continue
        checked.add(page)
        stale = {k: sel for k, sel in sh.stale_keys(report, page).items() if k in targets}
        cands, families = sh.candidates(report, page)
        for key, old in sorted(stale.items()):
            stale_all.add((page, key))
            if (page, key) in pending:
                fixed[(page, key)] = pending[(page, key)]
                continue
            name, how = sh.by_name(key, cands), "the live element has the key's name"
            if not name and cands and llm_factory is not None:
                users = [t for t in tests if (page, key) in reached[t]]
                prompt = sh.heal_prompt(template, page, entry.get("url", ""), key, old,
                                        str((entry.get("elements_notes") or {}).get(key) or ""),
                                        steps.get(users[0], []) if users else [], cands)
                name, why = sh.choose(llm_factory(), prompt, cands)
                how = f"chosen among {len(cands)} live element(s) by one model call: {why}"
            if not name:
                continue
            why_not = sh.fits(key, entry, name, families) or (
                "a person closed the pull request that proposed it"
                if (page, key, cands[name]) in rejected else "")
            if why_not:
                logger.info("%s.%s: %s not used - %s", page, key, name, why_not)
                continue
            heals.append({"page": page, "key": key, "old": old, "new": cands.pop(name),
                          "how": how})
    new, refused = sh.apply(inventory, heals)
    gone = {(r["page"], r["key"]) for r in refused}
    for r in refused:
        logger.info("%s.%s: not healed - %s", r["page"], r["key"], r["why"])
    heals = [h for h in heals if (h["page"], h["key"]) not in gone]
    for h in heals:
        fixed[(h["page"], h["key"])] = "this pull request"
    healed, not_healed = sh.healed_tests(reached, stale_all, fixed, checked)
    out.update(heals=heals, not_healed=not_healed)
    if not heals:
        # Every stale key is fixed by a pull request already open (or none is).
        return {**out, "healed": healed,
                "prs": {t: _pending_pr(keys, pending) for t, keys in healed.items()}}
    ours = {f"{h['page']}.{h['key']}" for h in heals}
    mine = {t: keys for t, keys in healed.items() if any(k in ours for k in keys)}
    body = sh.render_body(heals, mine, inventory_path=ctx.inventory_file, run_url=run_url)
    if dry_run or host is None:
        print(f"\n--dry-run: {len(heals)} selector(s) healed. The pull request would be:\n\n{body}")
        return {**out, "healed": {}, "prs": {}}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    branch = _unused_branch(host, f"{s['heal_branch_prefix']}{today}")
    host.create_branch(branch, "main")
    try:
        host.create_or_update_file(ctx.inventory_file, dump_like(original, new),
                                   f"fix(inventory): heal {len(heals)} changed selector(s)",
                                   branch)
        url = host.open_pull_request(
            f"fix(inventory): heal {len(heals)} selector(s) changed on the live page",
            body, branch, "main")
    except Exception:
        host.delete_branch(branch)        # never leave a half-written branch
        raise
    prs = {t: (url if t in mine else _pending_pr(keys, pending)) for t, keys in healed.items()}
    if tracker is not None:
        _tell_test_cases(tracker, healed, prs, run_url)
    return {**out, "healed": healed, "pr": url, "prs": prs}


def _pending_pr(keys, pending: dict) -> str:
    for k in keys:
        page, _, key = k.partition(".")
        if (page, key) in pending:
            return pending[(page, key)]
    return ""


def _tell_test_cases(tracker, healed: dict, prs: dict, run_url: str) -> None:
    from config.paths import FEATURES_DIR
    from core.defects import trace_of
    from integrations.tracker import add_markdown_comment
    for test, keys in healed.items():
        try:
            tc = trace_of(test, FEATURES_DIR, tracker).get("test_case")
            if tc and prs.get(test):
                add_markdown_comment(tracker, tc, sh.test_case_comment(test, keys, prs[test],
                                                                      run_url))
        except Exception as e:                                     # noqa: BLE001
            logger.warning("test case of %s not told: %s", test, e)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reports-dir", default="reports")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--plan", action="store_true",
                    help="only say whether a failure is worth checking live")
    ap.add_argument("--dry-run", action="store_true", help="print; open and post nothing")
    args = ap.parse_args(argv)
    from core.page_explore import settings
    s = settings()
    reports = Path(args.reports_dir)
    report_file = reports / sh.HEAL_FILE
    try:
        root = ET.parse(reports / "junit.xml").getroot()
    except (OSError, ET.ParseError) as e:
        print(f"No readable test report ({e}) - nothing to heal.")
        _output("needed", "false")
        return 0
    if not s.get("heal_selectors"):
        print("live_browser.heal_selectors is false - nothing healed.")
        _output("needed", "false")
        return 0
    if args.plan:
        from core.defects import settings as defect_settings
        failing = sh.healable(root, s.get("heal_failure_kinds") or [],
                              bool(defect_settings().get("only_after_retry", True)))
        for t, label, _text in failing:
            print(f"worth checking live: {t} ({label})")
        _output("needed", "true" if failing else "false")
        return 0
    host = tracker = None
    if not args.dry_run:
        try:
            from integrations.repo_host import get_repo_host
            from integrations.tracker import get_tracker
            host, tracker = get_repo_host(), get_tracker()
        except Exception as e:                                     # noqa: BLE001
            print(f"The repository host or the tracker cannot be used ({e}) - nothing healed.")
            sh.write_report(report_file, {}, {}, {})
            return 0
    from core.llm_client import LLMClient

    def llm_factory():
        return LLMClient(temperature=0.0, max_output_tokens=600)

    try:
        out = heal(root, s=s, run_url=args.run_url, dry_run=args.dry_run,
                   host=host, tracker=tracker, llm_factory=llm_factory)
    except Exception as e:                                         # noqa: BLE001
        logger.error("healing failed: %s - the triage raises every failure as before", e)
        sh.write_report(report_file, {}, {}, {})
        return 1
    sh.write_report(report_file, out["healed"], out["not_healed"], out.get("prs") or {})
    for h in out["heals"]:
        print(f"healed: {h['page']}.{h['key']}: {h['old']} -> {h['new']} ({h['how']})")
    for t, keys in out["healed"].items():
        print(f"no defect for {t}: fix in review ({', '.join(keys)})")
    for t, why in out["not_healed"].items():
        print(f"left to the triage: {t} - {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
