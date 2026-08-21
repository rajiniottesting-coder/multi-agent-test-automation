@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, manage my cart and log out
  So that I can complete a full shopping session

  # SCRUM-118 registers a fresh account so the cart starts genuinely empty
  # and the absolute "cart is empty" assertion holds regardless of run history.

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    Given a newly registered account is logged in
    When I click "Products" in the navigation
    And I search for "Blue Top"
    Then the search results should contain "Blue Top" priced "Rs. 500"
    When I open the product "Blue Top" from the results
    Then I should see the product name "Blue Top" on the detail page
    When I add the product to the cart from the detail page
    And I view the cart from the modal
    Then the cart should contain "Blue Top" priced "Rs. 500" with quantity "1"
    When I remove "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in
    And I should see the login link in the navigation

  @negative @shopping
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
    And I should see the login link in the navigation

  @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    Given I am logged in as a "registered" user
    When I click "Products" in the navigation
    And I search for "Zzxcvbnmqwerty404"
    Then the search should have executed
    And no product cards should be displayed

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    Given I am logged in as a "registered" user
    When I click "Products" in the navigation
    And I search for "top"
    Then the search should have executed
    And the search results should contain "Blue Top" priced "Rs. 500"
