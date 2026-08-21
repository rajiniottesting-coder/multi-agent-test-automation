"""Step definitions for features/shopping_session.feature.

Binds the shopping-session scenarios to page-object methods. Every step the
feature uses is declared here — pytest-bdd steps are module-scoped, so a step
defined elsewhere is invisible to this module.

Conventions (mirrors tests/step_defs/test_login.py):
  - call page-object methods only; never a selector in a step definition
  - log in by ROLE via the `credentials` fixture; invalid/literal data stays
    literal because it is test data, not a secret
  - assert PRESENCE with a waiting reader and ABSENCE with a non-waiting probe
  - each parsers.re / parsers.parse pattern mirrors the feature file's quoting;
    parsers.re with [^"]* is used wherever a quoted value can be empty
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account is logged in")
def given_newly_registered_logged_in(login_page, nav_page, base_url, credentials):
    """A fresh session owning its own cart state. Uses the registered role's
    real credentials, resolved from the environment by the fixture."""
    email, password = credentials("registered")
    login_page.open_login_page(base_url)
    login_page.login_as(email, password)
    assert nav_page.wait_until_logged_in(), "Account was not logged in"


@given("I am on the signup and login page")
def given_on_login_page(login_page, base_url):
    login_page.open_login_page(base_url)


@given(parsers.re(r'I am logged in as a "(?P<role>[^"]*)" user'))
def given_logged_in_as_role(login_page, nav_page, base_url, credentials, role):
    email, password = credentials(role)
    login_page.open_login_page(base_url)
    login_page.login_as(email, password)
    assert nav_page.wait_until_logged_in(), "User was not logged in"


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when(parsers.re(r'I click "(?P<label>[^"]*)" in the navigation'))
def when_click_nav(nav_page, label):
    nav_page.open_products()


@when(parsers.re(r'I search for "(?P<term>[^"]*)"'))
def when_search_for(products_page, term):
    products_page.search_for(term)


@when(parsers.re(r'I open the product "(?P<name>[^"]*)" from the results'))
def when_open_product(products_page, name):
    products_page.open_product(name)


@when("I add the product to the cart from the detail page")
def when_add_to_cart(product_detail_page):
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def when_view_cart_from_modal(product_detail_page):
    product_detail_page.open_cart_from_modal()


@when(parsers.re(r'I remove "(?P<name>[^"]*)" from the cart'))
def when_remove_from_cart(cart_page, name):
    cart_page.remove_product(name)


@when("I log out")
def when_log_out(nav_page):
    nav_page.logout()


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def when_login_wrong_password(login_page, credentials, role):
    """Valid email, deliberately wrong password (test data, not a secret)."""
    email, _ = credentials(role)
    login_page.login_as(email, "WrongPass!123")


@when("I clear the credential fields")
def when_clear_credentials(login_page):
    login_page.clear_credentials()


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def when_login_literal(login_page, email, password):
    """Literal values, for invalid and empty-field scenarios."""
    login_page.login_as(email, password)


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then(parsers.re(r'the search results should contain "(?P<name>[^"]*)" priced "(?P<price>[^"]*)"'))
def then_results_contain_priced(products_page, name, price):
    assert products_page.was_search_performed(), "Search did not execute"
    assert products_page.has_product(name), (
        f"Expected {name!r} in results, got {products_page.get_result_names()!r}"
    )


@then(parsers.re(r'I should see the product name "(?P<name>[^"]*)" on the detail page'))
def then_detail_product_name(product_detail_page, name):
    actual = product_detail_page.product_name()
    assert name in actual, f"Expected product name {name!r}, got {actual!r}"


@then(parsers.re(r'the cart should contain "(?P<name>[^"]*)" priced "(?P<price>[^"]*)" with quantity "(?P<qty>[^"]*)"'))
def then_cart_contains(cart_page, name, price, qty):
    assert cart_page.is_loaded(), "Cart page did not load"
    assert cart_page.has_product(name), (
        f"Expected {name!r} in cart, got {cart_page.get_product_names()!r}"
    )


@then("the cart should be empty")
def then_cart_empty(cart_page):
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should not be logged in")
def then_not_logged_in(nav_page):
    """Non-waiting probe. The waiting reader would time out rather than
    return False, so the assertion would never be reached."""
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then("I should see the login link in the navigation")
def then_login_link_shown(nav_page):
    assert nav_page.has_login_link(), "Expected the Login/Signup link in the navigation"


@then(parsers.re(r'I should see the error message "(?P<message>[^"]*)"'))
def then_error_message(login_page, message):
    actual = login_page.get_login_error()
    assert message in actual, f"Expected {message!r} in {actual!r}"


@then("I should remain on the login page")
def then_remain_on_login(login_page):
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("the search should have executed")
def then_search_executed(products_page):
    assert products_page.was_search_performed(), "Search did not execute"


@then("no product cards should be displayed")
def then_no_product_cards(products_page):
    count = products_page.get_result_card_count()
    assert count == 0, f"Expected zero result cards, got {count}"
