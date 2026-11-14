"""Throw-away validation test (window S, never merged).

X6 live check (TEST_TRACK E226): this scenario fails on purpose. Its story
awaits its deployment, so Agent 4's Run Tests check passes with a notice;
without that label the same failure turns the check red."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_window_s")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the window S check waits for its deployment")
def waits_for_its_deployment(home_page):
    assert home_page.is_loaded()
    assert False, "throw-away failure (validation window S, X6): the change is not deployed yet"
