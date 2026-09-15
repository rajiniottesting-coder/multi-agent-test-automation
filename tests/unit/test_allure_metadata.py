"""The Allure report's metadata panels must be filled at run time.

A generated report has four panels that stay blank unless something writes
them, because none is a by-product of running tests:

    ENVIRONMENT   environment.properties
    CATEGORIES    categories.json
    EXECUTORS     executor.json
    TREND         history/, carried from the previous report

Four empty boxes read as a report that does not work, which is a poor thing
to hand to anyone. All four are derived here rather than written by hand, so
pointing the framework at a different application changes every value without
changing any code - which is also what makes them testable.
"""
import json
import os
import re
from pathlib import Path

import pytest

from core.allure_meta import write_allure_metadata

_PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def written(tmp_path):
    results = tmp_path / "allure-results"
    summary = write_allure_metadata(results, project_root=_PROJECT)
    return results, summary


def test_environment_reports_what_the_run_was_against(written):
    results, _ = written
    text = (results / "environment.properties").read_text(encoding="utf-8")
    keys = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line}

    # The facts that would change the outcome. Not everything - a panel with
    # forty rows is skimmed and one with ten is read.
    for key in ("Application", "Base.URL", "Browser.Headless", "Playwright",
                "Python", "Run.Type"):
        assert key in keys, f"{key} missing from the environment panel"

    assert all("=" in line for line in text.splitlines() if line), (
        "environment.properties is a key=value file; a bare line is dropped "
        "silently by the report"
    )


def test_environment_reports_the_url_actually_used(written, monkeypatch, tmp_path):
    """BASE_URL overrides config at run time. A panel reporting the config
    value while the run used another is worse than no panel."""
    monkeypatch.setenv("BASE_URL", "https://override.example")
    results = tmp_path / "r2"
    write_allure_metadata(results, project_root=_PROJECT)
    text = (results / "environment.properties").read_text(encoding="utf-8")

    assert "Base.URL=https://override.example" in text


def test_categories_come_from_the_diagnosis_signatures(written):
    """Derived, not listed.

    A signature added to core.failure_diagnosis appears here on the next run,
    and one removed stops appearing. A hand-written list would drift, which is
    the failure this project has paid for more than any other.
    """
    from core.failure_diagnosis import _SIGNATURES

    results, summary = written
    categories = json.loads((results / "categories.json").read_text(encoding="utf-8"))
    names = {c["name"].lower() for c in categories}

    for _pattern, diagnosis in _SIGNATURES:
        label = getattr(diagnosis, "label", "")
        if label:
            assert label.lower() in names, (
                f"the diagnosis module classifies {label!r} and the report has "
                f"no category for it"
            )

    assert summary["categories"] >= len(_SIGNATURES)


def test_every_signature_has_a_category_built_from_its_own_pattern(written):
    """Break the thing the guard guards.

    A category whose regex matches nothing is worse than an absent one: the
    panel looks populated and every failure lands in Allure's default bucket.
    Two versions did exactly that - one double-escaped its pattern, and one
    keyed on the `CAUSE (...)` line, which pytest prints and allure-pytest
    never reads. Both looked identical to working.

    Checked STRUCTURALLY: each category must carry the signature's own
    pattern. The patterns are written for Java, which Python cannot evaluate
    faithfully - three attempts to re-run them here failed on named groups and
    on inline flags, testing the translation rather than the thing. The
    behaviour is proven by generating a real report; what belongs here is that
    the two stay tied together.
    """
    from core.failure_diagnosis import _SIGNATURES

    results, _ = written
    categories = json.loads((results / "categories.json").read_text(encoding="utf-8"))
    by_name = {c["name"].lower(): c for c in categories}

    for pattern, diagnosis in _SIGNATURES:
        label = getattr(diagnosis, "label", "")
        if not label:
            continue
        category = by_name.get(label.lower())
        assert category, f"no category for {label!r}"

        core = getattr(pattern, "pattern", "")
        # Named groups are rewritten for Java; compare on the part that is not.
        stable = core.split("(?P<")[0][-40:] or core[:40]
        assert stable in category.get("traceRegex", ""), (
            f"the category for {label!r} does not contain its signature's "
            f"pattern - it was written from something else and cannot match "
            f"what the signature recognises"
        )


