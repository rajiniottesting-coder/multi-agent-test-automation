"""Step definitions for features/test_cases_search.feature.

Binds the Test Cases keyword-search scenarios to TestCasesPage methods.

Every step the feature uses is declared here — steps are module-scoped, so a
step defined elsewhere is not visible to this module. Page-object methods are
the only way these steps touch the UI; no selectors appear here. Presence is
asserted with waiting readers, absence with a non-waiting predicate.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("test_cases_search")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("I am on the Test Cases page")
def open_test_cases(test_cases_page, base_url):
    test_cases_page.open_test_cases(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I search the test cases for a distinctive word from the first title")
def search_distinctive_word(test_cases_page):
    """Capture the baseline titles, take a distinctive word from the first,
    stash both on the page object, and run the search."""
    baseline = test_cases_page.title_texts()
    assert baseline, "Expected a baseline list of test case titles"
    first_title = baseline[0]

    generic = {"test", "case", "of", "the", "and", "for", "to", "a", "an", "in", "on"}
    keyword = None
    for raw in first_title.split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if len(token) >= 4 and token.casefold() not in generic:
            keyword = token
            break
    assert keyword, f"No distinctive word found in first title {first_title!r}"

    test_cases_page.search_test_cases_for(keyword)

    # Remember for the Then steps.
    test_cases_page._search_baseline = baseline
    test_cases_page._search_keyword = keyword
    test_cases_page._search_first_title = first_title


@when(parsers.parse('I search the test cases for "{keyword}"'))
def search_for_keyword(test_cases_page, keyword):
    test_cases_page.search_test_cases_for(keyword)


@when("I clear the keyword and search the test cases again")
def clear_keyword_and_search(test_cases_page):
    test_cases_page.clear_keyword_and_search()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("every displayed test case title should contain that word")
def assert_titles_contain_word(test_cases_page):
    keyword = test_cases_page._search_keyword
    displayed = test_cases_page.title_texts()
    assert displayed, f"Expected at least one title containing {keyword!r}"
    for title in displayed:
        assert keyword.casefold() in title.casefold(), (
            f"Title {title!r} does not contain the keyword {keyword!r}"
        )


@then("a title lacking that word should not be shown on the Test Cases page")
def assert_no_nonmatching_title_shown(test_cases_page):
    keyword = test_cases_page._search_keyword
    displayed = test_cases_page.title_texts()
    non_matching = [
        title for title in displayed if keyword.casefold() not in title.casefold()
    ]
    assert not non_matching, (
        f"These displayed titles do not contain {keyword!r}: {non_matching!r}"
    )


@then("the first title should still be displayed among the results")
def assert_first_title_still_displayed(test_cases_page):
    first_title = test_cases_page._search_first_title
    displayed = test_cases_page.title_texts()
    assert any(
        first_title.casefold() == t.casefold() for t in displayed
    ), f"Expected {first_title!r} among the filtered results, got {displayed!r}"


@then("no test case titles should be displayed")
def assert_no_titles_displayed(test_cases_page):
    assert test_cases_page.is_titles_absent(), (
        "Expected no test case titles to be displayed"
    )


@then("the full baseline list of test case titles should be displayed")
def assert_baseline_restored(test_cases_page):
    baseline = test_cases_page._search_baseline
    restored = test_cases_page.title_texts()
    assert restored == baseline, (
        f"Expected the baseline list to reappear.\n"
        f"Baseline: {baseline!r}\nRestored: {restored!r}"
    )
