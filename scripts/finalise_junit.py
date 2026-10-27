"""Write what Agent 4 learned about each test into junit.xml (core/junit_marks.py).

    python -m scripts.finalise_junit reports/junit.xml [--retry reports/junit-retry.xml]
    python -m scripts.finalise_junit --count-failed reports/junit.xml
    python -m scripts.finalise_junit --verdict reports/junit.xml --exit-code 1

Runs after scripts/collapse_junit_reruns.py.

  --retry    merges the one retry of the failed tests (F-19). A test that
             passed on it takes the retry's result and is marked `flaky` -
             or `outage_recovered` when its first failure was the
             application's outage (not a flake: the test did nothing wrong);
             `first_failure` keeps the first failure's first line. A test that
             failed again takes the retry's failure and is marked `retried`.
  (always)   marks every failure whose text says the application was
             unavailable (core.failure_diagnosis.is_outage) `outage` (F-7).
  --verdict  the job's E2E result: exit 1 when anything still fails (outages
             included - the application stopped it, so it was not tested),
             when pytest was interrupted or could not collect (`--exit-code`),
             or when there is no readable report or no test at all.

Marking never fails: a missing or unreadable file is left alone, exit code 0.
"""
from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from core import junit_marks as jm
from core.failure_diagnosis import is_outage

# pytest exit codes: 0 all passed, 1 some failed, 2 interrupted, 3 internal
# error, 4 usage error, 5 no tests collected.
_TESTS_FAILED = 1


def mark_outages(root: ET.Element) -> list:
    """Mark outage failures in place. Returns their test ids."""
    marked = []
    for case in jm.cases(root):
        if jm.outcome(case) in ("failed", "error") and is_outage(jm.failure_text(case)):
            jm.set_prop(case, "outage", "1")
            marked.append(jm.case_id(case))
    return marked


def _first_line(text: str) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0][:300] if lines else ""


def merge_retry(root: ET.Element, retry: ET.Element) -> dict:
    """Replace each failed test with its retry, in place. Returns
    {"flaky": [ids], "outage_recovered": [ids], "retried": [ids]}."""
    again = {(c.get("classname", ""), c.get("name", "")): c for c in jm.cases(retry)}
    out = {"flaky": [], "outage_recovered": [], "retried": []}
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        for i, case in enumerate(list(suite)):
            if case.tag != "testcase" or jm.outcome(case) not in ("failed", "error"):
                continue
            second = again.get((case.get("classname", ""), case.get("name", "")))
            if second is None or jm.outcome(second) not in ("passed", "failed", "error"):
                continue                      # not retried (or skipped on retry): keep it
            first_text = jm.failure_text(case)
            earlier = jm.props(case)
            replacement = copy.deepcopy(second)
            for name, value in earlier.items():
                if name not in jm.MARKS:      # e.g. `reruns` from the first run
                    jm.set_prop(replacement, name, value)
            jm.set_prop(replacement, "first_failure", _first_line(first_text))
            if jm.outcome(second) == "passed":
                mark = "outage_recovered" if is_outage(first_text) else "flaky"
            else:
                mark = "retried"
            jm.set_prop(replacement, mark, "1")
            out[mark].append(jm.case_id(case))
            suite.remove(case)
            suite.insert(i, replacement)
    jm.recount(root)
    return out


def finalise(root: ET.Element, retry: ET.Element | None = None) -> dict:
    """Every mark, in place."""
    result = merge_retry(root, retry) if retry is not None else \
        {"flaky": [], "outage_recovered": [], "retried": []}
    result["outage"] = mark_outages(root)
    return result


def _load(path: Path, quiet: bool = False):
    if not path.is_file():
        if not quiet:
            print(f"{path}: no report")
        return None
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        if not quiet:
            print(f"{path}: unreadable ({exc})")
        return None


def count_failed(path: Path) -> int:
    tree = _load(path, quiet=True)
    if tree is None:
        return 0
    return sum(1 for c in jm.cases(tree.getroot()) if jm.outcome(c) in ("failed", "error"))


def verdict(path: Path, exit_code: str | None) -> tuple:
    """(job exit code, reason) for the E2E after the retry."""
    code = (exit_code or "").strip()
    if code and code not in ("0", str(_TESTS_FAILED)):
        names = {"2": "interrupted", "3": "an internal error", "4": "a usage error",
                 "5": "no tests collected"}
        return 1, f"pytest ended with exit code {code} ({names.get(code, 'unexpected')})"
    tree = _load(path, quiet=True)
    if tree is None:
        return 1, f"no readable report at {path}"
    cases = jm.cases(tree.getroot())
    if not cases:
        return 1, "the report holds no tests"
    failing = [c for c in cases if jm.outcome(c) in ("failed", "error")]
    outages = [c for c in failing if jm.is_outage(c)]
    flaky = [c for c in cases if jm.is_flaky(c)]
    if failing:
        real = len(failing) - len(outages)
        parts = [f"{real} failed"] if real else []
        if outages:
            parts.append(f"{len(outages)} not judged (application unavailable)")
        return 1, f"{' and '.join(parts)} of {len(cases)} after the retry"
    note = f" ({len(flaky)} passed only on the retry - flaky)" if flaky else ""
    return 0, f"all {len(cases)} tests passed{note}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default="reports/junit.xml")
    ap.add_argument("--retry", help="junit report of the one retry of the failed tests")
    ap.add_argument("--count-failed", action="store_true",
                    help="print how many tests failed or errored, and stop")
    ap.add_argument("--verdict", action="store_true",
                    help="exit 1 when the E2E still fails after the retry")
    ap.add_argument("--exit-code", help="--verdict: the first pytest run's exit code")
    args = ap.parse_args(argv)
    path = Path(args.path)

    if args.count_failed:
        print(count_failed(path))
        return 0
    if args.verdict:
        code, reason = verdict(path, args.exit_code)
        print(("E2E failed: " if code else "E2E passed: ") + reason)
        return code

    tree = _load(path)
    if tree is None:
        return 0
    retry_tree = _load(Path(args.retry), quiet=True) if args.retry else None
    result = finalise(tree.getroot(), retry_tree.getroot() if retry_tree is not None else None)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    for test in result["flaky"]:
        print(f"flaky - failed, then passed on the retry: {test}")
    for test in result["outage_recovered"]:
        print(f"passed on the retry after the application's outage: {test}")
    for test in result["retried"]:
        print(f"failed again on the retry: {test}")
    for test in result["outage"]:
        print(f"application unavailable (reported apart from test failures): {test}")
    if not any(result.values()):
        print(f"{path}: nothing to mark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
