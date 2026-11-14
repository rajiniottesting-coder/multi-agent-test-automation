"""Agent 0's workflow: each trigger runs exactly its own jobs, and the drift
job can be started on demand (dispatch mode `drift`) without the scan or the
reconcile running beside it.

X10 (14 Nov 2026): the drift job has no schedule of its own. Inventory Health
runs the one nightly crawl and dispatches mode = drift with its run id; the
drift job then reads that run's report instead of crawling again.
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


def test_the_drift_job_has_no_schedule_of_its_own():
    crons = [c["cron"] for c in _workflow()[True]["schedule"]]
    drift_if = _workflow()["jobs"]["drift"]["if"]
    assert not any(_runs(drift_if, "schedule", c) for c in crons), \
        "Inventory Health starts it with its report: one nightly crawl"


def test_a_drift_run_reads_the_inventory_health_report_and_crawls_only_by_hand():
    on = _workflow()[True]
    assert on["workflow_dispatch"]["inputs"]["drift_report_run"]["default"] == ""
    job = _workflow()["jobs"]["drift"]
    assert job["permissions"]["actions"] == "read"
    steps = {s.get("name"): s for s in job["steps"]}
    fetch = steps["Fetch the Inventory Health report"]
    assert fetch["if"] == "github.event.inputs.drift_report_run != ''"
    assert fetch["uses"].startswith("actions/download-artifact@")
    assert fetch["with"]["name"] == "inventory-drift-report"
    assert fetch["with"]["run-id"] == "${{ github.event.inputs.drift_report_run }}"
    assert steps["Install the browser (a run by hand checks the inventory itself)"]["if"] \
        == "github.event.inputs.drift_report_run == ''"
    check = steps["Check the inventory, then analyse the drift"]
    assert check["env"]["REPORT_RUN"] == "${{ github.event.inputs.drift_report_run }}"
    assert 'if [ -z "$REPORT_RUN" ]; then' in check["run"]
    names = list(steps)
    assert names.index("Fetch the Inventory Health report") \
        < names.index("Check the inventory, then analyse the drift")
