"""A scenario that never signs in owns its persistent state.

The persistent-state gate refuses an exact claim on a page the inventory
marks `persistent_state`, because the application keeps that state against
the SIGNED-IN user and a shared account inherits every earlier run's
leftovers. A scenario that never signs in has no such user: the `page`
fixture opens a fresh browser context per test, so the state starts empty.

SCRUM-111 (every acceptance criterion anonymous) failed Agent 2 because the
gate could not tell the two apart. Covered here:
  - anonymous: an exact count passes
  - any sign of signing in keeps the rule (credentials fixture, login method,
    a signed-in fixture, a shared account named as a string)
  - probing the session (is_logged_in) is not signing in
  - step TEXT saying "not signed in" proves nothing either way
Generic names only; no network, no model.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_persistent_state_assertions


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "pages": {"basket": {"url": "/basket", "page_object_class": "BasketPage",
                             "elements": {"rows": "#rows"}, "persistent_state": True}},
        "test_users": {"member": "A shared, pre-registered account."},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Test App\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")
    return tmp_path


def _check(project, body):
    return validate_persistent_state_assertions(
        [SimpleNamespace(file_path="tests/step_defs/test_flow.py",
                         content=textwrap.dedent(body))], project)


EXACT = '''
    @then('the basket shows "Widget" with quantity 2 and I am not signed in')
    def assert_quantity(basket_page):
        assert basket_page.quantity_of("Widget") == "2"
        assert len(basket_page.item_names()) == 1
'''


def test_an_anonymous_scenario_may_assert_an_exact_state(project):
    assert _check(project, EXACT) == []


@pytest.mark.parametrize("sign_in", [
    "def sign_in(login_page, credentials):\n    login_page.login_as(*credentials('x'))\n",
    "def sign_in(account_page):\n    account_page.sign_in_with_saved_identity()\n",
    "def check(logged_in_page):\n    pass\n",
    "def who(basket_page):\n    basket_page.open_for('member')\n",
    "def ctx(storage_state):\n    pass\n",
])
def test_any_sign_of_signing_in_keeps_the_rule(project, sign_in):
    errors = _check(project, sign_in + EXACT)
    assert errors and "basket_page" in errors[-1]


def test_probing_the_session_is_not_signing_in(project):
    """How an anonymous scenario proves it is anonymous."""
    probe = "def check(nav_page):\n    assert not nav_page.is_logged_in()\n"
    assert _check(project, probe + EXACT) == []


def test_step_text_proves_nothing(project):
    """The decorator says "not signed in" in EXACT and passes; saying "signed
    in" in text alone must not switch the rule on either."""
    assert _check(project, EXACT.replace("I am not signed in", "I signed in earlier")) == []
