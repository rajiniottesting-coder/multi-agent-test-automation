@shopping
Feature: Shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart, and sign out
  So that I can complete a full shopping session

  # JIRA: SCRUM-191 (hash: 1a2b3c4d)
  @smoke @regression @shopping
  # JIRA: SCRUM-191 (hash: e8b68120)
  Scenario: Registered shopper completes a full session
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I search for the product "Blue Top"
    Then I should see a search result for "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail for "Blue Top"
    And I should see the product price "Rs. 500"
    When I add the product to the cart from the product detail page
    Then I should see the product added confirmation
    When I view the cart from the confirmation modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  # JIRA: SCRUM-192 (hash: 2b3c4d5e)
  @negative @shopping
  # JIRA: SCRUM-192 (hash: e1599727)
  Scenario: Login attempt with incorrect or unregistered credentials is rejected
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I dismiss the login error
    And I log in with email "no.such.user@example.com" and password "AnyPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page

  # JIRA: SCRUM-193 (hash: 3c4d5e6f)
  @edge @shopping
  # JIRA: SCRUM-193 (hash: 6d00d98f)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I search for the product "Zznonexistentproduct999"
    Then the search results should show no product cards
