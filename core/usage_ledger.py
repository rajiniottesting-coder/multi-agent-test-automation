"""
Usage ledger — end-to-end LLM token & cost tracking per story, across agents.

PROBLEM: each agent runs in a separate CI process, so in-memory usage
tracking (core/llm_client.py) can only see ONE agent's calls. A story's true
end-to-end cost spans Agent 0 (impact analysis), Agent 1 (test designer),
Agent 2 (coder, possibly several update/regen/review-fix runs), Agent 3
(reviewer) and Agent 5 (reporter).

SOLUTION: the story itself is the ledger. Each agent run records one entry,
and the story shows the cost to people in ONE place. Two ways to store it,
chosen per tracker (`mode()`):

  properties (F-31, the default when the tracker can)
      Each run is a hidden issue property `llm.usage.<time>.<id>` (append-only:
      two agents finishing together never overwrite each other); a new attempt
      is `llm.reset.<time>.<id>`; a budget hold `llm.hold.<time>.<id>`. People
      see ONE cost comment per attempt, edited in place after every run without
      notifying anyone: a row per agent (its modes and run count), the total and
      the story budget. Agent 5's report carries one line pointing to it - the
      table is no longer repeated in every report, nor in a comment per run.
      A new attempt closes the old comment with a line saying why, and the next
      run opens a new one.

  comments (a tracker without issue properties or comment editing, or
      `usage_ledger.store: comments` in config.yaml)
      The original behaviour, unchanged: after each agent finishes it posts one
      machine-parseable comment, Agent 5 appends the table to its report.

          [LLM-USAGE] agent="Agent 2 (Coder)" calls=5 input_tokens=48213 \\
output_tokens=9877 input_cost_usd=0.144639 output_cost_usd=0.148155 \\
cost_usd=0.292794

Stories costed before the switch keep their `[LLM-USAGE]` / `[LEDGER-RESET]`
comments: they count, after their last reset, until the story's first
property-ledger reset (every later entry is a property, so nothing is counted
twice or lost).

Token usage and cost are tracked as SEPARATE quantities throughout:
tokens are always exact (reported by the API); cost is derived from the
LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M env vars and may be
absent ("n/a") if pricing isn't configured — aggregation handles both.

All posting/reading is best-effort: a tracker hiccup can never fail a run.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import uuid
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Appended to an agent's name in the usage entry of a run that raised (F-3).
FAILED_SUFFIX = " (failed)"

USAGE_MARKER = "[LLM-USAGE]"

# Boundary marker. Posted by Agent 1 when it re-processes a story that already
# carries usage entries (i.e. the story was reset to `ai-ready` and is being
# costed again from scratch). Only the entries AFTER the last reset count, so
# a discarded run's tokens never inflate the report.
#
# Deliberately NOT posted for ai-update / ai-regenerate: those are rework on the
# SAME costed story, and their tokens SHOULD accumulate into the lifetime total.
RESET_MARKER = "[LEDGER-RESET]"

# The agent that STARTS a change story's attempt. Its entries are the first
# cost of an attempt, so they never make a later agent think the story was
# costed before: has_usage() is told to ignore them by Agent 1.
IMPACT_ANALYST = "Agent 0 (Impact Analyst)"

# Issue-property ledger (F-31). Keys sort by time: `<prefix>.<UTC time>.<id>`.
PROP_USAGE = "llm.usage"
PROP_RESET = "llm.reset"
PROP_HOLD = "llm.hold"
PROP_COMMENT = "llm.comment"       # {"ref": what add_comment returned, "since", "reason"}

# Parses the machine-readable comment line. cost fields may be a float or "n/a".
_USAGE_RE = re.compile(
    r"\[LLM-USAGE\]\s+"
    r'agent="(?P<agent>[^"]+)"\s+'
    r"calls=(?P<calls>\d+)\s+"
    r"input_tokens=(?P<input_tokens>\d+)\s+"
    r"output_tokens=(?P<output_tokens>\d+)\s+"
    r"input_cost_usd=(?P<input_cost>n/a|[\d.]+)\s+"
    r"output_cost_usd=(?P<output_cost>n/a|[\d.]+)\s+"
    r"cost_usd=(?P<cost>n/a|[\d.]+)"
)
_RESET_REASON_RE = re.compile(r'\[LEDGER-RESET\](?:\s+reason="([^"]*)")?')


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _fmt_cost(value) -> str:
    """Format a cost value for the comment line: 6-decimal float or 'n/a'."""
    if value is None:
        return "n/a"
    return f"{value:.6f}"


# ─────────────────────────────────────────────────────────────
# Where the ledger lives
# ─────────────────────────────────────────────────────────────

def _store_setting() -> str:
    try:
        from core.ops_settings import section
        return str(section("usage_ledger").get("store", "auto")).strip().lower()
    except Exception:                                              # noqa: BLE001
        return "auto"


def mode(tracker) -> str:
    """'properties' when the tracker can keep the ledger hidden and edit the
    one cost comment in place, else 'comments' (the original behaviour)."""
    from integrations.tracker import capability
    if tracker is None or _store_setting() == "comments":
        return "comments"
    can_read = capability(tracker, "properties") is not None or (
        capability(tracker, "property_keys") is not None
        and capability(tracker, "get_property") is not None)
    if (can_read and capability(tracker, "set_property") is not None
            and capability(tracker, "update_comment") is not None):
        return "properties"
    return "comments"


def _read_properties(tracker, issue: str, prefix: str) -> dict:
    """{key: value} of the issue's properties under `prefix` (one request when
    the tracker offers `properties`)."""
    from integrations.tracker import capability
    read_all = capability(tracker, "properties")
    if read_all is not None:
        return dict(read_all(issue, prefix) or {})
    keys_of, get = capability(tracker, "property_keys"), capability(tracker, "get_property")
    return {k: get(issue, k) for k in (keys_of(issue) or []) if k.startswith(prefix)}


def _stamp(key: str) -> str:
    """The time part of `<prefix>.<time>.<id>` (sortable)."""
    parts = key.split(".")
    return parts[2] if len(parts) > 3 else ""


def _new_key(prefix: str) -> str:
    return f"{prefix}.{_now().strftime('%Y%m%dT%H%M%S%fZ')}.{uuid.uuid4().hex[:8]}"


def _cap(tracker, name: str):
    """An optional tracker operation, looked up as every caller must
    (integrations.tracker.capability); mode() has checked it exists."""
    from integrations.tracker import capability
    fn = capability(tracker, name)
    if fn is None:
        raise RuntimeError(f"the tracker has no {name}")
    return fn


def _tracker_or_default(jira):
    if jira is not None:
        return jira
    from integrations.tracker import get_tracker
    return get_tracker()


# ─────────────────────────────────────────────────────────────
# Comment format (the original ledger, and the one still read for old stories)
# ─────────────────────────────────────────────────────────────

def format_usage_comment(agent_name: str, usage: dict) -> str:
    """Build the machine-parseable usage comment body for a story.

    `usage` is the dict returned by llm_client.get_usage_summary() /
    log_usage_summary(): keys llm_calls, input_tokens, output_tokens,
    input_cost_usd, output_cost_usd, estimated_cost_usd.
    """
    line = (
        f'{USAGE_MARKER} agent="{agent_name}" '
        f"calls={usage.get('llm_calls', 0)} "
        f"input_tokens={usage.get('input_tokens', 0)} "
        f"output_tokens={usage.get('output_tokens', 0)} "
        f"input_cost_usd={_fmt_cost(usage.get('input_cost_usd'))} "
        f"output_cost_usd={_fmt_cost(usage.get('output_cost_usd'))} "
        f"cost_usd={_fmt_cost(usage.get('estimated_cost_usd'))}"
    )
    unreported = usage.get("calls_without_usage", 0)
    if unreported:
        line += f"\n(note: {unreported} call(s) did not report token usage — lower bound)"
    return line


def _entry(agent_name: str, usage: dict) -> dict:
    """One ledger entry, the shape parse_usage_comment returns."""
    return {
        "agent": agent_name,
        "calls": int(usage.get("llm_calls", usage.get("calls", 0)) or 0),
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "input_cost_usd": usage.get("input_cost_usd"),
        "output_cost_usd": usage.get("output_cost_usd"),
        "cost_usd": usage.get("estimated_cost_usd", usage.get("cost_usd")),
        "unreported": int(usage.get("calls_without_usage", usage.get("unreported", 0)) or 0),
    }


def post_usage_to_story(story_key: str, agent_name: str, usage: dict, jira=None) -> bool:
    """Record this agent run's usage on the story. Best-effort.

    Properties mode: one hidden entry, then the story's cost comment is
    brought up to date. Comments mode: one `[LLM-USAGE]` comment.

    Returns True if recorded, False otherwise. NEVER raises — usage
    bookkeeping must not fail a pipeline run. Creates a tracker
    lazily if one isn't supplied (and swallows env/config errors, e.g.
    an agent whose workflow lacks tracker credentials).
    """
    if not story_key:
        logger.info("Usage ledger: no story key available — skipping usage entry.")
        return False
    try:
        jira = _tracker_or_default(jira)
        if mode(jira) == "properties":
            entry = _entry(agent_name, usage)
            entry["at"] = _now().isoformat()
            _cap(jira, "set_property")(story_key, _new_key(PROP_USAGE), entry)
            logger.info(f"Usage ledger: recorded {agent_name} on {story_key}.")
            refresh_cost_comment(story_key, jira, after=agent_name)
            return True
        body = format_usage_comment(agent_name, usage)
        jira.add_comment(story_key, body)
        logger.info(f"Usage ledger: posted usage comment to {story_key} for {agent_name}.")
        return True
    except Exception as e:
        logger.warning(
            f"Usage ledger: could not record usage on {story_key}: "
            f"{type(e).__name__}: {e}. Non-fatal — continuing."
        )
        return False


def format_reset_comment(reason: str = "") -> str:
    """Build the ledger-reset boundary comment body (comments mode)."""
    suffix = f" reason=\"{reason}\"" if reason else ""
    return (
        f"{RESET_MARKER}{suffix}\n\n"
        "_Cost accounting for this story restarts here. Usage comments above this "
        "line belong to a previous, discarded run and are excluded from the "
        "end-to-end total._"
    )


def post_reset_to_story(story_key: str, reason: str = "", jira=None) -> bool:
    """Start a new attempt on the story's ledger. Best-effort, NEVER raises.

    Properties mode: the current cost comment gets a closing line saying why,
    then a hidden reset entry; the next run opens a new cost comment.
    Comments mode: one `[LEDGER-RESET]` comment."""
    if not story_key:
        logger.info("Usage ledger: no story key available — skipping reset marker.")
        return False
    try:
        jira = _tracker_or_default(jira)
        if mode(jira) == "properties":
            when = _now()
            refresh_cost_comment(story_key, jira, create=False, closing=(
                f"Closed {when.strftime('%Y-%m-%d %H:%M')} UTC: a new attempt started"
                + (f" ({reason})" if reason else "")
                + ". Its cost is counted from zero in a new cost comment; the runs "
                  "above are not part of it."))
            _cap(jira, "set_property")(story_key, _new_key(PROP_RESET),
                              {"reason": reason, "at": when.isoformat()})
            _cap(jira, "set_property")(story_key, PROP_COMMENT,
                              {"ref": None, "since": when.isoformat(), "reason": reason})
        else:
            jira.add_comment(story_key, format_reset_comment(reason))
        logger.info(f"Usage ledger: reset recorded on {story_key} ({reason}).")
        from core import spend_budget
        spend_budget.ledger_reset(story_key)        # F-24: the budget restarts with it
        return True
    except Exception as e:
        logger.warning(
            f"Usage ledger: could not record a reset on {story_key}: "
            f"{type(e).__name__}: {e}. Non-fatal — continuing."
        )
        return False


def record_hold(story_key: str, spent: float, limit: float, jira=None) -> bool:
    """Properties mode: remember a budget hold on the ledger (the person-facing
    `[budget:hold]` comment is posted by core.spend_budget either way; in
    comments mode that comment is what the ledger reads). Never raises."""
    try:
        jira = _tracker_or_default(jira)
        if mode(jira) != "properties":
            return False
        _cap(jira, "set_property")(story_key, _new_key(PROP_HOLD),
                          {"spent": round(float(spent), 6), "limit": float(limit),
                           "at": _now().isoformat()})
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Usage ledger: budget hold on %s not recorded: %s", story_key, e)
        return False


def has_usage_comments(comment_bodies: list[str], ignore_agents=()) -> bool:
    """True if any comment after the last reset is a usage entry from an agent
    not in `ignore_agents` (comments mode; has_usage() reads either store).

    Used to decide whether a story has already been costed and therefore
    needs a reset boundary before it is processed again. The agent that opens
    an attempt passes the agents that run BEFORE it in that same attempt, so
    their entries are kept rather than discarded as a "previous run".
    """
    return _any_other(_entries_from_comments(comment_bodies or []), ignore_agents)


def has_usage(story_key: str, tracker, ignore_agents=()) -> bool:
    """has_usage_comments over whichever store the story's ledger is in."""
    return _any_other(story_ledger(story_key, tracker)["entries"], ignore_agents)


