"""Throw-away validation test on main (window P, removed at its end).

Fails after reaching the home page while WINDOW_P_PASSES is False, so the
nightly defect triage raises a defect (E193: its description names the close
labels; E194: a defect raised by the pipeline in the defect history) and the
Latest run page lists a failed test (E173). The next commit sets it True:
the run passes and the triage comments 'Passed on main' with the close
labels (E193)."""
from pytest_bdd import given, scenarios, then

from config.paths import feature_path

WINDOW_P_PASSES = False

scenarios(str(feature_path("zz_validation_window_p")))


@given("I am on the home page")
def open_home_page(home_page, base_url):
    home_page.open_home_page(base_url)


@then("the throw-away window P check passes once it is switched on")
def fails_until_switched_on(home_page):
    assert home_page.is_loaded()
    assert WINDOW_P_PASSES, "throw-away failure on main (validation window P, E173 E193 E194)"
