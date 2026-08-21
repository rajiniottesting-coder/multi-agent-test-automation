@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart, and log out
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session from login through cart removal to logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
    When I view the product "Blue Top"
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I go to the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should remain on the login page

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product Blue Top
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results

  @edge @negative @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And I should see no product results

  @negative @validation @shopping
  # JIRA: SCRUM-119 (hash: bf4a0509)
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
    And I should see the login or signup link in the navigation
