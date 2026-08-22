@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue and manage my cart
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products page
    And I search for "Blue Top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should see the login and signup link

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds a known product
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products page
    And I search for "top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results

  @edge @negative @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search results should be shown
    And no products should be displayed in the results
