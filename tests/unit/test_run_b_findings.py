"""What Run B of the validation found (4 Nov 2026), one test per fix.

A truncated answer is shown; a draft that cannot succeed on a retry is handed
back; a draft sees the scenarios that exist; a planned file left unchanged is
not claimed; a labelled story the scan cannot take is told why; one story can
be analysed again on request; a code-change report reads as markdown on the
pull request; a notes rewrite quotes only what the story states; its PR table
shows where a passage changed; the judge sees each element's selector; the
orphan clean-up and the page-object contract agree, and respect open pull
requests. Generic names only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from core.schemas import CriterionCoverage, TestCase, TestCaseList, TestStep

ROOT = Path(__file__).resolve().parents[2]


def _tc(title, *expected):
    return TestCase(title=title, description="d", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)], expected_outcome="done")


# ── a truncated answer is shown ─────────────────────────────────────────

def test_a_loop_is_named_and_large_content_is_not():
    from core.llm_client import truncation_evidence
    loop = "\n".join(['  "expected_result": "The item is shown in the list again and again",'] * 60)
    lines = truncation_evidence(loop)
    assert any("LIKELY A LOOP" in x for x in lines) and any("most repeated  : x60" in x for x in lines)
    varied = "\n".join(f'  "action": "step number {i} does a different thing entirely here",'
                       for i in range(60))
    lines = truncation_evidence(varied)
    assert any("no loop seen" in x for x in lines)
    assert lines[-1].startswith("  last characters:") and "step number 59" in lines[-1]


@pytest.mark.parametrize("content", [None, "", [{"type": "text", "text": "abc"}], 42])
def test_the_evidence_never_raises(content):
    from core.llm_client import truncation_evidence
    assert truncation_evidence(content)


def test_the_truncation_report_logs_the_evidence(caplog):
    from core.llm_client import OutputTruncatedError, _check_output_not_truncated
    response = NS(response_metadata={"finish_reason": "length"},
                  usage_metadata={"output_tokens": 10}, content="x " * 500)
    with caplog.at_level(logging.ERROR), pytest.raises(OutputTruncatedError):
        _check_output_not_truncated(response, label="structured:Thing", cap=10, knob="k")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "repetition     :" in text and "last characters:" in text


# ── a draft that cannot succeed on a retry is handed back ───────────────

def test_which_failures_stop_retrying():
    from agents.agent1_analyst import stops_retrying
    from core.llm_client import OutputTruncatedError
    from core.spend_budget import BudgetExceeded
    from core.test_case_rules import DraftRejected
    assert stops_retrying(OutputTruncatedError("x")) and stops_retrying(DraftRejected("x"))
    assert not stops_retrying(ValueError("x")) and not stops_retrying(ConnectionError("x"))
    assert not stops_retrying(BudgetExceeded("day", "x"))
    assert issubclass(DraftRejected, ValueError), "callers catching ValueError still do"


class _Tracker:
    def __init__(self):
        self.removed, self.comments = [], []

    def remove_label(self, key, label):
        self.removed.append((key, label))

    def add_comment(self, key, body):
        self.comments.append((key, body))


def test_hand_back_removes_the_trigger_and_says_why():
    from agents.agent1_analyst import STOPPED, hand_back
    from core.llm_client import OutputTruncatedError
    t = _Tracker()
    err = OutputTruncatedError("structured:Draft: output truncated at the 9-token cap. "
                               "To re-run with more room: raise it")
    removed = hand_back(t, "AB-1", err, {"selection": {"required_labels": ["go"]}})
    assert removed == ["go"] and t.removed == [("AB-1", "go")]
    (key, body), = t.comments
    assert key == "AB-1" and body.startswith(STOPPED)
    assert "output truncated at the 9-token cap" in body and "To re-run" not in body
    assert "Add `go` again to retry" in body


def test_the_scan_hands_back_only_such_failures_and_never_in_a_dry_run():
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert "if stops_retrying(e) and not args.dry_run:" in src


def test_a_draft_broken_twice_raises_draft_rejected(monkeypatch):
    from agents import agent1_analyst
    from core.test_case_rules import DraftRejected
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    bad = TestCaseList(story_summary="s", test_cases=[_tc("A", "continues the same session")])

    class LLM:
        def invoke_structured(self, **kw):
            return bad
    with pytest.raises(DraftRejected):
        agent1_analyst._draft_test_cases(LLM(), "PROMPT")


# ── a draft sees the scenarios that exist ───────────────────────────────

def test_a_new_test_case_titled_as_an_existing_scenario_is_sent_back():
    from agents.agent1_analyst import repeats_of_existing
    found = repeats_of_existing([_tc("[Positive] Visitor sends the form", "sent"),
                                 _tc("[Negative] Empty field is refused", "refused")],
                                {"visitor sends the form"})
    assert len(found) == 1 and "repeats an existing scenario" in found[0]


def test_an_unchanged_criterion_may_cite_an_existing_scenario(monkeypatch):
    from agents import agent1_analyst
    from core.acceptance_coverage import extract_criteria
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    criteria = extract_criteria("Form rule", "Acceptance criteria:\n1. The form still sends "
                                "as before.\n2. An empty title is refused.")
    draft = TestCaseList(story_summary="s",
                         test_cases=[_tc("[Negative] Empty title is refused",
                                         "the form is refused: no confirmation is shown")],
                         coverage=[CriterionCoverage(criterion="AC1",
                                                     covered_by=["visitor sends the form"]),
                                   CriterionCoverage(criterion="AC2",
                                                     covered_by=["[Negative] Empty title is refused"])])

    class LLM:
        def invoke_structured(self, **kw):
            return draft
    assert agent1_analyst._draft_test_cases(LLM(), "P", criteria,
                                            {"visitor sends the form"}) is draft


def test_the_draft_check_sends_a_copy_back(monkeypatch):
    from agents import agent1_analyst
    from core.test_case_rules import DraftRejected
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    copy = TestCaseList(story_summary="s", test_cases=[_tc("[Positive] Visitor sends the form", "sent")])

    class LLM:
        def invoke_structured(self, **kw):
            return copy
    with pytest.raises(DraftRejected, match="repeats an existing scenario"):
        agent1_analyst._draft_test_cases(LLM(), "P", None, {"visitor sends the form"})


def test_the_prompt_lists_the_existing_scenarios():
    prompt = (ROOT / "prompts" / "agent1_analyst.md").read_text(encoding="utf-8")
    assert "{existing_titles_block}" in prompt and "# Scenarios that already exist" in prompt
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert '"{existing_titles_block}"' in src


# ── a planned file left unchanged is not claimed ────────────────────────

def test_a_file_generated_exactly_as_on_main_is_not_committed():
    from agents.agent2_coder import unchanged_files_dropped, unchanged_section
    main = {"pages/a_page.py": "same\n"}

    class Host:
        def get_file_content(self, path, branch="main"):
            return main[path]
    files = [NS(file_path="pages/a_page.py", content="same\n", is_new_file=False),
             NS(file_path="pages/b_page.py", content="new\n", is_new_file=False),
             NS(file_path="features/x.feature", content="F\n", is_new_file=True)]
    keep, unchanged = unchanged_files_dropped(Host(), files)
    assert [f.file_path for f in keep] == ["pages/b_page.py", "features/x.feature"]
    assert unchanged == ["pages/a_page.py"]
    assert "`pages/a_page.py`" in unchanged_section(unchanged) and unchanged_section([]) == ""


# ── a labelled story the scan cannot take is told why ───────────────────

def _issue(key, status):
    return NS(key=key, fields=NS(status=NS(name=status)))


def test_the_tracker_finds_labelled_stories_outside_the_scope():
    from integrations.jira_client import JiraClient
    jql = []

    def search(q, maxResults=20):
        jql.append(q)
        if q.startswith("key in"):
            return [_issue("AB-2", "Done")]
        return [_issue("AB-1", "To Do"), _issue("AB-2", "Done")]
    c = JiraClient.__new__(JiraClient)
    c.project_key = "AB"
    c._client = NS(enhanced_search_issues=search)
    c.get_active_sprint_name = lambda: "Sprint 7"
    out = c.find_unselected_stories({"issue_type": "Story", "allowed_statuses": ["To Do"],
                                     "required_labels": ["go"], "excluded_labels": ["done"],
                                     "sprint": "auto"})
    assert 'AND NOT (status in ("To Do") AND sprint = "Sprint 7")' in jql[0]
    assert 'labels = "go"' in jql[0] and 'labels != "done"' in jql[0]
    assert out[0] == {"key": "AB-1", "status": "To Do", "why": "it is not in the sprint 'Sprint 7'"}
    assert out[1]["key"] == "AB-2" and "status 'Done' is not one of: To Do" in out[1]["why"]


def test_a_selection_without_scope_or_trigger_finds_nothing():
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    c.project_key = "AB"
    c._client = NS(enhanced_search_issues=lambda *a, **k: pytest.fail("no query expected"))
    assert c.find_unselected_stories({"required_labels": ["go"]}) == []
    assert c.find_unselected_stories({"allowed_statuses": ["To Do"]}) == []


class _Notified:
    def __init__(self, found):
        self.found, self.comments = found, {}

    def find_unselected_stories(self, selection, sprint_override=None):
        return self.found

    def get_comments(self, key):
        return list(self.comments.get(key, []))

    def add_comment(self, key, body):
        self.comments.setdefault(key, []).append(body)


def test_each_story_is_told_once_per_agent_and_reason():
    from core.selection_notice import MARKER, notify_unselected
    t = _Notified([{"key": "AB-1", "status": "To Do", "why": "it is not in the sprint 'S'"}])
    sel = {"required_labels": ["go"]}
    assert notify_unselected(t, sel, "Agent X") == [("AB-1", "it is not in the sprint 'S'")]
    notify_unselected(t, sel, "Agent X")
    (body,) = t.comments["AB-1"]
    assert body.startswith(MARKER) and "`go`" in body and "Agent X" in body
    notify_unselected(t, sel, "Agent Y")
    assert len(t.comments["AB-1"]) == 2, "another agent's notice is its own"


def test_a_dry_run_or_a_tracker_without_the_capability_posts_nothing():
    from core.selection_notice import notify_unselected
    t = _Notified([{"key": "AB-1", "status": "Done", "why": "w"}])
    assert notify_unselected(t, {"required_labels": ["go"]}, "A", dry_run=True)
    assert t.comments == {}
    assert notify_unselected(object(), {"required_labels": ["go"]}, "A") == []


def test_both_scans_tell_the_stories_they_cannot_take():
    a1 = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    a2 = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "notify_unselected(jira, selection," in a1
    assert "notify_unselected(jira, sel, name," in a2


# ── one story can be analysed again on request ──────────────────────────

def test_force_analyses_an_unchanged_story(monkeypatch):
    import agents.agent0_impact as a0
    calls = []
    monkeypatch.setattr(a0, "_start_usage", lambda: None)
    monkeypatch.setattr(a0, "_already_analysed", lambda *a: True)
    monkeypatch.setattr(a0, "requirement_hash", lambda s: "h")
    monkeypatch.setattr(a0, "analyse_requirement", lambda *a, **k: calls.append("analysed") or {})
    monkeypatch.setattr(a0, "publish", lambda *a, **k: calls.append(k.get("force")) or
                        {"action": "dry-run"})
    tracker = NS(get_story=lambda k: {"key": k}, remove_label=lambda *a: calls.append("label"))
    settings = {"labels": {"check": "c"}}
    assert a0.analyse_and_publish(tracker, "AB-1", None, settings, ROOT)["action"] == "unchanged"
    assert calls == ["label"]
    calls.clear()
    a0.analyse_and_publish(tracker, "AB-1", None, settings, ROOT, dry_run=True, force=True)
    assert calls == ["analysed", True]


def test_force_is_a_workflow_input_for_one_story():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "agent0_impact.yml").read_text())
    inputs = wf[True]["workflow_dispatch"]["inputs"] if True in wf else wf["on"]["workflow_dispatch"]["inputs"]
    assert inputs["force"]["type"] == "boolean"
    src = (ROOT / "agents" / "agent0_impact.py").read_text(encoding="utf-8")
    assert '"--force is for one story: use it with --story"' in src


# ── a code-change report reads as markdown on the pull request ──────────

def test_the_pull_request_copy_is_markdown():
    from agents.agent0_impact import for_pull_request
    body = ("[agent0:report] Impact of PR #1 | hash: h | graph: g\n\n||Tier||Test||\n|review|AB-1|\n\n"
            "note\n{code:json}\n{\"a\": \"{code}\"}\n{code}")
    out = for_pull_request(body)
    assert out.splitlines()[0] == body.splitlines()[0]
    assert "| Tier | Test |\n|---|---|\n|review|AB-1|" in out
    assert "```json" in out and '{"a": "{code}"}' in out and "{code:json}" not in out
    assert out.rstrip().endswith("</details>")


def test_a_report_with_nothing_affected_has_no_empty_table():
    """PR #287 (4 Nov): "Affected: 0" was followed by a table header with no rows."""
    from agents.agent0_impact import _render_report
    report = {"content_hash": "h", "graph_sha": "g", "no_component": False, "ranked": [],
              "unaffected": [], "not_judged": [], "by_owner": {},
              "seeds": {"elements": [], "methods": [], "pages": [], "dropped": []}}
    empty = _render_report(report, "Impact of PR #1 (code change)")
    assert "Affected: 0" in empty and "||Tier||" not in empty
    report["ranked"] = [{"tier": "review", "score": 0.4, "key": "AB-1", "owner": "AB-2",
                         "title": "t", "evidence": "e"}]
    assert "||Tier||Score||Test||Owner||Scenario||Evidence||" in _render_report(report, "x")


