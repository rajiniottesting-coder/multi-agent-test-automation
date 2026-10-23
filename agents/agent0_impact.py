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
    10              the outcome line, recorded by Agent 5 when the change
                    story's pull request runs (record_outcome); reconcile
                    (core.impact_reconcile, scheduled on its own)

Safety:
    agents.agent0_impact.enabled false  -> the scan does nothing
    shadow_mode true                    -> reports only: no review, no label,
                                           no hand-over (the trigger label is
                                           consumed; outcomes are still measured)
    reconcile (C7) runs in its own job (scripts.impact_reconcile), whatever
    these two say: it acts only on stories a hand-over labelled impact-applied

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
import re
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
        report = ia.extract(reviews[-1]["description"])
        if report is None:
            logger.warning("%s: the Agent 0 data in %s cannot be read - the repeat check, "
                           "the delta and the outcome measurement will treat the story as "
                           "never analysed.", story_key, reviews[-1]["key"])
        return report, reviews[-1]
    for body in reversed(tracker.get_comments(story_key)):
        if body.startswith(REPORT):
            if " - review " in body.split("\n", 1)[0]:
                # The report of a review that no longer counts (undone by
                # reconcile): the story has no current analysis.
                return None, None
            report = ia.extract(body)
            if report is None:
                logger.warning("%s: the Agent 0 data in the latest report comment cannot "
                               "be read.", story_key)
            return report, None
    return None, None


def requirement_hash(story: dict) -> str:
    """Stage 0: what a requirement analysis depends on - the story's text and
    Components. Computed before any model call, so a repeat is free."""
    return ia.content_hash(story["summary"], story.get("description") or "",
                           sorted(story.get("components") or []))


def _already_analysed(tracker, story_key: str, chash: str, settings: dict) -> bool:
    """Stage 0 guard: this exact content was already published.

    In live mode a report published in SHADOW mode does not count: it created
    no review, so switching shadow mode off must give the story a real one."""
    previous, review = _previous_report(tracker, story_key, settings)
    if not previous or previous.get("content_hash") != chash:
        return False
    if settings["shadow_mode"] or review:
        return True
    last = next((b for b in reversed(tracker.get_comments(story_key)) if b.startswith(REPORT)), "")
    return "(shadow mode)" not in last.split("\n", 1)[0]


def analyse_and_publish(tracker, story_key: str, llm, settings: dict, root: Path,
                        host=None, dry_run: bool = False, uncovered: dict | None = None) -> dict:
    """The requirement trigger, stage 0 first: an unchanged story costs no
    model call. Its impact-check label is consumed either way.

    `uncovered` (the nightly uncovered-element snapshot) feeds the optional
    hint. It is not part of the stage-0 hash: a new snapshot alone does not
    re-analyse a story, because that would cost model calls every night."""
    _start_usage()
    story = tracker.get_story(story_key)
    if _already_analysed(tracker, story_key, requirement_hash(story), settings):
        if not dry_run:
            tracker.remove_label(story_key, settings["labels"]["check"])
        return {"story": story_key, "action": "unchanged"}
    report = analyse_requirement(tracker, story_key, llm, settings, root, host,
                                 uncovered=uncovered)
    result = publish(tracker, story_key, report, settings, dry_run=dry_run)
    if result.get("action") == "nothing-to-review":
        # Released straight to ai-ready: no hand-over will follow, so the
        # context update is proposed now.
        result.update(_propose_context(tracker, host, llm, story_key, settings, root))
    if not dry_run:
        _post_usage(tracker, story_key)
    return result


def _start_usage() -> None:
    """Per-story numbers: nothing from an earlier story in this process counts."""
    from core.llm_client import reset_usage
    reset_usage()


