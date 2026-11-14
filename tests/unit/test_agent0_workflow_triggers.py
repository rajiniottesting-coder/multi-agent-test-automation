"""Agent 0's workflow: each trigger runs exactly its own jobs, and the drift
job can be started on demand (dispatch mode `drift`) without the scan or the
reconcile running beside it.
"""

import pytest
import yaml


def _workflow():
    from config.paths import PROJECT_ROOT
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "agent0_impact.yml")
                          .read_text(encoding="utf-8"))


def _runs(condition: str, event: str, schedule: str = "", mode: str = "") -> bool:
    """Evaluate a job's `if:` for one event (gate enabled). The expressions
    use only ==, !=, && and || over these names, so a direct translation is
    exact."""
    expr = (condition
            .replace("needs.gate.outputs.enabled", "'true'")
            .replace("github.event_name", repr(event))
            .replace("github.event.schedule", repr(schedule))
            .replace("github.event.inputs.mode", repr(mode))
            .replace("&&", " and ").replace("||", " or "))
    return bool(eval(expr))


@pytest.mark.parametrize("event, schedule, mode, expected", [
    ("schedule", "15 5 * * 1-5", "", {"scan", "reconcile"}),
    ("schedule", "45 1 * * *", "", {"drift"}),
    # The 30-minute story scans: the scan only - reconcile stays daily (#252).
    ("schedule", "32 4 * * 1-5", "", {"scan"}),
    ("schedule", "2,32 5-12 * * 1-5", "", {"scan"}),
    ("schedule", "2,32 13 * * 1-5", "", {"scan"}),
    ("workflow_dispatch", "", "", {"scan", "reconcile"}),          # no mode: as before
    ("workflow_dispatch", "", "scan", {"scan", "reconcile"}),
    ("workflow_dispatch", "", "drift", {"drift"}),
    ("pull_request", "", "", {"code-change"}),
])
def test_each_trigger_runs_exactly_its_jobs(event, schedule, mode, expected):
    jobs = _workflow()["jobs"]
    ran = {name for name, job in jobs.items()
           if name != "gate" and _runs(job.get("if", "false"), event, schedule, mode)}
    assert ran == expected


def test_dispatch_offers_the_drift_mode():
    on = _workflow()[True]                       # YAML 1.1 reads the key `on` as True
    mode = on["workflow_dispatch"]["inputs"]["mode"]
    assert mode["options"] == ["scan", "drift"] and mode["default"] == "scan"
