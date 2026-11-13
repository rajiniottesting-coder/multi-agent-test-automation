"""Reports for local runs, and storage that does not grow (13 Nov 2026).

- A local run (pytest on a person's machine) gets the same pages from its own
  store (scripts/local_report.py), never mixed into the shared history.
- A local run's outputs replace the previous run's (core/local_outputs.py).
- The stores keep `reporting.keep_days` of results; no dated PDF copies by
  default; the store branch is one commit replaced each run; the folder copy
  of the reports is the latest pages only (scripts/pull_reports.py).

Generic: synthetic junit files and archives.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from core import results_store as rs

ROOT = Path(__file__).resolve().parents[2]
NOW = dt.datetime(2026, 11, 13, 12, 0, tzinfo=dt.timezone.utc)
JUNIT = (b"<testsuites><testsuite><testcase classname='tests.step_defs.test_module_a' "
         b"name='test_one' time='1.5'/><testcase classname='tests.step_defs.test_module_a' "
         b"name='test_two' time='2'><failure message='boom'>x</failure></testcase>"
         b"</testsuite></testsuites>")


def _run(i, started):
    return {"id": i, "started": started, "event": "schedule"}


# ── retention ───────────────────────────────────────────────────────────

def test_prune_deletes_runs_and_results_older_than_the_window(tmp_path):
    for i, day in ((1, "2026-07-01T02:00:00Z"), (2, "2026-08-01T02:00:00Z"),
                   (3, "2026-11-12T02:00:00Z")):
        rs.append(tmp_path, _run(i, day), rs.case_records(JUNIT, _run(i, day)))
    assert rs.prune(tmp_path, 90, NOW) == 2
    assert [r["run_id"] for r in rs.read_runs(tmp_path)] == [3]
    assert {r["run_id"] for r in rs.read_results(tmp_path)} == {3}
    assert sorted(p.name for p in (tmp_path / "results").iterdir()) == ["2026-11.jsonl"]  # 07, 08 gone
    assert rs.prune(tmp_path, 90, NOW) == 0
    assert rs.prune(tmp_path, 0, NOW) == 0                       # 0: keep everything


def test_no_dated_pdf_copies_by_default(tmp_path):
    from core.ops_settings import section
    from scripts.build_site import keep_pdf
    assert section("reporting")["pdf_keep"] == 0
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF")
    old = tmp_path / "store" / "pdf"
    old.mkdir(parents=True)
    (old / "2026-11-13.pdf").write_bytes(b"x")                  # made before the change
    keep_pdf(tmp_path / "store", pdf, NOW, True, 0)
    assert not old.exists()


def test_the_cli_trims_the_store_after_recording(tmp_path, monkeypatch):
    from scripts import record_results as rr
    store = tmp_path / "store"
    rs.append(store, _run(1, "2025-01-01T00:00:00Z"), rs.case_records(JUNIT, _run(1, "2025-01-01T00:00:00Z")))
    monkeypatch.setattr(rr, "record", lambda *a: {"recorded": 0, "already": 0,
                                                  "no_report": 0, "not_full": 0})
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: None)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert rr.main(["--store", str(store)]) == 0
    assert rs.read_runs(store) == []


# ── a local run ─────────────────────────────────────────────────────────

def test_a_local_run_is_recorded_once_as_local(tmp_path, monkeypatch):
    from scripts import record_results as rr
    monkeypatch.setattr(rr, "_tracer", lambda features: (lambda t: {}))
    junit = tmp_path / "junit.xml"
    junit.write_bytes(JUNIT)
    store = tmp_path / "history"
    assert rr.record_local(store, junit, tmp_path)["recorded"] == 1
    assert rr.record_local(store, junit, tmp_path)["already"] == 1
    (run,) = rs.read_runs(store)
    assert run["event"] == "local" and str(run["run_id"]).startswith("local-")
    assert (run["passed"], run["failed"]) == (1, 1)
    assert rr.record_local(store, tmp_path / "missing.xml", tmp_path)["no_report"] == 1


def test_local_report_builds_the_pages_and_posts_nothing(tmp_path, monkeypatch):
    from scripts import local_report as lr
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "junit.xml").write_bytes(JUNIT)
    monkeypatch.setattr(lr.shutil, "which", lambda name: None)          # no Allure CLI
    monkeypatch.setattr("core.sprint_summary.post",
                        lambda *a, **k: pytest.fail("a local report posted a sprint summary"))
    monkeypatch.chdir(tmp_path)
    assert lr.main(["--reports", str(reports), "--no-tracker"]) == 0
    site = reports / "site"
    for page in ("index.html", "history.html", "traceability.html", "data.json"):
        assert (site / page).is_file(), page
    assert "test runs on this machine" in (site / "index.html").read_text(encoding="utf-8")
    assert "allure serve reports/allure-results" in (site / "allure" / "index.html").read_text()
    assert len(rs.read_runs(reports / "history")) == 1
    assert lr.main(["--reports", str(reports), "--no-tracker"]) == 0     # same run, once
    assert len(rs.read_runs(reports / "history")) == 1


def test_local_report_without_a_run_says_so(tmp_path, capsys):
    from scripts import local_report as lr
    assert lr.main(["--reports", str(tmp_path / "none"), "--no-tracker"]) == 1
    assert "run the application tests first" in capsys.readouterr().out


# ── a local run starts clean ────────────────────────────────────────────

def _session(tmp_path, items, ci=False, lf=False):
    opts = {"--alluredir": str(tmp_path / "reports" / "allure-results"), "lf": lf}
    config = SimpleNamespace(getoption=lambda name, default=None: opts.get(name, default))
    return SimpleNamespace(config=config, items=[SimpleNamespace(fspath=i) for i in items])


def _previous_run(tmp_path):
    allure = tmp_path / "reports" / "allure-results"
    (allure / "history").mkdir(parents=True)
    for name in ("a-result.json", "b-container.json", "c-attachment.png",
                 "environment.properties", "categories.json", "history/history.json"):
        (allure / name).write_text("x")
    ev = tmp_path / "reports" / "failure-evidence"
    ev.mkdir()
    (ev / "t.png").write_text("x")
    return allure, ev


def test_a_local_app_run_deletes_the_previous_runs_outputs(tmp_path, monkeypatch):
    from core.local_outputs import on_collection_finish
    allure, ev = _previous_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CI", raising=False)
    on_collection_finish(_session(tmp_path, ["/x/tests/step_defs/test_a.py"]))
    assert sorted(p.name for p in allure.iterdir()) == ["categories.json",
                                                        "environment.properties", "history"]
    assert not ev.exists()


@pytest.mark.parametrize("ci,lf,items", [
    ("true", False, ["/x/tests/step_defs/test_a.py"]),     # CI: a clean runner already
    (None, True, ["/x/tests/step_defs/test_a.py"]),        # the retry writes beside the run
    (None, False, ["/x/tests/unit/test_u.py"]),            # unit tests touch nothing
])
def test_ci_retries_and_unit_runs_keep_the_outputs(tmp_path, monkeypatch, ci, lf, items):
    from core.local_outputs import on_collection_finish
    allure, ev = _previous_run(tmp_path)
    monkeypatch.chdir(tmp_path)
    if ci:
        monkeypatch.setenv("CI", ci)
    else:
        monkeypatch.delenv("CI", raising=False)
    on_collection_finish(_session(tmp_path, items, lf=lf))
    assert (allure / "a-result.json").exists() and (ev / "t.png").exists()


def test_the_suite_wires_the_clean_start():
    src = (ROOT / "tests/conftest.py").read_text()
    assert "def pytest_collection_finish(session):" in src and "on_collection_finish" in src


# ── the folder copy ─────────────────────────────────────────────────────

def _archive(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr("owner-repo-abc123/" + name, data)
    return buf.getvalue()


def test_the_folder_gets_the_latest_pages_only(tmp_path):
    from scripts.pull_reports import extract_pages
    target = tmp_path / "TestReports"
    target.mkdir()
    (target / "old-page.html").write_text("stale")
    n = extract_pages(_archive({"latest/index.html": "new", "latest/summary.pdf": "%PDF",
                                "results/2026-11.jsonl": "{}", "runs.jsonl": "{}",
                                "latest/../../evil.txt": "x"}), target)
    assert n == 2
    assert sorted(p.name for p in target.iterdir()) == ["index.html", "summary.pdf"]
    assert not (tmp_path / "evil.txt").exists()


def test_a_failed_download_leaves_the_folder(tmp_path, monkeypatch, capsys):
    from scripts import pull_reports as pr
    target = tmp_path / "TestReports"
    target.mkdir()
    (target / "index.html").write_text("kept")

    def refused(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(pr, "download", refused)
    assert pr.main(["--to", str(target), "--repo", "o/r", "--branch", "b"]) == 1
    assert (target / "index.html").read_text() == "kept"
    monkeypatch.setattr(pr, "download", lambda repo, branch: _archive({"runs.jsonl": "{}"}))
    assert pr.main(["--to", str(target), "--repo", "o/r", "--branch", "b"]) == 1
    assert (target / "index.html").read_text() == "kept"


def test_the_repository_comes_from_the_environment_or_origin(monkeypatch):
    from scripts import pull_reports as pr
    monkeypatch.setenv("GITHUB_REPO", "own/er")
    assert pr.repo_name() == "own/er"
    monkeypatch.delenv("GITHUB_REPO")
    monkeypatch.setattr(pr.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="git@github.com:team/tests.git\n"))
    assert pr.repo_name() == "team/tests"


# ── the store branch ────────────────────────────────────────────────────

def test_the_store_branch_is_one_commit_replaced_each_run():
    wf = yaml.safe_load((ROOT / ".github/workflows/reports.yml").read_text())
    steps = {s.get("name"): s for s in wf["jobs"]["publish"]["steps"]}
    save = steps["Save the results store"]["run"]
    assert "git checkout -q --orphan" in save and "--force" in save
    assert "pull --rebase" not in save
    assert steps["Upload the site"]["with"]["retention-days"] == 1
