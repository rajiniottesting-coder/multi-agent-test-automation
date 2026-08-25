"""A missing method that is the OPPOSITE of an existing one is not a typo.

WHAT HAPPENED
    A step definition called `nav_page.wait_until_logged_out()`. The class had
    no such method, and the validator replied:

        Did you mean one of: wait_until_logged_in, is_logged_in, ...?

    Every suggestion asserts the CONTRARY state. A model told to prove a logout
    cannot use a method that proves a login, so it invented another name -
    `is_logged_out()` - was rejected again, and went back to
    `wait_until_logged_out()`. Three generations, oscillating between two
    spellings of a capability the page object did not have. The no-progress
    guard stopped it and the story failed with no pull request.

    The suggestion was not merely unhelpful, it pointed the wrong way. A
    missing counterpart is a MISSING CAPABILITY, and the remedy is to add the
    method - or to say the state cannot be observed - never to substitute its
    opposite.
"""
import pytest

from validators.method_resolution_validator import _opposite_of


@pytest.mark.parametrize("missing,existing,expected", [
    ("wait_until_logged_out", {"wait_until_logged_in"}, "wait_until_logged_in"),
    ("is_logged_out", {"is_logged_in"}, "is_logged_in"),
    ("wait_shown", {"wait_hidden"}, "wait_hidden"),
    ("is_disabled", {"is_enabled"}, "is_enabled"),
    ("assert_absent", {"assert_present"}, "assert_present"),
    ("switch_off", {"switch_on"}, "switch_on"),
])
def test_a_flipped_polarity_is_recognised(missing, existing, expected):
    assert _opposite_of(missing, existing) == expected


@pytest.mark.parametrize("missing,existing", [
    ("click_button", {"click_link", "press_button"}),      # ordinary typo
    ("wait_until_logged_in", {"wait_until_logged_in"}),    # it exists
    ("open_product", {"open_listing"}),                    # different nouns
    ("get_total", set()),                                  # nothing to compare
])
def test_an_ordinary_miss_is_not_treated_as_a_counterpart(missing, existing):
    assert _opposite_of(missing, existing) is None


def test_a_reserved_page_says_the_loop_cannot_win():
    """Ordering matters: for a RESERVED file this must beat the polarity
    message. No rewording of the CALL can help when the file may not be
    edited, and saying so in the FIRST error saves four attempts."""
    from types import SimpleNamespace
    from pathlib import Path
    from validators.method_resolution_validator import validate_method_resolution

    page = SimpleNamespace(file_path="pages/nav_page.py", content=(
        'from pages.base_page import BasePage\n\n\n'
        'class NavPage(BasePage):\n'
        '    INVENTORY_PAGE = "nav"\n\n'
        '    def wait_until_logged_in(self) -> bool:\n        return True\n'))
    step = SimpleNamespace(file_path="tests/step_defs/test_x.py", content=(
        'from pytest_bdd import then\n\n\n'
        '@then("I am signed out")\n'
        'def signed_out(nav_page) -> None:\n'
        '    assert nav_page.wait_until_logged_out()\n'))

    message = " ".join(validate_method_resolution([page, step], Path(".")))
    assert "RESERVED file" in message
    assert "A human has to add" in message
    assert "Do not keep renaming the call" in message


def test_the_message_forbids_substituting_the_opposite():
    """For a page Agent 2 MAY edit, the polarity warning is the right one."""
    from types import SimpleNamespace
    from pathlib import Path
    from validators.method_resolution_validator import validate_method_resolution

    page = SimpleNamespace(file_path="pages/widgets_page.py", content=(
        'from pages.base_page import BasePage\n\n\n'
        'class WidgetsPage(BasePage):\n'
        '    INVENTORY_PAGE = "widgets"\n\n'
        '    def wait_until_logged_in(self) -> bool:\n        return True\n'))
    step = SimpleNamespace(file_path="tests/step_defs/test_x.py", content=(
        'from pytest_bdd import then\n\n\n'
        '@then("I am signed out")\n'
        'def signed_out(widgets_page) -> None:\n'
        '    assert widgets_page.wait_until_logged_out()\n'))

    errors = validate_method_resolution([page, step], Path("."))
    assert errors, "the missing method must still be reported"
    message = " ".join(errors)
    assert "OPPOSITE state" in message
    assert "do not substitute" in message.lower()
    assert "Did you mean" not in message, \
        "offering the counterpart as a correction is what produced the loop"