"""Group B RP5: the AI metrics - cost per story and agent across all attempts,
first-attempt success, stops that needed a person, review findings, Agent 0's
recall and precision - kept on the results store and shown on History and
the PDF.

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import ai_metrics as am
from core import usage_ledger as ul
from tests.sandbox.fake_jira import FakeJira, jira_client_over

NOW = _dt.datetime(2026, 11, 14, 12, 0, tzinfo=_dt.timezone.utc)


def _use(jira, key, agent, cost):
    assert ul.post_usage_to_story(key, agent, {"llm_calls": 1, "input_tokens": 100,
                                               "output_tokens": 50,
                                               "estimated_cost_usd": cost}, jira=jira)


@pytest.fixture
def world(monkeypatch):
    fake = FakeJira()
    fake.add("Story", "Clean story", key="SBX-1", labels=["ai-processed", "ai-coded"])
    fake.add("Story", "Reworked story", key="SBX-2", labels=["ai-processed", "ai-coded"])
    fake.add("Story", "Drafted only", key="SBX-3", labels=["ai-processed"])
    fake.add("Story", "Untouched", key="SBX-4")
    jira = jira_client_over(fake, monkeypatch)
    assert ul.mode(jira) == "properties"
    _use(jira, "SBX-1", "Agent 1 (Test Designer)", 0.40)
    _use(jira, "SBX-1", "Agent 2 (Coder, initial)", 1.10)
    _use(jira, "SBX-1", "Agent 3 (Reviewer)", 0.20)
    _use(jira, "SBX-2", "Agent 1 (Test Designer)", 0.50)
    _use(jira, "SBX-2", "Agent 2 (Coder, initial)", 1.00)
    _use(jira, "SBX-2", "Agent 2 (Coder, waiting)", 0.00)
    _use(jira, "SBX-2", "Agent 2 (Coder, review fix)", 0.60)
    _use(jira, "SBX-3", "Agent 1 (Test Designer)", 0.30)
    jira.add_comment("SBX-3", "[agent1:stopped] Agent 1 stopped on this story ...")
    jira.add_comment("SBX-2", "[agent2:blocked] inputs: x reasons: y")
    return fake, jira


def _stories(fake):
    return [{"key": k, "labels": list(d["labels"]), "updated": "2026-11-13T10:00:00"}
            for k, d in fake.issues.items() if d["issuetype"] == "Story"]


def _rec(world, key):
    fake, jira = world
    story = next(s for s in _stories(fake) if s["key"] == key)
    return am.story_record(jira, story, "ai-coded")


def test_cost_is_per_agent_and_first_attempt_is_one_initial_run(world):
    one = _rec(world, "SBX-1")
    assert one["cost_usd"] == pytest.approx(1.70) and one["first_attempt"] is True
    assert one["by_agent"] == {"Agent 1 (Test Designer)": 0.4, "Agent 2 (Coder)": 1.1,
                               "Agent 3 (Reviewer)": 0.2}
    two = _rec(world, "SBX-2")
    assert two["first_attempt"] is False and two["coding_runs"] == 2, "a waiting run is no run"
    assert two["refusals"] == {"Agent 2's gate refused the code": 1}
    three = _rec(world, "SBX-3")
    assert three["first_attempt"] is None, "not coded: not counted either way"
    assert three["refusals"] == {"Agent 1 handed the story back": 1}


def test_a_new_attempt_is_not_a_first_attempt_success_and_its_cost_still_counts(world):
    fake, jira = world
    ul.post_reset_to_story("SBX-1", "drafted again", jira=jira)
    _use(jira, "SBX-1", "Agent 2 (Coder, initial)", 0.90)
    rec = _rec(world, "SBX-1")
    assert rec["attempts"] == 2 and rec["first_attempt"] is False
    assert rec["cost_usd"] == pytest.approx(2.60), "every attempt's cost"


def test_reviews_and_predictions_are_read_from_the_story(world):
    fake, jira = world
    issues = [SimpleNamespace(severity="blocking"), SimpleNamespace(severity="minor"),
              SimpleNamespace(severity="minor")]
    assert am.record_review(jira, "SBX-1", 41, "request_changes", issues)
    assert am.record_review(jira, "SBX-1", 41, "approve", [])
    from agents.agent0_impact import save_outcome
    save_outcome(jira, "SBX-1", "#41", {"recall": 0.5, "precision": 1.0,
                                       "predicted": ["SBX-7"],
                                       "actual_changed": ["SBX-7"], "actual_failed": ["SBX-8"]})
    rec = _rec(world, "SBX-1")
    (review,) = rec["reviews"]
    assert review["verdict"] == "approve" and review["reviews"] == 2, "the latest, counted"
    assert rec["predictions"] == [{"recall": 0.5, "precision": 1.0, "predicted": ["SBX-7"],
                                   "actual": ["SBX-7", "SBX-8"]}]


def test_the_store_keeps_records_and_the_summary_adds_up_the_window(world, tmp_path,
                                                                   monkeypatch):
    fake, jira = world
    am.record_review(jira, "SBX-2", 42, "request_changes",
                     [SimpleNamespace(severity="major")])
    monkeypatch.setattr(jira, "defects_for_history",
                        lambda t, updated_since=None, open_only=False: _stories(fake))
    out = am.sync(tmp_path, jira, NOW, 30, 90)
    assert out == {"read": 4, "kept": 3}, "the untouched story has no record"
    data = am.read(tmp_path)
    data["stories"]["SBX-9"] = {"key": "SBX-9", "updated": "2026-09-01", "runs": 1,
                                "cost_usd": 99.0, "by_agent": {}}
    sm = am.summary(data["stories"], "2026-10-15")
    assert sm["stories"] == 3 and sm["cost_usd"] == pytest.approx(4.10), \
        "1.70 + 2.10 + 0.30; the record outside the window is left out"
    assert sm["cost_per_story"] == pytest.approx(1.37)
    assert sm["by_agent"][0] == ("Agent 2 (Coder)", 2.7)
    assert sm["coded"] == 2 and sm["first_attempt"] == 1 and sm["first_attempt_rate"] == 50.0
    assert sm["refusal_total"] == 2
    assert sm["reviews"] == 1 and sm["changes_requested"] == 1 and sm["findings"]["major"] == 1
    assert sm["costliest"][0] == ("SBX-2", pytest.approx(2.1))


def test_an_unreadable_tracker_leaves_the_store_alone(tmp_path, world, monkeypatch):
    fake, jira = world
    monkeypatch.setattr(jira, "defects_for_history", lambda *a, **k: None)
    assert am.sync(tmp_path, jira, NOW, 30, 90) is None
    assert not (tmp_path / am.STORE_FILE).exists()


def test_agent0_precision_and_recall_are_counted_over_every_prediction():
    recs = {"A": {"updated": "2026-11-10", "predictions": [
        {"predicted": ["T1", "T2"], "actual": ["T1"]},
        {"predicted": [], "actual": ["T3"]}]}}
    sm = am.summary(recs, "2026-11-01")
    assert sm["predictions"] == 2 and sm["precision"] == 50.0 and sm["recall"] == 50.0


def test_history_and_the_pdf_show_them(tmp_path):
    from scripts import build_site as bs
    sm = am.summary({"A": {"key": "SBX-1", "updated": "2026-11-10", "runs": 2, "cost_usd": 1.5,
                           "by_agent": {"Agent 2 (Coder)": 1.5}, "first_attempt": True,
                           "refusals": {"an approval was refused": 1}}}, "2026-11-01")
    page = bs.ai_metrics_html({"window_days": 30, "ai_metrics": {"summary": sm,
                                                                 "as_of": "2026-11-14 06:00"}})
    assert "AI metrics" in page and "$1.50" in page and "100%" in page
    assert "an approval was refused" in page and "Agent 2 (Coder)" in page
    assert "No AI metrics yet" in bs.ai_metrics_html({"window_days": 30, "ai_metrics": None})
    src = (Path(__file__).resolve().parents[2] / "scripts" / "build_site.py").read_text()
    assert 'Paragraph(f"AI metrics, last' in src


def test_agent3_records_each_review():
    src = (Path(__file__).resolve().parents[2] / "agents" / "agent3_reviewer.py").read_text()
    assert "record_review(get_tracker(), _m.group(1), pr_number, report.overall_verdict" in src


def test_the_site_reads_the_store_without_the_tracker_and_makes_the_pdf(tmp_path):
    import json
    from scripts import build_site as bs
    store, out = tmp_path / "store", tmp_path / "site"
    store.mkdir()
    today = _dt.date.today().isoformat()
    (store / am.STORE_FILE).write_text(json.dumps({"synced": f"{today}T06:00:00", "stories": {
        "SBX-1": {"key": "SBX-1", "updated": today, "runs": 3, "cost_usd": 1.7,
                  "by_agent": {"Agent 2 (Coder)": 1.1}, "first_attempt": True}}}))
    assert bs.main(["--store", str(store), "--out", str(out), "--no-tracker"]) == 0
    page = (out / "history.html").read_text()
    assert "AI metrics" in page and "$1.70" in page
    pytest.importorskip("reportlab")      # requirements-reports.txt: the Reports run only
    assert (out / "summary.pdf").exists()
