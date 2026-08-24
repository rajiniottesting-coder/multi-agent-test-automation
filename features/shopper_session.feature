@shopper
Feature: Automation Exercise shopper session
  As a registered shopper
  I want to log in, browse, search and manage my cart
  So that I can complete a full shopping session

  @smoke @shopper
  # JIRA: SCRUM-149 (hash: ec35a78d)
  Scenario: Full session from login through cart management to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should show a product named "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail for "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @login @shopper
  # JIRA: SCRUM-150 (hash: fd6cc97a)
  Scenario: Login is rejected for empty, wrong and malformed credentials
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

  @edge @negative @shopper
  # JIRA: SCRUM-151 (hash: 9fc2ad1a)
  Scenario: Searching for a non-existent product and an empty query returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "NonExistentProductXYZ123"
    Then the search results should contain 0 product cards
    When I search for ""
    Then the search results should contain 0 product cards
