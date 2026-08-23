@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search, manage my cart and log out
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
    Then I should see the search results
    And the search results should contain "Blue Top"
    When I open the product detail for "Blue Top"
    Then the product detail page for "Blue Top" is shown
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with quantity 1
    When I remove "Blue Top" from the cart
    Then the cart should not contain "Blue Top"
    And the cart should be empty
    When I log out
    Then I should not be logged in
    And I should see the login and signup link

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
    And I should remain on the login page

  @negative @search @shopping
  # JIRA: SCRUM-134 (hash: c7d90948)
  Scenario: Searching for non-matching, empty or special-character terms returns no results
    Given I am on the products page
    When I search for "Zznonexistentproduct999"
    Then the search should return no product cards
    When I search for ""
    Then the search should not falsely match "Zznonexistentproduct999"
    When I search for "@@@###!!!"
    Then the search should return no product cards

  @shopping @cart
  # JIRA: SCRUM-135 (hash: 610e06d9)
  Scenario: Product added via Continue Shopping is retained when the cart is opened separately
    Given I am on the signup and login page
    When I log in as a "registered" user
    And I empty the cart
    Then I should be logged in
    When I open the products page
    And I search for "Men Tshirt"
    Then the search results should contain "Men Tshirt"
    When I open the product detail for "Men Tshirt"
    Then the product detail page for "Men Tshirt" is shown
    When I add the product to the cart
    And I continue shopping from the modal
    Then the product detail page for "Men Tshirt" is shown
    When I open the cart from the navigation
    Then the cart should contain "Men Tshirt" with quantity 1
