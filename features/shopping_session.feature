@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-164 (hash: 33239b8b)
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    Then I should see the product listing
    When I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail for "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @negative @validation @shopping
  # JIRA: SCRUM-165 (hash: 4fc6cdfe)
  Scenario: Login fails with invalid credentials and the user stays unauthenticated
    Given I am on the signup and login page
    When I log in with email "nonexistent.user@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "not-an-email" and password "anything123"
    Then I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page

  @edge @shopping
  # JIRA: SCRUM-166 (hash: f844a244)
  Scenario: Search boundary conditions for nonexistent and empty queries
    Given I am on the products page
    When I search for "Zzzznotarealproduct123"
    Then the search should return no product cards
    When I search for ""
    Then the search should return the full catalogue
