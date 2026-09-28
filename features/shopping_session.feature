@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  Scenario: Complete a full shopping session for a single product
    Given I am on the home page
    And I should see the login and signup link
    When I go to the signup and login page
    And I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should be shown
    And a product card for "Blue Top" should be present
    When I view the product "Blue Top"
    Then the product detail page should show "Blue Top"
    When I add the product to the cart
    Then I should see the product added confirmation
    When I go to the cart from the confirmation modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should see the login and signup link

  @edge @search @shopping
  # JIRA: SCRUM-186 (hash: 9509c86c)
  Scenario: Searching for a term that matches no product returns zero result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzznonexistentproduct999"
    Then the search results should be shown
    And no product cards should be displayed

  @negative @login @shopping
  # JIRA: SCRUM-185 (hash: 5cd13da3)
  Scenario: Login with an incorrect password shows an error and leaves the user unauthenticated
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in
