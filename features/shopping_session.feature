@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart and log out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-141 (hash: 9ace7e12)
  Scenario: Complete a shopping session from login through logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I search for the product "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail for "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @validation @shopping
  # JIRA: SCRUM-142 (hash: 6dd5f59f)
  Scenario: Login is rejected with incorrect or empty credentials
    Given I am on the signup and login page
    When I log in with email "invalid_user_9999@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-143 (hash: ddd0969a)
  Scenario: Searching for a non-existent product returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I search for the product "Nonexistent Product XYZ123"
    Then the search results should contain no products

  @edge @shopping
  # JIRA: SCRUM-144 (hash: 08546c11)
  Scenario: A product added while logged out persists after logging in
    Given I am on the products page
    When I open the product "Men Tshirt" from the listing
    Then I should see the product detail for "Men Tshirt"
    When I add the product to the cart from the detail page
    And I dismiss the added-to-cart modal
    And I am on the signup and login page
    And I log in as a "registered" user
    Then I should be logged in
    When I view the cart
    Then the cart should contain a row for "Men Tshirt"