def _any_other(entries: list, ignore_agents) -> bool:
    ignore = set(ignore_agents or ())
    # An ignored agent's failed run ("<agent> (failed)", story_usage) is
    # still that agent: its cost is part of the same attempt.
    return any(e["agent"].removesuffix(FAILED_SUFFIX) not in ignore for e in entries)


def _comments_after_last_reset(comment_bodies: list[str]) -> list[str]:
    """Return only the comments posted AFTER the last [LEDGER-RESET] marker.

    Comments come oldest-first, so the last marker is the most recent
    boundary. With no marker present, every comment is returned — preserving
    the original (pre-reset-feature) behaviour exactly.
    """
    last = -1
    for i, body in enumerate(comment_bodies):
        if RESET_MARKER in (body or ""):
            last = i
    return comment_bodies[last + 1:] if last >= 0 else list(comment_bodies)


def _entries_from_comments(comment_bodies: list[str]) -> list[dict]:
    return [p for p in (parse_usage_comment(b) for b in _comments_after_last_reset(comment_bodies))
            if p]


def parse_usage_comment(comment_body: str) -> Optional[dict]:
    """Parse one comment body. Returns a usage dict or None if it isn't
    a usage comment (or is malformed)."""
    if USAGE_MARKER not in (comment_body or ""):
        return None
    m = _USAGE_RE.search(comment_body)
    if not m:
        logger.debug("Usage ledger: marker present but line malformed — ignoring.")
        return None

    def cost(field):
        raw = m.group(field)
        return None if raw == "n/a" else float(raw)

    return {
        "agent": m.group("agent"),
        "calls": int(m.group("calls")),
        "input_tokens": int(m.group("input_tokens")),
        "output_tokens": int(m.group("output_tokens")),
        "input_cost_usd": cost("input_cost"),
        "output_cost_usd": cost("output_cost"),
        "cost_usd": cost("cost"),
    }