def _post_usage(tracker, story_key: str) -> None:
    """Put this story's Agent 0 model cost on the story's ledger, so Agent 5's
    end-to-end table includes the analysis. Best-effort; never raises.

    Agent 0 opens a change story's attempt. If the ledger (after the last
    reset) already holds entries from agents that run AFTER it, those belong
    to an earlier attempt - a retry after an undo, or a story re-analysed
    once drafted - so a reset boundary goes first. Agent 0's own entries from
    re-analyses within one attempt accumulate, as rework on an attempt does."""
    from core.llm_client import log_usage_summary, reset_usage
    from core.usage_ledger import (
        IMPACT_ANALYST,
        has_usage_comments,
        post_reset_to_story,
        post_usage_to_story,
    )
    try:
        usage = log_usage_summary(f"story {story_key} (impact analysis)")
        reset_usage()
        if not usage.get("llm_calls"):
            return                       # stage 0 or nothing judged: no cost to record
        if has_usage_comments(tracker.get_comments(story_key),
                              ignore_agents=(IMPACT_ANALYST,)):
            post_reset_to_story(story_key, reason="change story analysed again",
                                jira=tracker)
        post_usage_to_story(story_key, IMPACT_ANALYST, usage, jira=tracker)
    except Exception as e:                                     # noqa: BLE001
        logger.warning("Usage ledger for %s not posted: %s", story_key, e)


def _propose_context(tracker, host, llm, story_key: str, settings: dict, root: Path) -> dict:
    """The context-update pull request (core.context_update). Never fails the
    hand-over it follows: that is already done and must stand."""
    if host is None or llm is None or not (settings.get("context_update") or {}).get("enabled"):
        return {}                         # off: the result keeps its usual shape
    from core.context_update import propose_for_story
    try:
        out = propose_for_story(tracker, host, llm, story_key, settings, Path(root))
        return {"context": out.get("context"), "context_pr": out.get("url")}
    except Exception as e:                                         # noqa: BLE001
        logger.error("context update for %s failed: %s", story_key, e, exc_info=True)
        return {"context": "error", "context_error": str(e)}


def _render_report(report: dict, title: str) -> str:
    lines = [f"{REPORT} {title} | hash: {report['content_hash']} | graph: {report['graph_sha']}"]
    if report["no_component"]:
        lines.append(f"No Component: whole-suite analysis, {len(report['not_judged'])} "
                     "tests not judged.")
    lines.append(f"Affected: {len(report['ranked'])}; unaffected: {len(report['unaffected'])}; "
                 f"not judged: {len(report['not_judged'])}.")
    if report.get("by_owner"):
        lines.append("By owning story: " + "; ".join(
            f"{owner}: {', '.join(refs)}" for owner, refs in report["by_owner"].items()))
    if report["seeds"]["dropped"]:
        lines.append("Dropped invented element keys: " + ", ".join(report["seeds"]["dropped"]))
    lines += ["", "||Tier||Score||Test||Owner||Scenario||Evidence||"]
    for r in report["ranked"]:
        lines.append(f"|{r['tier']}|{r['score']}|{r['key'] or '-'}|{r['owner'] or '-'}|"
                     f"{r['title']}|{short_evidence(r).replace('|', '/')}|")
    if report["not_judged"]:
        lines += ["", "Not judged (beyond max_candidates, never shown as unaffected): "
                  + ", ".join(n["key"] or n["ref"] for n in report["not_judged"][:50])]
    lines += _manual_section(report)
    return "\n".join(lines) + "\n\n" + ia.embed(report)


_ELEMENT_IN_PATH = re.compile(r"element (\S+:\S+)")
_EVIDENCE_LIMIT = 240


