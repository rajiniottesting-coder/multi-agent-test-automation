"""AI metrics: what the agents cost and how often their work held (Group B, RP5).

WHY
    Each story shows its own cost (the usage ledger) and each pull request its
    own review, but nothing added them up: what a story costs on average,
    which agent spends most, how often generated code was right the first
    time, how often an agent stopped and needed a person, what the reviewer
    finds, and how well Agent 0 predicts what a change touches. Those decide
    whether the pipeline earns its spend - and they were posted, never read.

WHAT
    The Reports run reads every story changed in the reporting window and
    keeps one record per story on the results store (`ai_metrics.json`), so a
    story deleted or archived later stays in the figures:

      cost           its usage entries across ALL attempts, per agent
                     (core/usage_ledger.py all_attempts)
      first attempt  coded (`ai-coded`) with one Agent 2 run - the initial
                     one, not failed - and no new attempt; None while not coded
      refusals       the agents' stop notices on it, by kind (Agent 1 handing
                     it back, Agent 2's gate, approval, partial automation,
                     an update stopped) and its budget holds
      reviews        Agent 3's latest review of each of its pull requests:
                     verdict and findings by severity (hidden property
                     `agent3.review.<pr>`, written by Agent 3)
      prediction     Agent 0's outcome per pull request: predicted vs the
                     tests that changed or failed (`agent0.outcome.*`, or the
                     `[agent0:outcome]` comment)

    summary() adds them up for the stories active in the window; the History
    page and the PDF show it. Nothing calls a model.

Generic: markers and property names are the framework's own; labels come
from config.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_FILE = "ai_metrics.json"
REVIEW_PREFIX = "agent3.review."
OUTCOME_PREFIX = "agent0.outcome."
OUTCOME_MARKER = "[agent0:outcome]"

# The agents' stop notices - a person was needed before the story could go on.
REFUSALS = {
    "[agent1:stopped]": "Agent 1 handed the story back",
    "[agent2:blocked]": "Agent 2's gate refused the code",
    "[agent2:approval]": "an approval was refused",
    "[agent2:incomplete]": "automated only in part",
    "[agent2:update-stopped]": "an update was stopped",
}
CODER = "Agent 2 (Coder"
NOT_A_CODING_RUN = ("waiting",)
FIRST_RUN_MODES = ("", "initial")


def settings() -> dict:
    from core.ops_settings import section
    return section("ai_metrics")


# ── one story ──────────────────────────────────────────────────────────

def _review_value(value) -> dict | None:
    return value if isinstance(value, dict) and value.get("verdict") else None


def _outcomes_from_comments(bodies) -> list:
    out = []
    for body in bodies or []:
        if not (body or "").startswith(OUTCOME_MARKER):
            continue
        try:
            out.append(json.loads(body.split("\n", 1)[1]))
        except (IndexError, ValueError):
            continue
    return out


def story_record(tracker, story: dict, coded_label: str) -> dict:
    """One story's figures. `story`: {"key", "labels", "updated"}."""
    from core import usage_ledger as ul
    key = story["key"]
    bodies = tracker.get_comments(key) or []
    used = ul.all_attempts(key, tracker, bodies)
    by_agent: dict = {}
    cost, priced = 0.0, True
    for row in ul.by_agent(used["entries"]):
        by_agent[row["agent"]] = round(row["cost_usd"], 6) if row["priced"] else None
        if row["priced"]:
            cost += row["cost_usd"]
        else:
            priced = False
    coding = []
    for e in used["entries"]:
        if not e["agent"].startswith(CODER):
            continue
        _base, run_mode = ul.agent_parts(e["agent"])
        if run_mode in NOT_A_CODING_RUN:
            continue
        coding.append(run_mode)
    coded = coded_label in (story.get("labels") or [])
    first = None
    if coded and coding:
        first = used["resets"] == 0 and len(coding) == 1 and coding[0] in FIRST_RUN_MODES
    refusals = {}
    for marker, kind in REFUSALS.items():
        n = sum(1 for b in bodies if (b or "").startswith(marker))
        if n:
            refusals[kind] = n
    if used["holds"]:
        refusals["held by the spend budget"] = used["holds"]
    props = {}
    if ul.mode(tracker) == "properties":
        try:
            props = ul.read_properties(tracker, key, "agent")
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s: agent properties not read: %s", key, e)
    reviews = [v for k, v in sorted(props.items())
               if k.startswith(REVIEW_PREFIX) and _review_value(v)]
    outcomes = [v for k, v in sorted(props.items())
                if k.startswith(OUTCOME_PREFIX) and isinstance(v, dict)]
    outcomes += _outcomes_from_comments(bodies)
    return {"key": key, "updated": str(story.get("updated") or "")[:10],
            "cost_usd": round(cost, 6), "priced": priced, "by_agent": by_agent,
            "runs": len(used["entries"]), "coding_runs": len(coding), "attempts":
            used["resets"] + 1, "coded": coded, "first_attempt": first,
            "refusals": refusals, "reviews": reviews,
            "predictions": [{"recall": o.get("recall"), "precision": o.get("precision"),
                             "predicted": list(o.get("predicted") or []),
                             "actual": sorted(set(o.get("actual_changed") or [])
                                              | set(o.get("actual_failed") or []))}
                            for o in outcomes]}


# ── the store ──────────────────────────────────────────────────────────