# ─────────────────────────────────────────────────────────────
# The ledger as one view, whichever store it is in
# ─────────────────────────────────────────────────────────────

def story_ledger(story_key: str, tracker) -> dict:
    """The story's current attempt, from either store.

    {"mode", "entries" (oldest first), "holds" ([spent] oldest first),
     "since" / "reason" (the last reset, if any), "comment" (the cost comment's
     property, properties mode), "keys" (the usage property keys, properties
     mode)} - every field present in either store. Never raises: an unreadable store reads as
    empty, and the caller's work goes on."""
    out = {"mode": "comments", "entries": [], "holds": [], "since": None, "reason": None,
           "comment": None, "keys": []}
    if tracker is None or not story_key:
        return out
    from core.spend_budget import _HOLD_RE
    try:
        m = mode(tracker)
        out["mode"] = m
        props = _read_properties(tracker, story_key, "llm.") if m == "properties" else {}
        resets = sorted((k for k in props if k.startswith(PROP_RESET + ".")), key=_stamp)
        if m == "comments" or not resets:
            # The comment ledger: everything in comments mode, and in properties
            # mode the entries of a story costed before the switch, until its
            # first property reset.
            bodies = tracker.get_comments(story_key) or []
            after = _comments_after_last_reset(bodies)
            out["entries"] = [p for p in (parse_usage_comment(b) for b in after) if p]
            out["holds"] = [float(h.group(1)) for h in (_HOLD_RE.search(b or "") for b in after)
                            if h]
            if len(after) != len(bodies):
                last = next(b for b in reversed(bodies) if RESET_MARKER in (b or ""))
                r = _RESET_REASON_RE.search(last)
                out["reason"] = (r.group(1) if r else None) or None
        cut = _stamp(resets[-1]) if resets else ""
        if resets:
            value = props.get(resets[-1]) or {}
            out["since"], out["reason"] = value.get("at"), value.get("reason") or None
        for key in sorted(props, key=_stamp):
            if _stamp(key) <= cut:
                continue
            value = props[key] or {}
            if key.startswith(PROP_USAGE + "."):
                out["entries"].append(_entry(value.get("agent", "unknown"), value))
            elif key.startswith(PROP_HOLD + "."):
                out["holds"].append(float(value.get("spent", 0.0)))
        out["comment"] = props.get(PROP_COMMENT) or None
        out["keys"] = sorted(k for k in props if k.startswith(PROP_USAGE + "."))
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Usage ledger of %s not read: %s", story_key, e)
    return out