def short_evidence(row: dict) -> str:
    """One readable line per test for the tables a person reads.

    The full structural paths repeat every element a scenario reaches and
    made the Impact Review hard to read; they stay in the embedded data.
    A person needs WHY the test is affected - the model's reason - and which
    of the changed elements it touches.
    """
    elements = sorted(set(_ELEMENT_IN_PATH.findall(row.get("evidence") or "")))
    reason = " ".join((row.get("reason") or "").split())
    parts = []
    if reason:
        parts.append(reason if len(reason) <= _EVIDENCE_LIMIT
                     else reason[:_EVIDENCE_LIMIT - 3].rsplit(" ", 1)[0] + "...")
    if elements:
        parts.append("Elements: " + ", ".join(elements))
    if not parts:
        text = " ".join((row.get("evidence") or "-").split())
        parts.append(text if len(text) <= _EVIDENCE_LIMIT
                     else text[:_EVIDENCE_LIMIT - 3] + "...")
    return " - ".join(parts)


def _norm_path(path) -> str:
    try:
        from core.app_context import _normalize_path
        return _normalize_path(path or "")
    except Exception:
        return path or ""


def _reserved_paths() -> set:
    try:
        from core.app_context import AppContext
        return set(AppContext.load().reserved_paths_normalized())
    except Exception:                      # no app config (tests, other trackers)
        return set()


def _manual_section(report: dict) -> list:
    """Affected scenarios that have no test case cannot be decided in the
    Impact Review or handed over, so they would otherwise vanish from it.
    They are listed here for a person to revise by hand, with why."""
    unmarked = [r for r in report["ranked"] if not r.get("key")]
    if not unmarked:
        return []
    reserved = _reserved_paths()
    lines = ["", "Revise by hand - affected, but not decidable here (no test case):"]
    for r in unmarked:
        why = ("reserved file: the agents never edit it" if _norm_path(r.get("file")) in reserved
               else "no test case marker: link one and it becomes a review row")
        lines.append(f"* {r['ref']} ({r['tier']}, {r['score']}) - {why}")
    return lines


def _review_rows(report: dict, decided: dict | None = None) -> list:
    rows = []
    for r in sorted(report["ranked"], key=lambda r: (r["owner"] or "~", -r["score"])):
        if not r["key"]:
            continue                     # an unmarked scenario has no test case to decide on
        decision = (decided or {}).get(r["key"])
        if r["blocked_by"]:
            decision = "blocked by " + ",".join(r["blocked_by"])
        rows.append({"key": r["key"], "owner": r["owner"], "tier": r["tier"], "score": r["score"],
                     "evidence": short_evidence(r), "decision": decision})
    return rows


# ─────────────────────────────────────────────────────────────
# Stages 2-6 for each trigger
# ─────────────────────────────────────────────────────────────

def analyse_requirement(tracker, story_key: str, llm, settings: dict, root: Path,
                        host=None, uncovered: dict | None = None) -> dict:
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
    # Uncovered-element hint: review-tier only, and only when switched on AND
    # the live uncovered snapshot was supplied. Off by default.
    if uncovered and settings.get("uncovered_hint", False):
        seeds, hits = ia.with_uncovered_hint(seeds, text, uncovered)
        if hits:
            logger.info("uncovered-element hint for %s: %s", story_key,
                        ", ".join(f"{p}.{e}" for p, e in hits))

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
    return ia.report_dict(story_key, requirement_hash(story), sha, ranked, not_judged,
                          no_component, seeds, dropped)


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

def _post_delta(tracker, story_key: str, change: dict | None, note: str = "") -> None:
    """D4: what a re-analysis added, removed and re-tiered. Posted on every
    live path that has an earlier report, so a removal is never silent."""
    if change is None:
        return                                   # a first analysis has nothing to compare
    if any(change.values()):
        tracker.add_comment(story_key, f"{DELTA} Re-analysed: added "
                            f"{[r['ref'] for r in change['added']]}, removed "
                            f"{[r['ref'] for r in change['removed']]}, tier changed "
                            f"{[(t['ref'], t['from'], t['to']) for t in change['tier_changed']]}."
                            + note)
    else:
        # A re-analysis runs only because the story changed (stage 0 skips an
        # unchanged one). Without this line a person sees a second full report
        # and has to compare it by hand to learn that the edit changed nothing.
        tracker.add_comment(story_key, f"{DELTA} Re-analysed after the story changed: "
                            "no change to the affected tests or their tiers." + note)