def test_categories_are_exclusive_like_the_diagnosis_is(written):
    """diagnose() returns the FIRST matching signature; Allure applies EVERY
    matching category. Left alone, one failure appears under several headings
    while the log names one, and a reader comparing them finds the report and
    the log disagreeing about what went wrong.

    Each category after the first therefore carries a negative lookahead for
    every earlier pattern, reproducing what diagnose() decided.
    """
    results, _ = written
    categories = json.loads((results / "categories.json").read_text(encoding="utf-8"))
    with_regex = [c for c in categories if c.get("traceRegex")]
    assert len(with_regex) > 3, "too few categories to prove anything"

    assert "(?!" not in with_regex[0]["traceRegex"], (
        "the first category excludes nothing - there is nothing before it"
    )
    # Asserted as a PROPERTY, not a count. The guard prefix and the signature
    # patterns both contain `.*` and both can contain `(?!`, so every attempt
    # to count exactly landed inside a lookahead and failed on correct output.
    # What matters is that exclusion is applied at all, and that the first
    # category - which has nothing before it - excludes nothing.
    for index, category in enumerate(with_regex[1:], start=1):
        assert "(?!" in category["traceRegex"], (
            f"{category['name']!r} is category {index} and excludes no earlier "
            f"pattern; a failure would appear under it AND under whichever "
            f"more specific heading also matches, while the log names one"
        )


def test_there_is_no_catch_all_category(written):
    """A category with no regex matches EVERY failure, so it duplicates every
    row rather than collecting the leftovers. Allure has its own default
    bucket for anything unrecognised."""
    results, _ = written
    categories = json.loads((results / "categories.json").read_text(encoding="utf-8"))

    regexless = [c["name"] for c in categories
                 if not c.get("traceRegex") and not c.get("messageRegex")]
    assert not regexless, (
        f"{regexless} match every failure and would appear alongside every "
        f"real classification"
    )


def test_the_executor_says_where_the_run_happened(monkeypatch, tmp_path):
    """Both branches, with the environment CONTROLLED rather than inherited.

    The first version read the ambient environment for the local case, so it
    passed on a laptop and failed on a runner - where GITHUB_REPOSITORY is
    set and the executor is correctly 'github'. It was asserting which
    machine the suite happened to be on.

    A test that reads the environment it is meant to be testing is testing
    the machine.
    """
    for name in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_NUMBER",
                 "GITHUB_WORKFLOW", "GITHUB_REF_NAME", "GITHUB_SERVER_URL"):
        monkeypatch.delenv(name, raising=False)

    local_results = tmp_path / "local"
    write_allure_metadata(local_results, project_root=_PROJECT)
    local = json.loads((local_results / "executor.json").read_text(encoding="utf-8"))

    assert local["type"] == "local"
    assert local.get("name"), "an empty executor panel looks like a failure"

    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "7")
    ci_results = tmp_path / "ci"
    write_allure_metadata(ci_results, project_root=_PROJECT)
    ci = json.loads((ci_results / "executor.json").read_text(encoding="utf-8"))

    assert ci["type"] == "github"
    assert ci["buildUrl"].endswith("/actions/runs/12345"), (
        "the report has to link back to the run that produced it"
    )


def test_history_is_carried_forward_when_a_previous_report_exists(tmp_path):
    """TREND plots a series, and the series lives in the PREVIOUS report.
    Nothing copies it automatically, which is why the panel says 'nothing to
    show' even on a tenth run."""
    previous = tmp_path / "allure-report"
    (previous / "history").mkdir(parents=True)
    (previous / "history" / "history-trend.json").write_text("[]", encoding="utf-8")

    results = tmp_path / "results"
    summary = write_allure_metadata(results, project_root=_PROJECT,
                                    previous_report=previous)

    assert summary["history"] is True
    assert (results / "history" / "history-trend.json").is_file()


def test_a_first_run_with_no_previous_report_is_not_an_error(tmp_path):
    """Break the thing the guard guards. There is no history on run one, and
    that must not stop anything."""
    summary = write_allure_metadata(tmp_path / "results", project_root=_PROJECT,
                                    previous_report=tmp_path / "nope")
    assert summary["history"] is False
    assert summary["environment"] > 0, "the rest must still be written"


def test_writing_metadata_never_raises(tmp_path):
    """This runs before a single test has done anything useful. A report with
    an empty panel is cosmetic; a session that dies decorating one is not."""
    write_allure_metadata(tmp_path / "x" / "y" / "z", project_root=Path("/nonexistent"))


def test_the_hook_is_wired_into_conftest():
    """A writer nothing calls is this project's recurring shape."""
    body = " ".join((_PROJECT / "tests" / "conftest.py").read_text(
        encoding="utf-8").split())

    assert "def pytest_configure(config)" in body, "no session hook"
    assert "write_allure_metadata(" in body, (
        "the writer exists but conftest never calls it - the panels stay blank"
    )
    assert 'config.getoption("--alluredir"' in body, (
        "the metadata must go where --alluredir points, not a hardcoded path"
    )


