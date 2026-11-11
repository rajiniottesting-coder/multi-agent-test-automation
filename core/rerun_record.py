"""Record in junit.xml how many times a test was re-run (a pytest plugin).

Agent 4 re-runs a test whose failure names a temporary HTTP error
(pytest-rerunfailures, `--only-rerun`). scripts/collapse_junit_reruns.py was
written for a plugin that writes every attempt as its own <testcase>: it
keeps the last one and lists the test as re-run. pytest-rerunfailures 16
writes ONE <testcase> for the final attempt and nothing about the earlier
ones - so on 11 Nov 2026 a test refused with HTTP 503 on its first attempt
passed on the re-run and the step printed "no re-run tests": the re-run was
invisible to every reader of the report.

This records it at the source, whatever the plugin's junit shape: each
attempt reported as `rerun` is counted, and the test's final testcase gets a
`reruns` property (the one collapse_junit_reruns also writes). Registered by
tests/conftest.py for the E2E run; harmless where nothing is re-run.

Generic: reads pytest's report outcomes only.
"""
from __future__ import annotations

PROPERTY = "reruns"

_counts: dict = {}


def pytest_runtest_logreport(report):
    if getattr(report, "outcome", "") == "rerun":
        _counts[report.nodeid] = _counts.get(report.nodeid, 0) + 1


def pytest_runtest_teardown(item):
    """Before the teardown report is made - junitxml writes a test's
    properties from it - put the count of earlier attempts on the test."""
    n = _counts.get(item.nodeid)
    if n:
        item.user_properties[:] = [(k, v) for k, v in item.user_properties if k != PROPERTY]
        item.user_properties.append((PROPERTY, n))