def publish(tracker, story_key: str, report: dict, settings: dict, dry_run: bool = False) -> dict:
    """Shadow: one report comment. Live: the Impact Review (or ai-ready when
    there is nothing to review), with D4's delta against an earlier report."""
    labels = settings["labels"]
    if _already_analysed(tracker, story_key, report["content_hash"], settings):
        if not dry_run:                                              # stage 0 guard
            tracker.remove_label(story_key, labels["check"])
        return {"story": story_key, "action": "unchanged"}
    previous, review = _previous_report(tracker, story_key, settings)
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
        # Shadow mode creates no review and adds no label, but it consumes the
        # trigger: Agent 1 skips impact-check (C1), so leaving it would hold
        # the story back for good and re-run the analysis on every scan.
        tracker.add_comment(story_key, _render_report(report, title + " (shadow mode)"))
        tracker.remove_label(story_key, labels["check"])
        return {"story": story_key, "action": "shadow-report", "affected": len(report["ranked"])}

    change = ia.delta(previous, report) if previous else None
    rows = _review_rows(report)
    if not rows:
        _post_delta(tracker, story_key, change)
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
            story_key, _review_rows(report, decided))
            + "\n".join(_manual_section(report)) + "\n\n" + ia.embed(report))
        review_key, action = review["key"], "review-updated"
    else:
        if review and change:
            # An approved review stands; the new one lists only what changed.
            # Removed tests are not rows - there is nothing left to decide on
            # them - so they are reported in the DELTA comment below, which is
            # posted on every path, including when no row remains.
            changed = {r["ref"] for r in change["added"]} | {t["ref"] for t in change["tier_changed"]}
            rows = [r for r in rows if any(x["ref"] in changed for x in report["ranked"]
                                           if x["key"] == r["key"])]
        if rows:
            description = (impact_review.render(story_key, rows, intro="Grouped by owning story.")
                           + "\n".join(_manual_section(report)) + "\n\n" + ia.embed(report))
            review_key = tracker.create_subtask(story_key, f"{prefix}: {story_key}", description)
            action = "review-created"
        else:
            review_key, action = review["key"], "no-new-impact"
    _post_delta(tracker, story_key, change,
                f" Nothing new to review; the approved review {review_key} stands."
                if action == "no-new-impact" else "")
    if action != "no-new-impact":
        # Stage 7: the ranked report on the change story itself, next to the
        # requirement, as well as the table in the Impact Review.
        tracker.add_comment(story_key, _render_report(report, f"{title} - review {review_key}"))
    # impact-check comes off on every path, or the next scan would analyse the
    # story again. With no new review the story keeps the labels it had.
    tracker.remove_label(story_key, labels["check"])
    if action != "no-new-impact":
        tracker.add_label(story_key, labels["proposed"])
    return {"story": story_key, "action": action, "review": review_key}


# ─────────────────────────────────────────────────────────────
# Stages 8-10 - hand-over, reconcile, outcome
# ─────────────────────────────────────────────────────────────

