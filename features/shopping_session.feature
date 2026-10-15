@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session with confidence

  @smoke @shopping
  # JIRA: SCRUM-244 (hash: dbca58e1) owner: SCRUM-187
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I search the products page for "Blue Top"
    Then the searched products heading should be shown
    And a product card for "Blue Top" should be present in the results
    When I view the product "Blue Top"
    Then the product detail page should show the name "Blue Top"
    And the product detail page should show the price "Rs. 500"
    When I add the product to the cart from the detail page
    Then I should see the added-to-cart confirmation
    When I view the cart from the modal
    Then a cart row for "Blue Top" should be present
    When I remove "Blue Top" from the cart
    Then a cart row for "Blue Top" should not be present
    When I log out
    Then I should be redirected to the login page
    And I should not be logged in

  @negative @login @shopping
  # JIRA: SCRUM-245 (hash: 3a425299) owner: SCRUM-187
  Scenario: Login is rejected for incorrect credentials and for empty fields
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "nonexistent.user@example.com" and password "AnyPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should remain on the login page
    And I should not be logged in

  @edge @negative @shopping
  # JIRA: SCRUM-246 (hash: a0cf22c0) owner: SCRUM-187
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search the products page for "Zznonexistentproduct999"
    Then the searched products heading should be shown
    And no product cards should be present in the results