# =========================================================================
# THE CI ARTIFACT MUST BE VIEWABLE
#
# pytest writes raw JSON. Rendering it needs the Allure CLI, which is not on
# the runner - so the artifact contained results nobody could open without
# installing a tool first, and a report nobody opens may as well not exist.
#
# And the rendered DIRECTORY is not enough on its own: it fetches its data
# over XHR, which browsers block on file://, so a downloaded folder shows
# "Loading..." for ever and reads as broken. That is exactly what happened
# the first time this report was opened locally.
# =========================================================================

def _runner_workflow() -> str:
    return (_PROJECT / ".github" / "workflows" / "agent4_runner.yml").read_text(
        encoding="utf-8")


def test_ci_renders_the_report_rather_than_shipping_raw_results():
    workflow = _runner_workflow()

    assert "allure generate" in workflow or "bin/allure" in workflow, (
        "CI uploads reports/ with raw allure-results and never renders them - "
        "the artifact needs a tool installed before anyone can read it"
    )
    assert "--single-file" in workflow, (
        "a directory report fetches its data over XHR, which browsers block "
        "on file:// - a downloaded folder shows 'Loading...' for ever"
    )


def test_the_report_is_generated_before_it_is_uploaded():
    """Ordering, because a report generated after the upload ships nothing."""
    workflow = _runner_workflow()

    generate_at = workflow.index("Generate the Allure report")
    upload_at = workflow.index("Upload test report")
    assert generate_at < upload_at, (
        "the report is generated after the artifact is uploaded, so the "
        "artifact contains raw results only"
    )


def test_ci_carries_the_trend_between_runs():
    """TREND plots a series, and the series lives in the PREVIOUS report.
    Nothing carries it between runs, which is why the panel says 'there is
    nothing to show' on the tenth run as loudly as the first."""
    workflow = _runner_workflow()

    assert "allure-report/history" in workflow, (
        "no history is carried between CI runs, so the trend is permanently "
        "a single point"
    )


def test_report_generation_runs_even_when_tests_failed():
    """A report is most wanted on the run that failed. A step that only runs
    on success produces one exactly when nobody needs it."""
    import re

    workflow = _runner_workflow()
    block = workflow[workflow.index("Generate the Allure report"):]
    block = block[:block.index("Upload test report")]

    assert re.search(r"if:\s*always\(\)", block), (
        "the report is skipped when tests fail - which is the run somebody "
        "will actually want to look at"
    )

# ─────────────────────────────────────────────────────────────────────────
# Evidence is attached at TEARDOWN, not at the call-phase report
#
# The page fixture writes the screenshot, video and trace in its teardown,
# which pytest runs AFTER the call-phase makereport. Attaching from there
# globbed a directory that did not yet contain them, so a failed test arrived
# in Allure with the "Why this failed" explanation and nothing to look at -
# the one place a screenshot earns its keep.
#
# The files existed on disk the whole time. Nothing in the report pointed at
# them, and their names are not ones a reader would guess.
# ─────────────────────────────────────────────────────────────────────────

def test_the_hook_attaches_evidence_on_the_teardown_report():
    """Ordering is the whole fix, so assert on the ordering."""
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2]
              / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'report.when == "teardown"' in source, (
        "evidence must be attached after the fixture teardown that WRITES it; "
        "attaching at call time finds nothing on disk"
    )
    teardown_at = source.index('report.when == "teardown"')
    assert "files_only=True" in source[teardown_at:teardown_at + 700], (
        "the teardown pass must not re-attach the explanation - the same text "
        "twice on one test reads as a bug in the report"
    )


def test_files_only_suppresses_the_reading_but_not_the_files(tmp_path):
    from types import SimpleNamespace
    from core.allure_steps import attach_failure_evidence

    stem = "test_some_case"
    for suffix in (".png", ".webm", ".trace.zip"):
        (tmp_path / f"{stem}{suffix}").write_bytes(b"x")
    report = SimpleNamespace(
        nodeid=f"tests/step_defs/test_x.py::{stem}",
        sections=[("Why this failed", "CAUSE: ...")])

    both = attach_failure_evidence(report, tmp_path)
    files = attach_failure_evidence(report, tmp_path, files_only=True)

    assert both == files + 1, \
        "files_only should drop exactly the one explanation attachment"
    assert files == 3, "screenshot, video and trace"


def test_a_test_with_no_evidence_still_gets_its_explanation(tmp_path):
    """A failure that never opened a browser has no files. The reading is the
    only attachment worth having there, and it must not be lost."""
    from types import SimpleNamespace
    from core.allure_steps import attach_failure_evidence

    report = SimpleNamespace(
        nodeid="tests/unit/test_x.py::test_no_browser",
        sections=[("Why this failed", "CAUSE: ...")])
    assert attach_failure_evidence(report, tmp_path / "does-not-exist") == 1