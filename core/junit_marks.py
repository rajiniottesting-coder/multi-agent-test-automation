"""What Agent 4 learned about each test, written into junit.xml once.

scripts/finalise_junit.py marks a test case with properties after the run:

  outage            failed because the application was unavailable (F-7) -
                    reported apart from test failures, never evidence for
                    Agent 3, never a defect
  flaky             failed, then passed when retried once (F-19) - counts as
                    passed and is recorded on the pipeline health issue
  outage_recovered  failed on an outage, then passed when retried - passed,
                    and not a flake: the test did nothing wrong
  first_failure     the first line of the failure a retry replaced
  retried           failed, retried once, failed again

Every reader - the run summary, Agent 5, Agent 3, the defect triage - asks
these helpers, so the readings never disagree. Standard library only.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

MARKS = ("outage", "flaky", "outage_recovered", "first_failure", "retried")


def props(case: ET.Element) -> dict:
    """{name: value} of a test case's <properties>."""
    node = case.find("properties")
    if node is None:
        return {}
    return {p.get("name", ""): p.get("value", "") for p in node.findall("property")}


def set_prop(case: ET.Element, name: str, value: str) -> None:
    """Set one property, replacing an earlier value of the same name."""
    node = case.find("properties")
    if node is None:
        node = ET.Element("properties")
        case.insert(0, node)
    for p in node.findall("property"):
        if p.get("name") == name:
            p.set("value", value)
            return
    ET.SubElement(node, "property", name=name, value=value)


def outcome(case: ET.Element) -> str:
    """passed | failed | error | skipped (junit's own reading)."""
    tags = {child.tag for child in case}
    return ("failed" if "failure" in tags else "error" if "error" in tags
            else "skipped" if "skipped" in tags else "passed")


def failure_text(case: ET.Element) -> str:
    """The failure's message and traceback (not captured output)."""
    node = case.find("failure")
    if node is None:
        node = case.find("error")
    if node is None:
        return ""
    return "\n".join(part for part in (node.get("message") or "", node.text or "") if part)


def is_outage(case: ET.Element) -> bool:
    return outcome(case) in ("failed", "error") and props(case).get("outage") == "1"


def is_flaky(case: ET.Element) -> bool:
    return outcome(case) == "passed" and props(case).get("flaky") == "1"


def case_id(case: ET.Element) -> str:
    return f"{case.get('classname', '')}::{case.get('name', '')}"


def cases(root: ET.Element) -> list:
    return list(root.iter("testcase"))


def recount(root: ET.Element) -> None:
    """Make each suite's tests/failures/errors/skipped match its test cases."""
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        kept = [c for c in suite if c.tag == "testcase"]
        counts = {"failed": 0, "error": 0, "skipped": 0}
        for case in kept:
            o = outcome(case)
            if o in counts:
                counts[o] += 1
        suite.set("tests", str(len(kept)))
        suite.set("failures", str(counts["failed"]))
        suite.set("errors", str(counts["error"]))
        suite.set("skipped", str(counts["skipped"]))
