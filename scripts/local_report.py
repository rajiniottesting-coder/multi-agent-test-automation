"""The same reports for test runs on your own machine.

    pytest tests/step_defs/            # a local run of the application tests
    python -m scripts.local_report     # then: record it and build the pages

Records the run's reports/junit.xml in a store of its own (reports/history/,
never the default branch's history: a local run may be a few scenarios on
unreviewed code, and would bend the shared trend) and builds the pages into
reports/site/ - Latest run (index.html), History, Traceability, PDF summary -
exactly as the Reports workflow builds them for the runs in CI. When the
Allure command line is on PATH, the run's Allure report is generated into
reports/site/allure/ as one file; otherwise the page says how to open it.

Nothing is posted anywhere: no sprint summary, no Pages deploy. The tracker is
read when its credentials are set (.env), for traceability and open defects.
Old local results go after `reporting.keep_days`, like the shared store's.

Options: --reports DIR (default reports), --no-tracker, --open (open the
Latest run page in the browser). Exit 0 unless the pages could not be built.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

logger = logging.getLogger("local_report")

SOURCE_LOCAL = "test runs on this machine"


def allure_report(results: Path, out: Path) -> bool:
    """The run's Allure report as one file, when the Allure CLI is installed."""
    cli = shutil.which("allure")
    if not cli or not results.is_dir():
        return False
    from core.allure_meta import prune_history
    prune_history(results)
    try:
        subprocess.run([cli, "generate", str(results), "-o", str(out), "--clean",
                        "--single-file"], check=True, capture_output=True, timeout=300)
        return (out / "index.html").is_file()
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Allure report not generated: %s", e)
        return False


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--reports", default=Path("reports"), type=Path)
    ap.add_argument("--features", default=Path("features"), type=Path)
    ap.add_argument("--no-tracker", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    from config import _ensure_env_file_loaded
    _ensure_env_file_loaded()
    junit = args.reports / "junit.xml"
    store, site = args.reports / "history", args.reports / "site"
    if not junit.is_file():
        print(f"No {junit}: run the application tests first (pytest tests/step_defs/).")
        return 1
    from scripts import build_site, record_results
    record_results.main(["--store", str(store), "--junit", str(junit),
                         "--features", str(args.features)])
    allure_dir = site / "allure"
    shutil.rmtree(allure_dir, ignore_errors=True)
    if not allure_report(args.reports / "allure-results", allure_dir):
        allure_dir.mkdir(parents=True, exist_ok=True)
        (allure_dir / "index.html").write_text(
            "<!doctype html><meta charset=utf-8><title>Allure report</title><p>The Allure "
            "command line is not installed, so no Allure report was generated. Open the "
            "run's results with <code>allure serve reports/allure-results</code>, or install "
            "Allure and run <code>python -m scripts.local_report</code> again. "
            "<a href='../index.html'>Back</a></p>", encoding="utf-8")
    code = build_site.main(["--store", str(store), "--out", str(site), "--features",
                            str(args.features), "--sprint-summary", "off",
                            "--source", SOURCE_LOCAL]
                           + (["--no-tracker"] if args.no_tracker else []))
    page = (site / "index.html").resolve()
    print(f"Local reports: {page}")
    if args.open and page.is_file():
        webbrowser.open(page.as_uri())
    return code


if __name__ == "__main__":
    sys.exit(main())
