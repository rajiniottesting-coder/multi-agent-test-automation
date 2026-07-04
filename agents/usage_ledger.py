"""
Usage ledger — end-to-end LLM token & cost tracking per story, across agents.

PROBLEM: each agent runs in a separate CI process, so in-memory usage
tracking (agents/llm_client.py) can only see ONE agent's calls. A story's
true end-to-end cost spans Agent 1 (analyst) + Agent 2 (coder, possibly
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
from typing import Optional

logger = logging.getLogger(__name__)

USAGE_MARKER = "[LLM-USAGE]"

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
    bookkeeping must not fail a pipeline run. Creates a JiraClient
    lazily if one isn't supplied (and swallows env/config errors, e.g.
    an agent whose workflow lacks Jira credentials).
    """
    if not story_key:
        logger.info("Usage ledger: no story key available — skipping usage comment.")
        return False
    try:
        if jira is None:
            from agents.jira_client import JiraClient
            jira = JiraClient()
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
    for body in comment_bodies or []:
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
