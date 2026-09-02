@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-164 (hash: 33239b8b)
  Scenario: Complete a full shopping session
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then the search results should include the product "Blue Top"
    When I open the product "Blue Top" from the results
    Then the product detail page should show the product name "Blue Top"
    When I add the displayed product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain a row for the product "Blue Top"
    When I log out
    Then I should not be logged in
    And I should see the login and signup link

  @negative @login @shopping
  # JIRA: SCRUM-165 (hash: 4fc6cdfe)
  Scenario: Login fails with invalid credentials and the user remains unauthenticated
    Given I am on the signup and login page
    When I log in with email "nonexistent.user@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "not-an-email" and password "anything123"
    Then I should remain on the login page
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should remain on the login page
    And I should not be logged in

  @edge @negative @shopping
  Scenario: Search boundary conditions for the product listing
    Given I am on the products page
    When I search for the product "Zzzznotarealproduct123"
    Then the search results should contain no product cards
    When I search for the product ""
    Then the search results should contain product cards
