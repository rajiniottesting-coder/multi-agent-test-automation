"""Notice what changed under the pipeline, and say so once (Group B: R2 R3 R4 X5).

    python -m scripts.watch_tracker [--dry-run]

Run by the pipeline health workflow after its check. See core/tracker_watch.py:
a story edited after drafting or coding (R2), a test case edited or deleted
after its scenario was coded (R3), a cancelled or deleted story whose
scenarios still run (R4), an agent pull request in conflict with or behind
main (X5). Every finding is a comment or a label, each said once; nothing is
regenerated, deleted or pushed.

Exit 0 always, unless the tracker refused writes (1): a watcher must never
hide the health check's own result.
"""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print what would be said")
    ap.add_argument("--features-dir", default=None)
    args = ap.parse_args(argv)
    from pathlib import Path
    from config.paths import FEATURES_DIR
    from core.tracker_watch import run
    tracker = host = None
    try:
        from integrations.tracker import get_tracker
        tracker = get_tracker()
    except Exception as e:                                         # noqa: BLE001
        print(f"::warning::The tracker could not be used: {e}")
    try:
        from integrations.repo_host import get_repo_host
        host = get_repo_host()
    except Exception as e:                                         # noqa: BLE001
        print(f"::warning::The repository host could not be used: {e}")
    out = run(tracker, host, Path(args.features_dir) if args.features_dir else FEATURES_DIR,
              dry_run=args.dry_run)
    for name, value in out.items():
        print(f"{name}: {value}")
    if out["errors"]:
        print(f"::warning::{len(out['errors'])} watcher step(s) or write(s) failed - see above.")
    return 1 if any(" " in what for what, _ in out["errors"]) else 0


if __name__ == "__main__":
    sys.exit(main())
