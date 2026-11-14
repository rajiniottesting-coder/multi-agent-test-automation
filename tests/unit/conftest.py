"""Unit-test isolation from a project's own gates (Group B).

A project turns on gates in config.yaml that decide whether a story may be
worked on at all: R1 readiness (`agents.agent1_analyst.readiness`) and R5
approvers (`agents.agent2_coder.approver_groups` / `approvers`). Those are the
project's choices, read from the shipped config - and the sandbox stories the
other unit tests drive (no acceptance-criteria list, no approval history)
would be refused by them, so tests of drafting, coding and budgets would be
testing the project's gates instead. The same holds for X4's deployment
signal (`deployment.enabled`): on, a hand-over labels the story and the
triage asks which stories wait - the other tests would be testing that.

So every unit test runs with those gates off, unless it is marked
`gates_on`; the gates' own tests call them with the settings they need.
"""
from __future__ import annotations

import pytest

_GATE_KEYS = {"agent1_analyst": ("readiness",),
              "agent2_coder": ("approver_groups", "approvers")}


@pytest.fixture(autouse=True)
def _project_gates_off(request, monkeypatch):
    if request.node.get_closest_marker("gates_on"):
        return
    import importlib
    for module, keys in (("agents.agent1_analyst", _GATE_KEYS["agent1_analyst"]),
                         ("agents.agent2_coder", _GATE_KEYS["agent2_coder"])):
        try:
            mod = importlib.import_module(module)
        except Exception:                                          # noqa: BLE001
            continue
        real = mod.load_agent_config

        def without(*args, _real=real, _keys=keys, **kwargs):
            cfg = _real(*args, **kwargs)
            return {k: v for k, v in cfg.items() if k not in _keys}
        monkeypatch.setattr(mod, "load_agent_config", without)


@pytest.fixture(autouse=True)
def _deployment_signal_off(request, monkeypatch):
    if request.node.get_closest_marker("gates_on"):
        return
    try:
        from core import deployment
    except Exception:                                              # noqa: BLE001
        return
    real = deployment.settings

    def off():
        return {**real(), "enabled": False}
    monkeypatch.setattr(deployment, "settings", off)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(collector, name, obj):
    """Only a class a test module DEFINES is a test class. A model imported
    into it whose name starts with Test (TestCase, TestStep, TestResult in
    core/schemas.py) is not one - pytest warned about each on every run - and
    a test class imported from another test module would run twice."""
    if isinstance(obj, type) and name.startswith("Test") and \
            getattr(obj, "__module__", None) != getattr(collector.obj, "__name__", None):
        return []
    return None


# ── no unexplained skip in CI ──────────────────────────────────────────────
#
# A test that skips in CI tests nothing, and a skip nobody reads stays for
# good: 14 Nov 2026, four PDF/chart tests and the workflow lint had never run
# in Agent 4's gate (their packages were installed by the Reports job only).
# With UNIT_TESTS_NO_SKIPS set (Agent 4's unit gate), the run fails on a skip
# unless it is:
#   - a project-state skip: what a fresh project has not got yet ("no page
#     objects committed yet", "... in this checkout") - the framework's own
#     tests of a project's content, deliberately skipped until it has some;
#   - a browser skip in a job that installed no browser on purpose
#     (UNIT_TESTS_BROWSER is not "true").
import os as _os
import re as _re

_PROJECT_STATE = _re.compile(
    r"in this checkout|committed yet|no inventory|configured yet|declares no|"
    r"this application declares|no GUIDE", _re.I)
_BROWSER = _re.compile(r"no browser", _re.I)
_SKIPS: list = []


def _skip_reason(report) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)


def unexplained_skips(skips, browser_installed: bool) -> list:
    """The (test, reason) pairs a CI unit run must not accept."""
    out = []
    for nodeid, reason in skips:
        if _PROJECT_STATE.search(reason):
            continue
        if _BROWSER.search(reason) and not browser_installed:
            continue
        out.append((nodeid, reason))
    return out


def pytest_runtest_logreport(report):
    if report.skipped:
        _SKIPS.append((report.nodeid, _skip_reason(report)))


def pytest_sessionfinish(session, exitstatus):
    if not _os.getenv("UNIT_TESTS_NO_SKIPS"):
        return
    bad = unexplained_skips(_SKIPS, _os.getenv("UNIT_TESTS_BROWSER", "").lower() == "true")
    if bad:
        print(f"\n[FAIL] {len(bad)} unit test(s) skipped in CI - a skipped test tests nothing. "
              "Install what they need (requirements-unit-tests.txt) or remove them:")
        for nodeid, reason in bad:
            print(f"  {nodeid}: {reason}")
        session.exitstatus = 1
