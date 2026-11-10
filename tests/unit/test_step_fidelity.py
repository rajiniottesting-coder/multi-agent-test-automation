"""A step does what it says, on the element it names (validators/step_fidelity.py).

10 Nov 2026: a side panel the inventory had no key for was "tested" through
the main list's item names, an item's page opened by name and a page-loaded
check - every gate passed. One model reading names such steps; their
scenarios are left out as not automated, and a story left with nothing is
refused naming them.
"""
from types import SimpleNamespace as NS

from validators import step_fidelity
from validators.action_steps import leave_out_stand_ins

PAGE = '''
class BasePage:
    def sel(self, key):
        return key

    def get_texts(self, locator):
        return []


class ShopPage(BasePage):
    INVENTORY_PAGE = "shop"

    def item_names(self):
        """The names in the main list."""
        return self.get_texts(self.sel("item_names"))

    def is_loaded(self):
        return True
'''

FEATURE = '''Feature: Side panel
  Background:
    Given I am on the shop page

  # JIRA: AB-2 (hash: 1) owner: AB-1
  Scenario: The side panel lists its filters
    Then the side panel lists "Red"

  # JIRA: AB-3 (hash: 2) owner: AB-1
  Scenario: The main list shows items
    Then the main list shows items
'''

STEPS = '''from pytest_bdd import given, then, parsers, scenarios

scenarios("side_panel.feature")


@given("I am on the shop page")
def on_shop(shop_page):
    shop_page.is_loaded()


@then(parsers.parse('the side panel lists "{name}"'))
def panel_lists(shop_page, name):
    assert name in shop_page.item_names()


@then("the main list shows items")
def main_list(shop_page):
    assert shop_page.item_names()
'''

INVENTORY = {"pages": {"shop": {"elements": {"item_names": ".list .name"},
                                "elements_notes": {"item_names": "names in the main list"}}}}


def _files():
    return [NS(file_path="features/side_panel.feature", content=FEATURE, is_new_file=True),
            NS(file_path="tests/step_defs/test_side_panel.py", content=STEPS, is_new_file=True)]


def _root(tmp_path):
    (tmp_path / "pages").mkdir(exist_ok=True)
    (tmp_path / "pages" / "shop_page.py").write_text(PAGE, encoding="utf-8")
    return tmp_path


class _LLM:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.prompts = answer, error, []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.prompts.append(user_prompt)
        if self.error:
            raise self.error
        return self.answer


def test_each_step_is_read_beside_the_code_and_elements_it_uses(tmp_path):
    steps = step_fidelity.step_bindings(_files(), INVENTORY, _root(tmp_path))
    panel = next(s for s in steps if s["phrase"] == 'the side panel lists "{name}"')
    assert panel["keyword"] == "then"
    assert "def item_names" in panel["code"], "the page-object method that runs is shown"
    assert "shop.item_names: .list .name - note: names in the main list" in panel["code"]


def test_a_named_stand_in_becomes_an_error_and_its_scenario_is_left_out(tmp_path):
    steps = step_fidelity.step_bindings(_files(), INVENTORY, _root(tmp_path))
    sid = next(s["id"] for s in steps if s["phrase"].startswith("the side panel"))
    llm = _LLM(step_fidelity.StepFidelityAudit(stand_ins=[step_fidelity.StepFinding(
        id=sid, reason="names the side panel's filters, and reads the main list's item names")]))
    errors = step_fidelity.audit(llm, _files(), INVENTORY, "prompt", _root(tmp_path))
    assert errors == [
        "Step fidelity error in 'tests/step_defs/test_side_panel.py': the step `Then the side "
        "panel lists \"{name}\"` - names the side panel's filters, and reads the main list's "
        "item names. Its code acts on or checks a different element than the step names, so "
        "the scenario passes or fails for something the story does not state. If the app "
        "inventory has no key for the element, a person adds it."]
    files, left_out = leave_out_stand_ins(_files(), errors)
    feature = next(f.content for f in files if f.file_path.endswith(".feature"))
    steps_file = next(f.content for f in files if f.file_path.endswith(".py"))
    assert "AB-2" not in feature and "AB-3" in feature and "Background" in feature
    assert "panel_lists" not in steps_file and "main_list" in steps_file
    assert list(left_out) == ["AB-2"]
    assert "acts on or checks a different element than it names" in left_out["AB-2"]
    assert "reads the main list's item names" in left_out["AB-2"]


