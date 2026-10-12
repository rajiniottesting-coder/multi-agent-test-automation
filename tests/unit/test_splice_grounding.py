"""Splice writers get the same grounding as the full-file writers.

SCRUM-206 (a change story) failed at Agent 2's final gate: the owner splice
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
