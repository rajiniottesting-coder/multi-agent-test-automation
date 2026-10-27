"""F-24: model spend budgets per story and per day, checked before every call.

Before: nothing limited spend. A looping story or a busy day ran until the
provider key's own budget was exhausted (twice), and then every agent stopped,
reviews of unrelated pull requests included.

Now core/spend_budget.py is asked before EVERY model call
(LLMClient._call_with_quota_check). Over `budget.per_story_usd` the story is
held (label + one comment; removing the label allows one more budget); over
`budget.per_day_usd` - counted from every process's recorded spend on the
pipeline health issue - a health alert opens and scans stop until the day ends.
The stop is a BaseException so no `except Exception` recovery path swallows it.

Sandbox: the real JiraClient over a fake Jira; model calls are simulated by
adding usage to the real counters (input price $1 per 1M tokens, so 1,000,000
tokens = $1). Generic names only.
"""
import datetime as dt
import sys
from types import SimpleNamespace

import pytest

from core import llm_client
from core import pipeline_health as ph
from core import spend_budget as sb
from core import usage_ledger as ul
from tests.sandbox.fake_jira import FakeJira, jira_client_over

STORY = "SBX-40"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("PIPELINE_BUDGET", "on")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "1")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "0")
    sb.reset()
    ph.reset_cache()
    llm_client.reset_usage()
    llm_client._lifetime.reset()
    yield
    sb.reset()
    ph.reset_cache()
    llm_client.reset_usage()
    llm_client._lifetime.reset()


@pytest.fixture(params=["comments", "auto"])
def world(monkeypatch, request):
    """Both ledger stores (F-31): [LLM-USAGE] comments, and issue properties."""
    monkeypatch.setattr(ul, "_store_setting", lambda: request.param)
    fake = FakeJira()
    fake.add("Story", "A shopper pays", key=STORY, labels=["ai-processed", "human-approved"])
    jira = jira_client_over(fake, monkeypatch)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda *a, **k: jira)
    return fake, jira


def spend(usd: float):
    llm_client._tracker.add(int(round(usd * 1_000_000)), 0)


def _limits(monkeypatch, **over):
    real = sb.section("budget")
    monkeypatch.setattr(sb, "settings", lambda: {**real, **over})


def _alerts(fake):
    key = next((k for k, d in fake.issues.items() if "pipeline-health" in d["labels"]), None)
    return [c.splitlines()[0] for c in fake.comments.get(key, [])] if key else []


def _today():
    return sb.day_of(dt.datetime.now(dt.timezone.utc))


# ── when it applies ──────────────────────────────────────────

def test_off_in_tests_unless_forced(monkeypatch):
    monkeypatch.delenv("PIPELINE_BUDGET")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert sb.active() is False, "PYTEST_CURRENT_TEST is set: a unit test never enforces"
    monkeypatch.setenv("PIPELINE_BUDGET", "off")
    assert sb.active() is False


def test_disabled_in_config(monkeypatch, world):
    _limits(monkeypatch, enabled=False)
    spend(100)
    sb.check_before_call()


def test_without_pricing_nothing_is_enforced(monkeypatch, world, caplog):
    monkeypatch.delenv("LLM_PRICE_INPUT_PER_1M")
    spend(100)
    sb.check_before_call()
    sb.check_before_call()
    assert caplog.text.count("no budget is enforced") == 1


def test_the_stop_is_not_an_exception():
    stop = sb.BudgetExceeded("day", "x")
    assert not isinstance(stop, Exception)
    with pytest.raises(sb.BudgetExceeded):
        try:
            raise stop
        except Exception:                              # a recovery path must not swallow it
            pytest.fail("caught by except Exception")


# ── the day ──────────────────────────────────────────────────

def test_the_day_counts_every_recorded_run_and_this_one(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_day_usd=12.0)
    ph.record(jira, "spend", [_today(), 7_000_000], {})
    ph.record(jira, "spend", [_today(), 3_000_000], {})
    ph.record(jira, "spend", ["20000101", 50_000_000], {})     # another day
    spend(1.5)
    sb.check_before_call()                                    # 7 + 3 + 1.5 = 11.5
    spend(0.5)
    with pytest.raises(sb.BudgetExceeded) as stop:
        sb.check_before_call()                                # 12.0
    assert stop.value.scope == "day" and "per_day_usd" in str(stop.value)
    assert f"[health:open] budget-day-{_today()}" in _alerts(fake)
    with pytest.raises(sb.BudgetExceeded):
        sb.check_before_call()
    assert _alerts(fake).count(f"[health:open] budget-day-{_today()}") == 1