def aggregate_story_usage(comment_bodies: list[str], extra_entries: list[dict] | None = None) -> dict:
    """Sum usage across all [LLM-USAGE] comments on a story (comments mode).

    Args:
        comment_bodies: raw text of every comment on the story.
        extra_entries: already-parsed usage dicts to include (e.g. the
            current agent's own usage, not yet posted).

    Returns dict with entries[], token totals (always exact) and cost
    totals (summed over entries that HAVE cost; cost_complete=False when
    any entry lacked pricing, meaning the total is a lower bound).
    """
    # Only count usage posted after the most recent reset boundary. A story that
    # was reset to `ai-ready` and re-run carries stale comments from the
    # discarded run; summing those would inflate the reported cost.
    return aggregate_entries(_entries_from_comments(comment_bodies or []), extra_entries)


def aggregate_entries(entries: list[dict], extra_entries: list[dict] | None = None) -> dict:
    """Totals over ledger entries (either store), plus `extra_entries`."""
    entries = [dict(e) for e in entries]
    for extra in extra_entries or []:
        entries.append(_entry(extra.get("agent", "unknown"), extra))

    total_in = sum(e["input_tokens"] for e in entries)
    total_out = sum(e["output_tokens"] for e in entries)
    total_calls = sum(e["calls"] for e in entries)
    costed = [e for e in entries if e["cost_usd"] is not None]
    total_cost = sum(e["cost_usd"] for e in costed) if costed else None
    total_in_cost = sum(e["input_cost_usd"] for e in costed if e["input_cost_usd"] is not None) if costed else None
    total_out_cost = sum(e["output_cost_usd"] for e in costed if e["output_cost_usd"] is not None) if costed else None

    return {
        "entries": entries,
        "agent_runs": len(entries),
        "total_calls": total_calls,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "total_input_cost_usd": total_in_cost,
        "total_output_cost_usd": total_out_cost,
        "total_cost_usd": total_cost,
        "cost_complete": len(costed) == len(entries) and len(entries) > 0,
        "unreported_calls": sum(e.get("unreported", 0) or 0 for e in entries),
    }


