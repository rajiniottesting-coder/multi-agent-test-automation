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
    # Cycle 2: another failure text, so its open defect is read under another
    # cause (validation E109).
    raise TimeoutError("Locator.click: Timeout 30000ms exceeded (validation E109)")


@then("the second throw-away check on main fails")
def second_fails_on_purpose(home_page):
    assert home_page.is_loaded()
    raise AssertionError("second throw-away failure on main (validation E31i)")


@then("the throw-away check on main passes only on its second attempt")
def passes_only_on_the_retry(home_page):
    import tempfile
    from pathlib import Path
    assert home_page.is_loaded()
    mark = Path(tempfile.gettempdir()) / "zz_validation_main_flaky.mark"
    if not mark.exists():
        mark.write_text("1", encoding="utf-8")
        raise AssertionError("first attempt fails on purpose (validation E31e)")
