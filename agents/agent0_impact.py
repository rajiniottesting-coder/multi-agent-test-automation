"""
Agent 0 - Impact Analyst.

Role:
    Before a change is built, find the EXISTING tests it affects, so they are
    revised in the same change instead of failing after it.

Position in pipeline:
    [Agent 0: Impact] -> Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 -> Agent 5

Triggers (design section 7, stage 0):
    requirement   a story labelled impact-check (the scan)
    code change   a pull request touching pages/ or app_inventory/
    drift         the nightly inventory staleness report

Stages:
    0 guard         stop if this exact content was already analysed
    1 graph         core.impact_graph, built from the repository, cached per commit
    2 seeds         ChangeSeeds (one model call) for a requirement; code diff or
                    drift report otherwise - no model
    3 layer 1       structural candidates           (core.impact_analysis)
    4 layer 2       semantic candidates + the short-list rule
    5 layer 3       ImpactAssessment (one model call per max_candidates), every
                    reason checked against supplied evidence
    6 rank          deterministic score and tier
    7 publish       shadow: a report comment only. Live: an Impact Review
                    sub-task (C2's table) and impact-check -> impact-proposed
    8-9             the review, once Done, is handed over (core.impact_handover)
    10              reconcile (core.impact_reconcile) and the outcome line

Safety:
    agents.agent0_impact.enabled false  -> the scan does nothing
    shadow_mode true                    -> reports only: no review, no label,
                                           no hand-over, no reconcile

Usage:
    python -m agents.agent0_impact --scan
    python -m agents.agent0_impact --story SCRUM-210 --dry-run
    python -m agents.agent0_impact --code-change --base <dir> --head <dir> [--pr 12]
    python -m agents.agent0_impact --drift-report reports/drift.json
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from core import impact_analysis as ia
from core import impact_review
from core.impact_settings import impact_settings
from integrations.tracker import get_tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("agent0_impact")

REPORT = "[agent0:report]"
DELTA = "[agent0:delta]"
NO_COMPONENT = "[agent0:no-component]"
OUTCOME = "[agent0:outcome]"

_GRAPHS: dict = {}


# ─────────────────────────────────────────────────────────────
# Stage 1 - the graph, cached per commit
# ─────────────────────────────────────────────────────────────

def graph_sha(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()[:12]
    except Exception:                                          # noqa: BLE001
        return "worktree"


def load_graph(root: Path):
    from core.impact_graph import build_impact_graph
    root = Path(root)
    sha = graph_sha(root)
    key = (str(root.resolve()), sha)
    if sha == "worktree" or key not in _GRAPHS:
        _GRAPHS[key] = build_impact_graph(root)
    return _GRAPHS[key], sha


# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────

def _story_text(story: dict) -> str:
    return f"Title: {story['summary']}\n\nDescription:\n{story.get('description') or ''}"


def _owners_and_blocks(tracker, host, story_key: str, candidates: list) -> None:
    """Owner per candidate (marker first, tracker second) and the in-flight
    guard (D4): a test is blocked while another story that impacts it, or its
    owning story, still has an open pull request."""
    open_pr: dict = {}

    def has_open_pr(story: str) -> bool:
        if host is None:
            return False
        if story not in open_pr:
            open_pr[story] = host.find_open_pr_for_story(story) is not None
        return open_pr[story]

    for c in candidates:
        if not c.test_case_key:
            continue
        c.owner = c.owner or tracker.get_parent_story_key(c.test_case_key)
        others = [s for s in tracker.get_impacting_stories(c.test_case_key) if s != story_key]
        if c.owner and c.owner != story_key:
            others.append(c.owner)
        c.blocked_by = sorted({s for s in others if has_open_pr(s)})


def _previous_report(tracker, story_key: str, settings: dict):
    """(report, review) from the latest review or report comment, if any."""
    prefix = settings["review"]["summary_prefix"]
    reviews = [s for s in tracker.get_subtasks(story_key) if s["summary"].startswith(prefix)]
    if reviews:
        return ia.extract(reviews[-1]["description"]), reviews[-1]
    for body in reversed(tracker.get_comments(story_key)):
        if body.startswith(REPORT):
            return ia.extract(body), None
    return None, None


def _render_report(report: dict, title: str) -> str:
    lines = [f"{REPORT} {title} | hash: {report['content_hash']} | graph: {report['graph_sha']}"]
    if report["no_component"]:
        lines.append(f"No Component: whole-suite analysis, {len(report['not_judged'])} "
                     "tests not judged.")
    lines.append(f"Affected: {len(report['ranked'])}; unaffected: {len(report['unaffected'])}; "
                 f"not judged: {len(report['not_judged'])}.")
    if report["seeds"]["dropped"]:
        lines.append("Dropped invented element keys: " + ", ".join(report["seeds"]["dropped"]))
    lines += ["", "||Tier||Score||Test||Owner||Scenario||Evidence||"]
    for r in report["ranked"]:
        lines.append(f"|{r['tier']}|{r['score']}|{r['key'] or '-'}|{r['owner'] or '-'}|"
                     f"{r['title']}|{(r['evidence'] or '-').replace('|', '/')}|")
    if report["not_judged"]:
        lines += ["", "Not judged (beyond max_candidates, never shown as unaffected): "
                  + ", ".join(n["key"] or n["ref"] for n in report["not_judged"][:50])]
    return "\n".join(lines) + "\n\n" + ia.embed(report)


def _review_rows(report: dict, decided: dict | None = None) -> list:
    rows = []
    for r in sorted(report["ranked"], key=lambda r: (r["owner"] or "~", -r["score"])):
        if not r["key"]:
            continue                     # an unmarked scenario has no test case to decide on
        decision = (decided or {}).get(r["key"])
        if r["blocked_by"]:
            decision = "blocked by " + ",".join(r["blocked_by"])
        rows.append({"key": r["key"], "owner": r["owner"], "tier": r["tier"], "score": r["score"],
                     "evidence": r["evidence"], "decision": decision})
    return rows


# ─────────────────────────────────────────────────────────────
# Stages 2-6 for each trigger
# ─────────────────────────────────────────────────────────────

def analyse_requirement(tracker, story_key: str, llm, settings: dict, root: Path,
                        host=None) -> dict:
    from core.app_context import AppContext
    from core.schemas import ChangeSeeds, ImpactAssessment
    from config.paths import PROMPTS_DIR

    story = tracker.get_story(story_key)
    components = story.get("components") or []
    graph, sha = load_graph(root)
    text = _story_text(story)

    # Stage 2: seeds, one model call, checked against the inventory
    prompt = ((PROMPTS_DIR / "agent0_seeds.md").read_text(encoding="utf-8")
              .replace("{story_text}", text)
              .replace("{components}", ", ".join(components) or "(none)")
              .replace("{inventory_json}", AppContext.load().load_page_inventory_json(components)))
    change = llm.invoke_structured(system_prompt="You are a senior QA analyst.",
                                   user_prompt=prompt, output_schema=ChangeSeeds)
    seeds = ia.validate_requirement_seeds(change, graph, components)

    # Stages 3-4: candidates and the short list
    layer1 = ia.structural_candidates(graph, seeds)
    layer2, no_component = ia.semantic_candidates(graph, components, {c.ref for c in layer1})
    judged, not_judged = ia.shortlist(layer1, layer2, text, settings["max_candidates"])
    for c in judged:
        c.component = ia.component_match(c, graph, list(seeds.components))
    _owners_and_blocks(tracker, host, story_key, judged)

    # Stage 5: adjudication, at most max_candidates per call; layer 1 never dropped
    judgements, dropped = {}, []
    template = (PROMPTS_DIR / "agent0_adjudicate.md").read_text(encoding="utf-8")
    for chunk in ia.chunks(judged, settings["max_candidates"]):
        if not chunk:
            continue
        listing = "\n\n".join(
            f"## {c.id} - {c.title} ({c.file})\n"
            + "".join(f"{p['id']}: {p['text']}\n" for p in c.paths)
            + "Steps:\n" + "\n".join(f"  {s}" for s in c.steps) for c in chunk)
        assessment = llm.invoke_structured(
            system_prompt="You are a senior QA analyst.",
            user_prompt=template.replace("{story_text}", text)
            .replace("{behaviours}", "\n".join(f"- {b}" for b in seeds.behaviours) or "(none)")
            .replace("{candidates}", listing),
            output_schema=ImpactAssessment)
        kept, lost = ia.checked_assessments(assessment, chunk)
        judgements.update(kept)
        dropped += lost

    ranked = ia.rank(judged, judgements, settings["weights"], settings["thresholds"])
    chash = ia.content_hash(story["summary"], story.get("description") or "", sorted(components))
    return ia.report_dict(story_key, chash, sha, ranked, not_judged, no_component, seeds, dropped)


def analyse_code_change(base_root: Path, head_root: Path, change_ref: str, settings: dict,
                        tracker=None, host=None) -> dict:
    graph, sha = load_graph(base_root)
    seeds = ia.code_change_seeds(Path(base_root), Path(head_root))
    return _structural_report(graph, sha, seeds, change_ref, settings, tracker, host,
                              ia.content_hash(change_ref, sorted(map(str, seeds.methods)),
                                              sorted(map(str, seeds.elements))))


def analyse_drift(drift: dict, root: Path, settings: dict, tracker=None, host=None) -> dict:
    graph, sha = load_graph(root)
    seeds = ia.drift_seeds(drift)
    return _structural_report(graph, sha, seeds, "inventory-drift", settings, tracker, host,
                              ia.content_hash("drift", sorted(map(str, seeds.elements)),
                                              sorted(seeds.pages)))


def _structural_report(graph, sha, seeds, change_ref, settings, tracker, host, chash) -> dict:
    """Code change and drift: stages 2, 3 and 6 only - no model (D1)."""
    layer1 = ia.structural_candidates(graph, seeds)
    judged, _ = ia.shortlist(layer1, [], "", max(settings["max_candidates"], len(layer1)))
    if tracker is not None:
        _owners_and_blocks(tracker, host, change_ref, judged)
    ranked = ia.rank(judged, {}, settings["weights"], settings["thresholds"],
                     signals=("structural",))
    return ia.report_dict(change_ref, chash, sha, ranked, [], False, seeds, [])


# ─────────────────────────────────────────────────────────────
# Stage 7 - publish
# ─────────────────────────────────────────────────────────────

def publish(tracker, story_key: str, report: dict, settings: dict, dry_run: bool = False) -> dict:
    """Shadow: one report comment. Live: the Impact Review (or ai-ready when
    there is nothing to review), with D4's delta against an earlier report."""
    labels = settings["labels"]
    previous, review = _previous_report(tracker, story_key, settings)
    if previous and previous.get("content_hash") == report["content_hash"]:
        return {"story": story_key, "action": "unchanged"}           # stage 0 guard
    if dry_run:
        print(_render_report(report, f"Impact report for {story_key} (dry run)"))
        return {"story": story_key, "action": "dry-run"}

    if report["no_component"] and not any(
            c.startswith(NO_COMPONENT) for c in tracker.get_comments(story_key)):
        tracker.add_comment(story_key, f"{NO_COMPONENT} This story has no Component, so Agent 0 "
                            "compared it with the whole suite. Add a Component to focus the "
                            "analysis on the pages it changes.")

    title = f"Impact report for {story_key}"
    if settings["shadow_mode"]:
        tracker.add_comment(story_key, _render_report(report, title + " (shadow mode)"))
        return {"story": story_key, "action": "shadow-report", "affected": len(report["ranked"])}

    change = ia.delta(previous, report) if previous else None
    rows = _review_rows(report)
    if not rows:
        tracker.add_comment(story_key, _render_report(report, title))
        tracker.remove_label(story_key, labels["check"])
        tracker.add_label(story_key, labels["ready"])
        return {"story": story_key, "action": "nothing-to-review"}

    prefix = settings["review"]["summary_prefix"]
    done = settings["review"]["done_status"].strip().lower()
    if review and review["status"].strip().lower() != done:
        # An open review: replace it, keeping decisions already made on rows
        # that did not change.
        decided = impact_review.parse(review["description"])
        tracker.set_description(review["key"], impact_review.render(
            story_key, _review_rows(report, decided)) + "\n\n" + ia.embed(report))
        review_key, action = review["key"], "review-updated"
    else:
        if review and change:
            # An approved review stands; the new one lists only what changed.
            changed = {r["ref"] for r in change["added"]} | {t["ref"] for t in change["tier_changed"]}
            rows = [r for r in rows if any(x["ref"] in changed for x in report["ranked"]
                                           if x["key"] == r["key"])]
            if not rows:
                return {"story": story_key, "action": "no-new-impact"}
        description = (impact_review.render(story_key, rows, intro="Grouped by owning story.")
                       + "\n\n" + ia.embed(report))
        review_key = tracker.create_subtask(story_key, f"{prefix}: {story_key}", description)
        action = "review-created"
    if change and any(change.values()):
        tracker.add_comment(story_key, f"{DELTA} Re-analysed: added "
                            f"{[r['ref'] for r in change['added']]}, removed "
                            f"{[r['ref'] for r in change['removed']]}, tier changed "
                            f"{[(t['ref'], t['from'], t['to']) for t in change['tier_changed']]}.")
    tracker.remove_label(story_key, labels["check"])
    tracker.add_label(story_key, labels["proposed"])
    return {"story": story_key, "action": action, "review": review_key}


