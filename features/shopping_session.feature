@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-132 (hash: cb5d884b)
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    And the cart is empty
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I search for "Blue Top" on the products page
    Then I should see the product "Blue Top" in the search results
    When I open the product "Blue Top" from the search results
    Then I should see the product detail page for "Blue Top"
    When I add the product to the cart from the detail page
    And I choose to view the cart from the modal
    Then I should be on the cart page
    And the cart should contain the product "Blue Top"
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain the product "Blue Top"
    And the cart should be empty
    When I log out
    Then I should not be logged in
    And I should not see my account name in the navigation

  @negative @login @shopping
  # JIRA: SCRUM-133 (hash: 24eda1a0)
  Scenario: Sign-in fails with incorrect credentials
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
    And I should not see my account name in the navigation

  @negative @search @shopping
  # JIRA: SCRUM-134 (hash: c7d90948)
  Scenario: Searching for terms that match nothing returns no results
    Given I am on the products page
    When I search for "Zznonexistentproduct999" on the products page
    Then no product cards should be shown
    When I search for "" on the products page
    Then the search should not error out
    When I search for "@@@###!!!" on the products page
    Then no product cards should be shown

  @edge @cart @shopping
  # JIRA: SCRUM-135 (hash: 610e06d9)
  Scenario: Product added via Continue Shopping still appears in the cart
    Given I am on the signup and login page
    And the cart is empty
    When I log in as a "registered" user
    Then I should be logged in
    When I search for "Men Tshirt" on the products page
    And I open the product "Men Tshirt" from the search results
    Then I should see the product detail page for "Men Tshirt"
    When I add the product to the cart from the detail page
    And I dismiss the modal with Continue Shopping
    Then I should see the product detail page for "Men Tshirt"
    When I open the cart from the navigation
    Then I should be on the cart page
    And the cart should contain the product "Men Tshirt"
