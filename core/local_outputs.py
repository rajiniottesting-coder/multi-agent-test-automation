"""A local run's outputs replace the previous run's, never pile up beside them.

On a person's machine `reports/` is reused run after run. pytest overwrites
junit.xml and the HTML report, but two folders only ever grew:

  reports/allure-results     one result, container and attachment file per
                             test per run - and Allure then shows every earlier
                             run's results as retries of the current one
  reports/failure-evidence   a screenshot, video and trace per failed test

So when a session that runs the application tests starts, the previous run's
files there are deleted. The run's history is not lost: the trend Allure
plots is carried from the last generated report (core/allure_meta.py, which
writes before this runs and is kept), and scripts/local_report.py keeps the
results of local runs in a small store of its own (`reporting.keep_days`).

Not in CI, where every job starts on a clean runner, and not for a session
that re-runs the last failures (`--last-failed`): Agent 4's retry writes
beside the first run's results on purpose. A unit-test session touches
nothing. Never raises.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# What Allure writes per test; environment.properties, categories.json,
# executor.json and history/ are written once per session and kept.
_ALLURE_PER_TEST = ("*-result.json", "*-container.json", "*-attachment*")


def runs_app_tests(items, app_tests_dir: str = "tests/step_defs") -> bool:
    marker = app_tests_dir.replace("\\", "/").strip("/") + "/"
    return any(marker in str(getattr(i, "fspath", getattr(i, "path", ""))).replace("\\", "/")
               for i in items or [])


def unit_only(args, root: Path, unit_dir: str = "tests/unit", base: Path | None = None) -> bool:
    """True when every path the session was given (relative to `base`, the
    directory pytest was started in) is inside the framework's unit tests -
    such a session writes no Allure results. No paths: False."""
    paths = [str(a).split("::", 1)[0] for a in args or [] if not str(a).startswith("-")]
    if not paths:
        return False
    unit = (Path(root) / unit_dir).resolve()
    for p in paths:
        q = Path(p)
        q = (q if q.is_absolute() else Path(base or root) / q).resolve()
        if q != unit and unit not in q.parents:
            return False
    return True


def keep_unit_tests_out_of_allure(config, root: Path) -> bool:
    """pytest_configure (before the Allure plugin's): a unit-test session
    writes no Allure results. 13 Nov 2026: every Agent 4 run wrote ~4,400
    unit tests into reports/allure-results beside the application tests, so
    the published Allure report listed them all and its history file reached
    11 MB; locally they piled up in the same folder. True when switched off."""
    try:
        base = getattr(getattr(config, "invocation_params", None), "dir", None)
        if getattr(config.option, "allure_report_dir", None) and \
                unit_only(config.args, root, base=base):
            config.option.allure_report_dir = None
            return True
    except Exception as e:                                         # noqa: BLE001
        logger.debug("Allure left as configured: %s", e)
    return False


LOCAL_JUNIT = "reports/junit.xml"


def default_junit_for_app_runs(config, root: Path) -> bool:
    """pytest_configure (before the junitxml plugin's): a session that runs
    the application tests writes reports/junit.xml even when not asked to.
    13 Nov 2026: `pytest tests/step_defs/` on the owner's machine passed 26
    tests and wrote no junit.xml, so `python -m scripts.local_report` had no
    run to record - only Agent 4 passed `--junit-xml`. A path given on the
    command line wins; a unit-test session writes none. True when set."""
    try:
        if getattr(config.option, "xmlpath", None) or getattr(config.option, "collectonly", False):
            return False                  # asked for elsewhere, or nothing runs
        base = getattr(getattr(config, "invocation_params", None), "dir", None)
        if unit_only(config.args, root, base=base):
            return False
        config.option.xmlpath = str(Path(root) / LOCAL_JUNIT)
        Path(config.option.xmlpath).parent.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.debug("junit.xml left as configured: %s", e)
        return False


def clear_previous_run(reports_dir: Path, allure_dir: Path | None) -> int:
    """Delete the previous run's per-test Allure files and failure evidence;
    the number of files deleted."""
    gone = 0
    if allure_dir and Path(allure_dir).is_dir():
        for pattern in _ALLURE_PER_TEST:
            for path in Path(allure_dir).glob(pattern):
                try:
                    path.unlink()
                    gone += 1
                except OSError:
                    pass
    evidence = Path(reports_dir) / "failure-evidence"
    if evidence.is_dir():
        gone += sum(1 for p in evidence.rglob("*") if p.is_file())
        shutil.rmtree(evidence, ignore_errors=True)
    return gone


def on_collection_finish(session) -> None:
    """pytest_collection_finish: clear the previous local run, when this
    session is a fresh local run of the application tests."""
    try:
        config = session.config
        if os.getenv("CI", "").strip().lower() in ("1", "true", "yes"):
            return
        if config.getoption("lf", default=False) or config.getoption("--last-failed", default=False):
            return
        if not runs_app_tests(session.items):
            return
        allure_dir = config.getoption("--alluredir", default=None)
        gone = clear_previous_run(Path("reports"), Path(allure_dir) if allure_dir else None)
        if gone:
            logger.info("Previous local run's outputs deleted: %d file(s) "
                        "(Allure results, failure evidence).", gone)
    except Exception as e:                                         # noqa: BLE001
        logger.debug("Previous run's outputs not cleared: %s", e)