def budget_line(total_cost: float | None, budget: dict | None, allowance: float | None = None,
                markdown: bool = True) -> str:
    """'Story budget: $x of $y (z%, ...)' or '' (budget off, no cost, no limit).

    `allowance` is what this story may spend now: one budget.per_story_usd, plus
    one more for every hold a person released (L40) - so a released story does
    not read over 100% of a budget it was allowed past."""
    if not budget or not budget.get("enabled") or total_cost is None:
        return ""
    per_story = float(budget.get("per_story_usd") or 0)
    limit = float(allowance) if allowance else per_story
    if limit <= 0:
        return ""
    share = total_cost / limit
    mark = "⚠ " if share >= float(budget.get("warn_at", 0.5)) else ""
    extra = "" if abs(limit - per_story) < 1e-9 else ", raised after a budget hold"
    return (f"{mark}Story budget: ${total_cost:.2f} of ${limit:.2f} "
            f"({share:.0%}, budget.per_story_usd{extra}).")


def format_e2e_section(agg: dict, budget: dict | None = None, allowance: float | None = None) -> str:
    """Render the aggregate as a markdown section for Agent 5's report (comments mode).

    `budget` (config.yaml `budget`, F-24): when enabled and the cost is known,
    one more line says how much of the story's budget is used, marked once it
    passes `warn_at` - no separate comment."""
    if not agg["entries"]:
        return ""
    lines = [
        "",
        "---",
        "**End-to-end LLM usage & cost for this story**",
        "",
        "| Agent run | Calls | Input tokens | Output tokens | Cost (USD) |",
        "|---|---|---|---|---|",
    ]
    for e in agg["entries"]:
        cost = f"${e['cost_usd']:.4f}" if e["cost_usd"] is not None else "n/a"
        lines.append(
            f"| {e['agent']} | {e['calls']} | {e['input_tokens']:,} "
            f"| {e['output_tokens']:,} | {cost} |"
        )
    total_cost = (
        f"${agg['total_cost_usd']:.4f}" if agg["total_cost_usd"] is not None else "n/a"
    )
    lines.append(
        f"| **TOTAL ({agg['agent_runs']} agent runs)** | **{agg['total_calls']}** "
        f"| **{agg['total_input_tokens']:,}** | **{agg['total_output_tokens']:,}** "
        f"| **{total_cost}** |"
    )
    if not agg["cost_complete"]:
        lines.append("")
        lines.append(
            "_Some agent runs had no pricing configured — the cost total is a "
            "lower bound. Token totals are exact._"
        )
    line = budget_line(agg["total_cost_usd"], budget, allowance)
    if line:
        lines += ["", line]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# The cost comment (properties mode)
