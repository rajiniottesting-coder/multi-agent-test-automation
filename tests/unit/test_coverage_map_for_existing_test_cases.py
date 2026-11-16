"""Coverage maps for stories whose test cases already exist (C4).

A story whose test cases were written before Agent 1 posted coverage maps,
or by a person - every story of a project that adopts the framework with its
tests already written - had no map, so the traceability matrix said "not
mapped" for each of its criteria. Agent 1's coverage-only mode maps each
criterion to the existing test cases (nothing drafted), checks the map as a
draft's is, and posts the `[agent1:coverage]` comment the reports read. The
reports also read the map inside Agent 1's impact-aware draft (change
stories) and match a cited test case by its key.

Generic names only (PRJ-*): no application is named here.
"""
from types import SimpleNamespace

import pytest
import yaml

from agents import agent1_coverage as cov
from core import acceptance_coverage as ac
from core import report_data as rd
from core.schemas import CoverageMap, CriterionCoverage, TestCase, TestStep

STORY = {"key": "PRJ-1", "summary": "Remove the gift-wrap option", "status": "Done",
         "labels": [], "description": (
             "As a shopper I want a simpler checkout.\n\nAcceptance criteria:\n"
             "1. The checkout page shows the order total\n"
             "2. The gift-wrap option is no longer shown on the checkout page\n"
             "3. A coupon code can be applied")}


def _desc(*steps):
    from integrations.jira_client import JiraClient
    return JiraClient._format_test_case_description(TestCase(
        title="t", description="d", expected_outcome="o",
        steps=[TestStep(step_number=i + 1, action=a, expected_result=e)
               for i, (a, e) in enumerate(steps)]))


CASES = [
    {"key": "PRJ-11", "summary": "[Positive] Checkout shows the total",
     "description": _desc(("Open the checkout page", "The order total is shown"))},
    {"key": "PRJ-12", "summary": "[Negative] Gift wrap is gone",
     "description": _desc(("Open the checkout page", "The page is shown"),
                          ("Look for the gift-wrap option",
                           "No gift-wrap option is present on the page"))},
]


class Tracker:
    def __init__(self, comments=(), labels=(), cases=CASES):
        self.comments, self.cases, self.posted = list(comments), list(cases), []
        self.story = dict(STORY, labels=list(labels))

    def get_story(self, key):
        if key == "PRJ-1":
            return self.story
        return {"key": key, "summary": f"Marked case {key}", "description": "The total is shown"}

    def get_linked_test_cases(self, key):
        return self.cases

    def get_comments(self, key):
        return self.comments

    def get_parent_story_key(self, key):
        return "PRJ-1"

    def add_comment(self, key, body):
        self.posted.append((key, body))


class LLM:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        assert output_schema is CoverageMap
        self.prompts.append(user_prompt)
        return self.answers.pop(0)


def _map(*entries):
    return CoverageMap(coverage=[CriterionCoverage(criterion=c, covered_by=list(k), how_verified=h)
                                 for c, k, h in entries])


GOOD = _map(("AC1", ["PRJ-11"], "step 1 asserts the total"),
            ("AC2", ["PRJ-12"], "step 2 asserts no gift-wrap option"),
            ("AC3", [], "no test case applies a coupon"))


@pytest.fixture(autouse=True)
def quiet_ledger(monkeypatch):
    """No usage bookkeeping against a real tracker in these tests."""
    import contextlib
    monkeypatch.setattr("core.usage_ledger.story_usage",
                        lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: True)
    monkeypatch.setattr("core.llm_client.log_usage_summary", lambda ctx: {"llm_calls": 1})


def _run(tracker, llm, **kw):
    return cov.run(tracker, lambda: llm, "PRJ-1", **kw)


# ── mapping a story ────────────────────────────────────────────────────

