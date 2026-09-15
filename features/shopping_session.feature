@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to browse, search, and manage my cart
  So that I can complete a full shopping session end to end

  @edge @regression @shopping
  # JIRA: SCRUM-177 (hash: c6a612ba)
  Scenario: An empty search returns the full product catalogue
    Given I am on the products page
    When I submit the search without entering a term
    Then the search results should include "Blue Top"
    And the search results should include "Men Tshirt"

  @edge @regression @shopping
  # JIRA: SCRUM-176 (hash: 3d9f03f7)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zzznonexistentproduct123"
    Then no product cards should be displayed

  @smoke @regression @shopping
  # JIRA: SCRUM-174 (hash: 78c80903)
  Scenario: Complete a full session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I view the product "Blue Top"
    Then I should see the product name "Blue Top"
    When I add the product to the cart
    And I view the cart from the added modal
    Then the cart should contain "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain "Blue Top"
    When I log out
    Then I should be on the login page
    And I should not be logged in
