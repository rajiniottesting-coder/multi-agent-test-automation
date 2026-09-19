@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping journey

  @smoke @shopping
  # JIRA: SCRUM-178 (hash: c72c6af6)
  Scenario: Complete shopping session: login, search, add to cart, verify, remove, logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the searched products heading should be shown
    And the search results should contain "Blue Top"
    When I view the product "Blue Top"
    Then the product name should be "Blue Top"
    And the product price should contain "500"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should no longer contain the product "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @shopping
  # JIRA: SCRUM-179 (hash: dbc718e1)
  Scenario: Login with invalid credentials shows an error and leaves the user unauthenticated
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-180 (hash: 78f2b7de)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzzznonexistentproduct123"
    Then the searched products heading should be shown
    And no product result cards should be displayed
