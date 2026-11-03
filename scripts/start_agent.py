"""Start an agent's workflow when stories wait for it (core/handoff.py).

    python -m scripts.start_agent --agent agent1_analyst [--previous-chain N] [--dry-run]

Run by a workflow after its agent: Agent 0 starts Agent 1, Agents 1 and 2
start themselves again while stories still wait. `--previous-chain` is the
`chain` input of the run it follows (empty for a scheduled or manual run).
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
    args = ap.parse_args(argv)
    from core import handoff
    try:
        from integrations.repo_host import get_repo_host
        from integrations.tracker import get_tracker
        tracker, host = get_tracker(), get_repo_host()
        result = handoff.start(tracker, host, args.agent, args.previous_chain,
                               dry_run=args.dry_run)
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


if __name__ == "__main__":
    sys.exit(main())