# ─────────────────────────────────────────────────────────────
# Stages 8-10 - hand-over, reconcile, outcome
# ─────────────────────────────────────────────────────────────

def hand_over_decided(tracker, settings: dict) -> list:
    from core.impact_handover import HandoverRefused, decisions_from_review, handover
    out = []
    for s in tracker.find_stories_to_process(
            {"issue_type": "Story", "required_labels": [settings["labels"]["proposed"]]},
            max_results=50):
        try:
            review_key, decisions = decisions_from_review(tracker, s["key"], settings)
            handover(tracker, s["key"], decisions, review_key=review_key, settings=settings)
            out.append({"story": s["key"], "action": "handed-over", "review": review_key})
        except HandoverRefused as e:
            out.append({"story": s["key"], "action": "waiting", "why": str(e)})
    return out


def record_outcome(tracker, story_key: str, settings: dict) -> dict | None:
    """Stage 10: recall and precision of the prediction, once per story."""
    if any(c.startswith(OUTCOME) for c in tracker.get_comments(story_key)):
        return None
    report, _review = _previous_report(tracker, story_key, settings)
    if not report:
        return None
    predicted = [r["key"] for r in report["ranked"] if r["key"]]
    actual = [c["key"] for c in tracker.get_impacted_test_cases(story_key, include_retired=True)]
    result = ia.outcome(predicted, actual)
    tracker.add_comment(story_key, f"{OUTCOME} recall: {result['recall']} precision: "
                                   f"{result['precision']}\n{json.dumps(result)}")
    return result


