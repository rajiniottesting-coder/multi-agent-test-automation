@cart
Feature: Cart persistence across sessions
  As a signed-in shopper
  I want my cart to persist across sign-out and sign-in
  So that I do not lose products I intended to buy

  Background:
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should see my account name in the navigation

  @smoke @cart @regression
  # JIRA: SCRUM-368 (hash: b63a1d96) owner: SCRUM-367
  Scenario: A product added to the cart survives sign-out and sign-in
    When I open the product detail page for "Blue Top"
    Then I should see the product name "Blue Top"
    And I should see the product price "Rs. 500"
    When I add the product to the cart and view the cart
    Then the cart should contain a row for "Blue Top"
    When I log out
    Then I should remain on the login page
    And the logout link should not be shown in the navigation
    When I log in as a "registered" user
    Then I should see my account name in the navigation
    When I navigate to the cart page
    Then the cart should contain a row for "Blue Top"

  @negative @cart @regression
  # JIRA: SCRUM-369 (hash: b7109afe) owner: SCRUM-367
  Scenario: A removed product stays removed after sign-out and sign-in
    When I open the product detail page for "Men Tshirt"
    Then I should see the product name "Men Tshirt"
    And I should see the product price "Rs. 400"
    When I add the product to the cart and view the cart
    Then the cart should contain a row for "Men Tshirt"
    When I remove "Men Tshirt" from the cart
    Then the cart should not contain a row for "Men Tshirt"
    When I log out
    Then I should remain on the login page
    And the logout link should not be shown in the navigation
    When I log in as a "registered" user
    Then I should see my account name in the navigation
    When I navigate to the cart page
    Then the cart should not contain a row for "Men Tshirt"

  @cart @regression
  # JIRA: SCRUM-370 (hash: d69dbfff) owner: SCRUM-367
  Scenario: Removing every product from the cart shows the empty-cart message
    When I open the product detail page for "Sleeveless Dress"
    Then I should see the product name "Sleeveless Dress"
    And I should see the product price "Rs. 1000"
    When I add the product to the cart and view the cart
    Then the cart should contain a row for "Sleeveless Dress"
    When I remove every product from the cart
    Then no product rows should be shown in the cart
    And the cart should show the empty-cart message
