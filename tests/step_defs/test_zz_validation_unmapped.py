"""Throw-away validation test on main (reverted in the next cycle): fails after
reaching the home page; no marker traces it to a test case."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_unmapped")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the throw-away check on main fails")
def fails_on_purpose(home_page):
    assert home_page.is_loaded()
    raise AssertionError("throw-away failure on main (validation E42c)")
