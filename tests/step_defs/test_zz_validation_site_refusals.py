"""Throw-away validation tests (never merged) - E15.

1. The site answers the first page load with HTTP 503 and the next one
   normally: the page object's navigation retries ("succeeded on attempt 2").
2. On the test's first attempt every page load is refused, so the test fails
   naming HTTP 503 and the run re-runs it; the re-run is not refused and
   passes ("Keep only the final attempt" lists it, Agent 5 counts it once).
"""
import tempfile
from pathlib import Path

from pytest_bdd import given, scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_site_refusals")))

_MARK = Path(tempfile.gettempdir()) / "zz_validation_refusal.mark"


def _refuse(page, times):
    left = {"n": times}

    def handler(route):
        if route.request.resource_type == "document" and left["n"] != 0:
            left["n"] -= 1
            route.fulfill(status=503, body="Service Unavailable")
        else:
            route.continue_()
    page.route("**/*", handler)


@given("the throw-away site refuses the next page load once")
def refuse_once(page):
    _refuse(page, 1)


@given("the throw-away site refuses every page load on the first attempt only")
def refuse_first_attempt(page):
    if not _MARK.exists():
        _MARK.write_text("1", encoding="utf-8")
        _refuse(page, -1)


@then("the throw-away Test Cases page loads")
def page_loads(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)
