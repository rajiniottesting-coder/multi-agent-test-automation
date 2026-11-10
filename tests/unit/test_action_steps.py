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
