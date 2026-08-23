@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-129 (hash: 49595f12)
  Scenario: Complete a shopping session from login through logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    Given the cart is empty
    When I open the products page
    And I search for "Blue Top"
    Then I should see the searched products results
    When I open the product "Blue Top" from the search results
    Then the product detail page should show the product name "Blue Top"
    When I add the product to the cart
    And I go to the cart from the add-to-cart modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in

  @negative @login @shopping
  # JIRA: SCRUM-130 (hash: be70a461)
  Scenario: Login fails with an incorrect email and password combination
    Given I am on the signup and login page
    When I log in with email "wrong_user_qa@example.com" and password "WrongPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-131 (hash: d4aee2e3)
  Scenario: Searching for a product that does not exist returns no results
    Given I am on the products page
    When I search for "Zzzznonexistentproduct123"
    Then I should see the searched products results
    And no product result cards should be displayed