def test_a_story_left_with_nothing_keeps_its_files_for_the_refusal(tmp_path):
    error = ("Step fidelity error in 'tests/step_defs/test_side_panel.py': the step `Then the "
             "main list shows items` - x. Its code acts on or checks a different element")
    both = [error, error.replace("the main list shows items", 'the side panel lists "{name}"')]
    files, left_out = leave_out_stand_ins(_files(), both)
    assert left_out == {} and [f.content for f in files] == [f.content for f in _files()]


def test_nothing_is_named_when_the_call_fails_or_names_no_known_step(tmp_path):
    root = _root(tmp_path)
    assert step_fidelity.audit(_LLM(error=RuntimeError("down")), _files(), INVENTORY, "p",
                               root) == []
    unknown = step_fidelity.StepFidelityAudit(stand_ins=[
        step_fidelity.StepFinding(id="S99", reason="x")])
    assert step_fidelity.audit(_LLM(unknown), _files(), INVENTORY, "p", root) == []


def test_the_files_of_another_story_are_not_read(tmp_path):
    steps = step_fidelity.step_bindings(_files(), INVENTORY, _root(tmp_path),
                                        skip={"tests/step_defs/test_side_panel.py"})
    assert steps == []


def test_the_refusal_advice_names_the_missing_element():
    from core import blocked
    text = blocked.blocked_comment("AB-1", "fp", [
        "Step fidelity error in 'tests/step_defs/test_x.py': the step `Then y` - z. Its code "
        "acts on or checks a different element than the step names"])
    assert "acts on or checks a different element than the step names" in text
    assert "plan_inventory element" in text and "retires the test case" in text


def test_agent2_reads_the_steps_after_the_gate_and_refuses_a_story_left_with_nothing():
    from pathlib import Path
    source = Path("agents/agent2_coder.py").read_text(encoding="utf-8")
    assert "step_fidelity.audit(" in source and 'load_prompt("agent2_step_fidelity.md")' in source
    assert "Step fidelity gate failed for" in source
    assert source.index("step_fidelity.audit(") < source.index("# 4c-pre. COVERAGE")


def test_a_story_the_plan_left_out_entirely_is_told_to_add_the_elements():
    from core import blocked
    text = blocked.blocked_comment("AB-1", "fp", [
        "AB-2: no scenario of its own in this pull request - the plan's notes: needs the side "
        "panel's filter links on shop, not in the app inventory."])
    assert "need element(s) - or a page - the app inventory does not have" in text
    assert "plan_inventory element" in text and "Change that test case" not in text


def test_agent2_generates_nothing_when_the_plan_left_every_test_case_out():
    from pathlib import Path
    source = Path("agents/agent2_coder.py").read_text(encoding="utf-8")
    stop = source.index("the plan left out all of its")
    assert stop < source.index("ordered_files = _sort_files_for_generation(plan.files_to_create)")
    assert "blocked.post_blocked_once(jira, story_id, input_fp, e.errors)" in source[stop:stop + 600]


def test_the_plans_skipped_form_is_read_per_key():
    from agents.agent2_coverage import skipped_by_plan
    notes = "Skipped: AB-2 -- needs x on shop, not in the app inventory\nskipped: ab-3 - y"
    assert skipped_by_plan(notes, "AB-2") and skipped_by_plan(notes, "AB-3")
    assert not skipped_by_plan(notes, "AB-20") and not skipped_by_plan(notes, "AB-4")
    assert not skipped_by_plan("AB-2 is covered by the outline", "AB-2")
