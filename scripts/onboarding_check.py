#!/usr/bin/env python3
"""Check whether an application is ready for Agent 0 (design E2).

Run it from anywhere, against any project root - this repository's own or
another application's. It reads the project and reports; it changes nothing.

    python -m scripts.onboarding_check --root /path/to/app-repo \\
        --inventory qa/inventory.json --tracker jira --repo-host github

Exit code: 1 when any check FAILs; with --strict, also when any WARNs.

The checklist and what each result means: docs/AGENT0_ONBOARDING.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.onboarding import FAIL, OK, WARN, run_checks, summarise

REPO_ROOT = Path(__file__).resolve().parents[1]
_MARK = {OK: "OK  ", WARN: "WARN", FAIL: "FAIL"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Agent 0 onboarding readiness check.")
    ap.add_argument("--root", default=str(REPO_ROOT),
                    help="the application's project root (default: this repository)")
    ap.add_argument("--inventory",
                    help="inventory file, relative to --root (default: the one "
                         "named in config/config.yaml)")
    ap.add_argument("--language", default="python-pytest-bdd",
                    help="suite language; selects the layer 1 graph builder "
                         "(default: python-pytest-bdd)")
    ap.add_argument("--tracker", default="jira", help="tracker adapter name (default: jira)")
    ap.add_argument("--repo-host", default="github",
                    help="repository-host adapter name (default: github)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on WARN as well as FAIL")
    args = ap.parse_args(argv)

    checks = run_checks(args.root, language=args.language,
                        inventory_file=args.inventory,
                        tracker=args.tracker, repo_host=args.repo_host)

    print(f"Agent 0 onboarding readiness for {Path(args.root).resolve()}\n")
    for c in checks:
        print(f"  [{_MARK[c.status]}] {c.name}: {c.detail}")
        if c.action and c.status != OK:
            print(f"         -> {c.action}")
    counts = summarise(checks)
    print(f"\n  {counts[OK]} ok, {counts[WARN]} warn, {counts[FAIL]} fail")

    if counts[FAIL] or (args.strict and counts[WARN]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
