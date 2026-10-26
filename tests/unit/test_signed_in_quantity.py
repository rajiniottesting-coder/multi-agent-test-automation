"""An exact quantity on persistent state is refused by BOTH gates, in the same place.

SCRUM-187 (validation, 26 Oct 2026): Agent 1 drafted "the cart page shows a row
for '<item>' with quantity 1" in a test case that signs in as the inventory's
shared account. Agent 1's check let it through - it looked only for "exactly",
"only", a row count and "empty" - a person approved it, and Agent 2's gate then
refused every way of coding it: the state is kept against the account, so a
run that died before removing '<item>' leaves it there and the next run reads 2.
Four repair attempts, the same rule each time, the story failed - and the scan
retried it every 30 minutes.

The two gates disagreed about one sentence. Here they are held to the same line:
  - signed in with a shared account + exact quantity on a persistent page:
    Agent 1 rejects the test case, Agent 2 rejects the code;
  - never signed in: both accept (a fresh session starts empty);
  - "is present" with no number: both accept.
Generic names only; the inventory is synthetic. No network, no model.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.schemas import TestCase, TestStep
from core.test_case_rules import (
    _EXACT_QUANTITY,
    draft_problems,
    persistent_pages,
    shared_accounts,
    test_case_problems,
)
from validators.method_resolution_validator import validate_persistent_state_assertions

for _cls in (TestCase, TestStep):
    _cls.__test__ = False
test_case_problems.__test__ = False

INVENTORY = {
    "pages": {"basket": {"url": "/basket", "page_object_class": "BasketPage",
                         "elements": {"rows": "#rows"}, "persistent_state": True},
              "widget_detail": {"url": "/widget_detail/{id}"}},
    "test_users": {"member": "A shared, pre-registered account."},
}
PERSISTENT = persistent_pages(INVENTORY)
ACCOUNTS = shared_accounts(INVENTORY)


def _tc(pre, expected, data=None):
    return TestCase(title="[Positive] Add a widget", description="d", priority="High",
                    test_type="Positive", preconditions=list(pre),
                    steps=[TestStep(step_number=1, action="Open the basket",
                                    expected_result=expected)],
                    expected_outcome="It works.", test_data=data)


SIGNED_IN = ["Credentials for the `member` role are available"]
ANONYMOUS = ["Shopper is not logged in", "Browser session is fresh, so the basket starts empty"]
QUANTITY = "The basket shows a row for 'Blue Widget' with quantity 1"
PRESENT = "The basket shows a row for 'Blue Widget'"


# ─────────────────────────────────────────────────────────────
# Agent 1's rule
# ─────────────────────────────────────────────────────────────
def test_a_signed_in_exact_quantity_is_rejected():
    problems = test_case_problems(_tc(SIGNED_IN, QUANTITY), PERSISTENT, ACCOUNTS)
    assert len(problems) == 1
    assert "exact quantity" in problems[0] and "'member'" in problems[0]
    assert "basket" in problems[0]


def test_a_test_data_account_counts_as_signing_in():
    tc = _tc(["A registered shopper"], QUANTITY, data={"login_role": "member"})
    assert test_case_problems(tc, PERSISTENT, ACCOUNTS)


@pytest.mark.parametrize("expected", [
    QUANTITY,
    "The basket row for 'Blue Widget' shows a quantity of 2",
    "The basket shows 'Blue Widget', qty: 3",
    "The basket holds 2 items of 'Blue Widget'",
    "The basket row for 'Blue Widget' has a total of 1500",
])
def test_every_way_of_stating_a_quantity_is_found(expected):
    assert _EXACT_QUANTITY.search(expected)
    assert test_case_problems(_tc(SIGNED_IN, expected), PERSISTENT, ACCOUNTS)


def test_an_anonymous_test_case_may_state_a_quantity():
    """The change-story walkthrough's tests are anonymous and keep their quantities."""
    assert test_case_problems(_tc(ANONYMOUS, QUANTITY), PERSISTENT, ACCOUNTS) == []


def test_not_logged_in_is_not_read_as_signing_in():
    tc = _tc(["Shopper is not logged in; no member account is used"], QUANTITY)
    assert test_case_problems(tc, PERSISTENT, ACCOUNTS) == []


def test_presence_without_a_number_is_fine_when_signed_in():
    assert test_case_problems(_tc(SIGNED_IN, PRESENT), PERSISTENT, ACCOUNTS) == []


def test_a_quantity_on_a_page_that_keeps_no_state_is_fine():
    tc = _tc(SIGNED_IN, "The widget detail page shows quantity 1 selected")
    assert test_case_problems(tc, PERSISTENT, ACCOUNTS) == []


def test_without_accounts_the_rule_is_off_as_before():
    assert test_case_problems(_tc(SIGNED_IN, QUANTITY), PERSISTENT) == []
    assert draft_problems([_tc(SIGNED_IN, QUANTITY)], PERSISTENT) == []


def test_the_real_inventory_declares_its_shared_accounts():
    from core.test_case_rules import load_shared_accounts
    assert isinstance(load_shared_accounts(), list)


# ─────────────────────────────────────────────────────────────
# Agent 2's gate draws the line in the same place
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps(INVENTORY), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Test App\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")
    return tmp_path


QUANTITY_STEP = '''
    @then(parsers.parse('the basket shows "{name}" with quantity {quantity:d}'))
    def assert_quantity(basket_page, name, quantity):
        assert basket_page.quantity_of(name) == quantity
'''
PRESENT_STEP = '''
    @then(parsers.parse('the basket shows "{name}"'))
    def assert_present(basket_page, name):
        assert name in basket_page.item_names()
'''
SIGN_IN_STEP = '''
    @given("I am signed in")
    def sign_in(login_page, credentials):
        login_page.login_as(*credentials("member"))
'''


def _agent2(project, body):
    return validate_persistent_state_assertions(
        [SimpleNamespace(file_path="tests/step_defs/test_flow.py",
                         content=textwrap.dedent(body))], project)


@pytest.mark.parametrize("pre, agent2_body", [
    (SIGNED_IN, SIGN_IN_STEP + QUANTITY_STEP),
    (ANONYMOUS, QUANTITY_STEP),
])
def test_both_gates_agree_on_a_quantity(project, pre, agent2_body):
    agent1_rejects = bool(test_case_problems(_tc(pre, QUANTITY), PERSISTENT, ACCOUNTS))
    agent2_rejects = bool(_agent2(project, agent2_body))
    assert agent1_rejects == agent2_rejects


def test_the_remedy_agent1_asks_for_passes_agent2(project):
    """Drop the number: Agent 1 accepts it, and the code for it passes Agent 2."""
    assert test_case_problems(_tc(SIGNED_IN, PRESENT), PERSISTENT, ACCOUNTS) == []
    assert _agent2(project, SIGN_IN_STEP + PRESENT_STEP) == []
