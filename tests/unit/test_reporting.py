"""Reports (RP1 results store, RP2 Pages site, RP3 dashboard, RP4
traceability, RP6 PDF summary, RP8 Allure labels).

Offline: a junit.xml written here, a fake repository host and a fake tracker.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import report_data as rd
from core import results_store as rs

NOW = dt.datetime(2026, 11, 13, 12, 0, tzinfo=dt.timezone.utc)


def junit(*cases) -> bytes:
    """cases: (classname, name, kind, seconds, props, text); kind is
    passed | failed | skipped."""
    out = ["<testsuites><testsuite name='pytest'>"]
    for cls, name, kind, secs, props, text in cases:
        p = "".join(f"<property name='{k}' value='{v}'/>" for k, v in (props or {}).items())
        body = f"<properties>{p}</properties>" if p else ""
        if kind == "failed":
            body += f"<failure message='{text}'>trace</failure>"
        elif kind == "skipped":
            body += "<skipped/>"
        out.append(f"<testcase classname='{cls}' name='{name}' time='{secs}'>{body}</testcase>")
    out.append("</testsuite></testsuites>")
    return "".join(out).encode()


LOGIN = "tests.step_defs.test_module_a"
CART = "tests.step_defs.test_module_b"


def sample_run(run_id=1, started="2026-11-12T20:30:00Z"):
    return {"id": run_id, "started": started, "event": "schedule", "head_sha": "abc",
            "url": f"https://ci/{run_id}", "conclusion": "success"}


def sample_xml():
    return junit(
        (LOGIN, "test_valid_login", "passed", 3.5, None, ""),
        (LOGIN, "test_bad_login", "failed", 7.25, None, "AssertionError: password=hunter2secret token ghp_" + "a" * 36),
        (CART, "test_add", "passed", 2.0, {"flaky": "1", "first_failure": "Timeout 5000ms"}, ""),
        (CART, "test_remove", "failed", 1.0, {"outage": "1"}, "503 Service Unavailable"),
        (CART, "test_later", "skipped", 0, None, ""),
    )


# ── results store (RP1) ─────────────────────────────────────────────────

def test_case_records_read_agent4s_final_verdicts():
    recs = rs.case_records(sample_xml(), sample_run(),
                           trace=lambda t: {"test_case": "TC-1", "owner": "ST-1"}
                           if t.endswith("valid_login") else None)
    by = {r["scenario"]: r for r in recs}
    assert [by[n]["verdict"] for n in ("test_valid_login", "test_bad_login", "test_add",
                                       "test_remove", "test_later")] == \
        ["passed", "failed", "flaky", "outage", "skipped"]
    assert by["test_valid_login"]["test_case"] == "TC-1" and by["test_valid_login"]["story"] == "ST-1"
    assert by["test_bad_login"]["test_case"] is None
    assert by["test_valid_login"]["file"] == "module_a.feature"
    assert by["test_add"]["file"] == "module_b.feature"
    assert by["test_add"]["first_failure"] == "Timeout 5000ms"
    assert by["test_bad_login"]["duration_s"] == 7.25


def test_a_recorded_failure_is_redacted_and_short():
    rec = next(r for r in rs.case_records(sample_xml(), sample_run())
               if r["scenario"] == "test_bad_login")
    assert "ghp_" + "a" * 36 not in rec["failure"]
    assert len(rec["failure"]) <= 300


def test_an_unreadable_report_records_nothing():
    assert rs.case_records(b"<not xml", sample_run()) == []


def test_append_is_idempotent_by_run(tmp_path):
    cases = rs.case_records(sample_xml(), sample_run())
    assert rs.append(tmp_path, sample_run(), cases) is True
    assert rs.append(tmp_path, sample_run(), cases) is False
    assert rs.append(tmp_path, sample_run(2), []) is False          # no results
    runs = rs.read_runs(tmp_path)
    assert len(runs) == 1 and runs[0]["tests"] == 5
    assert (runs[0]["passed"], runs[0]["failed"], runs[0]["flaky"],
            runs[0]["outage"], runs[0]["skipped"]) == (1, 1, 1, 1, 1)
    assert (tmp_path / "results" / "2026-11.jsonl").is_file()
    assert len(rs.read_results(tmp_path)) == 5


def test_read_results_since_and_latest(tmp_path):
    rs.append(tmp_path, sample_run(1, "2026-10-01T20:30:00Z"), rs.case_records(sample_xml(), sample_run(1, "2026-10-01T20:30:00Z")))
    later = junit((LOGIN, "test_bad_login", "passed", 1, None, ""))
    rs.append(tmp_path, sample_run(2), rs.case_records(later, sample_run(2)))
    assert {r["run_id"] for r in rs.read_results(tmp_path, since="2026-11-01")} == {2}
    latest = rs.latest_by_test(rs.read_results(tmp_path))
    assert latest[f"{LOGIN}::test_bad_login"]["verdict"] == "passed"
    assert latest[f"{LOGIN}::test_valid_login"]["run_id"] == 1


def test_an_unreadable_store_line_is_skipped(tmp_path):
    (tmp_path / "runs.jsonl").write_text('{"run_id": 1}\nnot json\n', encoding="utf-8")
    assert rs.recorded_run_ids(tmp_path) == {1}


# ── recording (RP1) ─────────────────────────────────────────────────────

class FakeHost:
    def __init__(self, runs, files):
        self.runs, self.files, self.asked = runs, files, []

    def get_workflow_runs(self, workflow_file, branch, limit=20, strict=False):
        return self.runs

    def get_run_artifact_file(self, run_id, prefix, filename):
        self.asked.append(run_id)
        return self.files.get(run_id)


def _run(i, event="schedule", conclusion="success", status="completed"):
    return {"id": i, "status": status, "conclusion": conclusion, "head_sha": "s",
            "event": event, "created_at": f"2026-11-1{i}T20:30:00Z", "url": f"u{i}"}


def test_record_takes_full_runs_once(tmp_path, monkeypatch):
    from scripts import record_results as rr
    monkeypatch.setattr(rr, "_tracer", lambda features: (lambda t: {}))
    host = FakeHost([_run(5, "pull_request"), _run(4, "push"), _run(3, "workflow_dispatch"),
                     _run(2, conclusion="cancelled"), _run(1, status="in_progress")],
                    {3: sample_xml()})
    c = rr.record(tmp_path, host, tmp_path, "main", 30)
    assert c == {"recorded": 1, "already": 0, "no_report": 1, "not_full": 1}
    assert host.asked == [3, 4]                       # oldest first; PRs never read
    c = rr.record(tmp_path, host, tmp_path, "main", 30)
    assert c["recorded"] == 0 and c["already"] == 1


def test_record_cli_tells_the_workflow_what_it_recorded(tmp_path, monkeypatch):
    from scripts import record_results as rr
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(rr, "record", lambda *a: {"recorded": 2, "already": 0,
                                                  "no_report": 0, "not_full": 0})
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: None)
    assert rr.main(["--store", str(tmp_path / "store")]) == 0
    assert out.read_text() == "recorded=2\n"


def test_record_cli_never_fails_the_run(tmp_path, monkeypatch):
    from scripts import record_results as rr
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    def boom(*a):
        raise RuntimeError("host down")
    monkeypatch.setattr(rr, "record", boom)
    monkeypatch.setattr("integrations.repo_host.get_repo_host", lambda: None)
    assert rr.main(["--store", str(tmp_path)]) == 0


# ── report numbers (RP3) ────────────────────────────────────────────────

def _store_with_two_runs(tmp_path):
    rs.append(tmp_path, sample_run(1, "2026-11-11T20:30:00Z"),
              rs.case_records(sample_xml(), sample_run(1, "2026-11-11T20:30:00Z"),
                              trace=lambda t: {"owner": "ST-1"} if "module_a" in t else {}))
    second = junit((LOGIN, "test_valid_login", "passed", 4.5, None, ""),
                   (LOGIN, "test_bad_login", "passed", 2, {"flaky": "1"}, ""),
                   (CART, "test_add", "passed", 2.0, None, ""))
    rs.append(tmp_path, sample_run(2), rs.case_records(second, sample_run(2),
                                                       trace=lambda t: {"owner": "ST-1"} if "module_a" in t else {}))
    return rs.read_runs(tmp_path), rs.read_results(tmp_path)


def test_pass_rate_counts_flakes_as_passed_and_ignores_outages_and_skips():
    recs = [{"verdict": v} for v in ("passed", "flaky", "failed", "outage", "skipped")]
    assert rd.pass_rate(recs) == pytest.approx(2 / 3)
    assert rd.pass_rate([{"verdict": "outage"}]) is None


def test_kpis_trend_and_rankings(tmp_path):
    runs, results = _store_with_two_runs(tmp_path)
    k = rd.kpis(runs, results)
    assert k["runs"] == 2 and k["latest_run"]["run_id"] == 2
    assert k["latest_pass_rate"] == 1.0
    assert k["window_pass_rate"] == pytest.approx(5 / 6)
    assert k["flaky"] == 2 and k["tests"] == 5
    t = rd.trend(runs)
    assert t["run"] == [1, 2] and t["failed"] == [1, 0] and t["flaky"] == [1, 1]
    assert t["started"][0] == "2026-11-11 20:30"
    slow = rd.slowest(results)
    assert slow[0]["test"].endswith("test_bad_login") and slow[0]["max_s"] == 7.2
    flaky = rd.flaky_ranking(results)
    assert {f["test"].rsplit("::")[-1] for f in flaky} == {"test_add", "test_bad_login"}
    assert all(f["runs"] == 2 for f in flaky)


def test_breakdowns_use_each_tests_latest_result(tmp_path):
    _, results = _store_with_two_runs(tmp_path)
    by_file = {r["name"]: r for r in rd.breakdown(results, "file")}
    assert by_file["module_a.feature"]["passed"] == 2 and by_file["module_a.feature"]["failed"] == 0
    assert by_file["module_b.feature"]["other"] == 2      # outage + skipped
    by_story = {r["name"]: r for r in rd.breakdown(results, "story")}
    assert set(by_story) == {"ST-1", "(not traced)"}


def test_defects_by_age_and_component():
    defects = [{"created": "2026-11-12T10:00:00.000+0000", "components": ["Cart"]},
               {"created": "2026-11-05T10:00:00Z", "components": []},
               {"created": "2026-09-01T10:00:00Z", "components": ["Cart", "Login"]},
               {"created": None}]
    s = rd.defects_summary(defects, NOW)
    assert s["total"] == 4
    assert s["by_age"] == [("0-2 days", 1), ("8-30 days", 1), ("over 30 days", 1), ("unknown age", 1)]
    assert dict(s["by_component"])["Cart"] == 2
    assert dict(s["by_component"])["(no component)"] == 2


# ── traceability (RP4) ──────────────────────────────────────────────────

COVERAGE = ("\\[agent1:coverage\\] Acceptance criteria and the test cases that cover them\n"
            "- AC1 User can log in -> \\[Positive\\] Valid login, with remember me | asserted\n"
            "- AC2 Wrong password is refused -> (none) | gap\n")
TCS = [{"key": "TC-1", "summary": "[Positive] Valid login, with remember me"},
       {"key": "TC-2", "summary": "[Negative] Locked account"}]


def test_coverage_map_reads_agent1s_comment_with_wiki_escapes():
    m = rd.coverage_map(COVERAGE, ["AC1", "AC2"], TCS)
    assert m == {"AC1": ["TC-1"], "AC2": []}


def test_traceability_rows_and_summary():
    story = {"key": "ST-1", "summary": "Login", "status": "Done",
             "criteria": [("AC1", "User can log in"), ("AC2", "Wrong password is refused")],
             "coverage": {"AC1": ["TC-1"], "AC2": []}, "test_cases": TCS,
             "scenarios": {"TC-1": [f"{LOGIN}::test_valid_login"], "TC-2": []}}
    latest = {f"{LOGIN}::test_valid_login": {"verdict": "failed", "started": "2026-11-12T20:30:00Z"}}
    rows = rd.traceability_rows([story], latest, {"TC-1": ["BUG-9"]})
    assert [(r["criterion"], r["test_case"], r["result"]) for r in rows] == [
        ("AC1", "TC-1", "failed"), ("AC2", "", "no test case"), ("-", "TC-2", "no scenario")]
    assert rows[0]["defects"] == ["BUG-9"] and rows[0]["result_date"] == "2026-11-12"
    s = rd.traceability_summary(rows)
    assert s == {"stories": 1, "criteria": 2, "criteria_uncovered": 1, "criteria_unmapped": 0,
                 "test_cases": 2, "test_cases_without_scenario": 1, "results": {"failed": 1}}


def test_a_story_without_criteria_still_lists_its_test_cases():
    rows = rd.traceability_rows([{"key": "ST-2", "test_cases": [TCS[1]], "criteria": [],
                                  "coverage": {}, "scenarios": {}}], {}, {})
    assert [(r["criterion"], r["test_case"]) for r in rows] == [("-", ""), ("-", "TC-2")]


# ── Allure labels (RP8) ─────────────────────────────────────────────────

def test_severity_is_the_most_severe_tag():
    from core.allure_labels import severity_for
    s = {"severity_by_tag": {"smoke": "critical", "@Edge": "minor", "x": "bogus"},
         "default_severity": "normal"}
    assert severity_for(["edge", "@SMOKE"], s) == "critical"
    assert severity_for(["edge"], s) == "minor"
    assert severity_for(["x", "other"], s) == "normal"
    assert severity_for([], {"default_severity": "bogus"}) == "normal"


def test_labels_link_the_test_case_and_its_story(tmp_path, monkeypatch):
    from core.allure_labels import labels_for
    (tmp_path / "module_a.feature").write_text(
        "Feature: Login\n\n  # JIRA: TC-7 (hash: 1234abcd) owner: ST-3\n"
        "  Scenario: Valid login\n    Given the login page\n", encoding="utf-8")
    monkeypatch.setenv("JIRA_URL", "https://tracker.example/")
    monkeypatch.setattr("integrations.tracker._configured_type", lambda: "jira")
    info = labels_for(str(tmp_path / "module_a.feature"), "Login", "Valid login", ["smoke"],
                      {"severity_by_tag": {"smoke": "critical"}}, str(tmp_path))
    assert info["severity"] == "critical" and info["feature"] == "Login" and info["story"] == "ST-3"
    assert info["links"] == [("https://tracker.example/browse/TC-7", "TC-7", "tms"),
                             ("https://tracker.example/browse/ST-3", "ST-3", "issue")]
    none = labels_for(str(tmp_path / "module_a.feature"), "Login", "Unmarked", [], {}, str(tmp_path))
    assert none["links"] == [] and none["story"] is None


def test_issue_url_needs_a_base_and_a_known_tracker(monkeypatch):
    from integrations.tracker import issue_url
    monkeypatch.delenv("JIRA_URL", raising=False)
    assert issue_url("A-1", "jira") is None
    monkeypatch.setenv("JIRA_URL", "https://t.example")
    assert issue_url("A-1", "jira") == "https://t.example/browse/A-1"
    assert issue_url("A-1", "unknown") is None
    assert issue_url("", "jira") is None


def test_apply_never_raises():
    from core.allure_labels import apply
    apply(object(), object(), features_dir="/no/such/dir")


# ── the site (RP2, RP3, RP4, RP6) ───────────────────────────────────────

class FakeTracker:
    def __init__(self):
        self.defects = [{"key": "BUG-9", "summary": "Login fails", "status": "To Do", "open": True,
                         "labels": [], "components": ["Login"],
                         "created": "2026-11-10T10:00:00Z", "links": ["TC-7"]}]

    def issues_for_report(self, issue_type, open_only=True, labels=None):
        self.asked = (issue_type, open_only, labels)
        return self.defects

    def get_active_sprint(self):
        return {"id": 1, "name": "Sprint 9", "start": "2026-11-01T00:00:00Z",
                "end": "2026-11-13T20:00:00Z"}

    def get_parent_story_key(self, key):
        return "ST-3"

    def get_story(self, key):
        return {"key": key, "summary": "Login story", "status": "In Progress",
                "description": "Acceptance criteria:\n1. User can log in\n2. A locked account is refused"}

    def get_linked_test_cases(self, key):
        return [{"key": "TC-7", "summary": "[Positive] Valid login"}]

    def get_comments(self, key):
        return ["older", "\\[agent1:coverage\\]\n- AC1 User can log in -> \\[Positive\\] Valid login | asserted"]


def _features(tmp_path):
    f = tmp_path / "features"
    f.mkdir()
    (f / "module_a.feature").write_text(
        "Feature: Login\n\n  # JIRA: TC-7 (hash: 1234abcd)\n"
        "  Scenario: Valid login\n    Given the login page\n", encoding="utf-8")
    return f


def test_open_defects_reads_every_open_defect_whoever_raised_it():
    from scripts import build_site as bs
    t = FakeTracker()
    assert bs.open_defects(t) == t.defects
    assert t.asked[1] is True and t.asked[2] is None             # no reporter or label filter
    assert bs.open_defects(object()) is None                      # capability absent


def test_traceability_from_the_tracker(tmp_path):
    from scripts import build_site as bs
    latest = {f"{LOGIN}::test_valid_login": {"test": f"{LOGIN}::test_valid_login",
                                             "test_case": "TC-7", "verdict": "passed",
                                             "started": "2026-11-12T20:30:00Z"}}
    t = FakeTracker()
    rows = bs.traceability(t, _features(tmp_path), latest, t.defects)
    ac1 = next(r for r in rows if r["criterion"] == "AC1")
    assert (ac1["story"], ac1["test_case"], ac1["result"], ac1["defects"]) == \
        ("ST-3", "TC-7", "passed", ["BUG-9"])
    assert any(r["criterion"] == "AC2" and not r["test_case"] for r in rows)


def test_sprint_last_day():
    from scripts.build_site import is_sprint_last_day
    assert is_sprint_last_day({"end": "2026-11-13T20:00:00Z"}, NOW)
    assert not is_sprint_last_day({"end": "2026-11-20T20:00:00Z"}, NOW)
    assert not is_sprint_last_day({"end": "2026-11-12T20:00:00Z"}, NOW)
    assert not is_sprint_last_day({"end": "not a date"}, NOW)
    assert not is_sprint_last_day(None, NOW)


def test_keep_pdf_keeps_the_newest_nightlies_and_every_sprint_end(tmp_path):
    from scripts.build_site import keep_pdf
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF")
    folder = tmp_path / "store" / "pdf"
    folder.mkdir(parents=True)
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        (folder / f"{d}.pdf").write_bytes(b"x")
    (folder / "2026-10-31-sprint-end.pdf").write_bytes(b"x")
    keep_pdf(tmp_path / "store", pdf, NOW, False, keep=2)
    assert sorted(p.name for p in folder.iterdir()) == [
        "2026-10-31-sprint-end.pdf", "2026-11-03.pdf", "2026-11-13.pdf"]


def test_the_site_is_built_from_the_store(tmp_path, monkeypatch):
    from scripts import build_site as bs
    store = tmp_path / "store"
    _store_with_two_runs(store)
    monkeypatch.setattr(bs, "_tracker", lambda: FakeTracker())
    monkeypatch.setenv("JIRA_URL", "https://tracker.example")
    monkeypatch.setattr("integrations.tracker._configured_type", lambda: "jira")
    monkeypatch.chdir(tmp_path)
    _features(tmp_path)
    out = tmp_path / "site"
    assert bs.main(["--store", str(store), "--out", str(out), "--features", "features",
                    "--site-url", "https://pages.example/repo/", "--sprint-summary", "off"]) == 0
    history = (out / "history.html").read_text(encoding="utf-8")
    assert "plotly" in history and "Results per run" in history
    assert 'href="https://tracker.example/browse/BUG-9"' in history
    # absolute, so the copy kept on the store branch links to the published report
    assert 'href="https://pages.example/repo/allure/index.html"' in history
    latest = (out / "index.html").read_text(encoding="utf-8")       # the landing page
    assert "Latest run" in latest and "flaky (passed on the retry)" in latest
    assert "test_bad_login" in latest and "test_valid_login" not in latest
    assert "The other 2 tests passed." in latest
    trace = (out / "traceability.html").read_text(encoding="utf-8")
    assert "TC-7" in trace and "AC2" in trace
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert data["kpis"]["runs"] in (0, 1, 2) and data["sprint"]["name"] == "Sprint 9"
    pytest.importorskip("reportlab")
    assert (out / "summary.pdf").read_bytes().startswith(b"%PDF")
    assert not (store / "pdf").exists()        # pdf_keep 0: the latest is published only


def test_the_site_is_built_without_a_tracker(tmp_path):
    from scripts import build_site as bs
    out = tmp_path / "site"
    assert bs.main(["--store", str(tmp_path / "empty"), "--out", str(out), "--no-tracker"]) == 0
    assert "No run recorded in the window yet" in (out / "history.html").read_text(encoding="utf-8")
    assert "No run recorded yet" in (out / "index.html").read_text(encoding="utf-8")
    assert "could not be read" in (out / "traceability.html").read_text(encoding="utf-8")


def test_html_is_escaped():
    from scripts import build_site as bs
    data = {"generated": "now", "window_days": 30, "traceability": [
        {"story": "ST-1", "story_summary": "<script>x</script>", "criterion": "AC1",
         "criterion_text": "t", "test_case": "", "test_case_summary": "", "scenario": "",
         "result": "no scenario", "result_date": "", "defects": []}],
        "traceability_summary": {"stories": 1, "criteria": 1, "criteria_uncovered": 1,
                                 "test_cases": 0, "test_cases_without_scenario": 0, "results": {}}}
    assert "<script>x</script>" not in bs.traceability_html(data)


# ── the tracker's report capabilities ───────────────────────────────────

def _jira(found=None, sprints=None, raise_=False):
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    c.project_key = "PRJ"
    c.board_id = "7"

    class Client:
        def enhanced_search_issues(self, jql, **kw):
            if raise_:
                raise RuntimeError("down")
            self.jql, self.kw = jql, kw
            return found or []

        def sprints(self, board_id, state):
            if raise_:
                raise RuntimeError("down")
            return sprints or []
    c._client = Client()
    return c


def test_issues_for_report_reads_open_issues_of_a_type():
    status = SimpleNamespace(name="To Do", statusCategory=SimpleNamespace(key="new"))
    link = SimpleNamespace(outwardIssue=SimpleNamespace(key="TC-1"), inwardIssue=None)
    issue = SimpleNamespace(key="PRJ-9", fields=SimpleNamespace(
        summary="s", status=status, labels=["ai-defect"],
        components=[SimpleNamespace(name="Cart")], created="2026-11-10", issuelinks=[link]))
    c = _jira([issue])
    got = c.issues_for_report("Bug")
    assert c._client.jql == 'project = PRJ AND issuetype = "Bug" AND statusCategory != Done ORDER BY created ASC'
    assert got == [{"key": "PRJ-9", "summary": "s", "status": "To Do", "open": True,
                    "labels": ["ai-defect"], "components": ["Cart"], "created": "2026-11-10",
                    "links": ["TC-1"]}]
    assert _jira(raise_=True).issues_for_report("Bug") == []


def test_active_sprint():
    sp = SimpleNamespace(id=3, name="Sprint 3", raw={"startDate": "a", "endDate": "b"})
    assert _jira(sprints=[sp]).get_active_sprint() == {"id": 3, "name": "Sprint 3",
                                                        "start": "a", "end": "b"}
    assert _jira().get_active_sprint() is None
    assert _jira(raise_=True).get_active_sprint() is None


def test_reporting_settings_have_defaults():
    from core.ops_settings import section
    s = section("reporting")
    assert s["store_branch"] and s["window_days"] > 0 and s["pdf_keep"] >= 0
    assert s["keep_days"] == 0 or s["keep_days"] >= s["window_days"]
    assert s["default_severity"] in ("blocker", "critical", "normal", "minor", "trivial")


def test_reports_workflow_publishes_only_new_results():
    wf = (Path(__file__).resolve().parents[2] / ".github/workflows/reports.yml").read_text()
    assert 'workflows: ["Agent 4 - Runner"]' in wf
    assert "steps.record.outputs.recorded != '0'" in wf
    assert "actions/deploy-pages" in wf and "cancel-in-progress: false" in wf
    assert "secrets.GH_APP_PRIVATE_KEY" in wf and "add-mask" in wf


def test_allure_history_survives_the_cache():
    """Agent 4 uploads the history (after the folder's exclusion, so it is
    taken back in) and restores it from the store when the cache is gone."""
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    a4 = (root / "agent4_runner.yml").read_text()
    path = a4[a4.index("name: pytest-report-"):]
    assert path.index("!reports/allure-report/") < path.index("reports/allure-report/history/")
    assert "Restore Allure history from the results store" in a4
    assert "store/allure-history" in (root / "reports.yml").read_text()


def test_latest_run_lists_what_needs_a_look_failed_first(tmp_path):
    runs, results = _store_with_two_runs(tmp_path)
    lr = rd.latest_run(runs[:1], [r for r in results if r["run_id"] == 1])
    assert [r["verdict"] for r in lr["rows"]] == ["failed", "outage", "flaky", "skipped"]
    assert lr["passed"] == 1 and lr["run"]["run_id"] == 1
    assert rd.latest_run([], []) is None


def test_a_test_no_longer_in_the_suite_leaves_the_breakdown(tmp_path):
    _, results = _store_with_two_runs(tmp_path)
    current = {r["test"] for r in results if r["run_id"] == 2}
    names = {r["name"]: r for r in rd.breakdown(results, "file", current)}
    assert names["module_b.feature"]["tests"] == 1             # test_remove, test_later gone
    assert rd.breakdown(results, "file")[0]["tests"] >= 1     # without `current`: every test


def test_runs_in_the_same_minute_get_a_bar_each(tmp_path):
    from scripts import build_site as bs
    store = tmp_path / "store"
    for i in (1, 2):
        run = sample_run(i, "2026-11-11T03:05:00Z")
        rs.append(store, run, rs.case_records(sample_xml(), run))
    out = tmp_path / "site"
    assert bs.main(["--store", str(store), "--out", str(out), "--no-tracker"]) == 0
    page = (out / "history.html").read_text(encoding="utf-8")
    assert '"x": ["1", "2"]' in page and 'ticktext:["2026-11-11 03:05", "2026-11-11 03:05"]' in page


def test_a_story_without_a_coverage_map_lists_its_test_cases_not_gaps():
    """13 Nov 2026, live matrix: stories older than Agent 1's coverage
    comment showed a row per criterion with test case 'none' - read as gaps on
    stories whose every test case passed."""
    rows = rd.traceability_rows([{"key": "ST-5", "criteria": [("AC1", "a"), ("AC2", "b")],
                                  "has_coverage_map": False, "coverage": {},
                                  "test_cases": TCS, "scenarios": {"TC-1": ["t::one"]}}],
                                {"t::one": {"verdict": "passed", "started": "2026-11-13"}}, {})
    assert [(r["criterion"], r["test_case"], r["result"]) for r in rows] == [
        ("-", "TC-1", "passed"), ("-", "TC-2", "no scenario")]
    assert "AC1, AC2: not mapped" in rows[0]["criterion_text"]
    s = rd.traceability_summary(rows)
    assert s["criteria_uncovered"] == 0 and s["criteria_unmapped"] == 2 and s["criteria"] == 2
    none = rd.traceability_rows([{"key": "ST-6", "criteria": [("AC1", "a")],
                                  "has_coverage_map": False, "test_cases": []}], {}, {})
    assert [(r["test_case"], r["result"]) for r in none] == [("", "no test case")]


def test_none_only_for_a_real_gap():
    from scripts.build_site import _test_case_cell
    base = {"test_case": "", "test_case_summary": "", "criterion": "AC2", "result": "no test case"}
    assert "none" in _test_case_cell(base)
    assert _test_case_cell({**base, "criterion": "-"}) == "-"          # unmapped story
    assert "cited title not found" in _test_case_cell({**base, "result": "cited test case not found"})


def test_open_defects_no_row_can_show_are_listed_apart():
    rows = [{"story": "ST-1", "test_case": "TC-1"}, {"story": "ST-1", "test_case": ""}]
    defects = [{"key": "BUG-1", "links": ["TC-1"]}, {"key": "BUG-2", "links": []},
               {"key": "BUG-3", "links": ["OTHER-9"]}, {"key": "BUG-4", "links": ["ST-1"]}]
    assert [d["key"] for d in rd.unlinked_defects(defects, rows)] == ["BUG-2", "BUG-3"]
    assert rd.unlinked_defects(None, rows) == []


def test_a_citation_whose_title_changed_says_so():
    comment = ("\\[agent1:coverage\\]\n- AC1 a -> \\[Negative\\] An old title | step 3\n"
               "- AC2 b -> (none) | gap\n")
    assert rd.unmatched_citations(comment, ["AC1", "AC2"], TCS) == {"AC1"}
    rows = rd.traceability_rows([{"key": "ST-6", "criteria": [("AC1", "a"), ("AC2", "b")],
                                  "coverage": {}, "unmatched": {"AC1"}, "test_cases": [],
                                  "scenarios": {}}], {}, {})
    assert [r["result"] for r in rows] == ["cited test case not found", "no test case"]


def test_a_marked_test_case_the_tracker_no_longer_links_is_listed(tmp_path):
    from scripts import build_site as bs

    class Unlinked(FakeTracker):
        def get_linked_test_cases(self, key):
            return []
    rows = bs.traceability(Unlinked(), _features(tmp_path), {}, [])
    assert any(r["test_case"] == "TC-7" and r["test_case_summary"] == "Valid login" for r in rows)


# ── a test case title revised after the coverage map was written ────────

REVISED_MAP = ("\\[agent1:coverage\\]\n"
               "- AC1 a -> \\[Positive\\] Visitor sends the form with every field filled | step 3\n"
               "- AC2 b -> \\[Negative\\] Sending the form with the email field left empty "
               "does not send it | step 3\n"
               "- AC3 c -> (none) | gap\n")
REVISED_TCS = [{"key": "TC-1", "summary": "[Positive] Visitor sends the form with every field filled"},
               {"key": "TC-2", "summary": "Sending the form with an empty email field does not send"},
               {"key": "TC-3", "summary": "Unrelated check of the page heading"}]


def test_a_revised_title_is_followed_by_its_wording():
    """13 Nov 2026: a criterion citing a test case's earlier title read as a
    gap, and the test case as not mapped to any criterion."""
    from scripts.build_site import _coverage
    c = _coverage(REVISED_MAP, ["AC1", "AC2", "AC3"], REVISED_TCS)
    assert c["coverage"] == {"AC1": ["TC-1"], "AC2": ["TC-2"], "AC3": []}
    assert c["reworded"] == {("AC2", "TC-2")} and c["unmatched"] == set()


def test_wording_never_picks_a_test_case_cited_exactly_or_an_unlike_one():
    assert rd.reworded_matches(REVISED_MAP, ["AC1", "AC2", "AC3"],
                               [REVISED_TCS[0], REVISED_TCS[2]]) == {}
    two_alike = [{"key": "A", "summary": "Sending the form with an empty email field"},
                 {"key": "B", "summary": "Sending the form with an empty email field twice"}]
    m = rd.reworded_matches(REVISED_MAP, ["AC2"], two_alike)
    assert m == {"AC2": ["A"]}                       # the single best, never both


def test_a_reworded_row_says_so():
    from scripts.build_site import _coverage, _test_case_cell
    story = {"key": "ST-9", "criteria": [("AC2", "b")], "test_cases": REVISED_TCS,
             "scenarios": {"TC-2": ["t::two"]}, **_coverage(REVISED_MAP, ["AC2"], REVISED_TCS)}
    rows = rd.traceability_rows([story], {"t::two": {"verdict": "passed", "started": "2026-11-13"}}, {})
    ac2 = next(r for r in rows if r["criterion"] == "AC2")
    assert (ac2["test_case"], ac2["result"]) == ("TC-2", "passed")
    assert "earlier title" in _test_case_cell(ac2)
