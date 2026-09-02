@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-167 (hash: 368d9625)
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart
    Then I should see the added to cart confirmation
    When I view the cart from the confirmation
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-169 (hash: db237175)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zzyzx Nonexistent Product 12345"
    Then the search should return no product cards

  @negative @shopping
  Scenario: Login is rejected for wrong password, malformed email and empty fields
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "not-an-email" and password "Whatever1!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