def test_a_story_is_mapped_to_its_existing_test_cases_and_the_map_posted():
    t, llm = Tracker(), LLM(GOOD)
    r = _run(t, llm)
    assert (r["status"], r["criteria"], r["test_cases"], r["gaps"]) == ("mapped", 3, 2, ["AC3"])
    (key, body), = t.posted
    assert key == "PRJ-1" and body.startswith("[agent1:coverage]")   # no renderer here
    assert "AC1 The checkout page shows the order total -> PRJ-11 [Positive] Checkout" in body
    assert "AC3 A coupon code can be applied -> (none)" in body
    assert "Not verified by any existing test case: AC3" in body
    prompt = llm.prompts[0]
    assert "### PRJ-12 - [Negative] Gift wrap is gone" in prompt
    assert "No gift-wrap option is present on the page" in prompt, "the steps as written"
    assert "- AC2: The gift-wrap option is no longer shown" in prompt and "REMOVED" in prompt
    assert "Do NOT write, change, merge or\ninvent test cases" in prompt
    # 16 Nov 2026, the first live dry run: "none of this requires signing in"
    # was a gap on two stories and covered on a third, though each one's test
    # cases start signed out and check the outcome. One rule for all.
    assert "works IN A STATE or WITHOUT a condition" in prompt
    assert "Judge the same criterion the same way on every story" in prompt


def test_the_reports_read_the_posted_map_per_criterion():
    t = Tracker()
    _run(t, LLM(GOOD))
    body = t.posted[0][1]
    assert ac.coverage_comment(["older", body]) == body
    m = rd.coverage_map(body, ["AC1", "AC2", "AC3"], CASES)
    assert m == {"AC1": ["PRJ-11"], "AC2": ["PRJ-12"], "AC3": []}
    assert rd.unmatched_citations(body, ["AC1", "AC2", "AC3"], CASES) == set()


def test_a_removal_cited_without_a_step_proving_it_becomes_a_gap():
    weak = _map(("AC1", ["PRJ-11"], "total"), ("AC2", ["PRJ-11"], "opens the page"),
                ("AC3", [], "none"))
    t = Tracker()
    r = _run(t, LLM(weak))
    assert r["status"] == "mapped" and r["gaps"] == ["AC2", "AC3"]
    line = next(x for x in t.posted[0][1].splitlines() if "AC2" in x)
    assert "-> (none) | no cited test case has the step that proves it" in line


def test_a_wrong_answer_is_sent_back_once():
    missing = _map(("AC1", ["PRJ-11"], "total"), ("AC2", ["PRJ-99"], "?"))
    llm = LLM(missing, GOOD)
    r = _run(Tracker(), llm)
    assert r["status"] == "mapped" and len(llm.prompts) == 2
    assert "AC2 cites PRJ-99, which is not one of this story's test cases" in llm.prompts[1]
    assert "AC3 is not in your answer" in llm.prompts[1]


def test_twice_wrong_posts_nothing():
    bad = _map(("AC1", ["PRJ-99"], "?"))
    t = Tracker()
    r = _run(t, LLM(bad, bad))
    assert r["status"] == "rejected" and t.posted == [] and r["problems"]


def test_a_dry_run_posts_nothing():
    t = Tracker()
    r = _run(t, LLM(GOOD), dry_run=True)
    assert r["status"] == "mapped" and t.posted == [] and "AC1" in r["comment"]


# ── what is left alone ────────────────────────────────────────────────

@pytest.mark.parametrize("tracker,why", [
    (Tracker(comments=["\\[agent1:coverage\\] earlier\n- AC1 x -> y"]), "it has a coverage map"),
    (Tracker(comments=["[agent1:impact-draft] d\n\n*Acceptance criteria and what verifies "
                       "them*\n- AC1 x -> PRJ-11"]), "it has a coverage map"),
    (Tracker(labels=["ai-skip"]), "labelled ai-skip"),
], ids=["mapped", "mapped-in-impact-draft", "ai-skip"])
def test_a_story_is_skipped_without_a_model_call(tracker, why):
    r = _run(tracker, LLM())
    assert r["status"] == "skipped" and why in r["why"] and tracker.posted == []


def test_force_maps_a_mapped_story_again():
    t = Tracker(comments=["\\[agent1:coverage\\] earlier\n- AC1 x -> y"])
    assert _run(t, LLM(GOOD), force=True)["status"] == "mapped"


def test_a_throwaway_story_is_skipped(monkeypatch):
    monkeypatch.setattr("core.ops_settings.section",
                        lambda name: {"delete_label": "test-data"} if name == "cleanup" else {})
    r = _run(Tracker(labels=["test-data"]), LLM())
    assert r["status"] == "skipped" and "throw-away" in r["why"]


