@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to search for products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-174 (hash: 78c80903)
  Scenario: Complete a full session - login, search, add to cart, verify, remove, and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products page
    And I search for "Blue Top"
    Then the search results should include the product "Blue Top"
    When I view the product "Blue Top"
    Then I should be on the product detail page for "Blue Top"
    When I add the displayed product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-176 (hash: 3d9f03f7)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    And I open the products page
    And I search for "Zzznonexistentproduct123"
    Then the search results should be empty

  @edge @shopping
  # JIRA: SCRUM-177 (hash: c6a612ba)
  Scenario: An empty search query returns the full product catalogue
    Given I open the products page
    When I search for ""
    Then the search results should include the product "Blue Top"
    And the search results should include the product "Men Tshirt"
