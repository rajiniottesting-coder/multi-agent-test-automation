@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, find products, manage my cart and sign out
  So that I can complete a shopping session end to end

  @smoke @shopping
  # JIRA: SCRUM-260 (hash: 8e32283e) owner: SCRUM-187
  Scenario: Complete a shopping session from login to logout with Blue Top
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product name "Blue Top"
    And I should see the product price "Rs. 500"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should list the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the product "Blue Top" should no longer be listed in the cart
    When I log out
    Then I should not be logged in
    And I should see the signup and login link in the navigation

  @negative @shopping
  # JIRA: SCRUM-261 (hash: 7047cd8f) owner: SCRUM-187
  Scenario: Login with incorrect credentials is rejected and shopper is not recognised
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in
    And I should see the signup and login link in the navigation

  @edge @shopping
  # JIRA: SCRUM-262 (hash: fbe1bcc9) owner: SCRUM-187
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "Zznonexistentproduct999"
    Then no product result cards should be shown
