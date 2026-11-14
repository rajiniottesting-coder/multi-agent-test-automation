"""The deployment signal (X4): these stories' changes are live.

    python -m scripts.deployment_signal --stories PRJ-1,PRJ-2 [--dry-run]

Run by the `Deployment signal` workflow - by a deployment pipeline's webhook
(repository_dispatch `deployed`, client_payload {"stories": [...]}) or by hand.
Each story awaiting its deployment (deployment.pending_label) is labelled
deployment.deployed_label, then the watcher's deployment step runs at once:
the pending label comes off and one reminder asks to merge the story's
context-update pull request (core/deployment.py). A story not awaiting a
deployment is left as it is and named.

Exit 1 when the signal is off, names no story, or a write was refused.
"""
from __future__ import annotations

import argparse
import logging
import sys


def keys_of(text: str) -> list[str]:
    """'PRJ-1, PRJ-2' or '["PRJ-1","PRJ-2"]' -> ['PRJ-1', 'PRJ-2']."""
    import re
    return re.findall(r"[A-Z][A-Z0-9_]*-\d+", text or "")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stories", required=True, help="the deployed stories' keys")
    ap.add_argument("--dry-run", action="store_true", help="print what would be done")
    args = ap.parse_args(argv)
    from core import deployment
    s = deployment.settings()
    if not deployment.enabled(s):
        print("[FAIL] deployment.enabled is false in config.yaml - no signal is taken.")
        return 1
    keys = keys_of(args.stories)
    if not keys:
        print(f"[FAIL] no story key in {args.stories!r}.")
        return 1
    from integrations.tracker import get_tracker
    tracker = get_tracker()
    host = None
    try:
        from integrations.repo_host import get_repo_host
        host = get_repo_host()
    except Exception as e:                                         # noqa: BLE001
        print(f"::warning::The repository host could not be used: {e}")
    if args.dry_run:
        print(f"(dry run) would label {', '.join(keys)} {s['deployed_label']} when awaiting "
              f"deployment, then remind.")
        return 0
    # First the label, then the step that acts on it: deployed() finds the
    # stories carrying both labels, so it must see the one just added.
    labelled = deployment.signal(tracker, keys, s)
    print(f"labelled {s['deployed_label']}: {labelled or 'none'}")
    result = {"deployed": [], "reminded": [], "errors": [], "write_errors": []}
    deployment.deployed(tracker, host, result, s=s)
    for name, value in result.items():
        print(f"{name}: {value}")
    return 1 if result["write_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
