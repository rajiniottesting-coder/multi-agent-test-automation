"""The nightly inventory health check verifies once more when the application
is up, and an application that is not up is an alert on the pipeline health
issue - not a red run.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml
from scripts import inventory_health_report as ihr


ROOT = Path(__file__).resolve().parents[2]
FIRST = ("  no password field appeared within 15000ms at https://app.example/login.\n"
         "  ERROR: login FAILED (still on the login page).\n")
SECOND = "  Verified 120 selectors: all as expected.\n"
UP = {"available": True}
DOWN = {"available": False, "summary": "home: the page showed 'Back soon'"}


def _files(tmp_path, first=FIRST, second=SECOND, probe=None):
    import json
    (tmp_path / "first.txt").write_text(first)
    (tmp_path / "second.txt").write_text(second)
    p = tmp_path / "probe.json"
    if probe is not None:
        p.write_text(json.dumps(probe))
    return ["--output", str(tmp_path / "first.txt"), "--retry-output", str(tmp_path / "second.txt"),
            "--app-probe", str(p)]


def test_a_second_reading_that_passes_is_healthy_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = ihr.main(["--code", "2", "--retry-code", "0", *_files(tmp_path, probe=UP)])
    out = capsys.readouterr().out
    assert code == 0 and out.startswith("## ✅ Inventory healthy")
    assert "The first reading did not pass (exit '2'): `ERROR: login FAILED" in out
    assert "Verified 120 selectors" in out


def test_a_second_reading_that_fails_is_reported_as_the_second(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = ihr.main(["--code", "2", "--retry-code", "2",
                     *_files(tmp_path, second=FIRST, probe=UP)])
    out = capsys.readouterr().out
    assert code == 1 and out.startswith("## ⚠️ Login failed")
    assert "verified once more" in out


def test_no_second_reading_reads_as_before(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert ihr.main(["--code", "1", "--retry-code", "", *_files(tmp_path, probe=UP)]) == 1
    assert "first reading" not in capsys.readouterr().out


def test_an_application_not_up_is_an_alert_not_a_red_run(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    seen = {}
    monkeypatch.setattr(ihr, "alert_app_down",
                        lambda probe, healthy, url: seen.update(probe=probe, url=url) or True)
    code = ihr.main(["--code", "2", *_files(tmp_path, probe=DOWN), "--alert",
                     "--run-url", "https://ci.example/run/1"])
    out = capsys.readouterr().out
    assert code == 0 and "The application is not up" in out and "not marked failed" in out
    assert seen == {"probe": DOWN, "url": "https://ci.example/run/1"}


@pytest.mark.parametrize("state", [None, False])
def test_an_alert_that_could_not_be_posted_keeps_the_run_red(tmp_path, monkeypatch, state):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ihr, "alert_app_down", lambda *a: state)
    assert ihr.main(["--code", "2", *_files(tmp_path, probe=DOWN), "--alert"]) == 1


def test_without_alert_the_application_down_stays_red(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ihr, "alert_app_down", lambda *a: pytest.fail("no alert asked for"))
    assert ihr.main(["--code", "2", *_files(tmp_path, probe=DOWN)]) == 1


class _Tracker:
    def __init__(self):
        self.comments = []

    def get_comments(self, key):
        return list(self.comments)

    def add_comment(self, key, body):
        self.comments.append(body)
        return "url"


def test_the_alert_opens_once_and_closes_when_the_application_is_up(monkeypatch):
    from core import pipeline_health as ph
    t = _Tracker()
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: t)
    monkeypatch.setattr(ph, "issue_key", lambda tracker, create=True: "OPS-1")
    monkeypatch.setattr(ph, "refresh_view", lambda tracker, now=None: True)
    assert ihr.alert_app_down(DOWN, False, "run1") is True
    assert ihr.alert_app_down(DOWN, False, "run2") is True
    assert len(t.comments) == 1 and "Back soon" in t.comments[0]
    assert ihr.alert_app_down(UP, False, "run3") is False
    assert len(t.comments) == 2 and ihr.APP_DOWN in t.comments[1]


def test_an_unreachable_tracker_is_none(monkeypatch):
    def boom():
        raise RuntimeError("401 refused")
    monkeypatch.setattr("integrations.tracker.get_tracker", boom)
    assert ihr.alert_app_down(DOWN, False, "run") is None


def _steps():
    wf = yaml.safe_load((ROOT / ".github/workflows/inventory_health.yml").read_text())
    return {s.get("id") or s.get("name"): s for s in wf["jobs"]["verify"]["steps"]}


def test_the_workflow_verifies_once_more_only_when_the_application_is_up():
    s = _steps()
    retry = s["retry"]
    assert "steps.verify.outputs.code != '0'" in retry["if"]
    assert "d.get('available') is True" in retry["run"] and "verify_locators" in retry["run"]
    names = list(s)
    assert names.index("probe") < names.index("retry") < names.index("Report")
    report = s["Report"]
    assert report["env"]["RETRY_CODE"] == "${{ steps.retry.outputs.code }}"
    assert "--alert" in report["run"] and "JIRA_API_TOKEN" in report["env"]
