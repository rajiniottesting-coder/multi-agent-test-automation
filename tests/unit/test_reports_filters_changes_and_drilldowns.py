"""The reports pages, second round (RP14-RP25): the traceability matrix's
filters, grouping and CSV; the latest run's changes since the previous run,
defects and expected failures; the History page's menu, stop drill-down,
spend per agent, weekly trends, review note and matrix links; labelled cards
on a phone; and this sprint against the one before (History and PDF).

Generic names only: the stories, test cases and defects are invented.
"""
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from core import ai_metrics as am
from core import report_data as rd
from scripts import build_site as bs

T1, T2, T3, T4 = (f"tests.step_defs.test_m::test_{n}" for n in ("one", "two", "three", "four"))


def _run(i, started):
    return {"run_id": i, "started": started, "url": f"https://ci.example/{i}", "event": "schedule",
            "passed": 1, "failed": 1, "flaky": 0, "outage": 0, "skipped": 0, "duration_s": 60}


def _res(run, test, verdict, started="2026-11-13T20:00:00Z", **kw):
    return {"run_id": run, "test": test, "verdict": verdict, "started": started,
            "scenario": test.split("::")[-1], "file": "m.feature", **kw}


# ── RP17: changed since the previous run ───────────────────────────────

def test_run_changes_sorts_each_test_into_what_changed():
    runs = [_run(1, "2026-11-12T20:00:00Z"), _run(2, "2026-11-13T20:00:00Z")]
    results = [_res(1, T1, "passed"), _res(1, T2, "failed"), _res(1, T3, "failed"),
               _res(1, "gone::t", "passed"),
               _res(2, T1, "failed"), _res(2, T2, "passed"), _res(2, T3, "failed"),
               _res(2, T4, "outage")]
    c = rd.run_changes(runs, results)
    assert c["previous"]["run_id"] == 1
    assert (c["newly_failing"], c["fixed"], c["still_failing"]) == ([T1], [T2], [T3])
    assert c["new"] == [T4] and c["gone"] == ["gone::t"]
    assert rd.run_changes(runs[:1], results) is None


def test_the_changes_card_lists_them_and_says_when_nothing_changed():
    runs = [_run(1, "2026-11-12T20:00:00Z"), _run(2, "2026-11-13T20:00:00Z")]
    page = bs.changes_html(rd.run_changes(runs, [_res(1, T1, "passed"), _res(2, T1, "failed")]))
    assert "Changed since the previous run" in page and "Newly failing" in page
    assert "<code>test_one</code>" in page and "https://ci.example/1" in page
    quiet = bs.changes_html(rd.run_changes(runs, [_res(1, T1, "passed"), _res(2, T1, "passed")]))
    assert "No test changed its result." in quiet and "<table" not in quiet
    assert "nothing to compare yet" in bs.changes_html(None)


# ── RP18: the defect and the expected failure ──────────────────────────

class _Pending:
    def __init__(self, waits):
        self.waits = waits

    def story_of(self, owner, test_case=None):
        return self.waits.get(owner)


def test_each_row_gets_its_open_defect_and_its_deployment_wait(monkeypatch):
    monkeypatch.setattr("core.deployment.PendingStories", lambda tracker: _Pending({"ST-2": "ST-2"}))
    latest = {"rows": [_res(2, T1, "failed", story="ST-1"), _res(2, T2, "failed", story="ST-2"),
                       _res(2, T3, "flaky", story="ST-2")]}
    records = [{"key": "BUG-1", "open": True, "test": T1, "deleted": None},
               {"key": "BUG-0", "open": False, "test": T2, "deleted": None},
               {"key": "BUG-X", "open": True, "test": T2, "deleted": "2026-11-13"}]
    bs.mark_latest_rows(latest, records, tracker=object())
    r1, r2, r3 = latest["rows"]
    assert (r1["defect"], r1["awaiting"]) == ("BUG-1", None)
    assert (r2["defect"], r2["awaiting"]) == (None, "ST-2"), "closed or deleted: no defect"
    assert r3["awaiting"] is None, "only a failure is expected"
    assert latest["expected"] == 1
    bs.mark_latest_rows(latest, records, tracker=None)
    assert latest["expected"] == 0


