@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart and log out
  So that I can complete a full shopping session

  # JIRA: SCRUM-118 (hash: 1a2b3c4d)
  @smoke @shopping
  Scenario: Full session - login, search, add to cart, verify, remove and logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top"
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I view the cart from the product modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain the product "Blue Top"
    When I log out
    Then I should not be logged in

  # JIRA: SCRUM-119 (hash: 2b3c4d5e)
  @negative @validation @shopping
  Scenario: Login attempts with incorrect, unknown or empty credentials are rejected
    Given I am on the signup and login page
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
    And the login link should be present and the logout link absent

  # JIRA: SCRUM-120 (hash: 3c4d5e6f)
  @edge @shopping
  Scenario: Searching for a non-existent product name returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And I should see no product results

  # JIRA: SCRUM-121 (hash: 4d5e6f7a)
  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
