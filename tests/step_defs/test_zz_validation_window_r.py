"""Throw-away validation tests (window R, removed at its end).

Group B batch B2 live checks (TEST_TRACK E215-E218): on its pull request the
selection runs these two scenarios and the smoke set (X1); the failing one is
raised as a defect by the raise-defect label (D6), then - its story awaiting
deployment - is expected on main until the deployment signal (X4)."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_window_r")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the window R check passes")
def passes(home_page):
    assert home_page.is_loaded()


@then("the window R check finds the application bug")
def finds_the_bug(home_page):
    assert home_page.is_loaded()
    assert False, "throw-away failure (validation window R, D6 X4)"
