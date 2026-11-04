"""Start an agent's workflow when stories wait for it (core/handoff.py).

    python -m scripts.start_agent --agent agent1_analyst [--previous-chain N] [--dry-run]
        [--waiting-before reports/handoff_waiting.json]
    python -m scripts.start_agent --agent agent2_coder --record-waiting reports/handoff_waiting.json

Run by a workflow after its agent: Agent 0 starts Agent 1, Agents 1 and 2
start themselves again while stories still wait. `--previous-chain` is the
`chain` input of the run it follows (empty for a scheduled or manual run).
An agent starting itself records what waits before its run (`--record-waiting`)
and passes it after (`--waiting-before`): it starts again only if the run took
one of those stories (core/handoff.py). A missing or unreadable record means
"not known" - the start is decided as without it.
Writes `started=true|false` to $GITHUB_OUTPUT and one line to the job summary.
Exit code always 0: a hand-off informs the pipeline, it never fails a run.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", required=True, help="agents.<key> in config.yaml")
    ap.add_argument("--previous-chain", default="", help="the chain input of this run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--record-waiting", metavar="PATH",
                    help="write the stories waiting for the agent now; start nothing")
    ap.add_argument("--waiting-before", metavar="PATH",
                    help="the record made before this run (--record-waiting)")
    args = ap.parse_args(argv)
    from core import handoff
    if args.record_waiting:
        return _record(args.agent, args.record_waiting)
    before = _read_record(args.waiting_before)
    try:
        from integrations.repo_host import get_repo_host
        from integrations.tracker import get_tracker
        tracker, host = get_tracker(), get_repo_host()
        result = handoff.start(tracker, host, args.agent, args.previous_chain,
                               dry_run=args.dry_run, waiting_before=before)
    except Exception as e:                                         # noqa: BLE001
        result = {"agent": args.agent, "started": False, "error": True,
                  "why": f"not checked ({type(e).__name__}: {e})", "waiting": []}
    waiting = ", ".join(result.get("waiting") or []) or "none"
    line = (f"Hand-off to {args.agent}: {result['why']}. Waiting: {waiting}.")
    print(("::warning::" if result.get("error") else "") + line)
    for env, text in (("GITHUB_OUTPUT", f"started={'true' if result['started'] else 'false'}\n"),
                      ("GITHUB_STEP_SUMMARY", line + "\n")):
        path = os.getenv(env)
        if path:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
    return 0


def _record(agent: str, path: str) -> int:
    """What waits before the run, for the progress check after it. Never fails
    the run: an unreadable tracker writes no record."""
    import json
    from pathlib import Path
    from core import handoff
    try:
        from integrations.tracker import get_tracker
        keys = handoff.waiting(get_tracker(), agent, limit=handoff.PROGRESS_LIMIT)
    except Exception as e:                                         # noqa: BLE001
        print(f"::warning::Waiting stories for {agent} not recorded ({type(e).__name__}: {e}).")
        return 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(keys), encoding="utf-8")
    print(f"Waiting for {agent} before the run: {', '.join(keys) or 'none'}.")
    return 0


def _read_record(path):
    """The recorded list, or None when there is none (decide as without it)."""
    if not path:
        return None
    import json
    from pathlib import Path
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        return None
    return [str(k) for k in data] if isinstance(data, list) else None


if __name__ == "__main__":
    sys.exit(main())
