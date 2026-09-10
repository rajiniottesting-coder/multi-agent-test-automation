@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to log in, search, manage my cart and log out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-170 (hash: 4f474dd1)
  Scenario: Complete a shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then the search results should include the product "Blue Top"
    When I open the product "Blue Top" from the search results
    Then the product detail page should show the product name "Blue Top"
    When I add the displayed product to the cart
    And I view the cart from the add-to-cart modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should no longer contain the product "Blue Top"
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-173 (hash: fd101529)
  Scenario: Product added while logged out is retained after logging in
    Given I am on the signup and login page
    And I should not be logged in
    When I go to the products page
    And I search for the product "Men Tshirt"
    And I open the product "Men Tshirt" from the search results
    Then the product detail page should show the product name "Men Tshirt"
    When I add the displayed product to the cart
    And I continue shopping from the add-to-cart modal
    And I am on the signup and login page
    And I log in as a "registered" user
    Then I should be logged in
    When I view the cart
    Then the cart should contain the product "Men Tshirt"

  @edge @negative @shopping
  # JIRA: SCRUM-172 (hash: bddf0f89)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "Zzzxcvbnm12345"
    Then the search should return no product result cards

  @negative @validation @shopping
  # JIRA: SCRUM-171 (hash: 56501d27)
  Scenario: Login is rejected for incorrect, empty and malformed credentials
    Given I am on the signup and login page
    When I log in with email "wrong.user@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    When I clear the credential fields
    And I log in with email "not-an-email" and password "WrongPass123!"
    Then I should not be logged in
