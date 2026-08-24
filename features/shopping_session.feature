@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-152 (hash: 2b3efef1)
  Scenario: Complete a full shopping session
    # JIRA: SCRUM-152 (hash: 7b1c4e2a)
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include the product "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail page for "Blue Top"
    When I add the product to the cart from the detail page
    And I view the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain the product "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @shopping
  # JIRA: SCRUM-153 (hash: 46b0cb64)
  Scenario: Login with incorrect credentials shows an error message
    # JIRA: SCRUM-153 (hash: 9f2d6a11)
    Given I am on the signup and login page
    When I log in with email "wronguser@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-154 (hash: b335d3d9)
  Scenario: Searching for a nonexistent product term returns no result cards
    # JIRA: SCRUM-154 (hash: 3c8e0b47)
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Xyzzy12345NoSuchProduct"
    Then the search results should contain no product cards
