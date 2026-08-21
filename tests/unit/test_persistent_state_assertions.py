"""An absolute assertion on state the application keeps between runs.

WHAT HAPPENED
    From the trace, unambiguously: one add-to-cart click in the whole run, one
    item added, and the collection read half a second after arriving held two.
    The second was left behind by a previous run against the same shared
    account.

        AssertionError: Expected exactly 1 product(s), got ['A', 'B']
        assert 2 == 1

    No wait fixes that. The retrying count helper added for an earlier failure
    would have retried for thirty seconds and found the same leftover, because
    the leftover is really there. The scenario asserted an ABSOLUTE number
    against state it did not create and does not own.

WHY THIS IS A GATE AND NOT GUIDANCE
    It was guidance, in the context modules, for months. It was regenerated
    away every time. A model reading "assert relatively" alongside a test case
    that says "should contain exactly one" writes what the test case says, and
    that is not unreasonable of it - the test case is the requirement.

    So the requirement has to be met a different way: the scenario registers
    its own account, or it clears the state in a Given. Both are things the
    generator can do. Neither is something it will do because a paragraph
    asked nicely.

THE RULE IS DECLARED, NOT ASSUMED
    It fires only where the INVENTORY says a page holds state that survives
    the run. An application without shared per-user state is untouched; one
    that has it says so in the inventory, which is where app knowledge lives.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import (
    validate_persistent_state_assertions,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project whose inventory declares one persistent page and one not."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "pages": {
            "basket": {
                "url": "/basket",
                "page_object_class": "BasketPage",
                "elements": {"rows": "#rows"},
                "persistent_state": True,
            },
            "listing": {
                "url": "/listing",
                "page_object_class": "ListingPage",
                "elements": {"cards": ".card"},
            },
        },
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n"
        "  name: Test App\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    return tmp_path


def _steps(body: str) -> SimpleNamespace:
    return SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent(body),
    )


# ─────────────────────────────────────────────────────────────────────────
# The shapes that must be rejected
# ─────────────────────────────────────────────────────────────────────────

def test_a_count_read_into_a_local_is_still_absolute(project):
    """The exact code that shipped. It never names the fixture inside the
    assertion - it reads into a local first - which is how the first draft of
    this validator passed it."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_item_count(basket_page, count):
            names = basket_page.item_names()
            assert len(names) == count, f"Expected exactly {count}, got {names}"
    ''')], project)

    assert len(errors) == 1
    assert "basket_page" in errors[0]
    assert "'basket'" in errors[0], "name the page whose state persists"


def test_an_emptiness_assertion_is_absolute(project):
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty(), "Expected it to be empty"
    ''')], project)
    assert len(errors) == 1


def test_the_rejection_offers_both_remedies(project):
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    message = errors[0].lower()

    assert "register" in message and "clear" in message, "how to own the state"
    assert "relative" in message, "or how to avoid needing to"
    assert "wait" in message, (
        "say that waiting will not help - the previous failure's remedy is "
        "the obvious wrong turn here"
    )


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# Every one of these is legitimate code. A validator that rejected them would
# make relative assertions impossible to write and would be turned off.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("assertion", [
    "assert item_name in basket_page.item_names()",
    "assert item_name not in basket_page.item_names()",
    "assert any(item_name in row for row in basket_page.rows())",
])
def test_relative_assertions_are_allowed(project, assertion):
    errors = validate_persistent_state_assertions([_steps(f'''
        def assert_state(basket_page, item_name):
            {assertion}
    ''')], project)
    assert errors == [], f"{assertion!r} holds whatever the state started as"


def test_a_scenario_that_clears_the_state_may_assert_absolutely(project):
    assert validate_persistent_state_assertions([_steps('''
        def given_empty(basket_page):
            basket_page.remove_all_items()

        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


def test_a_scenario_that_registers_its_own_account_may_assert_absolutely(project):
    assert validate_persistent_state_assertions([_steps('''
        def given_fresh(signup_page, unique_username):
            signup_page.register(unique_username)

        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


def test_the_assertion_is_not_read_as_its_own_remedy(project):
    """`is_empty` contains the word 'empty'. An earlier draft matched it as a
    state-clearing call and skipped the file - passing the exact code it was
    written to stop. Only a call made for its EFFECT counts."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    assert len(errors) == 1


def test_a_page_without_persistent_state_is_untouched(project):
    assert validate_persistent_state_assertions([_steps('''
        def assert_results(listing_page):
            assert listing_page.result_count() == 3
    ''')], project) == []


def test_an_application_declaring_nothing_persistent_is_untouched(tmp_path):
    """The default. Adding this check must not change any application that has
    not opted into it."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "T",
        "pages": {"basket": {"url": "/b", "page_object_class": "BasketPage",
                             "elements": {}}},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: T\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")

    assert validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path) == []


def test_page_objects_are_not_judged_only_step_definitions(project):
    """A page object comparing counts internally is its own business."""
    assert validate_persistent_state_assertions([SimpleNamespace(
        file_path="pages/basket_page.py",
        content=textwrap.dedent('''
            class BasketPage:
                def is_empty(self) -> bool:
                    return len(self.item_names()) == 0
        '''),
    )], project) == []


def test_an_unreadable_inventory_disables_the_check(tmp_path):
    """A validator must never be the reason a run dies."""
    assert validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path) == []


def test_the_mapping_survives_a_page_object_that_was_not_regenerated(project):
    """ai-update regenerates step definitions without their page objects. A
    check that only read generated files would find no mapping and silently
    pass - so the fixture name comes from the inventory's own
    page_object_class."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    assert len(errors) == 1, "no page object was supplied, and it still fired"