def test_the_warning_opens_once(monkeypatch, world):
    fake, _ = world
    _limits(monkeypatch, per_day_usd=10.0, warn_at=0.5)
    spend(4.9)
    sb.check_before_call()
    assert _alerts(fake) == []
    spend(0.2)
    sb.check_before_call()
    sb.check_before_call()
    assert _alerts(fake) == [f"[health:open] budget-warn-{_today()}"]


def test_an_unreadable_day_counts_this_run_only(monkeypatch, caplog):
    tracker = SimpleNamespace(find_stories_to_process=lambda *a, **k: [{"key": "X-1"}],
                              get_comments=lambda k: [], add_comment=lambda *a: None)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda *a, **k: tracker)
    _limits(monkeypatch, per_day_usd=2.0)
    spend(1.0)
    sb.check_before_call()
    assert "only this run's own spend" in caplog.text
    spend(1.0)
    with pytest.raises(sb.BudgetExceeded):
        sb.check_before_call()


def test_a_run_records_its_spend_once_and_then_only_more(world):
    fake, jira = world
    spend(0.25)
    sb.check_before_call()
    assert sb.record_run() is True
    keys = ph.record_keys(jira, "spend")
    assert len(keys) == 1 and keys[0].startswith(f"spend.{_today()}.250000.")
    assert sb.record_run() is False, "nothing new"
    spend(0.5)
    assert sb.record_run() is True
    assert sb.day_spent(jira, _today()) == pytest.approx(0.75)


def test_recording_is_off_when_inactive_and_never_raises(monkeypatch, world):
    spend(1)
    monkeypatch.setenv("PIPELINE_BUDGET", "off")
    assert sb.record_run() is False
    monkeypatch.setenv("PIPELINE_BUDGET", "on")
    monkeypatch.setattr(ph, "record", lambda *a: (_ for _ in ()).throw(OSError("down")))
    assert sb.record_run() is False


def test_when_the_day_turns_the_earlier_spend_stays_with_yesterday(monkeypatch, world):
    _limits(monkeypatch, per_day_usd=5.0)
    spend(4.0)
    sb.check_before_call()
    sb._state["day"] = "20000101"                           # the process began yesterday
    spend(2.0)
    sb.check_before_call()                                  # the day turned: yesterday keeps 6
    assert sb._state["day_base"] == pytest.approx(6.0)
    spend(4.9)
    sb.check_before_call()
    spend(0.2)
    with pytest.raises(sb.BudgetExceeded):
        sb.check_before_call()


def test_reset_records_nothing_at_exit(world):
    spend(1)
    sb.check_before_call()
    assert sb._state["registered"]
    import atexit
    registered = []
    monkey = atexit.unregister
    try:
        atexit.unregister = lambda fn: registered.append(fn)
        sb.reset()
    finally:
        atexit.unregister = monkey
    assert registered == [sb.record_run] and not sb._state["registered"]


def test_an_unknown_time_zone_counts_in_utc(monkeypatch, caplog):
    _limits(monkeypatch, timezone="Mars/Olympus")
    now = dt.datetime(2026, 10, 27, 23, 30, tzinfo=dt.timezone.utc)
    assert sb.day_of(now) == "20261027" and "is unknown" in caplog.text
    _limits(monkeypatch, timezone="Asia/Kolkata")
    assert sb.day_of(now) == "20261028"


# ── the story ────────────────────────────────────────────────

def _ledger(fake, usd):
    fake.comments.setdefault(STORY, []).append(ul.format_usage_comment(
        "Agent 2 (Coder, initial)", {"llm_calls": 1, "input_tokens": 1, "output_tokens": 1,
                                     "estimated_cost_usd": usd}))


def _story_run(jira, usd):
    with ul.story_usage(STORY, "Agent 2 (Coder, regenerate)", jira=jira):
        spend(usd)
        sb.check_before_call()