def test_no_test_cases_or_no_criteria_spend_nothing():
    assert _run(Tracker(cases=[]), LLM())["status"] == "no_test_cases"
    t = Tracker()
    t.story = dict(STORY, description="A story with no list.")
    assert _run(t, LLM())["status"] == "no_criteria" and t.posted == []


# ── the stories and their test cases ─────────────────────────────────

def test_stories_and_test_cases_are_the_matrixs_own(tmp_path):
    f = tmp_path / "features"
    f.mkdir()
    (f / "m.feature").write_text(
        "Feature: M\n\n  # JIRA: PRJ-11 (hash: 1234abcd) owner: PRJ-1\n  Scenario: A\n    Given x\n\n"
        "  # JIRA: PRJ-13 (hash: 1234abcd)\n  Scenario: B\n    Given y\n", encoding="utf-8")
    owners = cov.stories_with_test_cases(Tracker(), f)
    assert owners == {"PRJ-1": {"PRJ-11", "PRJ-13"}}, "marker owner, else the tracker's parent"
    cases = cov.story_test_cases(Tracker(), "PRJ-1", owners["PRJ-1"])
    assert [c["key"] for c in cases] == ["PRJ-11", "PRJ-12", "PRJ-13"]
    assert cases[-1]["summary"] == "Marked case PRJ-13", "a marked case the tracker no longer links"


# ── reading test cases and maps back ──────────────────────────────────

def test_a_test_case_is_read_back_step_by_step():
    w = ac.written_case("PRJ-12", CASES[1]["summary"], CASES[1]["description"])
    assert [(s.action, s.expected_result) for s in w.steps] == [
        ("Open the checkout page", "The page is shown"),
        ("Look for the gift-wrap option", "No gift-wrap option is present on the page")]
    assert ac.evidence_steps(w, ac.STRICT), "its absence step counts"


def test_a_test_case_a_person_wrote_is_read_line_by_line():
    w = ac.written_case("PRJ-20", "Gift wrap", "Go to checkout\nThe gift-wrap option is not shown")
    assert [s.expected_result for s in w.steps] == ["Go to checkout",
                                                    "The gift-wrap option is not shown"]
    assert ac.evidence_steps(w, ac.STRICT)


def test_the_impact_aware_drafts_map_is_read():
    draft = ("[agent1:impact-draft] Impact-aware draft for PRJ-9\n\n*Revised test cases*\n- PRJ-12\n\n"
             "*Acceptance criteria and what verifies them*\n- AC1 Gift wrap is gone -> PRJ-12 | step 2\n"
             "- AC2 Total shown -> New total check\n\n*Close to an existing test - check these*\n- x")
    body = ac.coverage_comment(["\\[agent1:coverage\\] old\n- AC1 a -> b", draft])
    assert body.splitlines() == ["[agent1:coverage] (from the impact-aware draft)",
                                 "- AC1 Gift wrap is gone -> PRJ-12 | step 2",
                                 "- AC2 Total shown -> New total check"]
    assert ac.coverage_comment(["plain", "notes"]) == ""


def test_a_map_citing_keys_matches_own_and_other_stories_test_cases():
    body = "[agent1:coverage] x\n- AC1 a -> PRJ-12 | step\n- AC2 b -> PRJ-40 | revised"
    own = [{"key": "PRJ-12", "summary": "Different title now"}]
    assert rd.coverage_map(body, ["AC1", "AC2"], own) == {"AC1": ["PRJ-12"], "AC2": []}
    assert rd.coverage_map(body, ["AC1", "AC2"], own, other_keys={"PRJ-40"}) == \
        {"AC1": ["PRJ-12"], "AC2": ["PRJ-40"]}
    assert rd.unmatched_citations(body, ["AC1", "AC2"], own, {"PRJ-40"}) == set()
    assert rd.unmatched_citations(body, ["AC1", "AC2"], own) == {"AC2"}


def test_a_map_citing_titles_reads_as_before():
    body = "[agent1:coverage] x\n- AC1 a -> [Positive] Checkout shows the total | ok"
    assert rd.coverage_map(body, ["AC1"], CASES) == {"AC1": ["PRJ-11"]}


# ── the matrix ─────────────────────────────────────────────────────────

