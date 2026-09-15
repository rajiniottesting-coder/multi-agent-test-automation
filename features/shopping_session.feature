@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to search the catalogue, manage my cart and my account session
  So that I can complete an end-to-end shopping workflow

  @edge @products
  # JIRA: SCRUM-177 (hash: c6a612ba)
  Scenario: An empty search query returns the full product catalogue
    Given I am on the products page
    When I submit the search without entering a term
    Then I should remain on the products page
    And the product results should contain "Blue Top"
    And the product results should contain "Men Tshirt"

  @edge @negative @products
  # JIRA: SCRUM-176 (hash: 3d9f03f7)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zzznonexistentproduct123"
    Then the search should return no product cards

  @negative @login
  # JIRA: SCRUM-175 (hash: b5f54ba9)
  Scenario: Login fails with wrong password, wrong email, and empty credentials
    Given I am on the signup and login page
    When I log in with email "invalid.user@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page

  @smoke @regression @shopping
  # JIRA: SCRUM-174 (hash: 78c80903)
  Scenario: Complete a full session with login, search, add to cart, remove and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the product results should contain "Blue Top"
    When I view the product "Blue Top" from the results
    Then I should see the product name "Blue Top" on the detail page
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should not be logged in
    And I should remain on the login page
