"""Throw-away validation tests (window T, removed at its end).

Live checks of the reports pages (TEST_TRACK E228-E239): one scenario fails
while its story awaits its deployment (expected), the other passes on the
first run on main and fails on the second (a real failure the triage raises a
defect for), so the Latest run shows the defect, the expected failure and
what changed since the run before."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_window_t")))

# Flipped to True by the window's second pull request.
STARTS_FAILING = True


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the window T check waits for its deployment")
def waits_for_its_deployment(home_page):
    assert home_page.is_loaded()
    assert False, "throw-away failure (validation window T): the change is not deployed yet"


@then("the window T check that starts failing holds")
def starts_failing(home_page):
    assert home_page.is_loaded()
    assert not STARTS_FAILING, "throw-away failure (validation window T): failing on purpose"
