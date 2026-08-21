"""Two rules that used to be advice, and the failure that made them checks.

WHAT HAPPENED
    A scenario removed an item and asserted the collection was empty. It was
    not — yet. The predicate behind the assertion was built on `is_visible()`,
    which reads the page once and returns.

    The whole failure, everything the run produced:

        E   AssertionError: Expected the collection to be empty
        E   assert False
        E    +  where False = is_empty()
        E    +    where is_empty = <pages.x_page.XPage object at 0x...>.is_empty

    No captured log. `is_visible()` does not log, so there was nothing to
    read — not which condition failed, not what the page held instead, not
    whether the state had ever existed. `is_showing()` would have logged the
    element, the URL, the timeout and the reason.

    In the SAME pull request the reviewer had flagged the same pattern in a
    different step, correctly, as a race against a state change. It was right
    and it was advice, and the run went ahead. Advice does not hold; this is
    statically checkable, so it is checked.

AND THE SECOND RULE
    That same review flagged a step definition calling `page.sel("a_key")` —
    a selector key in the step layer. It works, which is why it keeps coming
    back, and it quietly undoes the reason page objects exist: the key now
    lives in two places and the inventory can be re-crawled without the step
    noticing. The reviewer catches it most times. Most times is not a gate.
"""
import textwrap
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import (
    validate_no_selectors_in_step_defs,
    validate_predicates_wait,
)


def _page(body: str, path: str = "pages/widget_page.py") -> SimpleNamespace:
    """A page object class with `body` as its methods.

    The dedent-then-indent dance matters: the methods have to end up INSIDE
    the class, or the validator walks a module with no ClassDef and reports
    nothing, and every test here passes for the wrong reason.
    """
    methods = textwrap.indent(textwrap.dedent(body).strip("\n"), "    ")
    return SimpleNamespace(file_path=path, content=(
        "from pages.base_page import BasePage\n"
        "\n"
        "\n"
        "class WidgetPage(BasePage):\n"
        '    INVENTORY_PAGE = "widget"\n'
        "\n"
        f"{methods}\n"
    ))


def _step_def(body: str) -> SimpleNamespace:
    return SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent(body),
    )


# ─────────────────────────────────────────────────────────────────────────
# A predicate a test asserts on must wait
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("probe", ["is_visible", "get_count"])
def test_a_predicate_built_on_a_non_waiting_probe_is_rejected(probe):
    call = (f"return self.{probe}(self.sel('a_key'))" if probe == "is_visible"
            else f"return self.{probe}(self.sel('a_key')) == 0")
    errors = validate_predicates_wait([_page(f'''
        def is_empty(self) -> bool:
            {call}
    ''')])

    assert len(errors) == 1
    assert "is_empty" in errors[0]
    assert probe in errors[0], "name the probe that has to change"


def test_the_rejection_names_the_waiting_replacement():
    errors = validate_predicates_wait([_page('''
        def is_empty(self) -> bool:
            return self.is_visible(self.sel('a_key'))
    ''')])

    assert "is_showing" in errors[0], (
        "a rejection without the legal alternative is what makes a repair "
        "attempt change nothing"
    )


def test_a_waiting_predicate_passes():
    assert validate_predicates_wait([_page('''
        def is_empty(self) -> bool:
            return self.is_showing(self.sel('a_key'))
    ''')]) == []


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# The non-waiting probes are the RIGHT tool for branching on optional state.
# A rule that banned them outright would cost a full timeout every time a
# banner legitimately is not there, and would be switched off within a week.
# ─────────────────────────────────────────────────────────────────────────

def test_branching_on_optional_state_is_left_alone():
    assert validate_predicates_wait([_page('''
        def dismiss_banner_if_present(self) -> None:
            if self.is_visible(self.sel('banner')):
                self.click(self.sel('banner_close'))
    ''')]) == []


def test_a_method_that_is_not_a_question_is_left_alone():
    """`row_count()` returns a number for a caller to use, not a verdict."""
    assert validate_predicates_wait([_page('''
        def row_count(self) -> int:
            return self.get_count(self.sel('rows'))
    ''')]) == []


def test_a_probe_used_mid_method_is_left_alone():
    """Only a RETURNED probe is judged. A predicate that glances first and
    then waits properly is doing something this check cannot fairly assess,
    and guessing would produce the false positives that kill a validator."""
    assert validate_predicates_wait([_page('''
        def is_ready(self) -> bool:
            if self.is_visible(self.sel('overlay')):
                self.click(self.sel('overlay_close'))
            return self.is_showing(self.sel('panel'))
    ''')]) == []


def test_base_page_itself_is_exempt():
    """The helpers being recommended are defined there."""
    assert validate_predicates_wait([
        SimpleNamespace(file_path="pages/base_page.py", content=textwrap.dedent('''
            class BasePage:
                def is_visible(self, locator):
                    return self._locator(locator).is_visible()
        ''')),
    ]) == []


def test_a_syntax_error_is_not_this_validator_s_business():
    assert validate_predicates_wait([_page("def is_x(self)  ->  bool\n    pass")]) == []


# ─────────────────────────────────────────────────────────────────────────
# Selector keys stay inside the page object
# ─────────────────────────────────────────────────────────────────────────

def test_a_sel_call_in_a_step_definition_is_rejected():
    errors = validate_no_selectors_in_step_defs([_step_def('''
        def assert_link_visible(some_page):
            assert some_page.sel("a_key")
    ''')])

    assert len(errors) == 1
    assert "some_page.sel('a_key')" in errors[0], "quote it back exactly"


def test_a_step_definition_calling_named_methods_passes():
    assert validate_no_selectors_in_step_defs([_step_def('''
        def assert_link_visible(some_page):
            assert some_page.is_link_visible(), "the link should be there"
    ''')]) == []


def test_page_objects_may_call_sel_freely():
    """Break the thing the guard guards. sel() inside a page object is the
    whole point of sel(); scoping this rule to step_defs is what makes it
    safe to enforce."""
    assert validate_no_selectors_in_step_defs([_page('''
        def is_empty(self) -> bool:
            return self.is_showing(self.sel('a_key'))
    ''')]) == []