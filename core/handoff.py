"""An agent that leaves work for another agent starts it (settings: `handoff`).

Agents 1 and 2 were started by their schedules only. GitHub drops or delays
most scheduled runs of a quiet repository: on 3 Nov 2026 none of Agent 1's
scheduled runs had started by 14:00 IST, and over the two weeks before, about
4 of its 19 daily runs started, some hours late. A story released to Agent 1
waited hours, not the 30 minutes the schedule promised.

Now, after its run:
  Agent 0   starts Agent 1 when a story is waiting for it (Agent 0 released
            it, or a person labelled it);
  Agent 1   starts itself again while stories still wait - more than
            max_stories_per_run were waiting;
  Agent 2   the same.

"Waiting" is asked of the tracker with the started agent's OWN selections
(every `*selection` block under agents.<key> in config.yaml), so a start
never happens without work, and the started run scans exactly as its
schedule would. A run is started in scan mode with one input, `chain`: the
number of runs this hand-off has started in a row. At `handoff.max_chain` it
stops - the bound for a story that never leaves the queue. A run whose agent
failed starts nothing (the workflows run this step on success only), so a
failing story is retried by the schedule, as before, not in a loop.

Never fails the run it follows: a refused start is logged and reported, the
schedule still picks the work up. Generic: no application, project or story
name lives here; the workflow files are named in the settings.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def selections(agent_key: str, config: dict | None = None) -> list:
    """Every non-empty `*selection` block of agents.<agent_key>, `selection`
    first: Agent 2's normal, regenerate and update passes; Agent 1's one."""
    if config is None:
        import yaml
        from config.paths import CONFIG_YAML
        config = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
    block = ((config.get("agents") or {}).get(agent_key)) or {}
    names = sorted((k for k, v in block.items()
                    if k.endswith("selection") and isinstance(v, dict) and v),
                   key=lambda k: (k != "selection", k))
    return [block[k] for k in names]


def waiting(tracker, agent_key: str, config: dict | None = None) -> list:
    """Keys of stories waiting for the agent: the first of each selection."""
    found = []
    for sel in selections(agent_key, config):
        for story in tracker.find_stories_to_process(sel, max_results=1) or []:
            key = story.get("key") if isinstance(story, dict) else None
            if key and key not in found:
                found.append(key)
    return found


def parse_chain(raw) -> int:
    """The `chain` input as given: a schedule or a person gives none (0)."""
    try:
        return max(0, int(str(raw).strip() or 0))
    except (TypeError, ValueError):
        return 0


def start(tracker, host, agent_key: str, previous_chain=0, settings: dict | None = None,
          config: dict | None = None, dry_run: bool = False) -> dict:
    """Start `agent_key`'s workflow when stories wait for it.

    {"started", "why", "chain", "waiting": [keys], "error" when a start was
    due and did not happen}. Never raises."""
    from core.ops_settings import section
    s = settings if settings is not None else section("handoff")
    chain = parse_chain(previous_chain) + 1
    out = {"agent": agent_key, "started": False, "chain": chain, "waiting": []}
    if not s.get("enabled"):
        return {**out, "why": "handoff.enabled is false"}
    workflow = (s.get("workflows") or {}).get(agent_key)
    if not workflow:
        return {**out, "why": f"no workflow for {agent_key} in handoff.workflows"}
    if chain > int(s.get("max_chain") or 0):
        return {**out, "error": True, "why": f"{chain - 1} run(s) already started in a row "
                              f"(handoff.max_chain {s.get('max_chain')}) - the schedule "
                              "picks up what is left"}
    try:
        out["waiting"] = waiting(tracker, agent_key, config)
    except Exception as e:                                         # noqa: BLE001
        return {**out, "error": True, "why": f"could not ask the tracker what waits ({type(e).__name__}: {e})"}
    if not out["waiting"]:
        return {**out, "why": "no story waits for it"}
    if dry_run:
        return {**out, "why": f"dry run: would start {workflow}"}
    dispatch = getattr(host, "dispatch_workflow", None)
    if dispatch is None:
        return {**out, "error": True, "why": "the repo host cannot start a workflow"}
    try:
        dispatch(workflow, "main", {"chain": str(chain)})
    except Exception as e:                                         # noqa: BLE001
        return {**out, "error": True, "why": f"{workflow} not started ({type(e).__name__}: {e})"}
    return {**out, "started": True, "why": f"started {workflow} (run {chain} in a row)"}
