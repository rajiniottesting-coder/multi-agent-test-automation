@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-181 (hash: 6b953f6b)
  Scenario: Complete an end-to-end shopping session
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    Then the all products listing should be displayed
    When I search for "Blue Top"
    Then the searched products heading should be displayed
    And the search results should include "Blue Top"
    When I view the product "Blue Top"
    Then the product detail page should show the name "Blue Top"
    When I add the displayed product to the cart
    Then the added to cart confirmation should be displayed
    When I view the cart from the confirmation
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then "Blue Top" should no longer be in the cart
    When I log out
    Then I should not be logged in
    And I should be on the login page

  @negative @login @shopping
  Scenario: Login is rejected for invalid credential variants
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "not-an-email" and password "Test123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page

  @edge @negative @shopping
  # JIRA: SCRUM-183 (hash: 27dcfe7e)
  Scenario: Searching for a nonexistent product term returns no result cards
    Given I am on the products page
    Then the all products listing should be displayed
    When I search for "Zzznonexistentproduct123"
    Then the searched products heading should be displayed
    And no product result cards should be rendered
