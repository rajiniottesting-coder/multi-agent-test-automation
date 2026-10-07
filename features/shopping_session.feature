@shopping
Feature: Shopping session on Automation Exercise
  As a registered shopper
  I want to sign in, find and manage products in my cart, and sign out
  So that I can complete a full shopping session reliably

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-194 (hash: ccb6c8b5)
  Scenario: Registered shopper signs in, finds a product, adds and removes it from the cart, then signs out
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then I should see a product card for "Blue Top"
    When I view the product "Blue Top"
    Then the product name should be "Blue Top"
    And the product price should contain "500"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain "Blue Top"
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @negative @shopping
  # JIRA: SCRUM-195 (hash: 5d726a0d)
  Scenario: Login is rejected with incorrect credentials
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "nonexistent.user@example.com" and password "SomePassword1"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-196 (hash: 681055a4)
  Scenario: Searching for a non-existent product returns no result cards
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zznonexistentproduct999"
    Then no product result cards should be displayed