def read(store: Path) -> dict:
    try:
        data = json.loads((Path(store) / STORE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"stories": {}}
    return data if isinstance(data, dict) and isinstance(data.get("stories"), dict) \
        else {"stories": {}}


def sync(store: Path, tracker, now: _dt.datetime, days: int, keep_days: int,
         coded_label: str = "ai-coded", story_type: str = "Story") -> dict | None:
    """Read the stories changed in the last `days` into the store. None when
    the tracker cannot be read - the store is then left as it is."""
    from integrations.tracker import capability
    find = capability(tracker, "defects_for_history")       # any issue type, by update
    if find is None:
        return None
    since = (now - _dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    stories = find(story_type, updated_since=since)
    if stories is None:
        return None
    data = read(store)
    recs = data["stories"]
    read_n = 0
    # Throw-away stories (cleanup.delete_label) are left out, as from the
    # defect history: label them, let a Reports run drop them, then delete
    # them (14 Nov 2026: a validation story's spend and review were counted).
    from core.ops_settings import section
    throw_away = section("cleanup").get("delete_label") or ""
    for story in stories:
        if throw_away and throw_away in (story.get("labels") or []):
            recs.pop(story["key"], None)
            continue
        try:
            rec = story_record(tracker, story, coded_label)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s: AI metrics not read: %s", story.get("key"), e)
            continue
        read_n += 1
        if rec["runs"] or rec["refusals"] or rec["reviews"] or rec["predictions"]:
            recs[rec["key"]] = rec
        else:
            recs.pop(rec["key"], None)
    cut = (now - _dt.timedelta(days=keep_days)).date().isoformat()
    for key in [k for k, r in recs.items() if (r.get("updated") or "") < cut]:
        recs.pop(key)
    data["synced"] = now.isoformat()
    Path(store).mkdir(parents=True, exist_ok=True)
    (Path(store) / STORE_FILE).write_text(json.dumps(data, indent=1, sort_keys=True),
                                          encoding="utf-8")
    return {"read": read_n, "kept": len(recs)}


# ── the figures ────────────────────────────────────────────────────────

def _share(n: int, of: int) -> float | None:
    return None if not of else round(100.0 * n / of, 1)


def summary(records: dict, since: str) -> dict:
    """The window's figures: the stories updated on or after `since`."""
    recs = [r for r in records.values() if (r.get("updated") or "") >= since]
    costed = [r for r in recs if r.get("runs")]
    total = round(sum(r["cost_usd"] for r in costed), 2)
    agents: dict = {}
    for r in costed:
        for agent, cost in (r.get("by_agent") or {}).items():
            agents[agent] = agents.get(agent, 0.0) + (cost or 0.0)
    coded = [r for r in recs if r.get("first_attempt") is not None]
    first = sum(1 for r in coded if r["first_attempt"])
    refusals: dict = {}
    for r in recs:
        for kind, n in (r.get("refusals") or {}).items():
            refusals[kind] = refusals.get(kind, 0) + n
    severities = {"blocking": 0, "major": 0, "minor": 0, "info": 0}
    reviews = [v for r in recs for v in r.get("reviews") or []]
    for v in reviews:
        for sev, n in (v.get("counts") or {}).items():
            severities[sev] = severities.get(sev, 0) + int(n or 0)
    tp = predicted = actual = 0
    preds = [p for r in recs for p in r.get("predictions") or []]
    for p in preds:
        hit = len(set(p["predicted"]) & set(p["actual"]))
        tp, predicted, actual = tp + hit, predicted + len(p["predicted"]), actual + len(p["actual"])
    return {
        "stories": len(recs), "costed": len(costed), "cost_usd": total,
        "cost_per_story": round(total / len(costed), 2) if costed else None,
        "by_agent": sorted(((a, round(c, 2)) for a, c in agents.items()),
                           key=lambda x: -x[1]),
        "priced": all(r.get("priced", True) for r in costed),
        "coded": len(coded), "first_attempt": first,
        "first_attempt_rate": _share(first, len(coded)),
        "refusals": sorted(refusals.items(), key=lambda x: -x[1]),
        "refusal_total": sum(refusals.values()),
        "reviews": len(reviews),
        "changes_requested": sum(1 for v in reviews if v.get("verdict") == "request_changes"),
        "findings": severities,
        "predictions": len(preds),
        "recall": _share(tp, actual), "precision": _share(tp, predicted),
        "costliest": [(r["key"], r["cost_usd"]) for r in
                      sorted(costed, key=lambda r: -r["cost_usd"])[:5]],
    }


# ── Agent 3's side ─────────────────────────────────────────────────────

def record_review(tracker, story_key: str, pr_number: int, verdict: str, issues) -> bool:
    """Agent 3: keep the latest review of this pull request on its story
    (hidden property). Best effort: never fails the review."""
    from integrations.tracker import capability
    put, get = capability(tracker, "set_property"), capability(tracker, "get_property")
    if put is None or not story_key:
        return False
    counts: dict = {}
    for issue in issues or []:
        sev = getattr(issue, "severity", None) or "info"
        counts[sev] = counts.get(sev, 0) + 1
    key = f"{REVIEW_PREFIX}{pr_number}"
    try:
        before = (get(story_key, key) if get else None) or {}
        put(story_key, key, {"pr": pr_number, "verdict": verdict, "counts": counts,
                             "reviews": int(before.get("reviews", 0) or 0) + 1,
                             "at": _dt.datetime.now(_dt.timezone.utc).isoformat()})
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Review of PR #%s not recorded on %s: %s", pr_number, story_key, e)
        return False
