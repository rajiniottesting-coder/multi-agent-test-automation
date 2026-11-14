"""Throw-away validation tests on main (window Q, removed at its end).

Group B live checks (TEST_TRACK E202-E211): the passing scenarios carry
markers to throw-away test cases (R3, R4, D2); the @smoke one fails while
Q_SMOKE_PASSES is False (D5 priority, then D4 recurrence); the covered one
fails while Q_COVERED_PASSES is False and a person's Bug covers it (D1)."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

Q_SMOKE_PASSES = False
Q_COVERED_PASSES = True

scenarios(str(feature_path("zz_validation_window_q")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the window Q check passes")
def passes(home_page):
    assert home_page.is_loaded()


@then("the window Q smoke check passes once it is switched on")
def smoke_fails_until_switched_on(home_page):
    assert home_page.is_loaded()
    assert Q_SMOKE_PASSES, "throw-away failure on main (validation window Q, D4 D5)"


@then("the window Q covered check passes once it is switched on")
def covered_fails_until_switched_on(home_page):
    assert home_page.is_loaded()
    assert Q_COVERED_PASSES, "throw-away failure on main (validation window Q, D1)"
