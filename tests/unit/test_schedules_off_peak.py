"""Agents 0, 1 and 2 scan every 30 minutes in working hours, off :00 and :30.

3 Nov 2026: Agents 1 and 2 were scheduled every 30 minutes on :00 and :30;
for two months GitHub started 4 of their 19 weekday runs a day, and none
before 17:00 IST that day. GitHub drops scheduled runs of a quiet
repository, the ones at the start of an hour or half hour first. Agent 0's
story scan ran once a day (10:45 IST).

Now each of the three scans every 30 minutes, weekdays 10:00-19:00 IST, at
its own minutes off :00/:30. Agent 0's 30-minute runs are the story scan
only: reconcile keeps its one daily run, because its two-scan rule counts
scans. The hand-off (core/handoff.py) stays the primary start; the schedule
is the safety net.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
AGENTS = {"agent0_impact.yml": "scan", "agent1_analyst.yml": "analyze",
          "agent2_coder.yml": "generate"}
DAILY = {"15 5 * * 1-5", "45 1 * * *"}          # Agent 0's daily scan + reconcile, drift


def _wf(name):
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def _fires(cron: str) -> list:
    """(weekday-only, IST minutes of the day) for a cron of the forms used here."""
    minute, hour, dom, month, dow = cron.split()
    assert dom == month == "*"
    hours = (range(int(hour.split("-")[0]), int(hour.split("-")[1]) + 1) if "-" in hour
             else [int(h) for h in hour.split(",")])
    out = []
    for h in hours:
        for m in (int(x) for x in minute.split(",")):
            out.append((dow == "1-5", (h * 60 + m + 330) % 1440))
    return out


def _working_hour_crons(name):
    return [c["cron"] for c in _wf(name)[True]["schedule"] if c["cron"] not in DAILY]


@pytest.mark.parametrize("name", AGENTS)
def test_every_30_minutes_on_weekdays_from_10_to_19_ist(name):
    fires = sorted(t for c in _working_hour_crons(name) for wk, t in _fires(c) if wk)
    assert all(wk for c in _working_hour_crons(name) for wk, _ in _fires(c)), "weekdays only"
    assert 10 * 60 <= fires[0] < 10 * 60 + 15 and 19 * 60 <= fires[-1] < 19 * 60 + 15
    assert all(b - a == 30 for a, b in zip(fires, fires[1:])), "every 30 minutes, no gap"


@pytest.mark.parametrize("name", AGENTS)
def test_never_on_the_hour_or_half_hour(name):
    for cron in _working_hour_crons(name):
        assert all(int(m) % 30 != 0 for m in cron.split()[0].split(",")), cron


def test_the_agents_do_not_fire_together():
    minutes = {name: {int(m) % 30 for c in _working_hour_crons(name) for m in c.split()[0].split(",")}
               for name in AGENTS}
    assert all(len(v) == 1 for v in minutes.values())
    assert len({next(iter(v)) for v in minutes.values()}) == 3
    a0, a1, a2 = (next(iter(minutes[n])) for n in AGENTS)
    assert a0 < a1 < a2, "Agent 0 releases, Agent 1 drafts, Agent 2 codes - in that order"


def test_agent0s_30_minute_runs_are_the_story_scan_only():
    jobs = _wf("agent0_impact.yml")["jobs"]
    for cron in _working_hour_crons("agent0_impact.yml"):
        assert "github.event.schedule != '45 1 * * *'" in jobs["scan"]["if"]
        assert f"'{cron}'" not in jobs["reconcile"]["if"]
    assert "github.event.schedule == '15 5 * * 1-5'" in jobs["reconcile"]["if"], \
        "reconcile keeps its one daily run: its two-scan rule counts scans"


@pytest.mark.parametrize("name, job", AGENTS.items())
def test_a_scheduled_run_ends_before_the_next(name, job):
    assert int(_wf(name)["jobs"][job]["timeout-minutes"]) <= 30, \
        "concurrency queues the next run; a longer job would stack them"
