"""Two checks the generation gate should have made and didn't.

WHAT HAPPENED
    A page object shipped with two raw selector literals:

        row = self.row_containing(self.sel("table_rows"), name)
        return row.locator(".row-quantity").inner_text().strip()

    The generation gate passed it. The committed-tree scan then failed the
    build. Both checks exist to enforce the same rule, and the comment above
    the generation-time pattern said so:

        "Deliberately the SAME shape as tests/unit/test_page_object_selectors
         .py — the two must agree, or generation passes and the unit gate
         still fails."

    They did not agree. The generation-time version required an ASSIGNMENT
    (`= "..."`), so a literal handed straight to a call was invisible to it.
    The exact failure its own comment predicted.

    A comment asserting that two patterns agree is a wish. This file makes it
    a test: both patterns are run against the same corpus and must return the
    same verdict on every line.

AND THE ONE NOBODY WAS CHECKING
    The same review found `assert actual == quantity`, where the step
    decorator parses `{quantity:d}` as an int and the page-object reader is
    annotated `-> str`. `"2" == 2` is always False.

    That is the worst shape a test can have: it does not error and it does not
    flake. It fails every single run, including when the application is
    perfectly correct — so the failure points at the app, and the app is fine.
    Both halves are declared, so nothing has to be inferred.
"""
import re
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import (
    _SELECTOR_LITERAL_RE,
    validate_page_object_selectors,
    validate_step_parameter_types,
)

_PROJECT = Path(__file__).resolve().parents[2]


def _page(body: str) -> SimpleNamespace:
    return SimpleNamespace(file_path="pages/widget_page.py", content=(
        "from pages.base_page import BasePage\n\n\n"
        "class WidgetPage(BasePage):\n"
        '    INVENTORY_PAGE = "widget"\n\n'
        + textwrap.indent(textwrap.dedent(body).strip("\n"), "    ") + "\n"
    ))


# ─────────────────────────────────────────────────────────────────────────
# The two literal patterns must agree, line for line
# ─────────────────────────────────────────────────────────────────────────

_CORPUS = [
    # (line, is_a_literal_selector)
    ('    return row.locator(".row-quantity").inner_text()', True),
    ('    return row.locator("#total").inner_text()', True),
    ('    self.click("[data-qa=submit]")', True),
    ('    LOGIN = ".login-form"', True),
    ("    cell = row.locator('.price')", True),
    ('    self.click(self.sel("add_button"))', False),
    ('    self.navigate(base_url + "/basket")', False),
    ('    return self.get_text(self.sel("total"))', False),
    ('    name = "a plain string"', False),
    ("    return self.sel('cart_rows')", False),
]


def _unit_test_pattern():
    """The committed-tree scan's own pattern, read from its module."""
    import importlib
    mod = importlib.import_module("tests.unit.test_page_object_selectors")
    return mod._SELECTOR_LITERAL


@pytest.mark.parametrize("line,is_literal", _CORPUS)
def test_both_literal_patterns_reach_the_same_verdict(line, is_literal):
    gate = bool(_SELECTOR_LITERAL_RE.search(line))
    committed = bool(_unit_test_pattern().search(line))

    assert gate == committed, (
        f"the two selector-literal patterns disagree on {line.strip()!r}: "
        f"generation gate says {gate}, committed-tree scan says {committed}. "
        f"When the gate is the lenient one, the code ships and the build fails "
        f"afterwards - which is what happened."
    )
    assert gate == is_literal, (
        f"{line.strip()!r} should{'' if is_literal else ' not'} read as a "
        f"selector literal"
    )


def test_the_literal_that_shipped_is_now_rejected_at_generation():
    """Break the thing the guard guards: the exact two lines from the run."""
    errors = validate_page_object_selectors([_page('''
        def get_quantity(self, name: str) -> str:
            row = self.row_containing(self.sel("rows"), name)
            return row.locator(".row-quantity").inner_text().strip()
    ''')], _PROJECT)

    assert errors, "the generation gate still misses a literal on a chained locator"
    assert "row-quantity" in errors[0]


def test_inventory_keys_and_urls_are_not_mistaken_for_selectors():
    """The pattern got wider. If it got too wide, every correct page object
    would be rejected and the check would be turned off within a day.

    Only the LITERAL half is under test here - this page object names a page
    that is not in whatever inventory the repo is pointed at, and that is a
    different (correct) complaint.
    """
    errors = validate_page_object_selectors([_page('''
        def open_widget(self, base_url: str) -> None:
            self.navigate(base_url + "/widgets")

        def names(self):
            return self.get_all_texts(self.sel("widget_names"))
    ''')], _PROJECT)

    literals = [e for e in errors if "literal selector" in e]
    assert not literals, literals


# ─────────────────────────────────────────────────────────────────────────
# A parsed parameter compared against a mistyped reader
# ─────────────────────────────────────────────────────────────────────────

_READER = SimpleNamespace(file_path="pages/widget_page.py", content=textwrap.dedent('''
    from pages.base_page import BasePage


    class WidgetPage(BasePage):
        INVENTORY_PAGE = "widget"

        def get_quantity(self, name: str) -> str:
            return self.get_text(self.sel("quantity"))

        def get_row_count(self) -> int:
            return self.get_count(self.sel("rows"))
'''))


def _steps(body: str) -> SimpleNamespace:
    return SimpleNamespace(file_path="tests/step_defs/test_widget.py",
                           content=textwrap.dedent(body))


def test_an_int_parameter_against_a_str_reader_is_rejected():
    errors = validate_step_parameter_types([_READER, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            actual = widget_page.get_quantity(name)
            assert actual == quantity
    ''')], _PROJECT)

    assert len(errors) == 1
    message = errors[0]
    assert "int" in message and "str" in message, "name both types"
    assert "ALWAYS False" in message, (
        "say that it fails even when the application is correct - that is the "
        "whole reason this one is worth catching statically"
    )


def test_the_same_bug_written_inline_is_rejected():
    assert validate_step_parameter_types([_READER, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''')], _PROJECT)


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("body,why", [
    ('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == str(quantity)
    ''', "an explicit cast is the fix, and must not be flagged"),
    ('''
        @then(parsers.parse("the list holds {count:d} rows"))
        def assert_rows(widget_page, count):
            assert widget_page.get_row_count() == count
    ''', "int reader against int parameter is correct"),
    ('''
        @then(parsers.parse("the quantity should be {quantity}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''', "an untyped placeholder is a string on both sides"),
    ('''
        @then(parsers.parse("row {n:d} is present"))
        def assert_present(widget_page, n, name):
            assert name in widget_page.get_names()
    ''', "membership is not an equality comparison"),
])
def test_correct_comparisons_are_left_alone(body, why):
    assert validate_step_parameter_types([_READER, _steps(body)], _PROJECT) == [], why


def test_an_unannotated_reader_is_not_guessed_at():
    """No return annotation means no declared type. Inferring one would produce
    the false positives that get a validator switched off."""
    unannotated = SimpleNamespace(file_path="pages/widget_page.py", content=textwrap.dedent('''
        class WidgetPage:
            def get_quantity(self, name):
                return "2"
    '''))
    assert validate_step_parameter_types([unannotated, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''')], _PROJECT) == []