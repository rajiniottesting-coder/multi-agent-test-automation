"""Unit-test isolation from a project's own gates (Group B).

A project turns on gates in config.yaml that decide whether a story may be
worked on at all: R1 readiness (`agents.agent1_analyst.readiness`) and R5
approvers (`agents.agent2_coder.approver_groups` / `approvers`). Those are the
project's choices, read from the shipped config - and the sandbox stories the
other unit tests drive (no acceptance-criteria list, no approval history)
would be refused by them, so tests of drafting, coding and budgets would be
testing the project's gates instead.

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