# ─────────────────────────────────────────────────────────────

_NAME_RE = re.compile(r"^(?P<base>.+?) \((?P<role>[^,()]+)(?:, (?P<mode>[^()]+))?\)$")


def _agent_parts(name: str) -> tuple:
    """'Agent 2 (Coder, review fix) (failed)' -> ('Agent 2 (Coder)', 'review fix (failed)')."""
    failed = name.endswith(FAILED_SUFFIX)
    core = name.removesuffix(FAILED_SUFFIX) if failed else name
    m = _NAME_RE.match(core)
    if not m:
        return core, ("failed" if failed else "")
    base = f"{m.group('base')} ({m.group('role')})"
    run_mode = m.group("mode") or ""
    if failed:
        run_mode = f"{run_mode} (failed)" if run_mode else "failed"
    return base, run_mode


def by_agent(entries: list[dict]) -> list[dict]:
    """One row per agent, in order of first appearance: runs, calls, tokens,
    cost, and its run modes with counts ('initial, review fix ×2')."""
    rows: dict = {}
    for e in entries:
        base, run_mode = _agent_parts(e["agent"])
        row = rows.setdefault(base, {"agent": base, "runs": 0, "calls": 0, "input_tokens": 0,
                                     "output_tokens": 0, "cost_usd": 0.0, "priced": True,
                                     "modes": {}})
        row["runs"] += 1
        row["calls"] += e["calls"]
        row["input_tokens"] += e["input_tokens"]
        row["output_tokens"] += e["output_tokens"]
        if e["cost_usd"] is None:
            row["priced"] = False
        else:
            row["cost_usd"] += e["cost_usd"]
        if run_mode:
            row["modes"][run_mode] = row["modes"].get(run_mode, 0) + 1
    return list(rows.values())