# ── a notes rewrite quotes only what the story states ───────────────────

def test_a_quote_nobody_stated_is_found():
    from core.context_update import invented_quotes
    story = "The error explains what to do next."
    assert invented_quotes('- Error -> "Wrong input!"', '- Error -> "Wrong input. Try again later."',
                           story) == ["Wrong input. Try again later."]
    assert invented_quotes("a", 'shows "Next step" and `Save` and the user\'s name',
                           story + " Next step Save") == []


def _rw(path, old, new):
    return NS(path=path, old=old, new=new, reason="AC1")


def test_a_rewrite_with_an_invented_quote_is_not_applied():
    from core import context_update as cu
    src = {"prompts/app_context/a.md": "- Error -> \"Wrong input!\"\n"}
    rw = _rw("prompts/app_context/a.md", '- Error -> "Wrong input!"',
             '- Error -> "Wrong input. Try again later."')
    p = cu.propose(src, [], None, [rw], story_text="The error explains what to do next.")
    assert p.empty and "quotes a text the story does not state" in p.dropped[0][2]
    p = cu.propose(src, [], None, [rw], story_text='The error reads "Wrong input. Try again later."')
    assert not p.empty
    assert not cu.propose(src, [], None, [rw]).empty, "no story text: unchanged behaviour"


