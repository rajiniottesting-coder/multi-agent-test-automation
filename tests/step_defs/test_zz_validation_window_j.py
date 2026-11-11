"""Throw-away validation test on main (window J, removed at its end): fails
after reaching the home page, so the defect triage on main has a failure to
record (E31h)."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_window_j")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the throw-away window J check fails")
def fails_on_purpose(home_page):
    assert home_page.is_loaded()
    raise AssertionError("throw-away failure on main (validation window J, E31h)")
