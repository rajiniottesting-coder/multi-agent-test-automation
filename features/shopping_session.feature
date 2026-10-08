@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, find products, manage my cart, and log out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-197 (hash: 2547ce2b)
  Scenario: Registered shopper completes a full shopping session
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
    And I view the cart from the modal
    Then the cart should contain "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain "Blue Top"
    When I log out
    Then I should be logged out

  @negative @shopping
  # JIRA: SCRUM-198 (hash: 6499835a)
  Scenario: Sign-in with incorrect credentials is rejected
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-199 (hash: 541aaed3)
  Scenario: Searching for a non-existent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zznonexistentproduct999"
    Then no product result cards should be displayed
