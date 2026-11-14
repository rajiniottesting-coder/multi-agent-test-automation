"""Choose a pull request's tests (X1) - Agent 4's "Choose the tests" step.

    python -m scripts.select_tests --files changed.txt --labels "a,b" --out reports/selection.json

Writes the choice (core/test_selection.py) to --out and prints it. The
workflow then points pytest at it (AGENT4_SELECTION) only when it chose
scenarios; "full" runs the whole suite. Never fails the run: any error is a
whole-suite run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--files", required=True, help="changed paths, one per line")
    ap.add_argument("--labels", default="", help="the pull request's labels, comma-separated")
    ap.add_argument("--out", default="reports/selection.json")
    args = ap.parse_args(argv)
    from core import test_selection as ts
    try:
        changed = Path(args.files).read_text(encoding="utf-8").splitlines()
    except OSError:
        changed = []
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    try:
        choice = ts.select(changed, Path("."), labels=labels)
    except Exception as e:                                         # noqa: BLE001
        choice = ts.full(f"the selection failed ({type(e).__name__})")
    ts.write(choice, Path(args.out))
    if choice["mode"] == "selected":
        print(f"Selected {len(choice['scenarios'])} scenario(s)"
              f"{' + every @' + choice['smoke_tag'] if choice.get('smoke_tag') else ''}: "
              f"{choice['why']}")
        for f, t in choice["scenarios"]:
            print(f"    {f} :: {t}")
    else:
        print(f"The whole suite runs: {choice['why']}")
    print(f"mode={choice['mode']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
