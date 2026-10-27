"""F-31: a story's comments say each thing once - nothing a person reads is lost.

Found on the live board (27 Oct 2026): 41 of SCRUM-187's 71 comments were
`[LLM-USAGE]` / `[LEDGER-RESET]` bookkeeping, every agent run posted its cost
and Agent 5's report repeated all of it as a growing table; Agent 0's report on
a change story carried a second copy of the Impact Review's data; the delta of
a re-analysis, the no-Component note and the prediction outcome were each a
separate comment beside the comment of the same event.

With a tracker that has issue properties and comment editing (the property
ledger):
  * every run's cost is a hidden entry; ONE cost comment per attempt is edited
    in place (nobody notified) - a row per agent, its modes and run count;
  * Agent 5's report carries one line pointing to it, and Agent 0's outcome as
    a line; a re-run on the same commit with the same results posts nothing;
  * the comment ledger (a tracker without them, or `usage_ledger.store:
    comments`) behaves exactly as before.

Run through the REAL JiraClient over the sandbox's fake Jira. Generic names only.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import usage_ledger as ul
from tests.sandbox.fake_jira import FakeJira, jira_client_over

STORY = "SBX-5"


def _usage(calls=1, inp=1000, out=100, cost=0.01):
    return {"llm_calls": calls, "input_tokens": inp, "output_tokens": out,
            "input_cost_usd": cost * 0.8, "output_cost_usd": cost * 0.2,
            "estimated_cost_usd": cost}


@pytest.fixture
def world(monkeypatch):
    fake = FakeJira()
    fake.add("Story", "A shopper pays", key=STORY, labels=["ai-processed"])
    jira = jira_client_over(fake, monkeypatch)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda *a, **k: jira)
    monkeypatch.setattr(ul, "_store_setting", lambda: "auto")
    return fake, jira


def _cost_comments(fake):
    return [c for c in fake.comments.get(STORY, []) if c and "Brought up to date after every" in c]


def _bookkeeping(fake):
    return [c for c in fake.comments.get(STORY, []) if c and (
        c.startswith(ul.USAGE_MARKER) or c.startswith(ul.RESET_MARKER))]


# ── where the ledger lives ───────────────────────────────────────────────────

def test_the_store_follows_the_trackers_capabilities_and_the_setting(world, monkeypatch):
    _fake, jira = world
    assert ul.mode(jira) == "properties"
    monkeypatch.setattr(ul, "_store_setting", lambda: "comments")
    assert ul.mode(jira) == "comments", "the setting forces the original behaviour"
    monkeypatch.setattr(ul, "_store_setting", lambda: "auto")
    from integrations.tracker import Tracker
    protocol_only = MagicMock(spec=[m for m in dir(Tracker) if not m.startswith("_")])
    assert ul.mode(protocol_only) == "comments", "an adapter without the capabilities"
    no_edit = MagicMock(spec=[m for m in dir(Tracker) if not m.startswith("_")]
                        + ["set_property", "get_property", "property_keys"])
    assert ul.mode(no_edit) == "comments", "properties alone are not enough: the one " \
                                           "cost comment must be editable"
    assert ul.mode(None) == "comments"


def test_the_setting_ships_on_auto():
    from core.ops_settings import section
    assert section("usage_ledger")["store"] == "auto"


# ── the cost comment ─────────────────────────────────────────────────────────

def test_each_run_is_hidden_and_one_cost_comment_is_edited_in_place(world):
    fake, jira = world
    runs = [("Agent 1 (Test Designer)", _usage(1, 10953, 1515, 0.092640)),
            ("Agent 2 (Coder, initial)", _usage(4, 126543, 2758, 0.585027)),
            ("Agent 3 (Reviewer)", _usage(1, 20064, 228, 0.106020)),
            ("Agent 5 (Reporter)", _usage(1, 1713, 77, 0.010490)),
            ("Agent 2 (Coder, regenerate)", _usage(4, 131685, 2845, 0.697760)),
            ("Agent 3 (Reviewer)", _usage(1, 19511, 421, 0.108080)),
            ("Agent 2 (Coder, review fix)", _usage(1, 2049, 62, 0.011795)),
            ("Agent 2 (Coder, review fix)", _usage(3, 76053, 988, 0.353306))]
    for agent, usage in runs:
        assert ul.post_usage_to_story(STORY, agent, usage, jira=jira)
    assert _bookkeeping(fake) == [], "no comment per run"
    (body,) = _cost_comments(fake)
    entries = [k for k in fake.properties[STORY] if k.startswith(ul.PROP_USAGE + ".")]
    assert len(entries) == 8, "every run kept, hidden"
    edits = [c for c in fake.calls if c[0] == "update_comment"]
    assert len(edits) == 7 and all(notify is False for *_x, notify in edits), \
        "edited in place after the first run, without notifying watchers"
    # one row per agent, modes and run counts, totals that add up
    assert "|Agent 2 (Coder): initial, regenerate, review fix ×2|4|12|" in body
    assert "|Agent 3 (Reviewer)|2|2|" in body
    assert "|Agent 1 (Test Designer)|1|1|10,953|1,515|$0.0926|" in body
    assert sum(u["llm_calls"] for _a, u in runs) == 16
    assert sum(u["input_tokens"] for _a, u in runs) == 388571
    total = sum(u["estimated_cost_usd"] for _a, u in runs)
    assert round(total, 6) == 1.965118
    assert f"|*Total*|*8*|*16*|*388,571*|*8,894*|*${total:.4f}*|" in body
    assert "Story budget:" in body


def test_the_ledger_reads_the_same_in_both_stores(world, monkeypatch):
    fake, jira = world
    for store in ("auto", "comments"):
        monkeypatch.setattr(ul, "_store_setting", lambda s=store: s)
        fake.comments[STORY], fake.properties[STORY] = [], {}
        ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(2, cost=0.5), jira=jira)
        ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial) (failed)", _usage(3, cost=1.25),
                               jira=jira)
        ledger = ul.story_ledger(STORY, jira)
        assert [(e["agent"], e["calls"]) for e in ledger["entries"]] == [
            ("Agent 1 (Test Designer)", 2), ("Agent 2 (Coder, initial) (failed)", 3)], store
        assert ul.aggregate_entries(ledger["entries"])["total_cost_usd"] == 1.75
        assert ul.has_usage(STORY, jira, ignore_agents=("Agent 1 (Test Designer)",))
        assert not ul.has_usage(STORY, jira, ignore_agents=("Agent 1 (Test Designer)",
                                                            "Agent 2 (Coder, initial)"))


def test_a_new_attempt_closes_the_old_comment_and_opens_a_new_one(world):
    fake, jira = world
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.2), jira=jira)
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=1.0), jira=jira)
    assert ul.post_reset_to_story(STORY, reason="story reprocessed from ai-ready", jira=jira)
    assert _bookkeeping(fake) == [], "no [LEDGER-RESET] comment"
    (old,) = _cost_comments(fake)
    assert "Closed" in old and "a new attempt started (story reprocessed from ai-ready)" in old
    assert "$1.2000" in old, "the closed attempt keeps its figures"
    assert ul.story_ledger(STORY, jira)["entries"] == []
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.3), jira=jira)
    old_again, new = _cost_comments(fake)
    assert old_again == old, "the closed comment is not touched again"
    assert "this attempt, since" in new and "(story reprocessed from ai-ready)" in new
    assert "$0.3000" in new and "$1.2000" not in new


def test_a_story_costed_before_the_switch_keeps_its_comments_until_its_first_reset(world):
    fake, jira = world
    fake.comments[STORY] = [
        ul.format_usage_comment("Agent 1 (Test Designer)", _usage(cost=9.0)),
        ul.format_reset_comment("story reprocessed from ai-ready"),
        ul.format_usage_comment("Agent 1 (Test Designer)", _usage(1, cost=0.25)),
        ul.format_usage_comment("Agent 2 (Coder, initial)", _usage(2, cost=0.75))]
    ul.post_usage_to_story(STORY, "Agent 3 (Reviewer)", _usage(1, cost=0.5), jira=jira)
    ledger = ul.story_ledger(STORY, jira)
    assert [e["agent"] for e in ledger["entries"]] == [
        "Agent 1 (Test Designer)", "Agent 2 (Coder, initial)", "Agent 3 (Reviewer)"]
    assert ul.aggregate_entries(ledger["entries"])["total_cost_usd"] == 1.5
    (body,) = _cost_comments(fake)
    assert "$1.5000" in body and "$9.0000" not in body, "the discarded run stays discarded"
    ul.post_reset_to_story(STORY, reason="again", jira=jira)
    assert ul.story_ledger(STORY, jira)["entries"] == [], \
        "after a property reset the old comments no longer count"


def test_resetting_a_story_costed_before_posts_no_summary_of_its_old_comments(world):
    fake, jira = world
    fake.comments[STORY] = [ul.format_usage_comment("Agent 1 (Test Designer)", _usage(cost=0.5))]
    ul.post_reset_to_story(STORY, reason="story reprocessed from ai-ready", jira=jira)
    assert fake.comments[STORY] == [ul.format_usage_comment("Agent 1 (Test Designer)",
                                                             _usage(cost=0.5))], \
        "the old comment already shows that cost; the reset is hidden data"
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.25), jira=jira)
    (new,) = _cost_comments(fake)
    assert "(story reprocessed from ai-ready)" in new and "$0.2500" in new and "$0.5" not in new


def test_a_deleted_cost_comment_is_posted_again(world):
    fake, jira = world
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.1), jira=jira)
    fake.delete_comment(STORY, "1")                                   # a person deletes it
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=0.2), jira=jira)
    (body,) = _cost_comments(fake)
    assert "$0.3000" in body
    assert fake.properties[STORY][ul.PROP_COMMENT]["ref"].endswith("focusedCommentId=2")


def test_two_runs_finishing_together_both_end_up_in_the_comment(world, monkeypatch):
    fake, jira = world
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=1.0), jira=jira)
    real = jira.update_comment
    once = []

    def edit_while_another_run_records(issue, ref, body):
        real(issue, ref, body)
        if not once:                    # Agent 3 records between Agent 5's read and edit
            once.append(1)
            jira.set_property(STORY, ul._new_key(ul.PROP_USAGE),
                              ul._entry("Agent 3 (Reviewer)", _usage(cost=0.5)))
    monkeypatch.setattr(jira, "update_comment", edit_while_another_run_records)
    ul.post_usage_to_story(STORY, "Agent 5 (Reporter)", _usage(cost=0.25), jira=jira)
    (body,) = _cost_comments(fake)
    assert "Agent 3 (Reviewer)" in body and "$1.7500" in body


def test_bookkeeping_never_fails_a_run(world, monkeypatch):
    _fake, jira = world
    monkeypatch.setattr(jira, "set_property", MagicMock(side_effect=RuntimeError("403")))
    assert ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(), jira=jira) is False
    assert ul.post_reset_to_story(STORY, reason="x", jira=jira) is False


# ── the story budget line (L40) ──────────────────────────────────────────────

def test_a_released_story_is_measured_against_what_it_may_spend(world, monkeypatch):
    fake, jira = world
    from core import spend_budget as sb
    real = sb.section("budget")
    monkeypatch.setattr(sb, "settings", lambda: {**real, "enabled": True, "per_story_usd": 8.0,
                                                 "warn_at": 0.5, "hold_label": "budget-hold"})
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=9.0), jira=jira)
    ul.record_hold(STORY, 9.0, 8.0, jira=jira)
    # held: allowed what it had spent at the hold
    assert sb.allowance(9.0, True, 8.0) == 9.0
    # a person removed the label: one more budget
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, regenerate)", _usage(cost=1.0), jira=jira)
    (body,) = _cost_comments(fake)
    assert "Story budget: $10.00 of $17.00 (59%, budget.per_story_usd, raised after a " \
           "budget hold)." in body, "not 125% of a budget it was allowed past"
    assert round(10.0 / 17.0, 2) == 0.59


def test_without_a_hold_the_budget_line_is_unchanged():
    line = ul.budget_line(2.0, {"enabled": True, "per_story_usd": 8.0, "warn_at": 0.5})
    assert line == "Story budget: $2.00 of $8.00 (25%, budget.per_story_usd)."
    assert ul.budget_line(None, {"enabled": True, "per_story_usd": 8}) == ""
    assert ul.budget_line(1.0, {"enabled": False, "per_story_usd": 8}) == ""


# ── Agent 5 ──────────────────────────────────────────────────────────────────

def _agent5(monkeypatch, fake, jira, *, sha="abc1234", run="1", results=None, calls=None):
    import agents.agent5_reporter as a5
    from core.schemas import JiraCommentDraft, RunReport, TestResult
    results = results or [TestResult(name="test_pay", classname="tests.step_defs.test_pay",
                                     status="passed")]
    monkeypatch.setattr(a5, "parse_junit_xml", lambda p: RunReport(
        total=len(results), passed=sum(r.status == "passed" for r in results),
        failed=sum(r.status == "failed" for r in results), results=results, pr_number=7))
    monkeypatch.setattr(a5, "get_repo_host", lambda: SimpleNamespace(
        get_pr_changed_files=lambda n: [{"filename": "tests/step_defs/test_pay.py"}]))
    monkeypatch.setattr(a5, "load_prompt", lambda: "{run_report_json}")
    monkeypatch.setattr(a5, "get_tracker", lambda *a, **k: jira)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", sha)
    monkeypatch.setenv("GITHUB_RUN_ID", run)
    calls = calls if calls is not None else []

    class LLM:
        def __init__(self, *a, **k):
            pass

        def invoke_structured(self, **k):
            calls.append(1)
            return JiraCommentDraft(title="All passed", body_markdown="All 1 tests passed.")
    monkeypatch.setattr(a5, "LLMClient", LLM)
    import core.impact_results as ir
    monkeypatch.setattr(ir, "post_owner_results", lambda *a, **k: {})
    return a5.run(STORY, __import__("pathlib").Path("."), cli_pr=7)


def _reports(fake):
    return [c for c in fake.comments.get(STORY, []) if c and "Posted automatically by Agent 5" in c]


def test_agent5s_report_points_to_the_cost_comment_instead_of_repeating_it(world, monkeypatch):
    fake, jira = world
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(4, cost=0.5), jira=jira)
    result = _agent5(monkeypatch, fake, jira)
    assert result["status"] == "comment_posted"
    (report,) = _reports(fake)
    assert "Model cost for this story so far:" in report and "the cost comment" in report
    assert "End-to-end LLM usage" not in report and "|Agent run|" not in report.replace(" ", "")
    assert _bookkeeping(fake) == []
    (cost,) = _cost_comments(fake)
    assert "Agent 5 (Reporter)" in cost, "Agent 5's own run reaches the cost comment"


def test_with_the_comment_ledger_agent5s_report_keeps_the_table(world, monkeypatch):
    fake, jira = world
    monkeypatch.setattr(ul, "_store_setting", lambda: "comments")
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(4, cost=0.5), jira=jira)
    _agent5(monkeypatch, fake, jira)
    (report,) = _reports(fake)
    assert "End-to-end LLM usage & cost for this story" in report
    assert len(_bookkeeping(fake)) == 2 and _cost_comments(fake) == []


def test_the_same_commit_with_the_same_results_is_not_reported_again(world, monkeypatch):
    fake, jira = world
    import agents.agent5_reporter as a5
    flakes = []
    monkeypatch.setattr(a5, "record_flakes", lambda t, results, run: flakes.append(run))
    calls = []
    _agent5(monkeypatch, fake, jira, calls=calls)
    again = _agent5(monkeypatch, fake, jira, calls=calls)              # the job re-run
    assert again["status"] == "unchanged_not_reposted"
    assert len(_reports(fake)) == 1 and len(calls) == 1, "no second report, no model call"
    assert len(flakes) == 1, "the same run's flakes are not counted twice"
    _agent5(monkeypatch, fake, jira, run="2", calls=calls)            # tests re-run, same result
    assert len(_reports(fake)) == 1 and flakes[-1].endswith("/runs/2"), \
        "another run that agreed: no report, but its flakes count"
    _agent5(monkeypatch, fake, jira, sha="def5678", calls=calls)      # a new commit
    assert len(_reports(fake)) == 2 and len(calls) == 2


def test_a_different_result_on_the_same_commit_is_reported(world, monkeypatch):
    fake, jira = world
    from core.schemas import TestResult
    _agent5(monkeypatch, fake, jira)
    _agent5(monkeypatch, fake, jira, results=[TestResult(
        name="test_pay", classname="tests.step_defs.test_pay", status="failed",
        failure_message="AssertionError")])
    assert len(_reports(fake)) == 2


def test_a_run_without_a_commit_is_always_reported():
    import agents.agent5_reporter as a5
    from core.schemas import RunReport
    assert a5.report_fingerprint(STORY, RunReport(total=0, passed=0, failed=0, results=[]),
                                 "passed") is None


def test_agent0s_outcome_is_a_line_of_the_report_kept_once(world, monkeypatch):
    fake, jira = world
    import agents.agent0_impact as a0
    import core.impact_results as ir
    result = {"predicted": ["SBX-12"], "actual_changed": ["SBX-12"], "actual_failed": ["SBX-11"],
              "recall": 0.5, "precision": 1.0}
    seen = []

    def measure(tracker, host, story, pr_number, pr_url, results, features_dir, *a, save=True,
                **k):
        seen.append(save)
        return None if a0.outcome_recorded(tracker, story, pr_url) else dict(result)
    monkeypatch.setattr(ir, "record_prediction_outcome", measure)
    _agent5(monkeypatch, fake, jira)
    (report,) = _reports(fake)
    assert "Agent 0's prediction for this pull request:* recall 50%, precision 100%" in report
    assert "SBX-11" in report and "SBX-12" in report
    assert seen == [False], "measured before the report, kept after it"
    assert not [c for c in fake.comments[STORY] if c and c.startswith(a0.OUTCOME)]
    kept = [v for k, v in fake.properties[STORY].items() if k.startswith("agent0.outcome.")]
    assert len(kept) == 1 and kept[0]["recall"] == 0.5
    _agent5(monkeypatch, fake, jira, sha="def5678")                   # the next commit
    assert "Agent 0's prediction" not in _reports(fake)[-1], "once per pull request"


def test_an_outcome_comment_from_before_still_counts_as_recorded(world):
    fake, jira = world
    import agents.agent0_impact as a0
    fake.comments[STORY] = [f"{a0.OUTCOME} pr: u | recall: 1.0 precision: 1.0\n{{}}"]
    assert a0.outcome_recorded(jira, STORY, "u")
    assert not a0.outcome_recorded(jira, STORY, "other")


def test_the_outcome_is_a_comment_with_the_comment_ledger(world, monkeypatch):
    fake, jira = world
    import agents.agent0_impact as a0
    monkeypatch.setattr(ul, "_store_setting", lambda: "comments")
    assert a0.save_outcome(jira, STORY, "u", {"recall": 1.0, "precision": 0.5}) == "comment"
    assert fake.comments[STORY][-1].startswith(f"{a0.OUTCOME} pr: u | recall: 1.0 precision: 0.5")


# ── the tracker layer ────────────────────────────────────────────────────────

def test_properties_are_read_in_one_request_and_comments_edited_quietly(world):
    fake, jira = world
    jira.set_property(STORY, "llm.usage.1.a", {"x": 1})
    jira.set_property(STORY, "other.key", {"y": 2})
    assert jira.properties(STORY, "llm.") == {"llm.usage.1.a": {"x": 1}}
    assert [c for c in fake.calls if c[0] == "get_properties"] == [("get_properties", STORY)]
    url = jira.add_comment(STORY, "first")
    assert jira.update_comment(STORY, url, "second") == url
    assert jira.update_comment(STORY, "1", "third").endswith("focusedCommentId=1")
    assert fake.comments[STORY] == ["third"]
    assert ("update_comment", STORY, "1", False) in fake.calls
    fake.delete_comment(STORY, "1")
    with pytest.raises(LookupError):
        jira.update_comment(STORY, url, "gone")


def test_an_account_that_may_not_edit_quietly_edits_with_the_notification(world):
    fake, jira = world
    fake.quiet_edits_refused = True
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.1), jira=jira)
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=0.2), jira=jira)
    ul.post_usage_to_story(STORY, "Agent 3 (Reviewer)", _usage(cost=0.3), jira=jira)
    assert len(_cost_comments(fake)) == 1 and "$0.6000" in _cost_comments(fake)[0]
    assert [c[3] for c in fake.calls if c[0] == "update_comment"] == [True, True], \
        "refused once, then edits go straight to the notifying form"


def test_a_refused_edit_never_turns_into_a_comment_per_run(world, monkeypatch):
    fake, jira = world
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.1), jira=jira)
    monkeypatch.setattr(jira, "update_comment",
                        MagicMock(side_effect=RuntimeError("HTTP 403: no edit permission")))
    for _ in range(3):
        ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=0.2), jira=jira)
    assert len([c for c in fake.comments[STORY] if c]) == 1
    assert len(ul.story_ledger(STORY, jira)["entries"]) == 4, "the entries are all kept"


def test_a_dry_run_reads_the_ledger_and_writes_nothing(world):
    fake, jira = world
    from core import dry_run
    ul.post_usage_to_story(STORY, "Agent 1 (Test Designer)", _usage(cost=0.1), jira=jira)
    before = (list(fake.comments[STORY]), dict(fake.properties[STORY]))
    recorder = dry_run.tracker(jira)
    assert ul.mode(recorder) == "properties"
    assert len(ul.story_ledger(STORY, recorder)["entries"]) == 1, "reads pass through"
    ul.post_usage_to_story(STORY, "Agent 2 (Coder, initial)", _usage(cost=0.2), jira=recorder)
    assert (fake.comments[STORY], fake.properties[STORY]) == before
    assert {name for name, *_r in recorder.writes} >= {"set_property"}


# ── a whole story, end to end ────────────────────────────────────────────────

def _a_story(jira, monkeypatch, fake):
    """The run sequence of a real story (SCRUM-202 on 11 and 26 Oct): drafted,
    coded, reviewed, reported; regenerated, reviewed, two review fixes, each
    reviewed and reported."""
    import agents.agent5_reporter as a5
    monkeypatch.setattr(a5, "record_flakes", lambda *a, **k: 0)
    post = ul.post_usage_to_story
    post(STORY, "Agent 1 (Test Designer)", _usage(1, cost=0.09), jira=jira)
    post(STORY, "Agent 2 (Coder, initial)", _usage(4, cost=0.59), jira=jira)
    post(STORY, "Agent 3 (Reviewer)", _usage(1, cost=0.11), jira=jira)
    _agent5(monkeypatch, fake, jira, sha="c1", run="1")
    post(STORY, "Agent 2 (Coder, regenerate)", _usage(4, cost=0.70), jira=jira)
    post(STORY, "Agent 3 (Reviewer)", _usage(1, cost=0.11), jira=jira)
    post(STORY, "Agent 2 (Coder, review fix)", _usage(1, cost=0.01), jira=jira)
    _agent5(monkeypatch, fake, jira, sha="c2", run="2")
    post(STORY, "Agent 2 (Coder, review fix)", _usage(3, cost=0.35), jira=jira)
    post(STORY, "Agent 3 (Reviewer)", _usage(1, cost=0.10), jira=jira)
    _agent5(monkeypatch, fake, jira, sha="c3", run="3")
    _agent5(monkeypatch, fake, jira, sha="c3", run="3")               # the job re-run


def test_a_whole_story_says_each_thing_once(world, monkeypatch):
    fake, jira = world
    _a_story(jira, monkeypatch, fake)
    comments = [c for c in fake.comments[STORY] if c]
    assert len(comments) == 4, "three reports and one cost comment"
    assert len(_reports(fake)) == 3 and len(_cost_comments(fake)) == 1
    (cost,) = _cost_comments(fake)
    assert "|*Total*|*11*|" in cost, "every run counted: 8 agent runs and 3 reports"
    assert "|Agent 5 (Reporter)|3|" in cost


def test_the_same_story_with_the_comment_ledger_is_unchanged(world, monkeypatch):
    fake, jira = world
    monkeypatch.setattr(ul, "_store_setting", lambda: "comments")
    _a_story(jira, monkeypatch, fake)
    # as SCRUM-202 has today (14 comments), plus the job re-run reported again
    assert len(_bookkeeping(fake)) == 12 and len(_reports(fake)) == 4
    assert len([c for c in fake.comments[STORY] if c]) == 16
