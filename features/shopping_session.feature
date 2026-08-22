@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, find products, manage my cart, and log out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-118 (hash: 3d710ae2)
  Scenario: Full session - login, search, add to cart, verify, remove, and logout
    Given a newly registered account is logged in
    When I open the products page
    And I search for "Blue Top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results
    And the product "Blue Top" should be priced "Rs. 500"
    When I open the product "Blue Top" from the results
    Then I should see the product detail for "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should be logged out
    And I should see the login and signup link

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
    And I should see the login and signup link

  @edge @shopping
  # JIRA: SCRUM-121 (hash: 76bda556)
  Scenario: Case-insensitive partial search finds the known product 'Blue Top'
    Given I am logged in as a "registered" user
    When I open the products page
    And I search for "top"
    Then the search results should be shown
    And I should see the product "Blue Top" in the results
    And the product "Blue Top" should be priced "Rs. 500"

  @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    Given I am logged in as a "registered" user
    When I open the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search results should be shown
    And no product cards should be displayed
