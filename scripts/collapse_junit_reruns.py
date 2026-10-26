"""Keep only the final attempt of each re-run test in a junit report.

Agent 4 re-runs a test whose failure names a temporary HTTP error from the
application under test (pytest-rerunfailures, `--only-rerun`). The plugin then
writes EVERY attempt into junit.xml as its own <testcase>, and an attempt that
was re-run carries no <failure> element - so a test that failed once and then
passed is counted as two passes, and one that failed twice as a pass plus a
failure. Agent 5's story report, Agent 4's run summary and Agent 3's
per-scenario evidence all read this file.

This keeps the LAST <testcase> of each (classname, name) in each suite - the
attempt whose outcome counts - records how many attempts came before it as a
`reruns` property, and recomputes the suite's tests/failures/errors/skipped.

    python -m scripts.collapse_junit_reruns reports/junit.xml

A missing or unreadable file is left alone and the exit code is 0: this step
must never be the reason a run has no report.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _outcome(case: ET.Element) -> str:
    tags = {child.tag for child in case}
    return ("failure" if "failure" in tags else "error" if "error" in tags
            else "skipped" if "skipped" in tags else "passed")


def collapse(root: ET.Element) -> dict:
    """Collapse in place. Returns {"classname::name": earlier attempts} for the
    tests that were re-run."""
    reruns: dict = {}
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        cases = [c for c in list(suite) if c.tag == "testcase"]
        last: dict = {}
        for case in cases:
            last[(case.get("classname", ""), case.get("name", ""))] = case
        for case in cases:
            key = (case.get("classname", ""), case.get("name", ""))
            if last[key] is not case:
                suite.remove(case)
                label = f"{key[0]}::{key[1]}"
                reruns[label] = reruns.get(label, 0) + 1
        for key, case in last.items():
            n = reruns.get(f"{key[0]}::{key[1]}")
            if n:
                props = case.find("properties")
                if props is None:
                    props = ET.Element("properties")
                    case.insert(0, props)
                ET.SubElement(props, "property", name="reruns", value=str(n))
        kept = list(last.values())
        counts = {"failure": 0, "error": 0, "skipped": 0}
        for case in kept:
            outcome = _outcome(case)
            if outcome in counts:
                counts[outcome] += 1
        suite.set("tests", str(len(kept)))
        suite.set("failures", str(counts["failure"]))
        suite.set("errors", str(counts["error"]))
        suite.set("skipped", str(counts["skipped"]))
    return reruns


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else Path("reports/junit.xml")
    if not path.is_file():
        print(f"{path}: no report, nothing to collapse")
        return 0
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"{path}: unreadable ({exc}), left as it is")
        return 0
    reruns = collapse(tree.getroot())
    if not reruns:
        print(f"{path}: no re-run tests")
        return 0
    tree.write(path, encoding="utf-8", xml_declaration=True)
    for label, n in sorted(reruns.items()):
        print(f"re-run {n} time(s) after a temporary HTTP error: {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
