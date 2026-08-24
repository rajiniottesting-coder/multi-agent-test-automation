@shopping
Feature: Shopping session on Automation Exercise
  As a registered shopper
  I want to log in, search, manage my cart and log out
  So that I can complete a shopping session end to end

  @smoke @shopping
  # JIRA: SCRUM-149 (hash: ec35a78d)
  Scenario: Full session from login through cart management to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then I should see a product card for "Blue Top"
    When I view the product "Blue Top"
    Then I should see the product name "Blue Top"
    When I add the product to the cart from the product detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @validation @shopping
  # JIRA: SCRUM-150 (hash: fd6cc97a)
  Scenario: Login is rejected for blank, wrong and malformed credentials
    Given I am on the signup and login page
    When I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "wrong.email@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I dismiss the login error
    And I log in with email "not-an-email" and password "AnyPass123"
    Then I should not be logged in
    And I should remain on the login page

  @edge @shopping
  # JIRA: SCRUM-151 (hash: 9fc2ad1a)
  Scenario: Searching for a non-existent product and an empty query return no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "NonExistentProductXYZ123"
    Then I should see no product cards in the search results
    When I search for ""
    Then I should see no product cards in the search results
