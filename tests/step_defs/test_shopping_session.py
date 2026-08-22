"""Step definitions for features/shopping_session.feature.

Binds the shopping-session steps to page-object methods only. Selectors never
appear here — every UI interaction goes through a page-object method. Presence
is asserted with waiting readers; absence with non-waiting probes.

The "newly registered account" scenario owns its starting state so the cart's
absolute emptiness assertions are deterministic on this shared, persistent-cart
site. A fresh account is created here via the signup forms rather than through a
nonexistent fixture: the run-unique identity comes from unique_username.
"""
from pytest_bdd import given, when, then, parsers, scenarios

from config.paths import feature_path

scenarios(str(feature_path("shopping_session")))


# A run-unique password derived from the run's unique username. Not a real
# credential for any pre-existing account — it is created fresh in this run.
def _new_account_password(unique_username: str) -> str:
    return f"Pw!{unique_username}9"


def _new_account_email(unique_username: str) -> str:
    return f"{unique_username}@example.com"


# ─────────────────────────────────────────────────────────────
# Given
# ─────────────────────────────────────────────────────────────

@given("a newly registered account")
def register_new_account(login_page, base_url, unique_username) -> None:
    """Own the starting state: create a fresh account so cart assertions on an
    absolute empty state are deterministic on this shared, persistent-cart
    site. Uses run-unique identity so parallel/repeat runs never collide."""
    login_page.open_login_page(base_url)
    login_page.start_signup(unique_username, _new_account_email(unique_username))


@given("I am on the signup and login page")
def open_login_page(login_page, base_url) -> None:
    login_page.open_login_page(base_url)


# ─────────────────────────────────────────────────────────────
# When
# ─────────────────────────────────────────────────────────────

@when("I log in as the newly registered user")
def login_as_new_user(login_page, base_url, unique_username) -> None:
    login_page.open_login_page(base_url)
    login_page.login_as(
        _new_account_email(unique_username),
        _new_account_password(unique_username),
    )


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user$'))
def login_as_role(login_page, credentials, role) -> None:
    email, password = credentials(role)
    login_page.login_as(email, password)


@when(parsers.re(r'I log in as a "(?P<role>[^"]*)" user with an incorrect password'))
def login_as_role_wrong_password(login_page, credentials, role) -> None:
    email, _ = credentials(role)
    login_page.login_as(email, "definitely-not-the-password")


@when(parsers.re(r'I log in with email "(?P<email>[^"]*)" and password "(?P<password>[^"]*)"'))
def login_with_literal_credentials(login_page, email, password) -> None:
    login_page.login_as(email, password)


@when("I clear the credential fields")
def clear_credentials(login_page) -> None:
    login_page.clear_credentials()


@when("I open the products page")
def open_products(nav_page) -> None:
    nav_page.open_products()


@when(parsers.parse('I search for "{term}"'))
def search_for(products_page, term) -> None:
    products_page.search_for(term)


@when(parsers.parse('I open the product "{product_name}" from the search results'))
def open_product(products_page, product_name) -> None:
    products_page.open_product(product_name)


@when("I add the product to the cart")
def add_product_to_cart(product_detail_page) -> None:
    product_detail_page.add_product_to_cart()


@when("I view the cart from the modal")
def view_cart_from_modal(product_detail_page) -> None:
    product_detail_page.view_cart_via_modal()


@when(parsers.parse('I remove the product "{product_name}" from the cart'))
def remove_product(cart_page, product_name) -> None:
    cart_page.remove_product(product_name)


@when("I log out")
def log_out(nav_page) -> None:
    nav_page.logout()


# ─────────────────────────────────────────────────────────────
# Then
# ─────────────────────────────────────────────────────────────

@then("I should be logged in")
def assert_logged_in(nav_page) -> None:
    assert nav_page.wait_until_logged_in(), "No session after logging in"


@then("I should see my account name in the navigation")
def assert_account_name_shown(nav_page) -> None:
    banner = nav_page.logged_in_name()
    assert "Logged in as" in banner, f"Expected a logged-in banner, got {banner!r}"


@then("the search should have executed")
def assert_search_executed(products_page) -> None:
    assert products_page.search_has_run(), "Search does not appear to have executed"


@then(parsers.parse('the search results should contain "{product_name}"'))
def assert_results_contain(products_page, product_name) -> None:
    names = products_page.get_result_names()
    assert any(product_name in name for name in names), \
        f"Expected {product_name!r} in results, got {names!r}"


@then("the search results should contain no products")
def assert_no_results(products_page) -> None:
    assert products_page.get_result_card_count() == 0, \
        "Expected no product cards for an unmatched search term"


@then(parsers.parse('the product detail page should show "{product_name}"'))
def assert_detail_shows(product_detail_page, product_name) -> None:
    actual = product_detail_page.product_name()
    assert product_name in actual, f"Expected {product_name!r} on detail page, got {actual!r}"


@then(parsers.parse('the cart should contain the product "{product_name}"'))
def assert_cart_contains(cart_page, product_name) -> None:
    cart_page.wait_until_present(product_name)
    assert cart_page.has_product(product_name), \
        f"Expected {product_name!r} in the cart"


@then(parsers.parse('the cart should contain exactly {count:d} product'))
def assert_cart_count(cart_page, count) -> None:
    cart_page.assert_row_count(count)


@then("the cart should be empty")
def assert_cart_empty(cart_page) -> None:
    assert cart_page.is_empty(), "Expected the cart to be empty"


@then("I should be redirected to the login page")
def assert_on_login_page(login_page) -> None:
    assert login_page.is_loaded(), "Expected to land on the login page"


@then("I should not be logged in")
def assert_not_logged_in(nav_page) -> None:
    assert not nav_page.is_logged_in(), "Unexpectedly logged in"


@then(parsers.re(r'I should see the error message "(?P<expected_message>[^"]*)"'))
def assert_error_message(login_page, expected_message) -> None:
    actual = login_page.get_login_error()
    assert expected_message in actual, f"Expected {expected_message!r} in {actual!r}"


@then("I should remain on the login page")
def assert_still_on_login(login_page) -> None:
    assert login_page.is_loaded(), "Expected to stay on the login page"


@then("I should see the login and signup link")
def assert_signup_login_link(nav_page) -> None:
    assert nav_page.wait_until_logged_out(), "Expected the signed-out navigation"
