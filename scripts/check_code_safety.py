#!/usr/bin/env python3
"""Refuse unsafe test code before it runs with the application's login (S1).

    printf '%s\\n' <changed files> | python -m scripts.check_code_safety --stdin
    python -m scripts.check_code_safety --all
    python -m scripts.check_code_safety pages/x_page.py tests/step_defs/test_x.py

Run by Agent 4 on a pull request, before the browser run that has the
application's credentials in its environment. Checks the test code the pull
request changes - Python files under the directories the application's test
code lives in (`pages/`, `tests/step_defs/`), where Agent 2 writes - with
validators/code_safety.py, the same rules Agent 2's gate
applies to what it generates, so code that reached the branch any other way
(a review fix, a splice, a hand edit) is held to them too. `--all` checks
every such file (when the pull request's files cannot be listed).

Not checked: the framework's own files there - each `conftest.py` and every
path in `app_under_test.reserved_paths` (the base page and the reference
files) - which legitimately read the environment and drive the browser
directly, and are changed only in reviewed framework pull requests.

Exit 0 when nothing unsafe is found; 1 with each finding listed (the job
stops before the browser run); 2 on a usage error.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validators.code_safety import _norm, is_framework_file, settings, trusted_paths, unsafe_calls

__all__ = ["trusted_paths", "to_check", "check", "main"]


def to_check(paths, trusted: set, code_dirs) -> list:
    """The changed paths this check reads: Python under the test-code
    directories, not the framework's own files."""
    dirs = tuple(d if d.endswith("/") else d + "/" for d in code_dirs)
    out = []
    for raw in paths or []:
        p = _norm(raw)
        if not p.endswith(".py") or not p.startswith(dirs):
            continue
        if is_framework_file(p, trusted):
            continue
        if p not in out:
            out.append(p)
    return out


def check(paths, root: Path, allow=()) -> list:
    """[(path, line, what)] for each unsafe use in the files that exist."""
    found = []
    for p in paths:
        f = root / p
        if not f.is_file():
            continue                                   # removed by the pull request
        for line, what in unsafe_calls(f.read_text(encoding="utf-8", errors="replace"), allow):
            found.append((p, line, what))
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--stdin", action="store_true", help="read the paths, one per line")
    ap.add_argument("--all", action="store_true", help="every file under the test-code dirs")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    s = settings()
    if not s["enabled"]:
        print("agents.agent2_coder.code_safety.enabled is false - not checked.")
        return 0
    paths = list(args.paths)
    if args.stdin:
        paths += [line for line in sys.stdin.read().splitlines() if line.strip()]
    if args.all:
        paths += [str(p.relative_to(root)) for d in s["code_dirs"]
                  for p in sorted((root / d).rglob("*.py"))]
    if not paths and not (args.stdin or args.all):
        ap.print_usage()
        return 2
    files = to_check(paths, trusted_paths(), s["code_dirs"])
    found = check(files, root, s["allow"])
    print(f"code safety: {len(files)} test-code file(s) checked")
    for p, line, what in found:
        print(f"::error file={p},line={line}::Unsafe code: {what}")
        print(f"  UNSAFE {p}:{line} {what}")
    if found:
        print(f"\n{len(found)} unsafe use(s): generated test code reaches the application only "
              "through the page objects' BasePage helpers and the fixtures. The browser run is "
              "not started, so this code never runs with the application's login. Remove each "
              "use (or, for a reviewed need, allow it by name in "
              "agents.agent2_coder.code_safety.allow).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
