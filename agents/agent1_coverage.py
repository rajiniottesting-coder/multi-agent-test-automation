"""Agent 1, coverage-only mode: map a story's acceptance criteria to the test
cases it already has (C4).

WHY
    The traceability matrix says which test case verifies each acceptance
    criterion from Agent 1's coverage map - the `[agent1:coverage]` comment
    it posts when it drafts a story's test cases. A story whose test cases were
    written before Agent 1 posted maps (here: four stories drafted before 25
    Oct 2026), or by a person - every story of a project that adopts the
    framework with its tests already written - has none, so the matrix could
    only say "not mapped" for every one of its criteria.

WHAT
    For each story that has test cases and no coverage map:
      1. its criteria are read from the story text (extract_criteria, as when
         drafting) - a story with no acceptance-criteria list is reported, not
         guessed at;
      2. its test cases are read as they stand: the ones it owns in the tracker
         and the ones the suite's markers give it (the matrix's own set);
      3. one model call maps each criterion to the test case(s) that verify it,
         by key. NOTHING is drafted, changed or created; a criterion no test
         case verifies stays an honest gap;
      4. the map is checked as a draft's is (core/acceptance_coverage.py): a
         criterion left out or a key that is not one of the story's test cases
         is sent back once; a citation for a removal, restriction or limit
         whose test case has no step proving it is dropped - that criterion is
         a gap, with the reason;
      5. the map is posted as `[agent1:coverage]` (the comment Agent 1 posts
         for a new story), with the gaps listed. The reports read it unchanged.

    A story that has a map is left alone unless --force (a person changed its
    test cases). Throw-away stories (cleanup.delete_label) and stories the
    agents must not touch (`ai-skip`) are skipped. The model cost is recorded
    on the story as "Agent 1 (Test Designer, coverage map)", within the
    story's and the day's spend budget.

    python -m agents.agent1_coverage --story PRJ-1 [--story PRJ-2]
    python -m agents.agent1_coverage --all [--limit 10] [--force] [--dry-run]

Generic: the criteria come from the story text, the test cases from the
tracker and the markers; nothing here names an application.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("agent1_coverage")

AGENT_NAME = "Agent 1 (Test Designer, coverage map)"
DEFAULT_LIMIT = 10
DEFAULT_OUTPUT_TOKENS = 4096


def settings() -> dict:
    """agents.agent1_analyst.coverage_map in config.yaml (defaults if absent).
    Read here, not through agents.agent1_analyst: that module is started with
    `python -m`, and importing it by name would load a second copy of it."""
    import yaml
    from config.paths import CONFIG_YAML
    agents = (yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}).get("agents") or {}
    s = dict((agents.get("agent1_analyst") or {}).get("coverage_map") or {})
    s.setdefault("max_stories_per_run", DEFAULT_LIMIT)
    s.setdefault("max_output_tokens", DEFAULT_OUTPUT_TOKENS)
    s.setdefault("skip_labels", ["ai-skip"])
    return s


# ── which stories, and their test cases ────────────────────────────────

def stories_with_test_cases(tracker, features_dir: Path) -> dict:
    """{story key: {test case keys}} - every story that owns a test case the
    suite implements (its scenario marker, else the tracker's parent link).
    The same set the traceability matrix shows (scripts/build_site.py)."""
    from agents.agent2_coder import build_marker_index
    index = build_marker_index(features_dir)
    owners: dict = {}
    for key, entry in index.by_key.items():
        owner = getattr(entry, "owner", None) or tracker.get_parent_story_key(key)
        if owner:
            owners.setdefault(owner, set()).add(key)
    return owners


def story_test_cases(tracker, story_key: str, marked=()) -> list:
    """The story's test cases as they stand: [{"key", "summary",
    "description"}] - the ones it owns in the tracker, then any its scenarios'
    markers give it that the tracker no longer links."""
    cases = list(tracker.get_linked_test_cases(story_key) or [])
    have = {c["key"] for c in cases}
    for key in sorted(set(marked) - have):
        try:
            issue = tracker.get_story(key) or {}
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Test case %s not read: %s", key, e)
            continue
        cases.append({"key": key, "summary": issue.get("summary", ""),
                      "description": issue.get("description") or ""})
    return cases


# ── the map ────────────────────────────────────────────────────────────

def _cases_block(cases) -> str:
    return "\n\n".join(f"### {c.key} - {c.title}\n" + "\n".join(
        f"- {s.action} -> expected: {s.expected_result}".replace(" -> expected: ", " -> ")
        if s.action else f"- {s.expected_result}" for s in c.steps) for c in cases) or "(none)"


def check_map(criteria, coverage, cases) -> tuple:
    """(problems to send back, {criterion ref: why its citations are dropped}).

    Sent back: a criterion with no entry, or a citation that is not one of the
    story's test cases. Dropped: a citation for a removal, restriction or limit
    whose test case has no step proving it - the same obligation a draft
    meets (core.acceptance_coverage.coverage_problems), judged one criterion
    at a time so one weak citation never hides the others."""
    from core.acceptance_coverage import _ref, coverage_problems, index_cases
    keys = {c.key for c in cases}
    entries: dict = {}
    for e in coverage or []:
        entries.setdefault(_ref(e.criterion), []).append(e)
    problems, dropped = [], {}
    for c in criteria:
        if not c.mapped:
            continue
        if c.ref not in entries:
            problems.append(f"{c.ref} is not in your answer: give one entry for every criterion "
                            "(an empty covered_by when no test case verifies it).")
            continue
        cited = [k.strip() for e in entries[c.ref] for k in e.covered_by or []]
        bad = [k for k in cited if k not in keys]
        if bad:
            problems.append(f"{c.ref} cites {', '.join(bad)}, which is not one of this story's "
                            f"test cases. Cite only these keys: {', '.join(sorted(keys))}.")
            continue
        if cited and c.obligation:
            index = index_cases([(c2.key, c2) for c2 in cases if c2.key in cited])
            why = coverage_problems([c], entries[c.ref], index)
            if why:
                dropped[c.ref] = why[0]
    return problems, dropped


def map_story(tracker, llm, story_key: str, cases: list[dict], app: dict) -> dict:
    """Ask once, send back once. Returns {"criteria", "coverage", "dropped",
    "cases"} - nothing written here."""
    from config.paths import PROMPTS_DIR
    from core.acceptance_coverage import criteria_block, extract_criteria, written_case
    from core.schemas import CoverageMap
    story = tracker.get_story(story_key)
    criteria = extract_criteria(story.get("summary"), story.get("description"))
    if not any(c.mapped for c in criteria):
        return {"status": "no_criteria", "criteria": criteria}
    written = [written_case(c["key"], c.get("summary", ""), c.get("description", ""))
               for c in cases]
    mapped = [c for c in criteria if c.mapped]
    prompt = ((PROMPTS_DIR / "agent1_coverage.md").read_text(encoding="utf-8")
              .replace("{app_name}", app.get("name", ""))
              .replace("{app_base_url}", app.get("base_url", ""))
              .replace("{story_text}", f"Title: {story.get('summary', '')}\n\nDescription:\n"
                                       f"{story.get('description') or ''}")
              .replace("{criteria_block}", criteria_block(mapped))
              .replace("{test_cases_block}", _cases_block(written)))
    system = "You are a meticulous, expert QA test analyst."
    answer = llm.invoke_structured(system_prompt=system, user_prompt=prompt,
                                   output_schema=CoverageMap)
    problems, dropped = check_map(mapped, answer.coverage, written)
    if problems:
        logger.warning("%s: coverage map sent back once: %s", story_key, problems)
        answer = llm.invoke_structured(
            system_prompt=system, output_schema=CoverageMap,
            user_prompt=prompt + "\n\n# Your previous answer was rejected\n"
            + "\n".join(f"- {p}" for p in problems) + "\nReturn a corrected answer.")
        problems, dropped = check_map(mapped, answer.coverage, written)
        if problems:
            return {"status": "rejected", "criteria": mapped, "problems": problems}
    return {"status": "mapped", "criteria": mapped, "coverage": answer.coverage,
            "dropped": dropped, "cases": written}


def render(result: dict) -> tuple:
    """(comment body, gap refs). Each line names the cited test cases by key
    AND title, so the reports match them either way."""
    from core.acceptance_coverage import COVERAGE_MARKER, _ref, _short
    titles = {c.key: c.title for c in result["cases"]}
    entries: dict = {}
    for e in result["coverage"]:
        entries.setdefault(_ref(e.criterion), []).append(e)
    lines, gaps = [], []
    for c in result["criteria"]:
        group = entries.get(c.ref, [])
        why_dropped = result["dropped"].get(c.ref)
        keys = [] if why_dropped else list(dict.fromkeys(
            k.strip() for e in group for k in e.covered_by or []))
        how = "; ".join(e.how_verified for e in group if e.how_verified)
        if why_dropped:
            how = "no cited test case has the step that proves it: " + _short(why_dropped, 160)
        if not keys:
            gaps.append(c.ref)
        cited = ", ".join(f"{k} {titles.get(k, '')}".strip() for k in keys) or "(none)"
        lines.append(f"- {c.ref} {_short(c.text, 140)} -> {cited}"
                     + (f" | {_short(how, 200)}" if how else ""))
    body = (f"{COVERAGE_MARKER} Acceptance criteria and the test cases that verify them "
            f"(mapped from the story's existing test cases)\n" + "\n".join(lines))
    if gaps:
        body += (f"\n\nNot verified by any existing test case: {', '.join(gaps)}. "
                 "Add a test case for each - the traceability matrix shows them as gaps "
                 "until then.")
    return body, gaps


# ── one story, then many ───────────────────────────────────────────────

def _skip_reason(tracker, story_key: str, s: dict, force: bool) -> str | None:
    from core.acceptance_coverage import coverage_comment
    from core.ops_settings import section
    labels = set((tracker.get_story(story_key) or {}).get("labels") or [])
    throwaway = (section("cleanup").get("delete_label") or "").strip()
    if throwaway and throwaway in labels:
        return f"a throw-away story ({throwaway})"
    held = sorted(labels & set(s.get("skip_labels") or []))
    if held:
        return f"labelled {', '.join(held)}"
    if not force and coverage_comment(tracker.get_comments(story_key) or []):
        return "it has a coverage map (--force maps it again)"
    return None


def run(tracker, llm_factory, story_key: str, marked=(), dry_run: bool = False,
        force: bool = False, app: dict | None = None) -> dict:
    """Map one story. Returns {"story", "status", ...}; never posts on a dry run."""
    from core.usage_ledger import post_usage_to_story, story_usage
    from core.llm_client import log_usage_summary, reset_usage
    s = settings()
    why = _skip_reason(tracker, story_key, s, force)
    if why:
        return {"story": story_key, "status": "skipped", "why": why}
    cases = story_test_cases(tracker, story_key, marked)
    if not cases:
        return {"story": story_key, "status": "no_test_cases"}
    with story_usage(story_key, AGENT_NAME, jira=tracker, dry_run=dry_run):
        result = map_story(tracker, llm_factory(), story_key, cases, app or {})
        usage = log_usage_summary(f"story {story_key} (coverage map)")
        reset_usage()
        if not dry_run and (usage or {}).get("llm_calls"):
            post_usage_to_story(story_key, AGENT_NAME, usage, jira=tracker)
    out = {"story": story_key, "status": result["status"], "test_cases": len(cases)}
    if result["status"] == "rejected":
        out["problems"] = result["problems"]
        return out
    if result["status"] != "mapped":
        return out
    body, gaps = render(result)
    out.update({"gaps": gaps, "criteria": len(result["criteria"]), "comment": body})
    if not dry_run:
        from integrations.tracker import add_markdown_comment
        add_markdown_comment(tracker, story_key, body)
    return out


def main(argv=None) -> int:
    from config import REQUIRED_JIRA_ENV_VARS, REQUIRED_LLM_ENV_VARS, validate_required_env
    from config.paths import FEATURES_DIR
    from core.app_context import AppContext
    from core.llm_client import LLMClient
    from core.spend_budget import BudgetExceeded
    from integrations.tracker import get_tracker

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--story", action="append", default=[],
                    help="A story to map (repeat, or comma-separated)")
    ap.add_argument("--all", action="store_true",
                    help="Every story with test cases in the suite and no coverage map")
    ap.add_argument("--limit", type=int, default=None,
                    help="At most this many stories (default: coverage_map.max_stories_per_run)")
    ap.add_argument("--force", action="store_true", help="Map again a story that has a map")
    ap.add_argument("--dry-run", action="store_true", help="Print the maps; post nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    keys = [k.strip() for item in args.story for k in item.split(",") if k.strip()]
    if not keys and not args.all:
        ap.error("give --story KEY or --all")
    validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)
    s = settings()
    tracker = get_tracker()
    ctx = AppContext.load()
    owners = stories_with_test_cases(tracker, FEATURES_DIR)
    if args.all:
        keys = keys + [k for k in sorted(owners, key=lambda k: (len(k), k)) if k not in keys]
    limit = args.limit if args.limit is not None else int(s["max_stories_per_run"])
    cap = int(s["max_output_tokens"])

    def llm():
        return LLMClient(temperature=0.0, max_output_tokens=cap,
                         cap_setting="agents.agent1_analyst.coverage_map.max_output_tokens")
    results, done = [], 0
    for key in keys:
        if done >= limit:
            results.append({"story": key, "status": "left for the next run (--limit)"})
            continue
        try:
            r = run(tracker, llm, key, owners.get(key, ()), args.dry_run, args.force,
                    {"name": ctx.name, "base_url": ctx.base_url})
        except BudgetExceeded as e:
            logger.error("Spend budget reached at %s: %s", key, e)
            results.append({"story": key, "status": "held by the spend budget"})
            break
        except Exception as e:                                     # noqa: BLE001
            logger.exception("%s: not mapped", key)
            r = {"story": key, "status": "error", "why": str(e)[:300]}
        if r["status"] not in ("skipped",):
            done += 1 if r["status"] in ("mapped", "rejected", "error") else 0
        results.append(r)
    failed = False
    print("\nCoverage maps")
    for r in results:
        extra = (f"{r['criteria']} criteria, {r['test_cases']} test cases, gaps: "
                 f"{', '.join(r['gaps']) or 'none'}" if r["status"] == "mapped"
                 else r.get("why") or "; ".join(r.get("problems") or []))
        print(f"  {r['story']}: {r['status']}" + (f" - {extra}" if extra else ""))
        if r["status"] == "mapped" and args.dry_run:
            print("    " + r["comment"].replace("\n", "\n    "))
        failed |= r["status"] in ("rejected", "error", "held by the spend budget")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
