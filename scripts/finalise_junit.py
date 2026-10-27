"""Write what Agent 4 learned about each test into junit.xml (core/junit_marks.py).

    python -m scripts.finalise_junit reports/junit.xml

Runs after scripts/collapse_junit_reruns.py. Marks every failure whose text
says the application was unavailable (core.failure_diagnosis.is_outage) with
the `outage` property, so the run summary, Agent 5, Agent 3 and the defect
triage all report it apart from test failures (F-7).

A missing or unreadable file is left alone and the exit code is 0: this step
must never be the reason a run has no report.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from core import junit_marks as jm
from core.failure_diagnosis import is_outage


def mark_outages(root: ET.Element) -> list:
    """Mark outage failures in place. Returns their test ids."""
    marked = []
    for case in jm.cases(root):
        if jm.outcome(case) in ("failed", "error") and is_outage(jm.failure_text(case)):
            jm.set_prop(case, "outage", "1")
            marked.append(jm.case_id(case))
    return marked


def finalise(root: ET.Element) -> dict:
    """Every mark, in place. Returns {"outage": [ids]}."""
    return {"outage": mark_outages(root)}


def _load(path: Path):
    if not path.is_file():
        print(f"{path}: no report, nothing to finalise")
        return None
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        print(f"{path}: unreadable ({exc}), left as it is")
        return None


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else Path("reports/junit.xml")
    tree = _load(path)
    if tree is None:
        return 0
    result = finalise(tree.getroot())
    tree.write(path, encoding="utf-8", xml_declaration=True)
    for test in result["outage"]:
        print(f"application unavailable (reported apart from test failures): {test}")
    if not any(result.values()):
        print(f"{path}: nothing to mark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
