@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, find products, manage my cart and log out
  So that I can complete a full shopping session

  # JIRA: SCRUM-118 (hash: a1b2c3d4)
  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    Given a newly registered account
    When I log in as the newly registered user
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products page
    And I search for "Blue Top"
    Then the search should have executed
    And the search results should contain "Blue Top"
    When I open the product "Blue Top" from the search results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 product
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should be redirected to the login page
    And I should not be logged in

  # JIRA: SCRUM-119 (hash: b2c3d4e5)
  @negative @validation @shopping
  # JIRA: SCRUM-119 (hash: bf4a0509)
  Scenario: Login attempts with incorrect, unknown, or empty credentials are all rejected
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
    And I should remain on the login page
    And I should see the login and signup link

  # JIRA: SCRUM-120 (hash: c3d4e5f6)
  @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And the search results should contain no products

  # JIRA: SCRUM-121 (hash: d4e5f6a7)
  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product Blue Top
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    When I open the products page
    And I search for "top"
    Then the search should have executed
    And the search results should contain "Blue Top"
