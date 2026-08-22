@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart and log out
  So that I can complete an end-to-end shopping session

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    # JIRA: SCRUM-118 (hash: a1b2c3d4)
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    Given a newly registered account with an empty cart
    When I go to the products page
    And I search for "Blue Top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
    When I open the product "Blue Top" from the results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top"
    And the cart should show the price "Rs. 500" for "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should see the login and signup link

  @negative @validation @shopping
  # JIRA: SCRUM-119 (hash: bf4a0509)
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
    # JIRA: SCRUM-119 (hash: b2c3d4e5)
    Given I am on the signup and login page
    When I log in as a "registered" user with password "WrongPass!123"
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
    And I should see the login and signup link

  @negative @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    # JIRA: SCRUM-120 (hash: c3d4e5f6)
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And no product cards should be displayed

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product Blue Top
    # JIRA: SCRUM-121 (hash: d4e5f6a7)
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "top"
    Then the search should have executed
    And I should see the product "Blue Top" in the results
    And I should see the price "Rs. 500" among the results
