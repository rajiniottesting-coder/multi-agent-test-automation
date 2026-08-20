@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue and manage my cart
  So that I can complete an end-to-end shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  Scenario: Full session - login, search, add to cart, verify, remove and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then I should see search results
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the add-to-cart modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain "Rs. 500"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product Blue Top
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "top"
    Then I should see search results
    And I should see the product "Blue Top" in the results
    And I should see the product price "Rs. 500" in the results

  @edge @negative @shopping
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "Zzxcvbnmqwerty404"
    Then I should see search results
    And I should see no product results
