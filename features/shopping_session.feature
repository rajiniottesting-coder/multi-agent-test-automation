@shopping
Feature: Shopping session
  As a shopper
  I want to search, add products to my cart, and manage my session
  So that I can complete a shopping journey from login to logout

  @smoke @shopping
  # JIRA: SCRUM-145 (hash: 24eb438c)
  Scenario: Complete a shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I search for "Blue Top" on the products page
    Then the search results should be shown
    And I should see a product named "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then the product detail page should show the name "Blue Top"
    When I add the product to the cart
    Then I should see the add-to-cart confirmation modal
    When I view the cart from the modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should not be logged in
    And I should be back on the login page

  @negative @validation @shopping
  Scenario Outline: Login is rejected for invalid credentials
    Given I am on the signup and login page
    When I log in with email "<email>" and password "<password>"
    Then the login attempt should be rejected
    And I should not be logged in

    Examples:
      | email                        | password       |
      | REGISTERED_EMAIL             | WrongPass123!  |
      | no-such-user-xyz@example.com | AnyPass123!    |
      |                              |                |

  @edge @shopping
  # JIRA: SCRUM-147 (hash: 33eabeab)
  Scenario: Searching for a non-existent product returns no result cards
    Given I am on the products page
    When I search for "Nonexistentproduct123456" on the products page
    Then no product result cards should be displayed

  @edge @shopping
  # JIRA: SCRUM-148 (hash: 2dedbf4c)
  Scenario: An anonymous cart is carried into the logged-in session
    Given I am on the products page
    When I search for "Men Tshirt" on the products page
    Then the search results should be shown
    When I open the product "Men Tshirt" from the results
    And I add the product to the cart
    And I continue shopping from the modal
    And I am on the signup and login page
    And I log in as a "registered" user
    Then I should be logged in
    When I open the cart page
    Then the cart should contain a row for "Men Tshirt"
