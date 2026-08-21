@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, and manage my cart
  So that I can complete a shopping session end to end

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session: login, search, add to cart, verify, remove, and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products listing from the navigation
    Then the products listing should be shown
    When I search for "Blue Top"
    Then the search should have executed
    And I should see the product "Blue Top" priced "Rs. 500" in the results
    When I open the product "Blue Top" from the results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart from the product detail page
    And I view the cart from the add-to-cart modal
    Then the cart should contain exactly one row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should be empty
    When I log out from the navigation
    Then I should be redirected to the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing from the navigation
    Then the products listing should be shown
    When I search for "top"
    Then the search should have executed
    And I should see the product "Blue Top" priced "Rs. 500" in the results

  @edge @negative @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing from the navigation
    Then the products listing should be shown
    When I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And no product results should be displayed
