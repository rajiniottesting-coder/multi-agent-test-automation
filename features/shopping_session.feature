@shopping
Feature: Automation Exercise shopping session
  As a shopper
  I want to sign in, find products, manage my cart and sign out
  So that I can complete a full shopping session reliably

  @smoke @shopping
  # JIRA: SCRUM-132 (hash: cb5d884b)
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    And I empty the cart
    Then I should be logged in
    And I should see my account name in the navigation
    When I open the products page
    And I search for "Blue Top"
    Then I should see a product card for "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should see the product detail page for "Blue Top"
    When I add the product to the cart from the detail page
    And I follow the View Cart link in the modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-135 (hash: 610e06d9)
  Scenario: Product added via Continue Shopping is retained in the cart
    Given I am on the signup and login page
    When I log in as a "registered" user
    And I empty the cart
    Then I should be logged in
    When I open the products page
    And I search for "Men Tshirt"
    And I open the product "Men Tshirt" from the search results
    Then I should see the product detail page for "Men Tshirt"
    When I add the product to the cart from the detail page
    And I dismiss the modal with Continue Shopping
    Then I should remain on the product detail page for "Men Tshirt"
    When I open the cart from the navigation
    Then the cart should contain "Men Tshirt" with quantity 1

  @negative @search @shopping
  # JIRA: SCRUM-134 (hash: c7d90948)
  Scenario: Searching for non-matching terms returns no results
    Given I open the products page
    When I search for "Zznonexistentproduct999"
    Then no product cards should be shown
    When I search for ""
    Then the search should not falsely match "Zznonexistentproduct999"
    When I search for "@@@###!!!"
    Then no product cards should be shown

  @negative @login @shopping
  # JIRA: SCRUM-133 (hash: 24eda1a0)
  Scenario: Sign-in fails with invalid credentials
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "nonexistent_user_9999@example.com" and password "AnyPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