def _label(row: dict) -> str:
    if not row["modes"]:
        return row["agent"]
    modes = ", ".join(m if n == 1 else f"{m} ×{n}" for m, n in row["modes"].items())
    return f"{row['agent']}: {modes}"


def render_cost_comment(ledger: dict, budget: dict | None = None, allowance: float | None = None,
                        after: str | None = None, closing: str | None = None) -> str:
    """The story's one cost comment (Markdown): a row per agent, the total, the
    story budget, and when it was last brought up to date."""
    agg = aggregate_entries(ledger["entries"])
    since = ledger.get("since")
    head = "**Model cost for this story**"
    if since:
        head += (f" - this attempt, since {str(since)[:16].replace('T', ' ')} UTC"
                 + (f" ({ledger['reason']})" if ledger.get("reason") else ""))
    lines = [head, "",
             "| Agent | Runs | Calls | Input tokens | Output tokens | Cost (USD) |",
             "|---|---|---|---|---|---|"]
    for row in by_agent(agg["entries"]):
        cost = f"${row['cost_usd']:.4f}" if row["priced"] else (
            f"${row['cost_usd']:.4f}+" if row["cost_usd"] else "n/a")
        lines.append(f"| {_label(row)} | {row['runs']} | {row['calls']} | "
                     f"{row['input_tokens']:,} | {row['output_tokens']:,} | {cost} |")
    total = f"${agg['total_cost_usd']:.4f}" if agg["total_cost_usd"] is not None else "n/a"
    lines.append(f"| **Total** | **{agg['agent_runs']}** | **{agg['total_calls']}** | "
                 f"**{agg['total_input_tokens']:,}** | **{agg['total_output_tokens']:,}** | "
                 f"**{total}** |")
    notes = []
    if agg["entries"] and not agg["cost_complete"]:
        notes.append("_Some runs had no pricing configured - the cost total is a lower bound. "
                     "Token totals are exact._")
    if agg["unreported_calls"]:
        notes.append(f"_{agg['unreported_calls']} call(s) did not report token usage - the "
                     "totals are a lower bound._")
    line = budget_line(agg["total_cost_usd"], budget, allowance)
    if line:
        notes.append(line)
    stamp = _now().strftime("%Y-%m-%d %H:%M")
    notes.append(f"_Brought up to date after every agent run ({stamp} UTC"
                 + (f", {after}" if after else "") + "); nobody is notified of the edit._")
    if closing:
        notes.append(f"**{closing}**")
    return "\n".join(lines + [""] + notes)


def _allowance(story_key: str, tracker, ledger: dict, budget: dict) -> float | None:
    """What the story may spend now (core.spend_budget.allowance)."""
    try:
        from core import spend_budget
        labels = (tracker.get_story(story_key) or {}).get("labels") or []
        held_at = ledger["holds"][-1] if ledger["holds"] else None
        return spend_budget.allowance(held_at, budget.get("hold_label", "") in labels,
                                      float(budget.get("per_story_usd") or 0))
    except Exception:                                              # noqa: BLE001
        return None