def test_a_story_over_its_budget_is_held_once(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    _ledger(fake, 5.0)
    _story_run(jira, 2.0)                                    # 7.0: fine
    with pytest.raises(sb.BudgetExceeded) as stop:
        _story_run(jira, 1.5)                                # 7.0 + 1.5
    assert stop.value.scope == "story" and stop.value.story == STORY
    assert "budget-hold" in fake.issues[STORY]["labels"]
    holds = [c for c in fake.comments[STORY] if c.startswith(sb.HOLD_MARKER)]
    assert len(holds) == 1 and "remove the label" in holds[0]
    assert ("Agent 2 (Coder, regenerate) (failed)", 1) in [
        (e["agent"], e["calls"]) for e in ul.story_ledger(STORY, jira)["entries"]], \
        "the stopped run's cost is still on the ledger"
    with pytest.raises(sb.BudgetExceeded):
        _story_run(jira, 0.0)                                # still held: stopped at once
    assert len([c for c in fake.comments[STORY] if c.startswith(sb.HOLD_MARKER)]) == 1


def test_removing_the_label_allows_one_more_budget(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    _ledger(fake, 9.0)
    with pytest.raises(sb.BudgetExceeded):
        _story_run(jira, 0.0)
    fake.issues[STORY]["labels"].remove("budget-hold")
    _story_run(jira, 7.0)                                    # 9 + 7 = 16 < 9 + 8
    with pytest.raises(sb.BudgetExceeded):
        _story_run(jira, 1.0)                                # 17 >= 17
    assert len([c for c in fake.comments[STORY] if c.startswith(sb.HOLD_MARKER)]) == 2


def test_a_hold_before_the_ledger_reset_is_forgotten(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    fake.comments[STORY] = [f"{sb.HOLD_MARKER} spent: 9.0000 limit: 8.00", ul.format_reset_comment("x")]
    sb.begin_story(STORY, jira)
    assert sb._state["story"]["allowance"] == 8.0 and sb._state["story"]["prior"] == 0.0


def test_no_story_no_story_limit(monkeypatch, world):
    _limits(monkeypatch, per_story_usd=1.0, per_day_usd=1000.0)
    spend(5)
    sb.check_before_call()


def test_a_dry_run_neither_counts_the_story_nor_holds_it(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_story_usd=1.0, per_day_usd=1000.0)
    _ledger(fake, 5.0)
    with ul.story_usage(STORY, "Agent X", jira=jira, dry_run=True):
        spend(1)
        sb.check_before_call()
    assert "budget-hold" not in fake.issues[STORY]["labels"]


def test_the_story_is_forgotten_after_its_run(monkeypatch, world):
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    _story_run(jira, 0.1)
    assert sb._state["story"] is None


# ── the call itself ──────────────────────────────────────────

def test_the_check_comes_before_the_call(monkeypatch):
    called = []
    monkeypatch.setattr(sb, "check_before_call",
                        lambda: (_ for _ in ()).throw(sb.BudgetExceeded("day", "stop")))
    client = llm_client.LLMClient.__new__(llm_client.LLMClient)
    client.model_name = "m"
    with pytest.raises(sb.BudgetExceeded):
        client._call_with_quota_check(lambda: called.append(1))
    assert called == [], "nothing is spent"


def test_the_lifetime_counter_survives_the_per_story_reset():
    spend(1.0)
    llm_client.reset_usage()
    spend(0.5)
    assert llm_client.lifetime_cost_usd() == pytest.approx(1.5)
    assert llm_client.get_usage_summary()["estimated_cost_usd"] == pytest.approx(0.5)


def test_an_uncaught_stop_prints_its_reason(capsys):
    sb._install_excepthook()
    sys.excepthook(sb.BudgetExceeded, sb.BudgetExceeded("day", "Daily model budget reached"), None)
    assert "[BUDGET] Daily model budget reached" in capsys.readouterr().err


# ── the agents ───────────────────────────────────────────────

def _scan_agent2(monkeypatch, run):
    import agents.agent2_coder as a2
    tracker = SimpleNamespace(find_stories_to_process=lambda *a, **k: [])
    stories = iter([[{"key": "A-1"}, {"key": "A-2"}], [], []])
    tracker.find_stories_to_process = lambda *a, **k: next(stories)
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "run", run)
    summary = []
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: summary.extend(r))
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    code = 0
    try:
        a2.main()
    except SystemExit as e:
        code = e.code or 0
    return {r["story_id"]: r["status"] for r in summary}, code


def test_agent2_scan_stops_for_the_day_without_failing(monkeypatch):
    def run(key, **kw):
        if key == "A-2":
            raise sb.BudgetExceeded("day", "day over")
        return {"story_id": key, "status": "pr_opened"}
    statuses, code = _scan_agent2(monkeypatch, run)
    assert statuses == {"A-1": "pr_opened", "A-2": "deferred"} and code == 0


def test_agent2_scan_reports_a_held_story_and_goes_on(monkeypatch):
    def run(key, **kw):
        if key == "A-1":
            raise sb.BudgetExceeded("story", "held", story="A-1")
        return {"story_id": key, "status": "pr_opened"}
    statuses, code = _scan_agent2(monkeypatch, run)
    assert statuses == {"A-1": "failed", "A-2": "pr_opened"} and code == 1


def test_agent1_scan_stops_for_the_day(monkeypatch, capsys):
    import agents.agent1_analyst as a1
    tracker = SimpleNamespace(find_stories_to_process=lambda *a, **k: [
        {"key": "A-1", "status": "To Do", "summary": "s"},
        {"key": "A-2", "status": "To Do", "summary": "s"}])
    monkeypatch.setattr(a1, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a1, "validate_required_env", lambda *a: None)
    ran = []

    def run(key, dry_run=False):
        ran.append(key)
        raise sb.BudgetExceeded("day", "day over")
    monkeypatch.setattr(a1, "run", run)
    monkeypatch.setattr(sys, "argv", ["agent1", "--scan"])
    try:
        a1.main()
    except SystemExit as e:
        assert not e.code
    assert ran == ["A-1"] and "[BUDGET] day over" in capsys.readouterr().out


def test_agent0_scan_stops_for_the_day_before_hand_overs(monkeypatch):
    import agents.agent0_impact as a0
    tracker = SimpleNamespace(find_stories_to_process=lambda *a, **k: [{"key": "A-1"}, {"key": "A-2"}])
    monkeypatch.setattr(a0, "analyse_and_publish",
                        lambda *a, **k: (_ for _ in ()).throw(sb.BudgetExceeded("day", "day over")))
    monkeypatch.setattr(a0, "hand_over_decided", lambda *a, **k: pytest.fail("not reached"))
    out = a0.scan(tracker, None, None, {"enabled": True, "shadow_mode": False, "selection": {}},
                  root=".")
    assert out == [{"story": "A-1", "action": "budget", "error": "day over"}]


def test_agent3_says_why_nothing_was_reviewed():
    from agents.agent3_reviewer import failure_note
    note = failure_note(sb.BudgetExceeded("day", "Daily model budget reached: $12.10 of $12.00"))
    assert "Not reviewed: model budget reached" in note and "$12.10 of $12.00" in note
    assert "Re-run the job once the budget allows it" in note


def test_agent5_reports_without_the_model(monkeypatch, tmp_path, capsys):
    import agents.agent5_reporter as a5
    from core.schemas import RunReport, TestResult as Result
    report = RunReport(total=2, passed=1, failed=1, results=[
        Result(name="test_a", classname="tests.step_defs.test_m", status="passed"),
        Result(name="test_b", classname="tests.step_defs.test_m", status="failed",
               failure_message="AssertionError: got 2")], pr_number=7)
    monkeypatch.setattr(a5, "parse_junit_xml", lambda p: report)
    monkeypatch.setattr(a5, "get_repo_host", lambda: SimpleNamespace(
        get_pr_changed_files=lambda n: []))
    monkeypatch.setattr(a5, "load_prompt", lambda: "{run_report_json}")

    class LLM:
        def __init__(self, *a, **k):
            pass

        def invoke_structured(self, **k):
            raise sb.BudgetExceeded("day", "Daily model budget reached")
    monkeypatch.setattr(a5, "LLMClient", LLM)
    result = a5.run("S-1", tmp_path, dry_run=True)
    out = capsys.readouterr().out
    assert result["title"] == "1 of 2 tests failed"
    assert "`test_m::test_b`" in out and "AssertionError: got 2" in out   # dry run prints ASCII
    assert "Summary written without the model: Daily model budget reached" in out


def test_agent5_fallback_all_passed():
    import agents.agent5_reporter as a5
    from core.schemas import RunReport
    d = a5.fallback_draft(RunReport(total=3, passed=3, failed=0, duration_seconds=2), Exception("x"))
    assert d.body_markdown.startswith("✅ **All 3 tests passed** in 2.00s")


def test_review_fix_stops_before_pushing(monkeypatch):
    from tests.unit import test_agent2_review_fix as t
    import agents.agent2_review_fix as rf
    monkeypatch.setattr(rf, "settings", lambda: {"enabled": True, "command": "/fix",
                                                 "branch_prefix": "auto/", "max_files": 6})

    class StoppedLLM(t.FakeLLM):
        def invoke_structured(self, **k):
            raise sb.BudgetExceeded("day", "Daily model budget reached")
    host = t.FakeHost(inline=[t._inline()])
    out = t._run(host, StoppedLLM([]))
    assert out["status"] == "nothing_to_fix" and host.pushed == {}
    assert "Not attempted - the model budget is reached" in host.comments[-1]


# ── configuration and the report line ───────────────────────

def test_every_agent_selection_skips_a_held_story():
    import yaml
    from config.paths import CONFIG_YAML
    cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))
    hold = cfg["budget"]["hold_label"]
    selections = [(name, key, block) for name, agent in cfg["agents"].items()
                  if isinstance(agent, dict) for key, block in agent.items()
                  if isinstance(block, dict) and "required_labels" in block]
    assert len(selections) >= 5
    for name, key, block in selections:
        assert hold in block.get("excluded_labels", []), f"{name}.{key} would pick a held story"


