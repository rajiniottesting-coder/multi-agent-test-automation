@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, browse and manage my cart
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-248 (hash: 7573d412) owner: SCRUM-187
  Scenario: Complete shopping session: login, search, add to cart, verify, remove, and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should be displayed
    And I should see "Blue Top" in the search results
    When I open the product "Blue Top" from the search results
    Then I should see the product name "Blue Top"
    And I should see the product price "Rs. 500"
    When I add the product to the cart with the default quantity
    Then I should see the product added confirmation
    When I view the cart from the confirmation modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should not contain "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @shopping
  # JIRA: SCRUM-249 (hash: 7bcfe71f) owner: SCRUM-187
  Scenario: Login fails with incorrect credentials and shows an error message
    When I log in with email "wronguser@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    When I clear the credential fields
    And I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-250 (hash: 3848765e) owner: SCRUM-187
  Scenario: Signed-in search for a non-existent product returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zznonexistentproduct999"
    Then the search results should be displayed
    And there should be no product results
