@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to search, manage my cart and sign in and out
  So that I can complete a full shopping session reliably

  @smoke @shopping
  # JIRA: SCRUM-174 (hash: 78c80903)
  Scenario: Complete a full session: login, search, add to cart, verify, remove, and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then I should see the product name "Blue Top" on the detail page
    When I add the product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should be redirected to the login page
    And I should not be logged in

  @negative @login @shopping
  Scenario Outline: Login is rejected for invalid credentials
    Given I am on the signup and login page
    When I log in with email "<email>" and password "<password>"
    Then I should remain on the login page
    And I should not be logged in

    Examples:
      | email                    | password      |
      | invalid.user@example.com | WrongPass123! |
      |                          |               |

  @negative @login @shopping
  # JIRA: SCRUM-175 (hash: b5f54ba9)
  Scenario: Login fails with the registered email and a wrong password
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-177 (hash: c6a612ba)
  Scenario: An empty search query returns the full product catalogue
    Given I am on the products page
    When I submit an empty search
    Then the full product catalogue should still be shown
    And I should see the product "Blue Top" in the results
    And I should see the product "Men Tshirt" in the results

  @edge @shopping
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zzznonexistentproduct123"
    Then no product cards should be shown