def test_the_latest_run_page_shows_them():
    lr = {"run": _run(2, "2026-11-13T20:00:00Z"), "pass_rate": 0.5, "passed": 1, "expected": 1,
          "rows": [{**_res(2, T1, "failed", story="ST-1"), "defect": "BUG-1", "awaiting": None},
                   {**_res(2, T2, "failed", story="ST-2"), "defect": None, "awaiting": "ST-2"}],
          "changes": {"previous": _run(1, "2026-11-12T20:00:00Z"), "newly_failing": [T1],
                      "fixed": [], "still_failing": [T2], "new": [], "gone": []}}
    page = bs.latest_html({"generated": "2026-11-14 06:00", "window_days": 30, "latest": lr})
    assert "<th>Defect</th>" in page and ">BUG-1<" in page
    assert "expected until" in page and ">ST-2<" in page and "is deployed" in page
    assert "new since the previous run" in page
    assert "failed (1 expected)" in page
    assert "<i>Not judged</i>: failed because the application itself was unavailable" in page


# ── RP14-RP16: the traceability matrix ─────────────────────────────────

def _rows():
    def row(story, ref, text, tc, test, result, sprints, defects=()):
        return {"story": story, "story_summary": f"Summary of {story}", "story_status": "Done",
                "story_sprints": sprints, "criterion": ref, "criterion_text": text,
                "test_case": tc, "test_case_summary": f"Case {tc}" if tc else "",
                "scenario": test, "result": result, "result_date": "2026-11-13" if test else "",
                "defects": list(defects), "unmapped_criteria": 0, "note": ""}
    shared = "Acceptance criteria AC1, AC2: not mapped to test cases (the story has no coverage map)"
    rows = [row("ST-1", "-", shared, "TC-1", T1, "passed", ["Sprint 1"]),
            row("ST-1", "-", shared, "TC-2", T2, "failed", ["Sprint 1"], ["BUG-1"]),
            row("ST-2", "AC1", "User </script> can pay", "TC-3", T3, "passed", []),
            row("ST-2", "AC2", "A refused card is shown", "", "", "no test case", [])]
    rows[0]["unmapped_criteria"] = 2
    return rows


def test_story_groups_sum_up_each_story():
    g1, g2 = rd.story_groups(_rows())
    assert (g1["story"], g1["criteria"], g1["uncovered"], g1["test_cases"]) == ("ST-1", 2, 0, 2)
    assert g1["results"] == {"passed": 1, "failed": 1} and g1["defects"] == ["BUG-1"]
    assert g1["sprints"] == ["Sprint 1"] and g2["sprints"] == []
    assert (g2["criteria"], g2["uncovered"], g2["results"]) == (2, 1, {"passed": 1})


def _matrix_page():
    rows = _rows()
    data = {"generated": "2026-11-14 06:00", "window_days": 30, "traceability": rows,
            "traceability_summary": rd.traceability_summary(rows),
            "story_groups": rd.story_groups(rows), "unlinked_defects": []}
    return bs.traceability_html(data)


def test_the_matrix_is_grouped_by_story_with_filters():
    page = _matrix_page()
    assert page.count("<details class='story' open") == 2
    assert "data-story='ST-1'" in page and "data-sprints='[&quot;Sprint 1&quot;]'" in page
    for sel in ("f-story", "f-result", "f-sprint", "f-q", "f-csv", "f-clear"):
        assert f"id='{sel}'" in page
    assert "<option value='Sprint 1'>" in page and "<option value='(no sprint)'>" in page
    assert "<option value='failed'>failed</option>" in page
    assert "2 stories, 4 rows shown" in page
    assert "1 without a test case" in page, "the story's own gap is in its summary line"