def scan(tracker, host, llm, settings: dict | None = None, root: Path | None = None) -> list:
    from config.paths import PROJECT_ROOT
    from core.impact_reconcile import reconcile_all
    settings = settings or impact_settings()
    root = Path(root or PROJECT_ROOT)
    if not settings["enabled"]:
        logger.info("agents.agent0_impact.enabled is false - nothing to do.")
        return []
    results = []
    for s in tracker.find_stories_to_process(settings["selection"], max_results=10):
        try:
            report = analyse_requirement(tracker, s["key"], llm, settings, root, host)
            results.append(publish(tracker, s["key"], report, settings))
        except Exception as e:                                 # noqa: BLE001
            logger.error("Agent 0 failed on %s: %s", s["key"], e, exc_info=True)
            results.append({"story": s["key"], "action": "error", "error": str(e)})
    if settings["shadow_mode"]:
        return results                    # shadow mode never writes past a report
    results += hand_over_decided(tracker, settings)
    for r in reconcile_all(tracker, host, settings):
        results.append(r)
        if r["action"] == "merged":
            record_outcome(tracker, r["story"], settings)
    return results


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    from config.paths import PROJECT_ROOT
    ap = argparse.ArgumentParser(prog="python -m agents.agent0_impact",
                                 description="Agent 0 (Impact Analyst)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scan", action="store_true", help="the scheduled scan")
    mode.add_argument("--story", help="analyse one story")
    mode.add_argument("--code-change", action="store_true", help="analyse a pull request's code change")
    mode.add_argument("--drift-report", help="analyse a staleness report (JSON)")
    ap.add_argument("--base", help="--code-change: checkout of the base branch")
    ap.add_argument("--head", help="--code-change: checkout of the pull request")
    ap.add_argument("--pr", type=int, help="--code-change: pull request number to comment on")
    ap.add_argument("--dry-run", action="store_true", help="print the report; write nothing")
    args = ap.parse_args(argv)

    settings = impact_settings()
    if not settings["enabled"] and not args.dry_run:
        print("agents.agent0_impact.enabled is false - nothing to do (use --dry-run to preview).")
        return 0
    from integrations.repo_host import get_repo_host
    from core.llm_client import LLMClient
    tracker = get_tracker()
    host = get_repo_host()

    if args.scan:
        for r in scan(tracker, host, LLMClient(temperature=0.0), settings, PROJECT_ROOT):
            print(r)
        return 0
    if args.story:
        report = analyse_requirement(tracker, args.story.upper(), LLMClient(temperature=0.0),
                                     settings, PROJECT_ROOT, host)
        print(publish(tracker, args.story.upper(), report, settings, dry_run=args.dry_run))
        return 0
    if args.code_change:
        if not (args.base and args.head):
            ap.error("--code-change needs --base and --head")
        report = analyse_code_change(Path(args.base), Path(args.head), f"PR #{args.pr or '?'}",
                                     settings, tracker, host)
        body = _render_report(report, f"Impact of PR #{args.pr or '?'} (code change)")
        if args.dry_run or not args.pr:
            print(body)
        else:
            host.post_pr_comment(args.pr, body)
        return 0
    drift = json.loads(Path(args.drift_report).read_text(encoding="utf-8"))
    report = analyse_drift(drift, PROJECT_ROOT, settings, tracker, host)
    body = _render_report(report, "Impact of the nightly inventory drift")
    if args.dry_run or settings["shadow_mode"] or not report["ranked"]:
        print(body)
        return 0
    story = tracker.create_story(
        "Maintenance: inventory drift", "The nightly inventory check found drift.\n\n"
        + "\n".join(report["seeds"]["elements"]), [], [settings["labels"]["check"]])
    print(publish(tracker, story, report, settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