# ── its PR table shows where a passage changed ──────────────────────────

def test_the_table_cells_open_on_the_first_difference():
    from core import context_update as cu
    before = ("A long opening sentence that stays exactly the same in both versions of the "
              "passage, and then more of it. The ending says three.")
    after = before.replace("three", "four")
    b, a = cu.changed_part(before, after)
    assert b.startswith("…") and b.endswith("three.") and a.endswith("four.")
    assert cu.changed_part("same", "same") == ("same", "same")
    p = cu.Proposal()
    p.rewrites.append({"path": "n.md", "before": before * 3 + " x", "after": before * 3 + " y",
                       "reason": "r"})
    row = next(x for x in cu.render_body("AB-1", p).splitlines() if x.startswith("| `n.md`"))
    assert "x |" in row and "y |" in row


# ── the judge sees each element's selector ──────────────────────────────

def test_an_element_path_carries_its_selector():
    from core import impact_analysis as ia
    from core.impact_graph import ImpactGraph, ScenarioNode
    s = ScenarioNode(file="features/f.feature", title="t", jira_key="AB-2", steps=(),
                     step_definitions=(), methods=frozenset(), shared_methods=frozenset(),
                     elements=frozenset({("p", "go_button")}), pages=frozenset({"p"}),
                     components=frozenset())
    g = ImpactGraph(scenarios=[s], selectors={("p", "go_button"): "button.go"})
    (c,) = ia.structural_candidates(g, ia.Seeds(elements={("p", "go_button")}))
    assert c.paths[0]["text"].startswith("element p:go_button (selector `button.go`) <- ")
    prompt = (ROOT / "prompts" / "agent0_adjudicate.md").read_text(encoding="utf-8")
    assert "Finding an element is not reading its text" in prompt


