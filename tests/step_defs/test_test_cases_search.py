"""Step definitions for features/test_cases_search.feature.

Binds the test_cases_search feature steps to TestCasesPage methods.

Conventions followed (see pages/login_page.py and tests/step_defs/test_login.py):
- Declare EVERY step the feature uses in this file; steps are module-scoped.
- Call page-object methods only — never a selector in a step definition.
- Assert PRESENCE with a waiting reader, ABSENCE with a non-waiting probe.
- The noted word/title flows between steps via a mutable context fixture.
"""
import pytest
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_search")))


# ─────────────────────────────────────────────────────────────
# Shared scenario context — carries the noted word/title between steps
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def search_context() -> dict:
    return {}


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the Test Cases page")
def open_test_cases(test_cases_page, base_url) -> None:
    test_cases_page.open_test_cases(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I note a distinctive word from the first test case title")
def note_distinctive_word(test_cases_page, search_context) -> None:
    title = test_cases_page.first_title_text()
    word = title.strip().split()[0]
    search_context["title"] = title
    search_context["word"] = word


@when("I note a test case title that does not contain that word")
def note_non_matching_title(test_cases_page, search_context) -> None:
    word = search_context["word"]
    non_matching = next(
        (t for t in test_cases_page.all_titles() if word.casefold() not in t.casefold()),
        None,
    )
    assert non_matching is not None, (
        f"Expected at least one title that does not contain {word!r}, "
        f"got {test_cases_page.all_titles()!r}"
    )
    search_context["non_matching_title"] = non_matching


@when("I type that word into the test case search box")
def type_noted_word(test_cases_page, search_context) -> None:
    test_cases_page.search_for_test_case(search_context["word"])


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the Test Cases page should be headed "(?P<expected>[^"]*)"'))
def assert_heading(test_cases_page, expected) -> None:
    assert test_cases_page.heading_matches(expected), (
        f"Expected the Test Cases heading to be {expected!r}, "
        f"got {test_cases_page.heading_text()!r}"
    )


@then("the test case search box should be displayed")
def assert_search_box_displayed(test_cases_page) -> None:
    assert test_cases_page.has_search_box(), (
        "Expected the test case search box to be displayed"
    )


@then("every test case title shown should contain that word")
def assert_titles_contain_word(test_cases_page, search_context) -> None:
    word = search_context["word"]
    assert test_cases_page.shown_titles_all_contain(word), (
        f"Expected every shown title to contain {word!r}, "
        f"got {test_cases_page.all_titles()!r}"
    )


@then("the originally noted title should still be shown")
def assert_noted_title_still_shown(test_cases_page, search_context) -> None:
    title = search_context["title"]
    assert test_cases_page.shows_title(title), (
        f"Expected the originally noted title {title!r} to still be shown, "
        f"got {test_cases_page.all_titles()!r}"
    )


@then("the non-matching title should not be shown on the Test Cases page")
def assert_non_matching_title_absent(test_cases_page, search_context) -> None:
    non_matching = search_context["non_matching_title"]
    assert not test_cases_page.shows_title(non_matching), (
        f"Expected the non-matching title {non_matching!r} to no longer be shown, "
        f"got {test_cases_page.all_titles()!r}"
    )
