"""RP7 (the sprint's test summary on the tracker) and RP10 (a trend chart on
Agent 5's comment). Offline: a fake tracker records what it is asked."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from core import sprint_summary as ss
from core import story_trend as st

SPRINT = {"id": 4, "name": "Sprint 4", "start": "2026-11-01T00:00:00Z", "end": "2026-11-13T20:00:00Z"}
SETTINGS = {"sprint_summary": True, "sprint_summary_issue_type": "Task",
            "sprint_summary_status": "Done", "story_trend": True,
            "story_trend_points": 3, "story_trend_min_points": 2}


def data(**over):
    d = {"generated": "2026-11-13 18:00", "window_days": 30, "sprint": SPRINT,
         "kpis": {"latest_pass_rate": 0.9, "window_pass_rate": 0.8, "runs": 5, "tests": 10,
                  "flaky": 1, "latest_run": {"passed": 9, "failed": 1, "flaky": 0, "outage": 0}},
         "defects": {"total": 2}, "by_file": [{"name": "a.feature", "failed": 1, "tests": 4, "passed": 3, "other": 0, "pass_rate": 0.75}],
         "flaky": [{"test": "t::x", "flaky": 1, "runs": 5, "last": "2026-11-12"}],
         "traceability_summary": {"criteria_uncovered": 3}}
    d.update(over)
    return d


class Tracker:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.calls = []
        self.props = {}

    def issues_for_report(self, issue_type, open_only=True, labels=None):
        self.calls.append(("read", issue_type, open_only, labels))
        return self.existing

    def create_issue(self, issue_type, summary, description, labels=None):
        self.calls.append(("create", issue_type, summary, description, labels))
        return "SUM-1"

    def render_markdown(self, md):
        return "RENDERED:" + md

    def add_attachment(self, key, path, name=None):
        self.calls.append(("attach", key, Path(path).name, name))
        return f"!{name}!"

    def add_comment(self, key, body):
        self.calls.append(("comment", key, body))
        return "url"

    def transition_status(self, key, status):
        self.calls.append(("move", key, status))
        return True

    def set_property(self, key, name, value):
        self.props[name] = value

    def properties(self, key, prefix=""):
        return {k: v for k, v in self.props.items() if k.startswith(prefix)}


# ── RP7 ─────────────────────────────────────────────────────────────────

def test_the_summary_text_has_the_numbers_the_risks_and_the_link():
    text = ss.summary_markdown(data(), "https://site.example/")
    for part in ("**Sprint 4**", "2026-11-01 to 2026-11-13", "| Pass rate, latest run | 90% |",
                 "| Open defects | 2 |", "a.feature: 1 failing of 4", "t::x flaked 1 times",
                 "3 acceptance criteria have no test case", "https://site.example/"):
        assert part in text, part


def test_a_sprint_summary_is_recorded_once_and_moved_off_the_open_columns(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF")
    t = Tracker()
    assert ss.post(t, data(), pdf, "https://site.example/", settings=SETTINGS) == "SUM-1"
    kinds = [c[0] for c in t.calls]
    assert kinds == ["read", "create", "attach", "move"]
    create = t.calls[1]
    assert create[1:3] == ("Task", "Test summary: Sprint 4") and create[4] == [ss.LABEL]
    assert create[3].startswith("RENDERED:")                     # the tracker's markup
    assert t.calls[0][2] is False                                # closed ones count too
    assert t.calls[2][3] == "test-summary-sprint-4.pdf"
    assert t.calls[3] == ("move", "SUM-1", "Done")


def test_an_existing_summary_is_left_alone_unless_forced(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF")
    t = Tracker(existing=[{"key": "SUM-9", "summary": "Test summary: Sprint 4"}])
    assert ss.post(t, data(), pdf, None, settings=SETTINGS) == "SUM-9"
    assert [c[0] for c in t.calls] == ["read"]
    t.calls.clear()
    assert ss.post(t, data(), pdf, None, force=True, settings=SETTINGS) == "SUM-9"
    assert [c[0] for c in t.calls] == ["read", "comment"]      # no second PDF copy
    assert "Pass rate, latest run" in t.calls[-1][2]


def test_no_summary_without_a_sprint_a_capability_or_when_switched_off():
    assert ss.post(Tracker(), data(sprint=None), None, None, settings=SETTINGS) is None
    assert ss.post(Tracker(), data(), None, None,
                   settings={**SETTINGS, "sprint_summary": False}) is None
    assert ss.post(object(), data(), None, None, settings=SETTINGS) is None


def test_a_refused_summary_never_raises():
    class Refusing(Tracker):
        def create_issue(self, *a, **k):
            raise RuntimeError("HTTP 400 issue type Task not found ghp_" + "x" * 36)
    assert ss.post(Refusing(), data(), None, None, settings=SETTINGS) is None


def test_build_site_records_the_summary_when_forced(tmp_path, monkeypatch):
    from scripts import build_site as bs
    posted = {}
    monkeypatch.setattr(bs, "_tracker", lambda: Tracker())
    monkeypatch.setattr("core.sprint_summary.post",
                        lambda tracker, d, pdf, url, force=False: posted.update(url=url, force=force) or "SUM-1")
    monkeypatch.setattr(bs, "collect", lambda *a, **k: {
        **data(), "trend": {"run": [], "started": [], "url": [], "passed": [], "flaky": [],
                            "failed": [], "outage": [], "skipped": [], "duration_min": []},
        "slowest": [], "by_story": [], "defect_list": [], "defects": None,
        "traceability": None, "traceability_summary": None,
        "kpis": {**data()["kpis"], "latest_run": None}})
    assert bs.main(["--store", str(tmp_path), "--out", str(tmp_path / "site"),
                    "--site-url", "https://site.example/", "--sprint-summary", "force"]) == 0
    assert posted == {"url": "https://site.example/", "force": True}
    posted.clear()
    assert bs.main(["--store", str(tmp_path), "--out", str(tmp_path / "site"),
                    "--sprint-summary", "off"]) == 0
    assert posted == {}


# ── RP10 ────────────────────────────────────────────────────────────────

def _item(n, passed=3, failed=0):
    return st.entry(passed, failed, 0, 0, f"run{n}", "abcdef123",
                    now=dt.datetime(2026, 11, 13, 10, n, tzinfo=dt.timezone.utc))


def test_no_chart_on_a_storys_first_run(tmp_path):
    t = Tracker()
    assert st.attach_chart(t, "ST-1", _item(1, failed=2), tmp_path, SETTINGS) is None
    assert len(t.props) == 1 and next(iter(t.props)).startswith(st.PREFIX)
    assert not [c for c in t.calls if c[0] == "attach"]


def test_a_chart_from_the_second_run_on(tmp_path):
    pytest.importorskip("matplotlib")
    t = Tracker()
    for n in range(1, 5):
        shown = st.attach_chart(t, "ST-1", _item(n, failed=4 - n), tmp_path, SETTINGS)
    assert shown and shown.startswith("!test-trend-st-1-") and shown.endswith(".png!")
    assert len(st.history(t, "ST-1", 3)) == 3                   # the last `points`
    png = tmp_path / t.calls[-1][3]
    assert png.read_bytes()[:4] == b"\x89PNG"


def test_trend_switched_off_or_unsupported(tmp_path):
    t = Tracker()
    assert st.attach_chart(t, "ST-1", _item(1), tmp_path, {**SETTINGS, "story_trend": False}) is None
    assert t.props == {}
    assert st.attach_chart(object(), "ST-1", _item(1), tmp_path, SETTINGS) is None


def test_a_refused_attachment_never_raises(tmp_path):
    pytest.importorskip("matplotlib")

    class Refusing(Tracker):
        def add_attachment(self, *a, **k):
            raise RuntimeError("413 too large")
    t = Refusing()
    st.attach_chart(t, "ST-1", _item(1), tmp_path, SETTINGS)
    assert st.attach_chart(t, "ST-1", _item(2), tmp_path, SETTINGS) is None


def test_jira_attachment_markup(tmp_path):
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    sent = []

    class Client:
        def add_attachment(self, issue, attachment, filename):
            sent.append((issue, filename, attachment.read()))
    c._client = Client()
    png = tmp_path / "c.png"
    png.write_bytes(b"img")
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"doc")
    assert c.add_attachment("A-1", png) == "!c.png|thumbnail!"
    assert c.add_attachment("A-1", pdf, "x.pdf") == "[^x.pdf]"
    assert sent == [("A-1", "c.png", b"img"), ("A-1", "x.pdf", b"doc")]


def test_agent5_puts_the_chart_under_the_rendered_report():
    src = (Path(__file__).resolve().parents[2] / "agents/agent5_reporter.py").read_text()
    i = src.index("story_trend.attach_chart")
    assert src.index("body = render(final_body)") < i < src.index("comment_url = jira.add_comment(story_key, body)")


def test_reports_workflow_can_force_the_sprint_summary():
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    wf = (root / "reports.yml").read_text()
    assert "sprint_summary:" in wf and "--sprint-summary" in wf and "steps.pages.outputs.base_url" in wf
    assert "requirements-reports.txt" in (root / "agent4_runner.yml").read_text().split("Run Agent 5")[0][-2500:]


def test_the_reports_run_knows_the_board():
    """13 Nov 2026, first live run: no sprint was read - the board was not passed."""
    wf = (Path(__file__).resolve().parents[2] / ".github/workflows/reports.yml").read_text()
    build = wf[wf.index("- name: Build the site"):wf.index("- name: Keep a copy")]
    assert "JIRA_BOARD_ID: ${{ vars.JIRA_BOARD_ID }}" in build
