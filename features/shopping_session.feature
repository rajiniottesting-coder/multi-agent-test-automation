@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session reliably

  @smoke @shopping
  # JIRA: SCRUM-132 (hash: cb5d884b)
  Scenario: Complete a full shopping session: login, search, add to cart, view, remove, logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    And the cart is empty
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then the product detail page for "Blue Top" is shown
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should not contain "Blue Top"
    And the cart should be empty
    When I log out
    Then I should not be logged in

  @negative @login @shopping
  # JIRA: SCRUM-133 (hash: 24eda1a0)
  Scenario: Sign-in fails with incorrect credentials and the shopper is not recognised
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I dismiss the login error
    And I log in with email "nonexistent_user_9999@example.com" and password "AnyPass123!"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I dismiss the login error
    And I log in with email "" and password ""
    Then I should not be logged in

  @negative @search @shopping
  # JIRA: SCRUM-134 (hash: c7d90948)
  Scenario: Searching for a non-existent, empty or special-character term returns no results
    Given I go to the products page
    When I search for "Zznonexistentproduct999"
    Then no product cards should be shown
    When I search for ""
    Then the product search should not error
    When I search for "@@@###!!!"
    Then no product cards should be shown

  @edge @shopping
  # JIRA: SCRUM-135 (hash: 610e06d9)
  Scenario: Product added via 'Continue Shopping' modal option still appears in the cart when visited separately
    Given I am on the signup and login page
    When I log in as a "registered" user
    And the cart is empty
    Then I should be logged in
    When I go to the products page
    And I search for "Men Tshirt"
    Then the search results should include "Men Tshirt"
    When I open the product "Men Tshirt" from the search results
    Then the product detail page for "Men Tshirt" is shown
    When I add the product to the cart
    And I dismiss the add-to-cart modal with Continue Shopping
    Then the product detail page for "Men Tshirt" is shown
    When I open the cart from the navigation
    Then the cart should contain "Men Tshirt" with quantity 1