def test_the_budget_block_is_shipped():
    import yaml
    from config.paths import CONFIG_YAML
    from core.ops_settings import DEFAULTS
    shipped = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))["budget"]
    assert set(shipped) == set(DEFAULTS["budget"])
    assert (shipped["per_story_usd"], shipped["per_day_usd"], shipped["warn_at"]) == (8, 12, 0.5)


def test_agent5_cost_line():
    agg = ul.aggregate_story_usage([ul.format_usage_comment("A", {
        "llm_calls": 1, "input_tokens": 1, "output_tokens": 1, "estimated_cost_usd": 4.4})])
    line = ul.format_e2e_section(agg, {"enabled": True, "per_story_usd": 8, "warn_at": 0.5})
    assert "⚠ Story budget: $4.40 of $8.00 (55%" in line
    assert "⚠" not in ul.format_e2e_section(agg, {"enabled": True, "per_story_usd": 10,
                                                   "warn_at": 0.5})
    assert "Story budget" not in ul.format_e2e_section(agg, {"enabled": False})
    assert ul.format_e2e_section(agg) == ul.format_e2e_section(agg, None)


# ── the health issue ─────────────────────────────────────────

def test_the_health_view_and_housekeeping(monkeypatch, world):
    from scripts import pipeline_health_check as script
    fake, jira = world
    now = dt.datetime.now(dt.timezone.utc)
    ph.record(jira, "spend", [_today(), 2_500_000], {})
    ph.record(jira, "spend", ["20000101", 1], {})
    ph.raise_alert(jira, "budget-day-20000101", "old day")
    ph.raise_alert(jira, f"budget-warn-{_today()}", "today")
    script.housekeeping(jira, now)
    assert set(ph.open_alerts(jira)) == {f"budget-warn-{_today()}"}
    assert [k.split(".")[1] for k in ph.record_keys(jira, "spend")] == [_today()]
    ph.refresh_view(jira, now)
    assert "$2.50 of the $12.00 daily budget" in fake.issues[ph.issue_key(jira)]["description"]


