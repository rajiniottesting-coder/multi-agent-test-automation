"""
Usage ledger — end-to-end LLM token & cost tracking per story, across agents.

PROBLEM: each agent runs in a separate CI process, so in-memory usage
tracking (agents/llm_client.py) can only see ONE agent's calls. A story's
true end-to-end cost spans Agent 1 (test designer) + Agent 2 (coder, possibly
multiple update/regen runs) + Agent 3 (reviewer) + Agent 5 (reporter).

SOLUTION: the Jira story itself is the ledger. After each agent finishes,
it posts one compact, machine-parseable usage comment:

    [LLM-USAGE] agent="Agent 2 (Coder)" calls=5 input_tokens=48213 \
output_tokens=9877 input_cost_usd=0.144639 output_cost_usd=0.148155 \
cost_usd=0.292794

Agent 5 (the last agent in the pipeline) reads all such comments back,
adds its own usage, and appends an "End-to-end LLM usage & cost" section
to its test report — giving the actual, measured story cost in one place.

Token usage and cost are tracked as SEPARATE quantities throughout:
tokens are always exact (reported by the API); cost is derived from the
LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M env vars and may be
absent ("n/a") if pricing isn't configured — aggregation handles both.

All posting/reading is best-effort: a Jira hiccup can never fail a run.
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Appended to an agent's name in the usage comment of a run that raised (F-3).
FAILED_SUFFIX = " (failed)"

USAGE_MARKER = "[LLM-USAGE]"

# Boundary marker. Posted by Agent 1 when it re-processes a story that already
# carries usage comments (i.e. the story was reset to `ai-ready` and is being
# costed again from scratch). aggregate_story_usage() counts only the comments
# AFTER the last reset, so a discarded run's tokens never inflate the report.
#
# Deliberately NOT posted for ai-update / ai-regenerate: those are rework on the
# SAME costed story, and their tokens SHOULD accumulate into the lifetime total.
RESET_MARKER = "[LEDGER-RESET]"

# The agent that STARTS a change story's attempt. Its entries are the first
# cost of an attempt, so they never make a later agent think the story was
# costed before: has_usage_comments() is told to ignore them by Agent 1.
IMPACT_ANALYST = "Agent 0 (Impact Analyst)"

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


def _fmt_cost(value) -> str:
    """Format a cost value for the comment line: 6-decimal float or 'n/a'."""
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def format_usage_comment(agent_name: str, usage: dict) -> str:
    """Build the machine-parseable usage comment body for a Jira story.

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


def post_usage_to_story(story_key: str, agent_name: str, usage: dict, jira=None) -> bool:
    """Post this agent's usage comment onto the story. Best-effort.

    Returns True if posted, False otherwise. NEVER raises — usage
    bookkeeping must not fail a pipeline run. Creates a tracker
    lazily if one isn't supplied (and swallows env/config errors, e.g.
    an agent whose workflow lacks Jira credentials).
    """
    if not story_key:
        logger.info("Usage ledger: no story key available — skipping usage comment.")
        return False
    try:
        if jira is None:
            from integrations.tracker import get_tracker
            jira = get_tracker()
        body = format_usage_comment(agent_name, usage)
        jira.add_comment(story_key, body)
        logger.info(f"Usage ledger: posted usage comment to {story_key} for {agent_name}.")
        return True
    except Exception as e:
        logger.warning(
            f"Usage ledger: could not post usage comment to {story_key}: "
            f"{type(e).__name__}: {e}. Non-fatal — continuing."
        )
        return False


def format_reset_comment(reason: str = "") -> str:
    """Build the ledger-reset boundary comment body."""
    suffix = f" reason=\"{reason}\"" if reason else ""
    return (
        f"{RESET_MARKER}{suffix}\n\n"
        "_Cost accounting for this story restarts here. Usage comments above this "
        "line belong to a previous, discarded run and are excluded from the "
        "end-to-end total._"
    )


