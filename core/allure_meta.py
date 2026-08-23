"""Fill the Allure report's metadata panels at run time.

An Allure report has four panels that are blank unless something writes them,
and none of them is produced by running tests:

    ENVIRONMENT   environment.properties   - what was this run against?
    CATEGORIES    categories.json          - how should failures be grouped?
    EXECUTORS     executor.json            - who ran it, and where?
    TREND         history/                 - carried from the previous report

A report showing four empty boxes reads as a report that does not work, which
is a poor thing to put in front of anyone. All four are cheap, and all four
can be derived from what this project already knows.

Nothing here is written by hand for one application:

    environment  comes from config.yaml and the environment variables
    categories   come from core.failure_diagnosis's own signatures
    executor     comes from CI variables, or reports a local run
    history      is copied from the previously generated report, if any

Point the framework at a different application and every value changes with
it, because every value is read rather than stated.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
def _environment_lines(config: dict, project_root: Path) -> list:
    """The facts worth knowing when reading a result months later.

    Deliberately not everything: a panel with forty rows is skimmed and a
    panel with ten is read. What earns a place is anything that would change
    the outcome - the target, the browser settings, the versions.
    """
    app = (config or {}).get("app_under_test") or {}
    browser = (config or {}).get("browser") or {}

    def version_of(package: str) -> str:
        try:
            from importlib.metadata import version
            return version(package)
        except Exception:                                 # noqa: BLE001
            return "unknown"

    # BASE_URL overrides config at run time, so report what was actually used.
    base_url = os.getenv("BASE_URL") or app.get("base_url", "")

    headless = os.getenv("PLAYWRIGHT_HEADLESS")
    if headless is None:
        headless = "true" if os.getenv("CI") else str(browser.get("headless", ""))

    viewport = browser.get("viewport") or {}
    pairs = [
        ("Application", app.get("name", "")),
        ("Base.URL", base_url),
        ("Browser", browser.get("name", "chromium")),
        ("Browser.Headless", headless),
        ("Browser.SlowMo.ms", browser.get("slow_mo", "")),
        ("Browser.Viewport", f"{viewport.get('width', '')}x{viewport.get('height', '')}"
                             if viewport else ""),
        ("Browser.Timeout.ms", browser.get("timeout", "")),
        ("Playwright", version_of("playwright")),
        ("pytest", version_of("pytest")),
        ("pytest-bdd", version_of("pytest-bdd")),
        ("Python", platform.python_version()),
        ("Platform", f"{platform.system()} {platform.release()}"),
        ("Run.Type", "CI" if os.getenv("CI") else "local"),
    ]
    return [f"{key}={value}" for key, value in pairs if str(value) != ""]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
def _categories(project_root: Path) -> list:
    """Group failures by the framework's OWN diagnosis labels.

    core.failure_diagnosis already classifies every failure it recognises and
    writes `CAUSE (<label>)` into the captured output. Allure groups failures
    by matching a regex against the message, so those labels convert straight
    into categories - and the grouping in the report becomes the same grouping
    the logs use.

    Deriving them beats writing a list: a signature added to the diagnosis
    module shows up here on the next run, and one that is removed stops
    appearing. A hand-written list would drift, which is the failure this
    project has paid for more than any other.
    """
    categories: list = []
    seen_patterns: list = []
    try:
        sys.path.insert(0, str(project_root))
        from core.failure_diagnosis import _SIGNATURES

        import re as _re
        for _pattern, diagnosis in _SIGNATURES:
            label = getattr(diagnosis, "label", "")
            if not label:
                continue
            # Match the SIGNATURE, not the CAUSE line.
            #
            # attach_diagnosis writes `CAUSE (<label>)` into report.sections,
            # which pytest prints and junit.xml carries - and which
            # allure-pytest never reads. It takes `message` and `trace` from
            # the exception. Categories keyed on the CAUSE line therefore
            # matched nothing and every failure fell into Allure's default
            # "Product defects" bucket, with the panel looking populated.
            #
            # The signature's own pattern is the right key: it is what
            # produced the label in the first place, so there is still one
            # source and nothing to drift.
            pattern = _to_java_regex(getattr(_pattern, "pattern", ""))
            if not pattern:
                continue

            # EXCLUSIVE, in signature order, because the two systems disagree
            # about ties: diagnose() returns the FIRST signature that matches
            # and Allure applies EVERY category that does. Left alone, one
            # failure appears under several headings while the log names one,
            # and a reader comparing them finds the report and the log
            # disagreeing about what went wrong.
            #
            # Signature order is significance order - the specific readings
            # come before the general ones - so excluding the earlier patterns
            # reproduces exactly what diagnose() decided.
            guard = "".join(f"(?!.*{earlier})" for earlier in seen_patterns)
            categories.append({
                "name": label[:1].upper() + label[1:],
                "traceRegex": "(?s)\\A" + guard + ".*" + pattern + ".*",
                "matchedStatuses": ["failed", "broken"],
            })
            seen_patterns.append(pattern)
    except Exception:                                     # noqa: BLE001
        logger.debug("could not derive Allure categories from the diagnosis module")

    # Two catch-alls, last, so anything unrecognised is still visible rather
    # than silently absent from the panel.
    # No catch-all. A category with no regex matches EVERY failure, so it
    # duplicates every row rather than collecting the leftovers - Allure
    # applies all matching rules, not the first. Anything no signature
    # recognises still appears, under Allure's own built-in bucket.
    return categories


def _to_java_regex(pattern: str) -> str:
    """Make a Python pattern safe for Allure, which evaluates it in Java.

    Only one construct in this project's signatures differs: Python's
    `(?P<name>...)` named group is `(?<name>...)` in Java, and an unconverted
    one makes Allure drop the whole category silently - the panel keeps
    working and one classification is quietly missing.
    """
    import re as _r

    if not pattern:
        return ""
    return _r.sub(r"\(\?P<(\w+)>", r"(?<\1>", pattern)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def _executor() -> dict:
    """Who ran this, and where the run can be found.

    GitHub Actions exports enough to link the report back to the run that
    produced it. Locally there is no build to link to, and saying so is more
    useful than an empty panel that looks like something failed.
    """
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")

    if repo and run_id:
        return {
            "name": "GitHub Actions",
            "type": "github",
            "buildOrder": int(os.getenv("GITHUB_RUN_NUMBER", "0") or 0),
            "buildName": f"{os.getenv('GITHUB_WORKFLOW', 'workflow')} #"
                         f"{os.getenv('GITHUB_RUN_NUMBER', '')}",
            "buildUrl": f"{server}/{repo}/actions/runs/{run_id}",
            "reportName": f"{repo} — {os.getenv('GITHUB_REF_NAME', '')}".strip(" —"),
        }

    return {
        "name": f"Local ({platform.node()})",
        "type": "local",
        "buildName": f"local run by {os.getenv('USER') or os.getenv('USERNAME') or 'developer'}",
    }


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------
def _carry_history(results_dir: Path, previous_report: Path) -> bool:
    """Copy the last report's history so TREND has something to plot.

    Allure builds the trend from `history/` inside allure-results, which it
    takes from the PREVIOUS report. Nothing does that automatically, which is
    why the panel says "there is nothing to show" even on a tenth run.

    One run still produces a single point rather than a line - a trend needs
    a series, and the second run is where the panel starts earning its place.
    """
    source = previous_report / "history"
    if not source.is_dir():
        return False
    destination = results_dir / "history"
    try:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        return True
    except Exception:                                     # noqa: BLE001
        logger.debug("could not carry Allure history forward")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def write_allure_metadata(results_dir, config: Optional[dict] = None,
                          project_root=None,
                          previous_report=None) -> dict:
    """Write all four metadata inputs into the allure-results directory.

    Called once per session, before any test runs. Returns what it wrote, so
    a caller can log it and a test can assert on it.

    Never raises. A report with an empty panel is a cosmetic problem; a test
    session that dies writing report metadata is not, and this runs before
    a single test has had the chance to do anything useful.
    """
    written: dict = {}
    try:
        results = Path(results_dir)
        results.mkdir(parents=True, exist_ok=True)
        root = Path(project_root or Path(__file__).resolve().parents[1])

        if config is None:
            try:
                import yaml
                config = yaml.safe_load(
                    (root / "config" / "config.yaml").read_text(encoding="utf-8"))
            except Exception:                             # noqa: BLE001
                config = {}

        lines = _environment_lines(config, root)
        (results / "environment.properties").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        written["environment"] = len(lines)

        categories = _categories(root)
        (results / "categories.json").write_text(
            json.dumps(categories, indent=2), encoding="utf-8")
        written["categories"] = len(categories)

        (results / "executor.json").write_text(
            json.dumps(_executor(), indent=2), encoding="utf-8")
        written["executor"] = 1

        previous = Path(previous_report) if previous_report else (
            root / "reports" / "allure-report")
        written["history"] = _carry_history(results, previous)
    except Exception:                                     # noqa: BLE001
        logger.debug("Allure metadata not written", exc_info=True)
    return written