def test_a_criterion_text_shared_by_every_row_is_said_once():
    page = _matrix_page()
    st1 = page[page.index("data-story='ST-1'"):page.index("data-story='ST-2'")]
    shown = re.sub(r"<[^>]+>", " ", st1)              # what the page shows, not its attributes
    assert shown.count("not mapped to test cases") == 1
    assert "<th>Criterion</th>" not in st1, "said once, so no criterion column"
    st2 = page[page.index("data-story='ST-2'"):]
    assert "A refused card is shown" in st2 and "<b>AC2</b>" in st2


def test_every_row_carries_what_the_filters_and_the_csv_read():
    page = _matrix_page()
    attrs = re.findall(r"<tr data-i='(\d)' data-result='([^']*)' data-text='([^']*)'>", page)
    assert [(i, r) for i, r, _ in attrs] == [("0", "passed"), ("1", "failed"), ("2", "passed"),
                                            ("3", "no test case")]
    assert "bug-1" in attrs[1][2], "search finds a row by its defect"
    data = re.search(r"<script type='application/json' id='trace-rows'>(.*?)</script>",
                     page, re.S).group(1)
    assert "</script>" not in data and "<\\/script>" in data, "no early end of the script"
    rows = json.loads(data)
    assert rows[1]["defects"] == ["BUG-1"] and rows[0]["story_sprints"] == ["Sprint 1"]
    assert json.loads(re.search(r"id='trace-cols'>(.*?)</script>", page).group(1)) == bs._CSV_FIELDS


def test_without_sprints_there_is_no_sprint_filter():
    rows = [dict(r, story_sprints=[]) for r in _rows()]
    page = bs.traceability_html({"generated": "x", "window_days": 30, "traceability": rows,
                                 "traceability_summary": rd.traceability_summary(rows),
                                 "story_groups": rd.story_groups(rows), "unlinked_defects": []})
    assert "id='f-sprint'" not in page and "id='f-story'" in page


