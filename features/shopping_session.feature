@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, and manage my cart
  So that I can complete a shopping session end to end

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products listing from the navigation
    And I search for "Blue Top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    And the cart should have exactly 1 product row
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out from the navigation
    Then I should not be logged in
    And I should remain on the login page

  @negative @validation @shopping
  # JIRA: SCRUM-119 (hash: bf4a0509)
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "nonexistent_user_9999@example.com" and password "SomePass1!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page

  @negative @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing from the navigation
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And no products should be shown in the results

  @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing from the navigation
    And I search for "top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
