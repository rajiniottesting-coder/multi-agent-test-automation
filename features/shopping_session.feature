@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to search for products, manage my cart and sign out
  So that I can complete a full shopping session

  @smoke @shopping
  # JIRA: SCRUM-132 (hash: cb5d884b)
  Scenario: Complete a full shopping session from login to logout
    Given I am on the signup and login page
    When I log in as a "registered" user
    And the cart is empty
    Then I should see my account name in the navigation
    When I am on the products page
    And I search for "Blue Top"
    Then I should see a product card for "Blue Top"
    When I open the product detail page for "Blue Top"
    Then the product detail page for "Blue Top" is shown
    When I add the product to the cart from the detail page
    And I open the cart from the added-to-cart modal
    Then the cart should contain the product "Blue Top" with quantity 1
    When I remove the product "Blue Top" from the cart
    Then the cart should not contain the product "Blue Top"
    And the cart should be empty
    When I log out
    Then I should not be logged in

  @negative @shopping
  # JIRA: SCRUM-134 (hash: c7d90948)
  Scenario: Searching with non-matching, empty or special-character terms returns no products
    Given I am on the products page
    When I search for "Zznonexistentproduct999"
    Then the search should return no product cards
    When I search for ""
    Then the search should not falsely match any product
    When I search for "@@@###!!!"
    Then the search should return no product cards

  @shopping
  # JIRA: SCRUM-135 (hash: 610e06d9)
  Scenario: A product added via Continue Shopping is still in the cart when opened separately
    Given I am on the signup and login page
    When I log in as a "registered" user
    And the cart is empty
    And I am on the products page
    And I search for "Men Tshirt"
    And I open the product detail page for "Men Tshirt"
    Then the product detail page for "Men Tshirt" is shown
    When I add the product to the cart from the detail page
    And I dismiss the modal with Continue Shopping
    Then I should remain on the "Men Tshirt" product detail page
    When I open the cart from the navigation
    Then the cart should contain the product "Men Tshirt" with quantity 1
