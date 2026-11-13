"""A history of test results beyond one run (RP1).

Every full run of the application tests on the default branch (nightly, by
hand, or a push that ran them) is recorded on a branch of its own
(`reporting.store_branch`), written only by the reports workflow
(.github/workflows/reports.yml):

  runs.jsonl            one line per run: id, event, commit, start, totals
  results/YYYY-MM.jsonl one line per test per run, by the run's month

JSON lines, not a database file: appending is a one-line diff, two runs never
conflict on a binary, and any tool reads it. The dashboard, the traceability
matrix and the PDF (scripts/build_site.py) read only this store, so they show
the same numbers.

A test's verdict is Agent 4's final reading of junit.xml (core/junit_marks.py):
passed, failed, skipped, flaky (failed, passed on the retry - counts as
passed) or outage (the application was unavailable - nothing was tested).

Recording is idempotent by run id: a run already in runs.jsonl is skipped, so
the workflow can catch up on every recent run each time it starts.
"""
from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from core import junit_marks as jm

logger = logging.getLogger(__name__)

SCHEMA = 1
RUNS_FILE = "runs.jsonl"
RESULTS_DIR = "results"
_FAILURE_CHARS = 300


def verdict(case: ET.Element) -> str:
    """passed | failed | skipped | flaky | outage - Agent 4's final reading."""
    if jm.is_outage(case):
        return "outage"
    if jm.is_flaky(case):
        return "flaky"
    o = jm.outcome(case)
    return "failed" if o in ("failed", "error") else o


def _feature_file(test_id: str) -> str:
    """`tests.step_defs.test_login::...` -> `login.feature`."""
    module = test_id.split("::", 1)[0].rsplit(".", 1)[-1]
    return (module[5:] if module.startswith("test_") else module) + ".feature"


def _first_line(text: str) -> str:
    from core.redaction import redact
    line = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
    return redact(line)[:_FAILURE_CHARS]


def case_records(junit_xml: bytes, run: dict, trace=None) -> list[dict]:
    """One record per test case of a run's final junit.xml.

    `run` carries at least "id" and "started" (ISO time); `trace(test_id)`
    returns {"test_case", "owner"} (core.defects.trace_of) or None. An
    unreadable report gives []."""
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as e:
        logger.warning("Run %s: junit.xml unreadable (%s)", run.get("id"), e)
        return []
    out = []
    for case in jm.cases(root):
        test_id = jm.case_id(case)
        t = {}
        if trace is not None:
            try:
                t = trace(test_id) or {}
            except Exception as e:                                 # noqa: BLE001
                logger.debug("No trace for %s: %s", test_id, e)
        v = verdict(case)
        try:
            duration = round(float(case.get("time") or 0), 3)
        except ValueError:
            duration = 0.0
        out.append({
            "schema": SCHEMA, "run_id": run["id"], "started": run.get("started"),
            "test": test_id, "file": _feature_file(test_id),
            "scenario": case.get("name", ""),
            "test_case": t.get("test_case"), "story": t.get("owner"),
            "verdict": v, "duration_s": duration,
            "failure": _first_line(jm.failure_text(case)) if v in ("failed", "outage") else "",
            "first_failure": (_first_line(jm.props(case).get("first_failure", ""))
                              if v == "flaky" else ""),
        })
    return out


def run_record(run: dict, cases: list[dict]) -> dict:
    """The run's own line: what started it, on which commit, and its totals."""
    totals = {k: 0 for k in ("passed", "failed", "skipped", "flaky", "outage")}
    for c in cases:
        totals[c["verdict"]] = totals.get(c["verdict"], 0) + 1
    return {"schema": SCHEMA, "run_id": run["id"], "started": run.get("started"),
            "event": run.get("event"), "commit": run.get("head_sha"),
            "url": run.get("url"), "conclusion": run.get("conclusion"),
            "tests": len(cases), "duration_s": round(sum(c["duration_s"] for c in cases), 3),
            **totals}


def _lines(path: Path) -> list[dict]:
    out = []
    if not path.is_file():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("%s line %d unreadable; skipped", path, n)
    return out


def read_runs(store: Path) -> list[dict]:
    """Every recorded run, oldest first."""
    return sorted(_lines(Path(store) / RUNS_FILE), key=lambda r: r.get("started") or "")


def read_results(store: Path, since: str | None = None) -> list[dict]:
    """Every recorded test result, oldest first; `since` an ISO date or time."""
    rows = []
    for path in sorted((Path(store) / RESULTS_DIR).glob("*.jsonl")):
        if since and path.stem < since[:7]:
            continue                                  # a month before `since`
        rows.extend(_lines(path))
    if since:
        rows = [r for r in rows if (r.get("started") or "") >= since]
    return sorted(rows, key=lambda r: (r.get("started") or "", r.get("test") or ""))


def recorded_run_ids(store: Path) -> set:
    return {r.get("run_id") for r in _lines(Path(store) / RUNS_FILE)}


def append(store: Path, run: dict, cases: list[dict]) -> bool:
    """Add one run and its results. False (nothing written) when the run is
    already recorded or has no results."""
    store = Path(store)
    if not cases or run["id"] in recorded_run_ids(store):
        return False
    month = re.sub(r"[^0-9-]", "", (run.get("started") or "unknown")[:7]) or "unknown"
    (store / RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    with (store / RESULTS_DIR / f"{month}.jsonl").open("a", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, sort_keys=True) + "\n")
    with (store / RUNS_FILE).open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_record(run, cases), sort_keys=True) + "\n")
    return True


def prune(store: Path, keep_days: int, now=None) -> int:
    """Delete runs and results older than `keep_days`; the number of runs
    deleted. A month file left empty is removed. Nothing when keep_days <= 0."""
    import datetime as _dt
    store = Path(store)
    if keep_days <= 0:
        return 0
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = (now - _dt.timedelta(days=keep_days)).isoformat()
    runs = _lines(store / RUNS_FILE)
    kept = [r for r in runs if (r.get("started") or "") >= cutoff]
    if len(kept) == len(runs):
        return 0
    gone = {r.get("run_id") for r in runs} - {r.get("run_id") for r in kept}
    (store / RUNS_FILE).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in kept),
                                   encoding="utf-8")
    for path in sorted((store / RESULTS_DIR).glob("*.jsonl")):
        rows = [r for r in _lines(path) if r.get("run_id") not in gone]
        if rows:
            path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                            encoding="utf-8")
        else:
            path.unlink()
    logger.info("Results store: %d run(s) older than %d days deleted", len(gone), keep_days)
    return len(gone)


def latest_by_test(results: list[dict]) -> dict:
    """{test id: its most recent record}."""
    out = {}
    for r in results:                       # oldest first, so the last wins
        out[r["test"]] = r
    return out
