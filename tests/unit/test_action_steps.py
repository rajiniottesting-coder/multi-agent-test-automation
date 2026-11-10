"""E131: a step that says the user clicks makes a page-object call that clicks.

Generic page objects and steps only; no application names.
"""
from types import SimpleNamespace as F

from validators.action_steps import _action_steps, validate_click_steps_click

BASE = '''
class BasePage:
    def click(self, locator):
        self._locator(locator).click()
    def scroll_to_top(self):
        self.page.evaluate("window.scrollTo(0, 0)")
    def sel(self, key):
        return key
'''

PAGE = '''
from pages.base_page import BasePage
class StartPage(BasePage):
    def open_start(self, base_url):
        self.navigate(base_url)
    def back_to_top(self):
        self.scroll_to_top()
    def press_back_to_top(self):
        self.click(self.sel("top_control"))
    def press_through_helper(self):
        self._press()
    def _press(self):
        self.page.locator("x").click()
    def is_at_top(self):
        return True
'''

FEATURE = '''Feature: f
  Background:
    Given I open the start page
  Scenario: s
    When I scroll down
    And I click the back-to-top control
    Then the top is shown
'''


def _steps(body):
    return ('from pytest_bdd import given, when, then\n'
            '@given("I open the start page")\n'
            'def o(start_page, base_url):\n    start_page.open_start(base_url)\n'
            '@when("I scroll down")\n'
            'def d(start_page):\n    pass\n'
            '@when("I click the back-to-top control")\n'
            f'def c(start_page):\n    {body}\n'
            '@then("the top is shown")\n'
            'def t(start_page):\n    assert start_page.is_at_top()\n')


def _files(body):
    return [F(file_path="features/start.feature", content=FEATURE),
            F(file_path="tests/step_defs/test_start.py", content=_steps(body)),
            F(file_path="pages/base_page.py", content=BASE),
            F(file_path="pages/start_page.py", content=PAGE)]


def test_a_click_step_that_only_simulates_the_outcome_is_refused(tmp_path):
    (err,) = validate_click_steps_click(_files("start_page.back_to_top()"), tmp_path)
    assert err.startswith("Action step error in 'tests/step_defs/test_start.py'")
    assert "`When I click the back-to-top control`" in err
    assert "start_page.back_to_top() makes no click" in err
    assert "leave that test case out" in err


def test_a_click_through_the_base_class_or_a_helper_passes(tmp_path):
    assert validate_click_steps_click(_files("start_page.press_back_to_top()"), tmp_path) == []
    assert validate_click_steps_click(_files("start_page.press_through_helper()"), tmp_path) == []


def test_any_clicking_call_among_several_passes(tmp_path):
    body = "start_page.back_to_top()\n    start_page.press_back_to_top()"
    assert validate_click_steps_click(_files(body), tmp_path) == []


def test_what_cannot_be_read_is_left_alone(tmp_path):
    assert validate_click_steps_click(_files("start_page.not_defined_anywhere()"), tmp_path) == []
    assert validate_click_steps_click(_files("pass"), tmp_path) == [], "no page-object call"


def test_only_given_and_when_steps_that_claim_a_click():
    feature = ("Feature: f\n  Scenario: s\n    Given I click the menu\n    And I press Enter\n"
               "    When I tap the card\n    Then the clickable title is shown\n"
               "    And I click nothing here\n    When I open the pressed tab list\n")
    assert _action_steps(feature) == [("given", "I click the menu"), ("given", "I press Enter"),
                                      ("when", "I tap the card")]


# ── E134: the scenarios that stand in for a missing control are left out ──

from core.schemas import GeneratedFile  # noqa: E402
from validators.action_steps import leave_out_stand_ins  # noqa: E402

LONG = '''@start
Feature: Start page

  Background:
    Given I open the start page

  @smoke
  # JIRA: AB-1 (hash: 1) owner: AB-9
  Scenario: The footer shows the box
    When I scroll down
    Then the box is shown

  # JIRA: AB-2 (hash: 2) owner: AB-9
  Scenario: The control returns to the top
    When I scroll down
    When I click the back-to-top control
    Then the top is shown

  # JIRA: AB-3 (hash: 3) owner: AB-9
  Scenario: The control returns from half way
    When I click the back-to-top control
    Then the top is shown
'''

LONG_STEPS = '''from pytest_bdd import given, when, then


@given("I open the start page")
def o(start_page, base_url):
    start_page.open_start(base_url)


@when("I scroll down")
def d(start_page):
    start_page.back_to_top()


@then("the box is shown")
def b(start_page):
    assert start_page.is_at_top()


@when("I click the back-to-top control")
def c(start_page):
    start_page.back_to_top()


@then("the top is shown")
def t(start_page):
    assert start_page.is_at_top()
'''


def _long_files():
    return [GeneratedFile(file_path="features/start.feature", content=LONG),
            GeneratedFile(file_path="tests/step_defs/test_start.py", content=LONG_STEPS),
            GeneratedFile(file_path="pages/base_page.py", content=BASE),
            GeneratedFile(file_path="pages/start_page.py", content=PAGE)]


def test_the_stand_in_scenarios_are_left_out_and_named(tmp_path):
    files = _long_files()
    errors = validate_click_steps_click(files, tmp_path)
    out, left = leave_out_stand_ins(files, errors)
    assert set(left) == {"AB-2", "AB-3"}
    assert "app inventory has no key for that control" in left["AB-2"]
    feature = next(f.content for f in out if f.file_path.endswith(".feature"))
    assert "AB-1" in feature and "Background:" in feature
    assert "AB-2" not in feature and "AB-3" not in feature
    assert "back-to-top" not in feature
    steps = next(f.content for f in out if f.file_path.endswith(".py") and "step_defs" in f.file_path)
    assert "I click the back-to-top control" not in steps and "the top is shown" not in steps
    assert "I scroll down" in steps and "the box is shown" in steps, "still used by AB-1"
    assert validate_click_steps_click(out, tmp_path) == []
    from validators.gherkin_analyzer import (
        validate_no_unused_step_definitions, validate_step_definitions_complete)
    assert not validate_step_definitions_complete(out, tmp_path)
    assert not validate_no_unused_step_definitions(out)


def test_a_feature_left_with_no_scenario_is_not_changed(tmp_path):
    only = LONG.split("  @smoke")[0] + LONG.split("Then the box is shown\n")[1]
    files = [GeneratedFile(file_path="features/start.feature", content=only)] + _long_files()[1:]
    errors = validate_click_steps_click(files, tmp_path)
    out, left = leave_out_stand_ins(files, errors)
    assert left == {} and out[0].content == only


def test_protected_files_and_other_errors_are_left_alone(tmp_path):
    files = _long_files()
    errors = validate_click_steps_click(files, tmp_path)
    assert leave_out_stand_ins(files, errors, protected={"features/start.feature": 1})[1] == {}
    assert leave_out_stand_ins(files, ["Step coverage error in 'x': y"])[1] == {}
