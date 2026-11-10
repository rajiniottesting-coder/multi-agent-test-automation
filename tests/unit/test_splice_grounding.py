"""Splice writers get the same grounding as the full-file writers.

PRJ-206 (a change story) failed at Agent 2's final gate: the owner splice
rewrote a scenario around a value no element holds (a cart total), its new
step function called a page-object method that does not exist, and because
the splice runs after the repair loop the error could not be repaired.

The full-file writers already had both guards - the feature stage is told
what the application can show, the step-def stage gets the page objects'
real method signatures - but the two splice writers (shared by ai-update and
the change-story splice) had neither. These tests pin:

  1. _generate_single_scenario is told what the application can show;
  2. _generate_missing_step_functions gets the real page-object methods;
  3. a spliced step function calling an unknown method is corrected HERE,
     once, with the validator's words - before the gate - and an error the
     committed file already had is not blamed on the splice;
  4. every LLM writer in Agent 2 declares its grounding (a new writer without
     one fails this file, so the gap cannot reopen unnoticed).

Generic: synthetic page objects and steps; no network, no model.
"""
import ast

import pytest
from pathlib import Path

import agents.agent2_coder as coder
import agents.agent2_impact as impact

ROOT = Path(__file__).resolve().parents[2]

FEATURE = '''Feature: Basket
  Scenario: one item
    Given I am on the widget page
    Then the basket should list "Widget" with count 1
'''

EXISTING = '''from pytest_bdd import scenarios, given, when, then, parsers

scenarios("../../features/fake_basket.feature")


@given("I am on the widget page")
def _(widget_page):
    widget_page.open_widget()
'''

PAGE = '''from pages.base_page import BasePage


class WidgetPage(BasePage):
    def open_widget(self) -> None:
        self.navigate("/widget")

    def count_for(self, name: str) -> int:
        return int(self.get_text(self.sel("count")))
'''

BAD = '''@then(parsers.parse('the basket should list "{name}" with count {n:d}'))
def _(widget_page, name, n):
    assert widget_page.total_count_of(name) == n
'''

GOOD = '''@then(parsers.parse('the basket should list "{name}" with count {n:d}'))
def _(widget_page, name, n):
    assert widget_page.count_for(name) == n
'''


class FakeGH:
    def __init__(self, content):
        self.content = content

    def get_file_content(self, path, branch="main"):
        return self.content

    def list_files_in_directory(self, path, branch="main"):
        return []


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke_text(self, system_prompt="", user_prompt=""):
        self.prompts.append(user_prompt)
        return self.responses.pop(0)


def _batch():
    return [coder.GeneratedFile(file_path="pages/widget_page.py", content=PAGE,
                                is_new_file=True, purpose="page object")]


def _splice(llm, existing=EXISTING, batch=None):
    return coder._splice_step_defs_incremental(
        llm, FakeGH(existing), "features/fake_basket.feature", FEATURE,
        "tests/step_defs/test_fake_basket.py", ctx=None, references={},
        page_inventory="", batch_files=_batch() if batch is None else batch)


# ── 1. the scenario writer is told what can be shown ────────────────

def test_single_scenario_writer_is_told_what_the_app_can_show(monkeypatch):
    monkeypatch.setattr(coder, "_build_readable_values_block",
                        lambda: "\n## What this application can be asked to SHOW\n  page: x\n")
    llm = ScriptedLLM("  # JIRA: AB-1\n  Scenario: s\n    Given x\n")
    coder._generate_single_scenario(llm, "features/f.feature",
                                    {"key": "AB-1", "summary": "s", "description": "d"},
                                    None, "Feature: F\n")
    assert "What this application can be asked to SHOW" in llm.prompts[0]
    assert "keep the scenario's purpose" in llm.prompts[0]


# ── 2. the step writer gets the real methods ────────────────────────

def test_missing_step_writer_gets_page_methods_and_feedback():
    llm = ScriptedLLM("")
    coder._generate_missing_step_functions(
        llm, EXISTING, FEATURE, [("then", "x")], "tests/step_defs/t.py",
        page_objects_block="## `WidgetPage`\n    def count_for(name): ...",
        validator_feedback="- calls `widget_page.total_count_of()`")
    assert "count_for(name)" in llm.prompts[0]
    assert "rejected by the validator" in llm.prompts[0]
    assert "never invent a method" in llm.prompts[0]


