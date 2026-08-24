@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, find products, manage my cart and search
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-149 (hash: ec35a78d)
  Scenario: Full session from login through cart management to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    Then the products listing should be shown
    When I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top"
    Then the product detail page should show the product name "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @validation @login @shopping
  # JIRA: SCRUM-150 (hash: fd6cc97a)
  Scenario: Login is rejected for invalid, malformed, or missing credentials
    Given I am on the signup and login page
    When I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "wrong.email@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "not-an-email" and password "AnyPass123"
    Then I should not be logged in
    And I should remain on the login page

  @edge @negative @shopping
  # JIRA: SCRUM-151 (hash: 9fc2ad1a)
  Scenario: Searching for a non-existent product and an empty query returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    Then the products listing should be shown
    When I search for "NonExistentProductXYZ123"
    Then the search results should contain no product cards
    When I search for ""
    Then the search results should contain no product cards
