"""Flaky tests: failed, then passed when retried once (F-19).

Agent 4 retries a failed test once (agent4_runner.yml); a test that passed on
the retry is marked `flaky` in junit.xml (scripts/finalise_junit.py) and counts
as passed. That hides a real problem if nobody keeps count, so every such pass
is recorded here, on the pipeline health issue, and the issue's description
lists the tests by how often they flaked in `flaky_tests.window_days`.

Records are append-only issue properties (one per flake:
`flaky.<test hash>.<YYYYMMDD>.<unique>`), so two runs recording at once never
lose each other's. The test's name is kept once per test under
`flaky-name.<test hash>`. A flaky test never raises a defect (F-22).

Quarantining a test that flakes often is a later step: it needs a person's
decision, and this list is what that decision reads.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import logging

from core import pipeline_health
from core.ops_settings import section
from integrations.tracker import capability

logger = logging.getLogger(__name__)

PREFIX = "flaky"
NAME_PREFIX = "flaky-name"


def hash_of(test_id: str) -> str:
    return hashlib.sha1((test_id or "").encode("utf-8")).hexdigest()[:10]


def record(tracker, flakes: list, run_url: str | None, now: _dt.datetime | None = None) -> int:
    """Record each (test id, first failure message) as one flake. Returns how
    many were stored. Never raises."""
    if not flakes or not section("flaky_tests").get("enabled", True):
        return 0
    now = now or _dt.datetime.now(_dt.timezone.utc)
    day = now.strftime("%Y%m%d")
    stored = 0
    setter = capability(tracker, "set_property")
    for test_id, first_failure in flakes:
        h = hash_of(test_id)
        if pipeline_health.record(tracker, PREFIX, [h, day],
                                  {"test": test_id, "run": run_url or "",
                                   "first_failure": (first_failure or "")[:300]}):
            stored += 1
            issue = pipeline_health.issue_key(tracker, create=False)
            try:
                if setter and issue:
                    setter(issue, f"{NAME_PREFIX}.{h}", {"test": test_id})
            except Exception as e:                                 # noqa: BLE001
                logger.debug("flaky test name not stored: %s", e)
        logger.warning("FLAKY: %s failed, then passed when retried.", test_id)
    if stored:
        pipeline_health.refresh_view(tracker, now)
    return stored


def summary(tracker, issue: str, now: _dt.datetime) -> list:
    """[(test, times, last day YYYY-MM-DD)] within the window, most frequent first."""
    window = int(section("flaky_tests").get("window_days", 30))
    since = (now - _dt.timedelta(days=window)).strftime("%Y%m%d")
    counts: dict = {}
    for key in pipeline_health.record_keys(tracker, PREFIX, issue):
        parts = key[len(PREFIX) + 1:].split(".")
        if len(parts) < 2 or parts[1] < since:
            continue
        times, last = counts.get(parts[0], (0, ""))
        counts[parts[0]] = (times + 1, max(last, parts[1]))
    getter = capability(tracker, "get_property")
    out = []
    for h, (times, last) in counts.items():
        name = h
        try:
            value = getter(issue, f"{NAME_PREFIX}.{h}") if getter else None
            name = (value or {}).get("test") or h
        except Exception:                                          # noqa: BLE001
            pass
        out.append((name, times, f"{last[:4]}-{last[4:6]}-{last[6:]}"))
    return sorted(out, key=lambda r: (-r[1], r[0]))


def prune(tracker, now: _dt.datetime) -> int:
    """Delete flake records older than the window, and the name of a test with
    none left. Run by the health check. Returns how many records went."""
    window = int(section("flaky_tests").get("window_days", 30))
    keep_from = (now - _dt.timedelta(days=window)).strftime("%Y%m%d")
    gone = pipeline_health.prune(tracker, PREFIX, keep_from, day_part=2)
    issue = pipeline_health.issue_key(tracker, create=False)
    deleter = capability(tracker, "delete_property")
    if issue and deleter:
        live = {k[len(PREFIX) + 1:].split(".")[0]
                for k in pipeline_health.record_keys(tracker, PREFIX, issue)}
        for k in pipeline_health.record_keys(tracker, NAME_PREFIX, issue):
            if k[len(NAME_PREFIX) + 1:] not in live:
                try:
                    deleter(issue, k)
                except Exception as e:                             # noqa: BLE001
                    logger.debug("flaky name %s not deleted: %s", k, e)
    return gone