def test_the_health_checks_model_probe_is_not_a_credential_alert_when_the_budget_stops_it(
        monkeypatch):
    from core import health_checks as hc

    class Client:
        def __init__(self, *a, **k):
            self.llm = SimpleNamespace(invoke=lambda m: None)

        def _call_with_quota_check(self, fn, *a):
            raise sb.BudgetExceeded("day", "day over")
    monkeypatch.setattr(llm_client, "LLMClient", Client)
    assert hc.check_model("completion") is None


def test_a_ledger_reset_restarts_the_story_budget(monkeypatch, world):
    """Agent 1 re-processes a story: the reset is posted INSIDE its run, after
    the budget was read - the discarded run's cost must stop counting there."""
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    _ledger(fake, 7.5)
    with ul.story_usage(STORY, "Agent 1 (Test Designer)", jira=jira):
        ul.post_reset_to_story(STORY, "story reprocessed", jira=jira)
        spend(5.0)
        sb.check_before_call()                           # 5 of a fresh 8, not 12.5
    assert "budget-hold" not in fake.issues[STORY]["labels"]


def test_a_held_story_is_not_selected_again_until_the_label_goes(monkeypatch, world):
    """Through the real adapter's query: every Agent 2 selection skips it."""
    from agents.agent2_coder import load_agent_config
    fake, jira = world
    _limits(monkeypatch, per_story_usd=8.0, per_day_usd=1000.0)
    _ledger(fake, 9.0)
    selection = load_agent_config()["selection"]
    picked = lambda: [s["key"] for s in jira.find_stories_to_process(selection, max_results=50)]
    assert STORY in picked()
    with pytest.raises(sb.BudgetExceeded):
        _story_run(jira, 0.0)
    assert STORY not in picked()
    fake.issues[STORY]["labels"].remove("budget-hold")
    assert STORY in picked()