def post_reset_to_story(story_key: str, reason: str = "", jira=None) -> bool:
    """Post a ledger-reset boundary onto the story. Best-effort.

    Mirrors post_usage_to_story: NEVER raises. Bookkeeping must not fail a run.
    """
    if not story_key:
        logger.info("Usage ledger: no story key available — skipping reset marker.")
        return False
    try:
        if jira is None:
            from integrations.tracker import get_tracker
            jira = get_tracker()
        jira.add_comment(story_key, format_reset_comment(reason))
        logger.info(f"Usage ledger: posted reset marker to {story_key} ({reason}).")
        return True
    except Exception as e:
        logger.warning(
            f"Usage ledger: could not post reset marker to {story_key}: "
            f"{type(e).__name__}: {e}. Non-fatal — continuing."
        )
        return False


def has_usage_comments(comment_bodies: list[str], ignore_agents=()) -> bool:
    """True if any comment after the last reset is a usage entry from an agent
    not in `ignore_agents`.

    Used to decide whether a story has already been costed and therefore
    needs a reset boundary before it is processed again. The agent that opens
    an attempt passes the agents that run BEFORE it in that same attempt, so
    their entries are kept rather than discarded as a "previous run".
    """
    ignore = set(ignore_agents or ())
    for b in _comments_after_last_reset(comment_bodies or []):
        parsed = parse_usage_comment(b)
        # An ignored agent's failed run ("<agent> (failed)", story_usage) is
        # still that agent: its cost is part of the same attempt.
        if parsed and parsed["agent"].removesuffix(FAILED_SUFFIX) not in ignore:
            return True
    return False


def _comments_after_last_reset(comment_bodies: list[str]) -> list[str]:
    """Return only the comments posted AFTER the last [LEDGER-RESET] marker.

    Jira returns comments oldest-first, so the last marker is the most recent
    boundary. With no marker present, every comment is returned — preserving
    the original (pre-reset-feature) behaviour exactly.
    """
    last = -1
    for i, body in enumerate(comment_bodies):
        if RESET_MARKER in (body or ""):
            last = i
    return comment_bodies[last + 1:] if last >= 0 else list(comment_bodies)


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


def aggregate_story_usage(comment_bodies: list[str], extra_entries: list[dict] | None = None) -> dict:
    """Sum usage across all [LLM-USAGE] comments on a story.

    Args:
        comment_bodies: raw text of every comment on the story.
        extra_entries: already-parsed usage dicts to include (e.g. the
            current agent's own usage, not yet posted as a comment).

    Returns dict with entries[], token totals (always exact) and cost
    totals (summed over entries that HAVE cost; cost_complete=False when
    any entry lacked pricing, meaning the total is a lower bound).
    """
    entries: list[dict] = []
    # Only count usage posted after the most recent reset boundary. A story that
    # was reset to `ai-ready` and re-run carries stale comments from the
    # discarded run; summing those would inflate the reported cost.
    for body in _comments_after_last_reset(comment_bodies or []):
        parsed = parse_usage_comment(body)
        if parsed:
            entries.append(parsed)
    for extra in extra_entries or []:
        entries.append({
            "agent": extra.get("agent", "unknown"),
            "calls": extra.get("llm_calls", extra.get("calls", 0)),
            "input_tokens": extra.get("input_tokens", 0),
            "output_tokens": extra.get("output_tokens", 0),
            "input_cost_usd": extra.get("input_cost_usd"),
            "output_cost_usd": extra.get("output_cost_usd"),
            "cost_usd": extra.get("estimated_cost_usd", extra.get("cost_usd")),
        })

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
    }


def format_e2e_section(agg: dict) -> str:
    """Render the aggregate as a markdown section for Agent 5's report."""
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
    return "\n".join(lines)


@contextmanager
def story_usage(story_key: str, agent_name: str, *, jira=None, dry_run: bool = False):
    """One story's model cost, and only its own (F-3).

    In a scan, the usage counter was reset only after a SUCCESS, so a story
    that failed part-way left its calls in the counter and the next story's
    usage comment carried them - one story paid for another's failure, and
    the failed story's ledger showed nothing.

    Around each story: the counter starts at zero; on the way out, whatever
    the run did not post itself is posted to THIS story - as
    "<agent_name> (failed)" when the run raised, as `agent_name` otherwise (a
    successful run normally posts and resets, so nothing is left) - and the
    counter is reset. A dry run posts nothing. Never raises from bookkeeping;
    the run's own exception is re-raised unchanged."""
    from core.llm_client import get_usage_summary, log_usage_summary, reset_usage
    reset_usage()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
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
