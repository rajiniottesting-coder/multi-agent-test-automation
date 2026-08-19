@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search products, manage my cart, and log out
  So that I can complete an end-to-end shopping session

  @smoke @shopping
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for the product "Blue Top"
    Then the search results should be displayed
    And the product "Blue Top" should be shown with price "Rs. 500"
    When I open the product "Blue Top"
    Then the product detail page should show the product name "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain exactly one row for "Blue Top"
    And the cart row for "Blue Top" should show price "Rs. 500" and quantity "1"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @negative @validation @shopping
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "nonexistent_user_9999@example.com" and password "SomePass1!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page
    And the login or signup link should be present in the navigation

  @edge @shopping
  Scenario: Searching for a non-existent product name returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "Zzxcvbnmqwerty404"
    Then no product cards should be displayed in the results

  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product Blue Top
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for the product "top"
    Then the search results should be displayed
    And the product "Blue Top" should be shown with price "Rs. 500"
