@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart and log out
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session login, search, add to cart, verify, remove and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search should have executed
    And I should see "Blue Top" in the search results
    When I open the product "Blue Top" from the search results
    Then I should see the product name "Blue Top" on the detail page
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 product
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain the product "Blue Top"
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "top"
    Then the search should have executed
    And I should see "Blue Top" in the search results

  @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And I should see no products in the search results