def hand_over_decided(tracker, settings: dict, host=None, llm=None,
                      root: Path | None = None, dry_run: bool = False) -> list:
    """Hand over every story whose Impact Review is Done and fully decided.

    dry_run: the real hand-over runs against a tracker that performs no
    writes (core.dry_run) and prints the writes it would make; the context
    update is not proposed, so a dry run costs no model call."""
    from core.impact_handover import HandoverRefused, decisions_from_review, handover
    out = []
    for s in tracker.find_stories_to_process(
            {"issue_type": "Story", "required_labels": [settings["labels"]["proposed"]]},
            max_results=50):
        _start_usage()
        try:
            review_key, decisions = decisions_from_review(tracker, s["key"], settings)
            if dry_run:
                from core import dry_run as dry
                recorder = dry.tracker(tracker)
                handover(recorder, s["key"], decisions, review_key=review_key, settings=settings)
                for line in recorder.describe():
                    print(line)
                out.append({"story": s["key"], "action": "would-hand-over", "review": review_key,
                            "writes": len(recorder.writes)})
                continue
            handover(tracker, s["key"], decisions, review_key=review_key, settings=settings)
            result = {"story": s["key"], "action": "handed-over", "review": review_key}
        except HandoverRefused as e:
            out.append({"story": s["key"], "action": "waiting", "why": str(e)})
            continue
        if root is not None:
            result.update(_propose_context(tracker, host, llm, s["key"], settings, root))
        _post_usage(tracker, s["key"])           # the context update's model calls
        out.append(result)
    return out


def record_outcome(tracker, story_key: str, settings: dict, changed, failed,
                   ref: str) -> dict | None:
    """Stage 10: the prediction against what the pull request's run showed,
    once per pull request. Works in shadow mode too - measuring is what the
    shadow period is for (design section 10). Called by Agent 5
    (core.impact_results.record_prediction_outcome)."""
    head = f"{OUTCOME} pr: {ref} "
    if any(c.startswith(head) for c in tracker.get_comments(story_key)):
        return None
    report, _review = _previous_report(tracker, story_key, settings)
    if not report:
        return None                                   # no prediction, nothing to measure
    predicted = [r["key"] for r in report["ranked"] if r["key"]]
    result = ia.outcome(predicted, changed, failed)
    tracker.add_comment(story_key, f"{head}| recall: {result['recall']} precision: "
                                   f"{result['precision']}\n{json.dumps(result)}")
    return result


def scan(tracker, host, llm, settings: dict | None = None, root: Path | None = None,
         uncovered: dict | None = None, dry_run: bool = False) -> list:
    """The scheduled scan: analyse every impact-check story, then hand over
    decided reviews. dry_run reaches both: reports are printed, not posted,
    and the hand-over prints the writes it would make (no context update)."""
    from config.paths import PROJECT_ROOT
    settings = settings or impact_settings()
    root = Path(root or PROJECT_ROOT)
    if not settings["enabled"] and not dry_run:
        logger.info("agents.agent0_impact.enabled is false - nothing to do.")
        return []
    results = []
    for s in tracker.find_stories_to_process(settings["selection"], max_results=10):
        try:
            results.append(analyse_and_publish(tracker, s["key"], llm, settings, root, host,
                                               dry_run=dry_run, uncovered=uncovered))
        except Exception as e:                                 # noqa: BLE001
            logger.error("Agent 0 failed on %s: %s", s["key"], e, exc_info=True)
            results.append({"story": s["key"], "action": "error", "error": str(e)})
    if settings["shadow_mode"]:
        return results                    # shadow mode never writes past a report
    # Reconcile (C7) is not run here: it has its own scheduled job
    # (scripts.impact_reconcile), which also covers hand-overs a person made
    # and shadow mode. Running it in two places would let two concurrent
    # runs count as the two scans that trigger an undo.
    results += hand_over_decided(tracker, settings, host=host, llm=llm, root=root,
                                 dry_run=dry_run)
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
    ap.add_argument("--uncovered-snapshot", metavar="PATH",
                    help="--scan / --story: a check_inventory_staleness --compare report. "
                         "Used only when uncovered_hint is on and the report is fresh.")
    args = ap.parse_args(argv)

    settings = impact_settings()
    if not settings["enabled"] and not args.dry_run:
        print("agents.agent0_impact.enabled is false - nothing to do (use --dry-run to preview).")
        return 0
    from integrations.repo_host import get_repo_host
    from core.llm_client import LLMClient
    tracker = get_tracker()
    host = get_repo_host()

    uncovered = _uncovered_for(args.uncovered_snapshot, settings)
    if args.scan:
        for r in scan(tracker, host, LLMClient(temperature=0.0), settings, PROJECT_ROOT,
                      uncovered=uncovered, dry_run=args.dry_run):
            print(r)
        return 0
    if args.story:
        print(analyse_and_publish(tracker, args.story.upper(), LLMClient(temperature=0.0),
                                  settings, PROJECT_ROOT, host, dry_run=args.dry_run,
                                  uncovered=uncovered))
        return 0
    if args.code_change:
        if not (args.base and args.head):
            ap.error("--code-change needs --base and --head")
        report = analyse_code_change(Path(args.base), Path(args.head), f"PR #{args.pr or '?'}",
                                     settings, tracker, host)
        body = _render_report(report, f"Impact of PR #{args.pr or '?'} (code change)")
        if args.dry_run or not args.pr:
            print(body)
        elif _posted_on_pr(host, args.pr, report["content_hash"]):
            print(f"PR #{args.pr}: unchanged since the last report")   # stage 0
        else:
            host.post_pr_comment(args.pr, body)
        return 0
    drift = json.loads(Path(args.drift_report).read_text(encoding="utf-8"))
    report = analyse_drift(drift, PROJECT_ROOT, settings, tracker, host)
    body = _render_report(report, "Impact of the nightly inventory drift")
    if args.dry_run or settings["shadow_mode"] or not report["ranked"]:
        print(body)
        return 0
    story = _open_drift_story(tracker, settings)
    if story is None:
        story = tracker.create_story(
            "Maintenance: inventory drift", "The nightly inventory check found drift.\n\n"
            + "\n".join(report["seeds"]["elements"] + report["seeds"]["pages"]),
            _drift_components(report, PROJECT_ROOT),
            [settings["labels"]["check"], settings["labels"]["drift"]])
    print(publish(tracker, story, report, settings))
    return 0


