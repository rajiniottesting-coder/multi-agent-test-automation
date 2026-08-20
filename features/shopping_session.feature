@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, manage my cart and log out
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products listing
    And I search for "Blue Top"
    Then the search results should be displayed
    And I should see "Blue Top" in the search results
    When I view the product "Blue Top" from the results
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I view the cart from the product modal
    Then the cart should contain "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @negative @validation @shopping
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "nonexistent_user_9999@example.com" and password "SomePass1!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page

  @edge @negative @shopping
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing
    And I search for "Zzxcvbnmqwerty404"
    Then the search results should be displayed
    And no product cards should be shown

  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products listing
    And I search for "top"
    Then the search results should be displayed
    And I should see "Blue Top" in the search results
