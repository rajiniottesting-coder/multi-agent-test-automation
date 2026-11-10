@cart
Feature: Cart persistence
  As a signed-in shopper
  I want my cart to reflect the products I add and remove
  So that my cart stays accurate across sign-out and sign-in

  Background:
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should see my account name in the navigation

  @smoke @cart
  # JIRA: SCRUM-368 (hash: 45f774db) owner: SCRUM-367
  Scenario: A product added to the cart survives sign-out and sign-in
    When I open the product detail page for "Blue Top"
    Then the product name shown should be "Blue Top"
    And the product price shown should be "Rs. 500"
    When I add the product to the cart
    And I view the cart from the confirmation modal
    Then the cart should contain a row for "Blue Top"
    When I click the logout link
    Then I should not see my account name in the navigation
    When I log in as a "registered" user
    Then I should see my account name in the navigation
    When I open the cart page
    Then the cart should contain exactly 1 row
    And the cart should contain a row for "Blue Top"

  @negative @cart
  # JIRA: SCRUM-369 (hash: b7109afe) owner: SCRUM-367
  Scenario: A removed product stays removed after sign-out and sign-in
    When I open the product detail page for "Men Tshirt"
    Then the product name shown should be "Men Tshirt"
    And the product price shown should be "Rs. 400"
    When I add the product to the cart
    And I view the cart from the confirmation modal
    Then the cart should contain a row for "Men Tshirt"
    When I remove the "Men Tshirt" row from the cart
    Then the cart should not contain a row for "Men Tshirt"
    When I click the logout link
    Then I should not see my account name in the navigation
    When I log in as a "registered" user
    Then I should see my account name in the navigation
    When I open the cart page
    Then the cart should not contain a row for "Men Tshirt"

  @edge @cart
  # JIRA: SCRUM-370 (hash: d69dbfff) owner: SCRUM-367
  Scenario: Removing every product from the cart shows the empty-cart message
    When I open the product detail page for "Sleeveless Dress"
    Then the product name shown should be "Sleeveless Dress"
    And the product price shown should be "Rs. 1000"
    When I add the product to the cart
    And I view the cart from the confirmation modal
    Then the cart should contain a row for "Sleeveless Dress"
    When I remove every row from the cart
    Then the "Sleeveless Dress" row should not be shown in the cart
    And the cart should show the empty-cart message
