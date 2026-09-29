@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find and manage products in my cart, and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-188 (hash: 2331e17a)
  Scenario: Registered shopper completes a full shopping session
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products page
    Then I should see the all products listing
    When I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product detail for "Blue Top"
    Then the product detail name should be "Blue Top"
    And the product detail price should contain "Rs. 500"
    When I add the product to the cart from the detail page
    And I view the cart from the added modal
    Then the cart should contain "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain "Blue Top"
    When I log out
    Then I should not be logged in
    And I should see the login and signup forms

  @negative @login @shopping
  # JIRA: SCRUM-189 (hash: e4ef6eca)
  Scenario: Login is rejected with incorrect credentials
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "notregistered@example.com" and password "AnotherWrong1!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in
    And I should see the login and signup link

  @edge @negative @shopping
  # JIRA: SCRUM-190 (hash: a4c02b05)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zznonexistentproduct999"
    Then no product cards should be displayed
