@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, and manage my cart
  So that I can complete an end-to-end shopping session

  @smoke @shopping
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the search results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should see the login link in the navigation

  @negative @validation @shopping
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
    Given I am on the signup and login page
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
    And I should see the login link in the navigation

  @negative @shopping
  Scenario: Searching for a non-existent product name returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "Zzxcvbnmqwerty404"
    Then the search results should be shown
    And no products should be displayed in the results

  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product Blue Top
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results