@pytest.mark.skipif(shutil.which("node") is None, reason="no node in this checkout")
def test_the_matrix_script_is_valid_javascript(tmp_path):
    js = tmp_path / "matrix.js"
    js.write_text(bs._TRACE_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_traceability_reads_each_storys_sprints(tmp_path):
    from tests.unit.test_reporting import FakeTracker, _features
    t = FakeTracker()
    t.sprints_of = lambda keys: {k: ["Sprint 9"] for k in keys}
    rows = bs.traceability(t, _features(tmp_path), {}, t.defects)
    assert rows and all(r["story_sprints"] == ["Sprint 9"] for r in rows)
    t.sprints_of = lambda keys: (_ for _ in ()).throw(RuntimeError("no field"))
    assert all(r["story_sprints"] == [] for r in bs.traceability(t, tmp_path / "features", {},
                                                                 t.defects))


def test_jira_finds_the_sprint_field_by_its_schema():
    from integrations.jira_client import JiraClient
    j = JiraClient.__new__(JiraClient)
    sp = SimpleNamespace(name="Sprint 1")
    issue = SimpleNamespace(key="ST-1", fields=SimpleNamespace(customfield_9=[sp]))
    asked = {}
    j._client = SimpleNamespace(
        fields=lambda: [{"id": "summary", "schema": {}},
                        {"id": "customfield_9", "schema": {"custom":
                                                          "com.pyxis.greenhopper.jira:gh-sprint"}}],
        search_issues=lambda jql, fields, maxResults: asked.update(jql=jql, fields=fields) or [issue])
    assert j.sprints_of(["ST-1", "ST-1"]) == {"ST-1": ["Sprint 1"]}
    assert asked == {"jql": "key in (ST-1)", "fields": "customfield_9"}
    j._client = SimpleNamespace(fields=lambda: [{"id": "summary", "schema": {}}])
    assert j.sprints_of(["ST-1"]) is None and j.sprints_of([]) == {}


# ── RP19-RP23: the History page ────────────────────────────────────────

class _Tracker:
    def __init__(self):
        self.comments = [
            {"at": "2026-11-03T10:00:00.000+0000", "body": "[LLM-USAGE] Agent 2 (Coder)"},
            {"at": "2026-11-03T11:00:00.000+0000", "body": "[agent2:blocked] the gate refused"},
            {"at": "2026-11-10T09:00:00.000+0000", "body": "[agent2:incomplete] part"}]

    def get_comments_dated(self, key):
        return self.comments

    def get_comments(self, key):
        raise AssertionError("the dated read is used when the tracker offers it")


def test_a_story_record_dates_its_spend_stops_and_first_coding(monkeypatch):
    from core import usage_ledger as ul
    monkeypatch.setattr(ul, "mode", lambda tracker: "comments")

    def parse(body):
        if body.startswith("[LLM-USAGE]"):
            return {"agent": "Agent 2 (Coder)", "calls": 1, "input_tokens": 1,
                    "output_tokens": 1, "input_cost_usd": 0.5, "output_cost_usd": 0.5,
                    "cost_usd": 1.0, "unreported": 0}
        return None
    monkeypatch.setattr(ul, "parse_usage_comment", parse)
    rec = am.story_record(_Tracker(), {"key": "ST-1", "labels": ["ai-coded"],
                                       "updated": "2026-11-10"}, "ai-coded")
    assert rec["spend_days"] == {"2026-11-03": 1.0}
    assert rec["stop_days"] == {"2026-11-03": {"Agent 2's gate refused the code": 1},
                                "2026-11-10": {"automated only in part": 1}}
    assert rec["first_coded"] == "2026-11-03" and rec["runs_by_agent"] == {"Agent 2 (Coder)": 1}


def test_property_entries_carry_their_time():
    from core import usage_ledger as ul
    assert ul._stamp_time("llm.usage.20261114T101500123456Z.ab12cd34") == "2026-11-14T10:15:00Z"
    assert ul._stamp_time("llm.usage.x.y") is None


def _records():
    return {
        "ST-1": {"key": "ST-1", "updated": "2026-11-10", "runs": 3, "cost_usd": 6.0,
                 "by_agent": {"Agent 2 (Coder)": 5.0, "Agent 1 (Test Designer)": 1.0},
                 "runs_by_agent": {"Agent 2 (Coder)": 2, "Agent 1 (Test Designer)": 1},
                 "refusals": {"Agent 2's gate refused the code": 2},
                 "spend_days": {"2026-11-03": 5.0, "2026-11-10": 1.0},
                 "stop_days": {"2026-11-03": {"Agent 2's gate refused the code": 2}},
                 "first_coded": "2026-11-03", "first_attempt": False},
        "ST-2": {"key": "ST-2", "updated": "2026-11-11", "runs": 1, "cost_usd": 2.0,
                 "by_agent": {"Agent 2 (Coder)": 2.0}, "runs_by_agent": {"Agent 2 (Coder)": 1},
                 "refusals": {"Agent 2's gate refused the code": 1, "automated only in part": 1},
                 "spend_days": {"2026-11-11": 2.0},
                 "stop_days": {"2026-11-11": {"automated only in part": 1}},
                 "first_coded": "2026-11-11", "first_attempt": True},
        "OLD": {"key": "OLD", "updated": "2026-11-12", "runs": 1, "cost_usd": 1.0,
                "by_agent": {"Agent 2 (Coder)": 1.0}},          # read before dates were kept
    }


def test_the_summary_adds_agents_stories_per_stop_and_weeks():
    sm = am.summary(_records(), "2026-11-01")
    coder = next(a for a in sm["agents"] if a["agent"] == "Agent 2 (Coder)")
    assert (coder["cost_usd"], coder["runs"], coder["per_run"], coder["share"]) == (8.0, 3, 2.67, 88.9)
    assert sm["stories_by_stop"]["Agent 2's gate refused the code"] == [("ST-1", 2), ("ST-2", 1)]
    w1, w2 = sm["weekly"]
    assert (w1["week"], w1["cost_usd"], w1["stories"], w1["stop_total"]) == ("2026-11-02", 5.0, 1, 2)
    assert (w1["coded"], w1["first_attempt_rate"]) == (1, 0.0)
    assert (w2["week"], w2["cost_usd"], w2["stories"], w2["cost_per_story"]) == ("2026-11-09", 3.0, 2, 1.5)
    assert (w2["coded"], w2["first_attempt_rate"]) == (1, 100.0)
    assert am.weekly(_records().values(), "2026-11-09")[0]["week"] == "2026-11-09"


def test_the_history_page_has_its_menu_drilldown_trends_and_notes(monkeypatch):
    monkeypatch.delenv("JIRA_URL", raising=False)        # plain keys, whatever ran before
    sm = am.summary(_records(), "2026-11-01")
    data = {"generated": "2026-11-14 06:00", "window_days": 30,
            "kpis": {"latest_run": None, "latest_pass_rate": None, "window_pass_rate": None,
                     "runs": 0, "tests": 0, "flaky": 0},
            "trend": {"run": [], "started": [], "passed": [], "flaky": [], "failed": [],
                      "outage": [], "skipped": [], "duration_min": []},
            "slowest": [], "flaky": [], "by_file": [],
            "by_story": [{"name": "ST-1", "tests": 2, "passed": 2, "failed": 0, "other": 0,
                          "pass_rate": 1.0}],
            "defects": None, "defect_list": None, "defect_history": None,
            "ai_metrics": {"summary": sm, "as_of": "2026-11-14 06:00"},
            "sprint_compare": None}
    page = bs.dashboard_html(data)
    assert "<nav class='sections'>" in page
    for anchor in ("runs", "tests", "stories", "defects", "ai"):
        assert f"href='#{anchor}'" in page and f"id='{anchor}'" in page
    assert "href='#sprints'" not in page, "no sprint comparison yet, no link to it"
    assert "href='traceability.html#story=ST-1'>matrix</a>" in page
    assert "<th>Share</th><th>Runs</th><th>Per run</th>" in page and ">88.9%<" in page
    assert "<details><summary>Agent 2&#x27;s gate refused the code" in page
    assert "2 stories</span></summary>ST-1 (2), ST-2</details>" in page
    assert "a pull request with no story - framework changes - is not counted" in page
    assert "Plotly.newPlot('ai-trend'" in page and "Plotly.newPlot('stops-trend'" in page
    ai = page[page.index("Plotly.newPlot('ai-trend'"):page.index("Plotly.newPlot('stops-trend'")]
    assert "yaxis2:{overlaying:'y',side:'right'" in ai and "margin:{t:20,r:60" in ai, \
        "the right-hand axis has room for its labels"
    stops = page[page.index("Plotly.newPlot('stops-trend'"):]
    assert "legend:{orientation:'h',y:-0.5}" in ai and "legend:{orientation:'h',y:-0.45}" in stops, \
        "the legends sit below the plots - above them they wrapped onto the bars on a phone"


# ── RP24: a table on a phone ───────────────────────────────────────────

def test_every_cell_names_its_column_and_a_phone_shows_cards():
    table = bs._table(["Name", "Spend"], [["A", "$1"]], ["data-x='1'"])
    assert "<tr data-x='1'><td data-label='Name'>A</td><td data-label='Spend'>$1</td></tr>" in table
    assert "@media (max-width:640px)" in bs._CSS and "content:attr(data-label)" in bs._CSS
    # 14 Nov 2026, the first live build: a scenario name is one long token
    # (test_adding_the_same_product_twice_shows_...) and pushed the matrix
    # 268 px past a phone's width. On a phone a cell may break a long word.
    phone = bs._CSS[bs._CSS.index("@media (max-width:640px)"):]
    assert "overflow-wrap:anywhere" in phone[:phone.index("}}") + 2]
    # ...and the story filter, as wide as its longest story title.
    assert ".filters select,.filters input{max-width:100%}" in bs._CSS


# ── RP25: this sprint against the one before ───────────────────────────

def _sprints():
    return [{"name": "Sprint 1", "start": "2026-11-01", "end": "2026-11-07", "opened": 4,
             "closed": 1, "open": 3, "detection_rate": 50.0},
            {"name": "Sprint 2", "start": "2026-11-08", "end": "2026-11-14", "opened": 1,
             "closed": 3, "open": 1, "detection_rate": 100.0}]


def test_sprint_over_sprint_compares_the_two_newest():
    results = [_res(1, T1, "failed", "2026-11-03T20:00:00Z"),
               _res(1, T2, "passed", "2026-11-03T20:00:00Z"),
               _res(2, T1, "passed", "2026-11-10T20:00:00Z"),
               _res(2, T2, "passed", "2026-11-10T20:00:00Z")]
    c = rd.sprint_over_sprint(_sprints(), results, _records())
    a, b = c["previous"], c["current"]
    assert (a["name"], a["pass_rate"], a["runs"], a["spend_usd"], a["stops"]) == \
        ("Sprint 1", 0.5, 1, 5.0, 2)
    assert (b["name"], b["pass_rate"], b["runs"], b["spend_usd"], b["stops"]) == \
        ("Sprint 2", 1.0, 1, 3.0, 1)
    assert (b["opened"], b["closed"], b["detection_rate"]) == (1, 3, 100.0)
    assert rd.sprint_over_sprint(_sprints()[:1], results, {}) is None


def test_the_comparison_reads_better_and_worse():
    results = [_res(1, T1, "failed", "2026-11-03T20:00:00Z"),
               _res(2, T1, "passed", "2026-11-10T20:00:00Z")]
    page = bs.sprint_compare_html(rd.sprint_over_sprint(_sprints(), results, _records()))
    assert "id='sprints'" in page and "Sprint 1 (2026-11-01 to 2026-11-07)" in page
    assert "<span class='v-fixed'>+100 pts</span>" in page          # pass rate up: better
    assert "<span class='v-fixed'>-3</span>" in page                 # defects opened down: better
    assert "<span class='v-fixed'>-$2.00</span>" in page             # spend down: better
    assert bs.sprint_compare_html(None) == ""


def test_the_pdf_has_the_comparison(tmp_path):
    pytest.importorskip("reportlab")
    results = [_res(1, T1, "failed", "2026-11-03T20:00:00Z"),
               _res(2, T1, "passed", "2026-11-10T20:00:00Z")]
    data = {"generated": "2026-11-14 06:00", "window_days": 30,
            "kpis": {"latest_run": None, "latest_pass_rate": None, "window_pass_rate": None,
                     "runs": 0, "tests": 0, "flaky": 0},
            "trend": {"run": []}, "defects": None, "by_file": [], "flaky": [],
            "sprint_compare": rd.sprint_over_sprint(_sprints(), results, _records())}
    import reportlab.platypus as rp
    seen = []
    real = rp.SimpleDocTemplate.build

    def build(self, flow, *a, **k):
        seen.extend(flow)
        return real(self, flow, *a, **k)
    import unittest.mock as um
    with um.patch.object(rp.SimpleDocTemplate, "build", build):
        assert bs.summary_pdf(data, tmp_path / "s.pdf", False)
    texts = [getattr(f, "text", "") for f in seen]
    assert "This sprint against the one before" in texts
    table = next(f for f in seen if getattr(f, "_cellvalues", None)
                 and len(f._cellvalues[0]) == 3 and "Sprint 2" in f._cellvalues[0][2])
    assert table._cellvalues[1] == ["Pass rate", "0%", "100%"]
    assert table._cellvalues[7] == ["Model spend", "$5.00", "$3.00"]