# ── the orphan clean-up and the page-object contract agree ──────────────

COMMITTED = '''class APage:
    def keep(self):
        return 1

    def gone(self) -> bool:
        return True
'''


def test_a_method_the_orphan_clean_up_commented_out_is_not_lost(tmp_path):
    from validators.orphan_cleanup import OrphanPageMethod, comment_out_orphan_page_methods
    from validators.page_object_contract import validate_extended_page_objects_keep_methods as v
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a_page.py").write_text(COMMITTED)
    cleaned = comment_out_orphan_page_methods(
        COMMITTED, [OrphanPageMethod("pages/a_page.py", "APage", "gone", 5, 6)], ["AB-3"])
    assert "AI-ORPHAN" in cleaned
    assert v([NS(file_path="pages/a_page.py", content=cleaned)], tmp_path) == []
    dropped = COMMITTED.split("    def gone")[0]
    assert v([NS(file_path="pages/a_page.py", content=dropped)], tmp_path), \
        "a method simply dropped is still refused"


def test_a_method_an_open_pull_request_calls_is_not_orphaned():
    from agents.agent2_coder import methods_called_in_open_prs
    from validators.orphan_cleanup import cleanup_orphans_after_removal
    feature_before = ('Feature: f\n  # JIRA: AB-3 (hash: 1234abcd) owner: AB-1\n  Scenario: s\n'
                      '    Then the thing is gone\n')
    steps = {"tests/step_defs/test_f.py": (
        'from pytest_bdd import then\n\n@then("the thing is gone")\n'
        'def check_gone(a_page):\n    assert a_page.gone()\n')}
    pages = {"pages/a_page.py": COMMITTED}
    _s, updated, _d, orphans = cleanup_orphans_after_removal(
        feature_before, "Feature: f\n", ["AB-3"], steps, pages)
    assert [o.method_name for o in orphans] == ["gone"]
    _s, updated, _d, orphans = cleanup_orphans_after_removal(
        feature_before, "Feature: f\n", ["AB-3"], steps, pages, called_elsewhere={"gone"})
    assert orphans == [] and updated["pages/a_page.py"] == COMMITTED

    class Host:
        def list_open_prs(self, strict=False):
            return [{"number": 7}]

        def get_pr_changed_files(self, n):
            return [{"filename": "tests/step_defs/test_g.py", "patch": "+    a_page.gone()\n-x.old()"},
                    {"filename": "docs/x.md", "patch": "+ y.not_code()"}]
    assert methods_called_in_open_prs(Host()) == {"gone"}

    class Broken:
        def list_open_prs(self, strict=False):
            raise RuntimeError("down")
    assert methods_called_in_open_prs(Broken()) is None
    src = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "if called_in_prs is None:\n                page_object_files = {}" in src