def refresh_cost_comment(story_key: str, tracker, after: str | None = None,
                         closing: str | None = None, create: bool = True) -> str | None:
    """Bring the story's cost comment up to date (properties mode): edit it in
    place, or post it when the attempt has none yet (or a person deleted it).
    Returns its reference. Never raises. create=False only edits an existing
    one (closing an attempt whose cost is still in the old comments must not
    post a summary of them).

    Two agents finishing together each render from what they read; a run whose
    render missed an entry recorded meanwhile renders once more, so the last
    edit carries every entry."""
    if mode(tracker) != "properties":
        return None
    try:
        from core import spend_budget
        from integrations.tracker import capability
        budget = spend_budget.settings()
        ref = None
        for _attempt in range(3):
            ledger = story_ledger(story_key, tracker)
            if not ledger["entries"]:
                return None
            body = render_cost_comment(ledger, budget, _allowance(story_key, tracker, ledger, budget),
                                       after=after, closing=closing)
            render = capability(tracker, "render_markdown")
            body = render(body) if render is not None else body
            current = ledger["comment"] or {}
            ref = current.get("ref")
            if ref:
                try:
                    _cap(tracker, "update_comment")(story_key, ref, body)
                except LookupError as e:
                    # A person deleted it: the attempt's cost comment is posted
                    # again, so the figures stay in sight.
                    logger.info("Cost comment on %s is gone (%s) - posting it anew.",
                                story_key, e)
                    ref = None
                except Exception as e:                             # noqa: BLE001
                    # Any other refusal: never a new comment per run - that is
                    # the clutter this replaces. The entries stay on the ledger
                    # and Agent 5's report line still gives the total.
                    logger.warning("Cost comment on %s not brought up to date: %s",
                                   story_key, e)
                    return ref
            if not ref and not create:
                return None
            if not ref:
                ref = tracker.add_comment(story_key, body)
                _cap(tracker, "set_property")(story_key, PROP_COMMENT,
                                     {"ref": ref, "since": ledger.get("since"),
                                      "reason": ledger.get("reason")})
            seen = set(ledger.get("keys") or [])
            now = set(story_ledger(story_key, tracker).get("keys") or [])
            if now <= seen:
                return ref
        return ref
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Cost comment on %s not brought up to date: %s", story_key, e)
        return None


def cost_line(story_key: str, tracker, extra_entries: list[dict] | None = None) -> str:
    """One line for Agent 5's report (properties mode): the story's model cost
    so far, pointing to the cost comment that holds the table - instead of
    repeating the table in every report."""
    ledger = story_ledger(story_key, tracker)
    agg = aggregate_entries(ledger["entries"], extra_entries)
    if not agg["entries"]:
        return ""
    total = (f"${agg['total_cost_usd']:.2f}" + ("" if agg["cost_complete"] else "+")
             if agg["total_cost_usd"] is not None else "not priced")
    ref = (ledger["comment"] or {}).get("ref")
    where = f"[the cost comment]({ref})" if ref and str(ref).startswith("http") else \
        "the cost comment on this story"
    return (f"**Model cost for this story so far:** {total} over {agg['agent_runs']} agent "
            f"runs - per agent in {where}.")


@contextmanager
def story_usage(story_key: str, agent_name: str, *, jira=None, dry_run: bool = False):
    """One story's model cost, and only its own (F-3).

    In a scan, the usage counter was reset only after a SUCCESS, so a story
    that failed part-way left its calls in the counter and the next story's
    usage entry carried them - one story paid for another's failure, and
    the failed story's ledger showed nothing.

    Around each story: the counter starts at zero; on the way out, whatever
    the run did not record itself is recorded on THIS story - as
    "<agent_name> (failed)" when the run raised, as `agent_name` otherwise (a
    successful run normally records and resets, so nothing is left) - and the
    counter is reset. A dry run records nothing. Never raises from bookkeeping;
    the run's own exception is re-raised unchanged."""
    from core import spend_budget
    from core.llm_client import get_usage_summary, log_usage_summary, reset_usage
    reset_usage()
    if not dry_run:
        # F-24: the story's budget counts its ledger and this run's calls.
        spend_budget.begin_story(story_key, jira)
    failed = False
    try:
        yield
    except spend_budget.BudgetExceeded as stop:
        failed = True
        if not dry_run:
            spend_budget.hold_story(jira if jira is not None else spend_budget.current_tracker(),
                                    stop)
        raise
    except BaseException:
        failed = True
        raise
    finally:
        spend_budget.end_story()
        try:
            if (get_usage_summary() or {}).get("llm_calls"):
                usage = log_usage_summary(
                    f"story {story_key} ({'failed' if failed else 'not posted by the run'})")
                if not dry_run:
                    post_usage_to_story(story_key,
                                        agent_name + (FAILED_SUFFIX if failed else ""),
                                        usage, jira=jira)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Usage ledger for %s not recorded: %s", story_key, e)
        finally:
            reset_usage()