def _uncovered_for(path: str | None, settings: dict) -> dict | None:
    """The uncovered snapshot to pass on, or None. Read only when the hint is
    switched on; every reason it is not used is logged, never raised."""
    if not settings.get("uncovered_hint", False):
        return None
    uncovered, why_not = ia.load_uncovered_snapshot(
        path, settings.get("uncovered_max_age_hours", 48))
    if why_not:
        logger.info("uncovered-element hint not used: %s", why_not)
        return None
    return uncovered


def _drift_components(report: dict, root: Path) -> list:
    """The Components of the drifted pages - the maintenance-story template
    (design A1) carries a Component, like any story, so its later analysis
    is focused instead of whole-suite."""
    graph, _sha = load_graph(root)
    pages = {e.split(":", 1)[0] for e in report["seeds"]["elements"]} | set(report["seeds"]["pages"])
    return sorted({c for p in pages for c in graph.page_components.get(p, ())})


def _posted_on_pr(host, pr_number: int, chash: str) -> bool:
    """Stage 0 for the code-change trigger: every push re-runs the workflow,
    but a report whose content (the seeds) is unchanged is not posted again."""
    return any(c.startswith(REPORT) and f"| hash: {chash} |" in c.split("\n", 1)[0]
               for c in host.get_pr_comments(pr_number))


def _open_drift_story(tracker, settings: dict) -> str | None:
    """The drift maintenance story still open, if any.

    Drift persists until someone fixes the inventory, so the nightly job finds
    it again and again. One story carries it: publish() then treats a repeat
    as a re-analysis (D4) - unchanged drift is skipped by the stage-0 guard, an
    open review is updated in place, an approved one gets a difference-only
    review - instead of a new story every night."""
    found = tracker.find_stories_to_process(
        {"issue_type": "Story", "required_labels": [settings["labels"]["drift"]],
         "allowed_statuses": settings["selection"]["allowed_statuses"]}, max_results=10)
    return found[0]["key"] if found else None


if __name__ == "__main__":
    sys.exit(main())
