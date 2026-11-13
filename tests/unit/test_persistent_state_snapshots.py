"""C2 (L11): a membership or count read once from a persistent page, in a
signed-in step definition, is a race - the page shows the saved change a
moment after the action. The waiting forms are BasePage.wait_for_row and
wait_for_count, through a page-object method.

Generic: a synthetic inventory with one persistent page.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_persistent_state_snapshots


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "test_users": {"shared_user": {}},
        "pages": {
            "basket": {"url": "/basket", "page_object_class": "BasketPage",
                       "elements": {"rows": "#rows"}, "persistent_state": True},
            "listing": {"url": "/listing", "page_object_class": "ListingPage",
                        "elements": {"cards": ".card"}},
        },
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Test App\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")
    return tmp_path


SIGNED_IN = '''
from pytest_bdd import given, then, parsers

@given("I am signed in")
def signed_in(login_page, credentials):
    login_page.login(credentials)
'''


def _steps(body: str, signed_in: bool = True) -> SimpleNamespace:
    return SimpleNamespace(file_path="tests/step_defs/test_flow.py",
                           content=(SIGNED_IN if signed_in else
                                    "from pytest_bdd import then, parsers\n")
                           + textwrap.dedent(body))


def test_membership_read_into_a_local_is_a_snapshot(project):
    errors = validate_persistent_state_snapshots([_steps('''
        @then(parsers.parse('the basket shows "{item}"'))
        def basket_shows(basket_page, item):
            names = basket_page.item_names()
            assert item in names
    ''')], project)
    assert len(errors) == 1
    e = errors[0]
    assert e.startswith("Persistent state snapshot error in 'tests/step_defs/test_flow.py' line")
    assert "wait_for_row" in e and "present=True" in e and "'basket'" in e


def test_absence_inline_asks_for_present_false(project):
    (e,) = validate_persistent_state_snapshots([_steps('''
        @then(parsers.parse('"{item}" is gone from the basket'))
        def gone(basket_page, item):
            assert item not in basket_page.item_names()
    ''')], project)
    assert "present=False" in e


def test_a_count_of_owned_state_read_once_is_a_snapshot(project):
    """The absolute-state check exempts a scenario that clears first; the
    count it then asserts is still read once."""
    (e,) = validate_persistent_state_snapshots([_steps('''
        @given("the basket is empty")
        def empty(basket_page):
            basket_page.clear_basket()

        @then(parsers.parse("the basket holds {n:d} items"))
        def holds(basket_page, n):
            assert basket_page.row_count() == n
    ''')], project)
    assert "wait_for_count" in e and "a count" in e


def test_an_absolute_claim_is_reported_once_by_the_absolute_check(project):
    """Unowned state: the absolute check reports `len(...) == n`; C2 does not
    report the same line again."""
    from validators.method_resolution_validator import validate_persistent_state_assertions
    files = [_steps('''
        @then(parsers.parse("the basket holds {n:d} items"))
        def holds(basket_page, n):
            assert len(basket_page.item_names()) == n
    ''')]
    assert len(validate_persistent_state_assertions(files, project)) == 1
    assert validate_persistent_state_snapshots(files, project) == []


@pytest.mark.parametrize("body", [
    # a waiting page-object method
    '''
    @then(parsers.parse('the basket shows "{item}"'))
    def shows(basket_page, item):
        basket_page.wait_for_item(item)
    ''',
    # a predicate that waits
    '''
    @then(parsers.parse('the basket shows "{item}"'))
    def shows(basket_page, item):
        assert basket_page.has_item(item)
    ''',
    # waited first, then read
    '''
    @then(parsers.parse('the basket shows "{item}"'))
    def shows(basket_page, item):
        basket_page.wait_for_item(item)
        assert item in basket_page.item_names()
    ''',
    # a page that keeps no state
    '''
    @then(parsers.parse('the listing shows "{item}"'))
    def shows(listing_page, item):
        assert item in listing_page.card_titles()
    ''',
])
def test_waiting_forms_and_other_pages_pass(project, body):
    assert validate_persistent_state_snapshots([_steps(body)], project) == []


def test_an_anonymous_file_owns_its_state(project):
    assert validate_persistent_state_snapshots([_steps('''
        @then(parsers.parse('the basket shows "{item}"'))
        def shows(basket_page, item):
            assert item in basket_page.item_names()
    ''', signed_in=False)], project) == []


def test_no_persistent_page_no_check(tmp_path):
    assert validate_persistent_state_snapshots([_steps('''
        @then("x")
        def x(basket_page):
            assert "a" in basket_page.item_names()
    ''')], tmp_path) == []


def test_agent2_runs_it_beside_the_absolute_check():
    src = (Path(__file__).resolve().parents[2] / "agents/agent2_coder.py").read_text()
    i = src.index("errors.extend(validate_persistent_state_assertions(")
    assert src.index("errors.extend(validate_persistent_state_snapshots(") > i
