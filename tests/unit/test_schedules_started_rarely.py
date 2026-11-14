"""A schedule the repository host starts only rarely (a share of its slots
below `schedule_min_share`) is reported by the pipeline health check, and
enough starts close the alert. A schedule that never started at all is the
other alert (test_scheduled_runs_not_started.py).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from core import health_checks as hc


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def _tree(tmp_path, cron="0 * * * *"):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "job.yml").write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n')
    return tmp_path


class _Host:
    def __init__(self, runs):
        self.runs = runs

    def get_workflow_runs(self, name, branch, limit=20):
        return self.runs[:limit]


def _run(hours_ago, event="schedule"):
    return {"event": event, "created_at": (NOW - dt.timedelta(hours=hours_ago)).isoformat()}


def _by_id(findings):
    return {f.alert_id: f for f in findings}


def test_a_schedule_started_rarely_is_reported(tmp_path):
    root = _tree(tmp_path)                                   # 24 asked for in 24 h
    runs = [_run(3), _run(11), _run(19), _run(30)]           # 3 started
    f = _by_id(hc.schedule_findings(_Host(runs), root, NOW, 24, 3, 0.25))
    rare = f["workflow-starting-rarely:job.yml"]
    assert rare.problem and "3 of 24" in rare.title
    assert "GUIDE -> Scheduled runs that do not start" in rare.detail
    assert not f["workflow-not-starting:job.yml"].problem   # some did start


def test_enough_starts_close_it(tmp_path):
    root = _tree(tmp_path)
    runs = [_run(h) for h in range(0, 24, 3)] + [_run(30)]  # 8 of 24 = 33%
    rare = _by_id(hc.schedule_findings(_Host(runs), root, NOW, 24, 3, 0.25))[
        "workflow-starting-rarely:job.yml"]
    assert not rare.problem and "start as asked again" in rare.title


def test_none_started_is_the_other_alert_not_this_one(tmp_path):
    root = _tree(tmp_path)
    f = _by_id(hc.schedule_findings(_Host([_run(30)]), root, NOW, 24, 3, 0.25))
    assert f["workflow-not-starting:job.yml"].problem
    assert not f["workflow-starting-rarely:job.yml"].problem


def test_the_share_check_is_off_at_zero_and_by_default(tmp_path):
    root = _tree(tmp_path)
    runs = [_run(3), _run(30)]
    assert set(_by_id(hc.schedule_findings(_Host(runs), root, NOW, 24, 3))) == \
        {"workflow-not-starting:job.yml"}
    assert set(_by_id(hc.schedule_findings(_Host(runs), root, NOW, 24, 3, 0))) == \
        {"workflow-not-starting:job.yml"}


def test_the_health_check_passes_the_share():
    from core.ops_settings import section
    assert 0 < section("pipeline_health")["schedule_min_share"] < 1
    src = (ROOT / "scripts/pipeline_health_check.py").read_text()
    assert 'schedule_min_share' in src
