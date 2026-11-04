"""What the validation found after Run B (4 Nov 2026), one test per fix.

Scheduled runs the repository host never started are reported. Generic
names only.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from core import health_checks as hc

ROOT = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc


# ── scheduled runs the host never started ───────────────────────────────

@pytest.mark.parametrize("expr, start, end, n", [
    ("*/30 * * * *", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 5, 2, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 6, 0, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 0),
    ("45 1 * * *", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 2),
    ("0 0 1 * 0", dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 1, 12, 0, 0), 2),
    ("0 12 * * 7", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 1),
])
def test_cron_fires_counts_the_minutes_a_line_names(expr, start, end, n):
    # 5 Jan 2026 is a Monday. "0 0 1 * 0" is the 1st OR a Sunday: the window
    # starts after 1 Jan 00:00, so Sunday 4 and Sunday 11 Jan count.
    assert hc.cron_fires(expr, start.replace(tzinfo=UTC), end.replace(tzinfo=UTC)) == n


@pytest.mark.parametrize("expr", ["", "* * * *", "60 * * * *", "0 0 * * MON", "*/0 * * * *"])
def test_a_line_that_cannot_be_read_counts_nothing(expr):
    now = dt.datetime(2026, 1, 5, tzinfo=UTC)
    assert hc.cron_fires(expr, now - dt.timedelta(hours=1), now) is None


def _tree(tmp_path, cron):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "job.yml").write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n  workflow_dispatch:\n')
    return tmp_path


class _Host:
    def __init__(self, runs):
        self.runs = runs

    def get_workflow_runs(self, name, branch, limit=20):
        return self.runs[:limit]


NOW = dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)


def _run(hours_ago, event="schedule"):
    return {"event": event, "created_at": (NOW - dt.timedelta(hours=hours_ago)).isoformat()}


def test_a_schedule_that_never_started_is_reported(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(2, "workflow_dispatch"), _run(30)]), root, NOW, 24, 3)
    assert f.problem and f.alert_id == "workflow-not-starting:job.yml"
    assert "asked for 24 runs" in f.detail and "started none" in f.detail


def test_one_started_run_closes_it(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(5), _run(30)]), root, NOW, 24, 3)
    assert not f.problem and f.title.startswith("Scheduled runs of job.yml start again")


def test_a_schedule_asking_for_few_runs_is_not_judged_silent(tmp_path):
    root = _tree(tmp_path, "0 3 * * *")                # once a day: below the minimum of 3
    (f,) = hc.schedule_findings(_Host([_run(30)]), root, NOW, 24, 3)
    assert not f.problem


def test_runs_that_do_not_reach_the_window_start_give_no_finding(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    busy = [_run(h / 10, "push") for h in range(100)]   # 100 runs, all inside the last 10 h
    assert hc.schedule_findings(_Host(busy), root, NOW, 24, 3) == []


def test_an_unreadable_schedule_gives_no_finding(tmp_path):
    root = _tree(tmp_path, "0 0 * * MON")
    assert hc.schedule_findings(_Host([]), root, NOW, 24, 3) == []


def test_the_health_check_runs_it_with_the_shipped_settings():
    import yaml
    from core.ops_settings import DEFAULTS
    shipped = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())["pipeline_health"]
    assert shipped["schedule_window_hours"] == DEFAULTS["pipeline_health"]["schedule_window_hours"]
    assert shipped["schedule_min_expected"] == DEFAULTS["pipeline_health"]["schedule_min_expected"]
    src = (ROOT / "scripts" / "pipeline_health_check.py").read_text(encoding="utf-8")
    assert "hc.schedule_findings(host, root, now," in src


# ── a planned list of like elements can be declared a family ────────────

def _inv():
    return {"pages": {"p": {"url": "/p", "elements": {"head": "h1"}}}}


def test_a_planned_family_is_declared_multi_match():
    from core.inventory_planned import add_planned_element, add_planned_page
    out, why = add_planned_element(_inv(), "p", "rows", "ul > li", family=True)
    assert not why and out["pages"]["p"]["multi_match"] == ["rows"]
    out, why = add_planned_element(_inv(), "p", "one", "#one")
    assert not why and "multi_match" not in out["pages"]["p"]
    out, why = add_planned_page(_inv(), "q", "/q", {"items": ".item", "title": "h2"},
                                ["Q"], families=["items"])
    assert not why and out["pages"]["q"]["multi_match"] == ["items"]
    _out, why = add_planned_page(_inv(), "q", "/q", {"title": "h2"}, ["Q"], families=["nope"])
    assert "--family names no element" in why


def test_a_declared_planned_family_with_several_matches_is_confirmed():
    from inventory_tools.introspect import diff_page
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_family={"rows"}, declared_planned={"rows"})
    assert [x["element"] for x in d["planned_live"]] == ["rows"] and not d["ambiguous"]
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_planned={"rows"})
    assert not d["planned_live"] and d["ambiguous"], "undeclared: ambiguous, never confirmed"


def test_the_script_takes_family():
    from scripts.plan_inventory import main
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main(["page", "--page", "zz_demo", "--url", "/zz_demo", "--component", "Z",
                     "--element", "rows=ul > li", "--family", "rows", "--dry-run"]) == 0
    assert '"multi_match": [\n    "rows"' in buf.getvalue()


# ── a test case about the prompt is sent back ───────────────────────────

def _case(title, *expected):
    from core.schemas import TestCase, TestStep
    return TestCase(title=title, description="d", expected_outcome="done", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)])


@pytest.mark.parametrize("title, expected", [
    ("[Negative] The list page and its search are not defined in the Application Under Test",
     "the page opens"),
    ("[Negative] Search", "the search box is not described in the application context"),
    ("[Negative] Search", "the filter is not present in the app notes"),
])
def test_a_test_case_about_the_prompt_is_refused(title, expected):
    from core.test_case_rules import test_case_problems
    problems = test_case_problems(_case(title, expected))
    assert problems and "tests what the prompt describes" in problems[0]


@pytest.mark.parametrize("expected", [
    "the search box is not present on the page",
    "the product is not available in the inventory",
    "no row for 'Item' is present",
])
def test_absence_on_the_application_is_not_about_the_prompt(expected):
    from core.test_case_rules import test_case_problems
    assert not any("tests what the prompt" in p
                   for p in test_case_problems(_case("[Negative] Gone", expected)))


def test_both_prompts_say_a_new_thing_is_new():
    for name in ("agent1_analyst.md", "agent1_impact_aware.md"):
        text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
        assert "never write a test case stating that something is not defined" in text


# ── a red run still starts the agent again while stories wait ───────────

@pytest.mark.parametrize("name", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_red_run_still_hands_off(name):
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    (job,) = wf["jobs"].values()
    step = next(s for s in job["steps"] if "again while stories wait" in s.get("name", ""))
    assert step["if"].startswith("${{ !cancelled()")
    src = (ROOT / "core" / "handoff.py").read_text(encoding="utf-8")
    assert "the run took none of the stories that waited when it began" in src, \
        "the progress rule is what keeps a red run from looping"


# ── a story that needs a person is handed back, not taken every scan ────

def test_a_partial_set_is_handed_back_with_what_to_do():
    from agents.agent1_analyst import NEEDS_A_PERSON_WHY, STOPPED, hand_back

    class T:
        def __init__(self):
            self.removed, self.comments = [], []

        def remove_label(self, k, label):
            self.removed.append(label)

        def add_comment(self, k, body):
            self.comments.append(body)
    t = T()
    why = NEEDS_A_PERSON_WHY["partial_test_cases"].format(n=1)
    assert hand_back(t, "AB-1", why, {"selection": {"required_labels": ["go"]}}) == ["go"]
    (body,) = t.comments
    assert body.startswith(STOPPED) and "take a place another story waits for" in body
    assert "1 test case(s) are linked" in body and "Add `go` again to retry" in body
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert 'if result.get("status") in _NEEDS_A_PERSON and not args.dry_run:' in src


# ── the impact-aware draft has room to reason and answer ────────────────

def test_the_budget_grows_with_the_approved_cases():
    from agents.agent1_impact import BASE_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS, output_budget
    assert output_budget(0) == BASE_OUTPUT_TOKENS
    assert output_budget(7) > 2 * BASE_OUTPUT_TOKENS > output_budget(1)
    assert output_budget(100) == MAX_OUTPUT_TOKENS
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert "max_output_tokens=output_budget(len(impacted))" in src


def test_an_empty_truncated_answer_is_named_as_reasoning():
    from core.llm_client import truncation_evidence
    lines = truncation_evidence("", {"output_token_details": {"reasoning": 12288}})
    assert "the answer never began" in lines[0] and "12,288 tokens" in lines[1]
    assert "not a loop" in truncation_evidence(None)[1]