def test_the_splice_passes_this_runs_page_objects_to_the_writer():
    llm = ScriptedLLM(GOOD)
    content, mode = _splice(llm)
    assert mode == "spliced" and "count_for" in content
    assert "def count_for(name)" in llm.prompts[0]


# ── 3. an unknown method is corrected at the splice, not at the gate ─

def test_an_unknown_method_is_corrected_once_with_the_validators_words():
    llm = ScriptedLLM(BAD, GOOD)
    content, mode = _splice(llm)
    assert mode == "spliced"
    assert "count_for(name)" in content and "total_count_of" not in content
    assert len(llm.prompts) == 2
    assert "total_count_of" in llm.prompts[1] and "rejected by the validator" in llm.prompts[1]


def test_still_unknown_after_one_correction_falls_back_to_whole(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE")
    llm = ScriptedLLM(BAD, BAD)
    content, mode = _splice(llm)
    assert (content, mode) == ("WHOLE", "regenerated")
    assert len(llm.prompts) == 2


def test_an_error_the_committed_file_already_had_is_not_blamed_on_the_splice():
    broken = EXISTING + '''

@when("I do something old")
def _(widget_page):
    widget_page.no_such_method()
'''
    llm = ScriptedLLM(GOOD)
    _content, mode = _splice(llm, existing=broken)
    assert mode == "spliced" and len(llm.prompts) == 1


def test_whole_regeneration_sees_this_runs_page_objects(monkeypatch):
    seen = {}

    def whole(*a, **k):
        seen["paths"] = [p.file_path for p in k.get("existing_page_objects") or []]
        return "WHOLE"
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole", whole)
    _splice(ScriptedLLM(""))                      # no usable function -> whole
    assert "pages/widget_page.py" in seen["paths"]


def test_the_owner_splice_hands_its_batch_on(monkeypatch):
    got = {}

    def fake_splice(*a, **k):
        got.update(k)
        return "x", "unchanged"
    monkeypatch.setattr(coder, "_splice_step_defs_incremental", fake_splice)

    class OF:
        revise, retire, step_defs_path = [], [], "tests/step_defs/test_o.py"

    class GH:
        def get_file_content(self, path, branch="main"):
            return "Feature: O\n"
    batch = _batch()
    impact.splice_owner_files(None, GH(), "AB-9", {"features/o.feature": OF()}, None, None,
                              {}, "", None, batch_files=batch)
    assert got["batch_files"] is batch


# ── 4. every LLM writer declares its grounding ──────────────────────

# A function that asks the model to WRITE something, and the helpers that
# ground it in what exists. A new writer must be added here with its
# grounding - an unlisted one fails test_every_llm_writer_is_grounded.
WRITERS = {
    ("agents/agent2_coder.py", "build_plan"): {"plan"},
    ("agents/agent2_coder.py", "generate_file_content"):
        {"_build_readable_values_block", "_build_sibling_page_object_context",
         "_build_base_page_helpers_block"},
    ("agents/agent2_coder.py", "_generate_single_scenario"): {"_build_readable_values_block"},
    ("agents/agent2_coder.py", "_generate_missing_step_functions"): {"page_objects_block"},
}


def _llm_writers():
    found = set()
    for rel in ("agents/agent2_coder.py", "agents/agent2_impact.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = {ast.unparse(c.func).split(".")[-1] for c in ast.walk(node)
                         if isinstance(c, ast.Call)}
                if calls & {"invoke_text", "invoke_structured"}:
                    found.add((rel, node.name))
    return found


def test_every_llm_writer_is_grounded():
    found = _llm_writers()
    unlisted = sorted(found - set(WRITERS))
    assert not unlisted, (f"New LLM writer(s) {unlisted}: add them to WRITERS with the "
                          "grounding they receive (what the app can show, real page methods)")
    for (rel, name), grounding in WRITERS.items():
        if grounding == {"plan"}:
            continue
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        names = {getattr(n, "id", None) or getattr(n, "attr", None) or getattr(n, "arg", None)
                 for n in ast.walk(fn)}
        assert grounding <= names, f"{name} lost its grounding: {grounding - names}"


def test_run_hands_its_files_to_the_owner_splice():
    tree = ast.parse((ROOT / "agents/agent2_coder.py").read_text(encoding="utf-8"))
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run")
    calls = [c for c in ast.walk(run) if isinstance(c, ast.Call)
             and ast.unparse(c.func).endswith("splice_owner_files")]
    assert calls and all(any(k.arg == "batch_files" for k in c.keywords) for c in calls)


# ── 5. a step no page-object method checks is never given another check ─

NEEDS = '''@then(parsers.parse('the basket should list "{name}" with count {n:d}'))
def _(widget_page, name, n):
    raise NotImplementedError("needs a page-object method: the count of a named item")
'''


def test_the_writer_is_told_not_to_substitute_an_unrelated_check():
    llm = ScriptedLLM(GOOD)
    _splice(llm)
    assert "do NOT substitute one that checks something else" in llm.prompts[0]
    assert coder.NEEDS_PAGE_METHOD in llm.prompts[0]
    assert "assert with one that does" not in llm.prompts[0]


def test_a_step_no_method_checks_stops_the_update_with_the_remedy():
    """5 Nov 2026: a spliced step for a section no method reads asserted an unrelated list.
    An ai-update writes no page object (no batch): one answer, the ai-regenerate remedy."""
    import pytest
    llm = ScriptedLLM(NEEDS)
    with pytest.raises(coder.GateFailure) as stop:
        _splice(llm, batch=[])
    assert "ai-regenerate" in str(stop.value)
    (err,) = stop.value.errors
    assert "the count of a named item" in err and "test_fake_basket.py" in err


def test_a_stopped_update_tells_the_story_once_and_takes_the_label_off(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(coder, "load_agent_config", lambda *a: {"update_label": "go-update"})
    jira = MagicMock()
    stop = coder.GateFailure("needs a method", errors=["Step needs a page-object method ..."])
    coder._hand_back_update(jira, "AB-1", stop)
    body = jira.add_comment.call_args[0][1]
    assert body.startswith(coder.UPDATE_STOPPED) and "Step needs a page-object method" in body
    jira.remove_label.assert_called_once_with("AB-1", "go-update")
    src = __import__("inspect").getsource(coder.run_update)
    assert "_hand_back_update(jira, story_id, stop)" in src


def test_the_notes_addition_body_claims_nothing_about_the_tests():
    from core import context_update as cu
    body = cu.render_addition_body("AB-1", cu.Additions())
    assert "its tests passed" not in body and "once the story's tests pass on main" in body


# ── F45: a page missing from the inventory is what the gate reports ─────

def test_a_missing_page_is_reported_before_any_other_gate(monkeypatch):
    """5 Nov 2026, PRJ-292: the repair stopped on a page the inventory lacks,
    then the gate refused an undefined step and the blocked comment named
    that, with advice to edit the test case."""
    import pytest
    from core.blocked import blocked_comment
    page_err = ("Selector inventory error in 'pages/reports_list_page.py': class "
                "ReportsListPage sets INVENTORY_PAGE = 'reports_list_zz', which is not a "
                "page in the app inventory. Available pages: home.")
    monkeypatch.setattr(coder, "validate_page_object_selectors", lambda *a, **k: [page_err])
    monkeypatch.setattr(coder, "validate_step_definitions_complete",
                        lambda *a, **k: ["Step coverage error in 'tests/step_defs/x.py': ..."])
    with pytest.raises(coder.GateFailure) as stop:
        coder._validate_generated_files([], "AB-1")
    assert "reports_list_zz" in str(stop.value) and stop.value.errors == [page_err]
    text = blocked_comment("AB-1", "0" * 16, stop.value.errors)
    assert "plan_inventory page" in text and "reports_list_zz" in text



# ── 6. a change story's run names the methods it wrote before giving up (E119)

def test_a_change_storys_splice_is_told_the_methods_its_run_wrote(monkeypatch):
    """10 Nov 2026: the run extended the page object with the methods its
    revised steps need, the writer still answered 'needs a page-object
    method', and the run stopped on that first answer."""
    llm = ScriptedLLM(NEEDS, GOOD)
    content, mode = _splice(llm)
    assert mode == "spliced" and "count_for" in content
    assert "This run has just written these page-object methods" in llm.prompts[1]
    assert "WidgetPage.count_for" in llm.prompts[1]


def test_still_no_method_after_that_stops_with_the_change_story_remedy():
    import pytest
    llm = ScriptedLLM(NEEDS, NEEDS)
    with pytest.raises(coder.GateFailure) as stop:
        _splice(llm)
    assert "Run Agent 2 again with the story's key" in str(stop.value)
    assert "ai-regenerate" not in str(stop.value) and "ai-update" not in str(stop.value)
    assert "WidgetPage.count_for" in str(stop.value)


def test_only_methods_new_in_this_run_are_named():
    committed = PAGE.replace("    def count_for", "    def _private(self):\n        pass\n\n    def count_for_old")
    written = coder._page_methods_written_in_run(FakeGH(PAGE), _batch())
    assert written == [], "the committed copy already has every method"
    written = coder._page_methods_written_in_run(FakeGH(committed), _batch())
    assert written == ["WidgetPage.count_for"]


# ── 7. still unmet: back to the page-object repair once (E120) ─────────

def test_a_change_storys_unmet_step_is_a_routable_stop():
    import pytest
    llm = ScriptedLLM(NEEDS, NEEDS)
    with pytest.raises(coder.SpliceNeedsPageMethods) as stop:
        _splice(llm)
    assert stop.value.needs == ["the count of a named item"]
    assert stop.value.step_defs_path == "tests/step_defs/test_fake_basket.py"
    assert isinstance(stop.value, coder.GateFailure), "unrouted, it is still a gate refusal"


def test_the_page_object_repair_is_told_each_unmet_check(monkeypatch):
    from types import SimpleNamespace
    seen = {}

    def fake_generate(llm, file_plan, plan, cases, refs, inv, ctx, validator_feedback=None,
                      previous_attempt=None, already_generated=None, **k):
        seen["feedback"], seen["prior"] = validator_feedback, previous_attempt
        return previous_attempt + "\n    def count_of_named_item(self, name):\n        return 1\n"
    monkeypatch.setattr(coder, "generate_file_content", fake_generate)
    # The tiny fixture page is below the real files' size floor.
    monkeypatch.setattr(coder, "_is_degraded_regeneration", lambda *a, **k: False)
    committed = PAGE.replace("    def count_for", "    def count_for_old")
    files = _batch()
    plan = SimpleNamespace(files_to_create=[coder.FilePlan(
        file_path="pages/widget_page.py", file_type="page_object", is_new_file=False,
        purpose="extend")])
    need = coder.SpliceNeedsPageMethods("x", needs=["the count of a named item"],
                                        step_defs_path="tests/step_defs/t.py")
    assert coder._extend_page_objects_for_splice(None, FakeGH(committed), plan, files, need,
                                                 [], {}, "", None)
    assert "the count of a named item" in seen["feedback"][0]
    assert "keep every existing method exactly as it is" in seen["feedback"][0]
    assert seen["prior"] == PAGE and "count_of_named_item" in files[0].content


def test_nothing_written_in_the_run_means_nothing_to_repair(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(coder, "generate_file_content",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    need = coder.SpliceNeedsPageMethods("x", needs=["n"], step_defs_path="t.py")
    assert not coder._extend_page_objects_for_splice(
        None, FakeGH(PAGE), SimpleNamespace(files_to_create=[]), _batch(), need, [], {}, "", None)


def test_run_routes_each_new_stop_back_and_splices_again():
    import inspect
    src = inspect.getsource(coder.run)
    assert "rounds = 2 * len(owner_files) + 1" in src, "two rounds per owner file"
    route = src[src.index("for _round in range(rounds):"):]
    route = route[:route.index("by_path = {")]
    assert "except SpliceNeedsPageMethods as need:" in route
    assert "_extend_page_objects_for_splice(" in route
    assert "key in asked" in route, "the same stop twice is not routed again"
    assert route.count("agent2_impact.splice_owner_files(") == 1 and "break" in route


# ── 8. the writer names the page object; a committed one joins the batch (E121)

def test_the_writer_is_asked_to_name_the_page_object():
    llm = ScriptedLLM(GOOD)
    _splice(llm)
    assert "<PageObjectClass>: <what the step checks>" in llm.prompts[0]


@pytest.mark.parametrize("raw, target", [
    ("FormPage: the form is shown", ("FormPage", "the form is shown")),
    ("the form is shown", (None, "the form is shown")),
    ("  WidgetPage :  a: b ", ("WidgetPage", "a: b")),
])
def test_a_need_names_its_page_object(raw, target):
    assert coder._need_target(raw) == target


def test_a_committed_page_object_the_writer_names_joins_the_batch(monkeypatch, tmp_path):
    from types import SimpleNamespace
    (tmp_path / "pages").mkdir()
    form = "from pages.base_page import BasePage\n\n\nclass FormPage(BasePage):\n    def open(self):\n        pass\n"
    (tmp_path / "pages" / "form_page.py").write_text(form)
    seen = {}

    def fake_generate(llm, file_plan, plan, cases, refs, inv, ctx, validator_feedback=None,
                      previous_attempt=None, **k):
        seen[file_plan.file_path] = validator_feedback
        return previous_attempt + "\n    def is_form_shown(self):\n        return True\n"
    monkeypatch.setattr(coder, "generate_file_content", fake_generate)
    monkeypatch.setattr(coder, "_is_degraded_regeneration", lambda *a, **k: False)
    monkeypatch.setattr("validators.method_resolution_validator._reserved_page_files", lambda: set())
    files = _batch()
    plan = SimpleNamespace(files_to_create=[coder.FilePlan(
        file_path="pages/widget_page.py", file_type="page_object", is_new_file=False,
        purpose="extend")])
    need = coder.SpliceNeedsPageMethods(
        "x", needs=["FormPage: the form is shown", "WidgetPage: the count of a named item"],
        step_defs_path="tests/step_defs/t.py")
    committed = PAGE.replace("    def count_for", "    def count_for_old")
    assert coder._extend_page_objects_for_splice(None, FakeGH(committed), plan, files, need,
                                                 [], {}, "", None, root=tmp_path)
    assert "the form is shown" in seen["pages/form_page.py"][0]
    assert "the count of a named item" in seen["pages/widget_page.py"][0]
    assert len(seen["pages/form_page.py"]) == 1, "each file gets only its own checks"
    form_file = next(f for f in files if f.file_path == "pages/form_page.py")
    assert "is_form_shown" in form_file.content
    assert plan.files_to_create[0].file_path == "pages/form_page.py"


def test_a_reserved_page_object_never_joins(monkeypatch, tmp_path):
    from types import SimpleNamespace
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "form_page.py").write_text("class FormPage:\n    pass\n")
    monkeypatch.setattr("validators.method_resolution_validator._reserved_page_files",
                        lambda: {"pages/form_page.py"})
    monkeypatch.setattr(coder, "generate_file_content",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    files = []
    need = coder.SpliceNeedsPageMethods("x", needs=["FormPage: the form is shown"],
                                        step_defs_path="t.py")
    assert not coder._extend_page_objects_for_splice(
        None, FakeGH(""), SimpleNamespace(files_to_create=[]), files, need, [], {}, "", None,
        root=tmp_path)
    assert files == []


# ── 9. the splice runs the repair loop's rules on what it adds (E125) ───

ABSENCE_FEATURE = '''Feature: Basket
  Scenario: one item
    Given I am on the widget page
    Then the help link should not be shown
'''

ABSENCE_EMPTY = '''@then("the help link should not be shown")
def _(widget_page):
    widget_page.open_widget()
'''

ABSENCE_GOOD = '''@then("the help link should not be shown")
def _(widget_page):
    assert widget_page.is_help_link_absent()
'''

PAGE_ABSENT = PAGE + '''
    def is_help_link_absent(self) -> bool:
        return self.is_gone(self.sel("help"))
'''


def test_a_gate_rule_the_new_functions_break_is_fed_back_once(monkeypatch):
    seen = []
    real = coder._new_repairable_errors

    def spy(*a):
        out = real(*a)
        seen.append(out)
        return out
    monkeypatch.setattr(coder, "_new_repairable_errors", spy)
    llm = ScriptedLLM(ABSENCE_EMPTY, ABSENCE_GOOD)
    batch = [coder.GeneratedFile(file_path="pages/widget_page.py", content=PAGE_ABSENT,
                                 is_new_file=True, purpose="page object")]
    content, mode = coder._splice_step_defs_incremental(
        llm, FakeGH(EXISTING), "features/fake_basket.feature", ABSENCE_FEATURE,
        "tests/step_defs/test_fake_basket.py", ctx=None, references={}, page_inventory="",
        batch_files=batch)
    assert mode == "spliced" and "is_help_link_absent" in content
    assert any("Absence step error" in e for e in seen[0]), seen[0]
    assert "rejected by the validator" in llm.prompts[1]
    assert "Absence step error" in llm.prompts[1]