def test_the_matrix_shows_a_change_storys_revised_test_case(tmp_path):
    from scripts import build_site as bs
    f = tmp_path / "features"
    f.mkdir()
    (f / "m.feature").write_text(
        "Feature: M\n\n  # JIRA: PRJ-40 (hash: 1234abcd) owner: PRJ-8\n  Scenario: Gift wrap gone\n"
        "    Given x\n\n  # JIRA: PRJ-41 (hash: 1234abcd) owner: PRJ-9\n  Scenario: Own\n"
        "    Given y\n", encoding="utf-8")

    class T(Tracker):
        def get_story(self, key):
            return {"key": key, "summary": f"Story {key}", "status": "Done",
                    "description": "Acceptance criteria:\n1. Gift wrap is gone\n2. Own check"}

        def get_linked_test_cases(self, key):
            return [{"key": "PRJ-41", "summary": "Own check"}] if key == "PRJ-9" else []

        def get_comments(self, key):
            return ([] if key != "PRJ-9" else [
                "[agent1:impact-draft] d\n\n*Acceptance criteria and what verifies them*\n"
                "- AC1 Gift wrap is gone -> PRJ-40 | step 2\n- AC2 Own check -> Own check | ok"])
    test = "tests.step_defs.test_m::test_gift_wrap_gone"
    latest = {test: {"test": test, "test_case": "PRJ-40", "verdict": "passed",
                     "started": "2026-11-14T20:00:00Z"}}
    rows = [r for r in bs.traceability(T(), f, latest, []) if r["story"] == "PRJ-9"]
    by = {(r["criterion"], r["test_case"]): r for r in rows}
    assert set(by) == {("AC1", "PRJ-40"), ("AC2", "PRJ-41")}, "no 'not mapped' rows"
    assert by[("AC1", "PRJ-40")]["test_case_summary"] == "Gift wrap gone"
    assert (by[("AC1", "PRJ-40")]["scenario"], by[("AC1", "PRJ-40")]["result"]) == \
        (test, "passed"), "the revised test case's own scenario and result"


def test_an_unmapped_story_names_the_way_to_map_it():
    stories = [{"key": "PRJ-1", "summary": "s", "status": "Done", "criteria": [("AC1", "x")],
                "test_cases": [{"key": "PRJ-11", "summary": "t"}], "has_coverage_map": False,
                "scenarios": {"PRJ-11": []}}]
    row = rd.traceability_rows(stories, {}, {})[0]
    assert "Agent 1 - Map acceptance coverage" in row["criterion_text"]


# ── the workflow ──────────────────────────────────────────────────────

def test_the_workflow_runs_by_hand_and_passes_its_inputs_safely():
    from config.paths import PROJECT_ROOT
    wf = yaml.safe_load((PROJECT_ROOT / ".github/workflows/agent1_coverage_map.yml")
                        .read_text(encoding="utf-8"))
    assert set(wf[True]) == {"workflow_dispatch"}
    assert set(wf[True]["workflow_dispatch"]["inputs"]) == {"stories", "all", "force",
                                                            "dry_run", "limit"}
    assert wf["permissions"] == {"contents": "read"}
    step = next(s for s in wf["jobs"]["map"]["steps"] if s.get("name") == "Map the stories")
    assert "${{" not in step["run"], "inputs reach the shell through env only"
    assert 'python -m agents.agent1_coverage "${ARGS[@]}"' in step["run"]
    assert step["env"]["LLM_MODEL"].startswith("${{ vars.LLM_MODEL_LIGHT")


def test_main_maps_every_unmapped_story_up_to_the_limit(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("config.validate_required_env", lambda *a: None)
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: Tracker())
    monkeypatch.setattr("core.app_context.AppContext.load",
                        staticmethod(lambda: SimpleNamespace(name="App", base_url="https://x")))
    monkeypatch.setattr(cov, "stories_with_test_cases",
                        lambda t, f: {"PRJ-1": set(), "PRJ-2": set(), "PRJ-3": set()})
    monkeypatch.setattr(cov, "run", lambda t, llm, key, *a, **k: calls.append(key) or {
        "story": key, "status": "mapped", "criteria": 1, "test_cases": 1, "gaps": [],
        "comment": "c"})
    assert cov.main(["--all", "--limit", "2"]) == 0
    assert calls == ["PRJ-1", "PRJ-2"]
    out = capsys.readouterr().out
    assert "PRJ-3: left for the next run (--limit)" in out
    with pytest.raises(SystemExit):
        cov.main([])
