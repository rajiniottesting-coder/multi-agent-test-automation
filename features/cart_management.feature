@cart
Feature: Automation Exercise cart management
  As a shopper
  I want to add, view, and remove products in my cart
  So that I can manage what I intend to buy

  Background:
    Given the cart is empty

  @smoke @cart
  # JIRA: SCRUM-125 (hash: 21fadcc5)
  Scenario: Full cart lifecycle: add, add another, remove one, remove all
    When I open the "Blue Top" product from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 row
    When I open the "Men Tshirt" product from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain the product "Men Tshirt"
    And the cart should contain exactly 2 rows
    When I remove the product "Blue Top" from the cart
    Then the product "Blue Top" should no longer be in the cart
    And the cart should contain the product "Men Tshirt"
    And the cart should contain exactly 1 row
    When I remove the product "Men Tshirt" from the cart
    Then the product "Men Tshirt" should no longer be in the cart
    And the cart should be empty

  @regression @cart
  # JIRA: SCRUM-126 (hash: 4bdc92a2)
  Scenario: Adding the same product twice increases its quantity
    When I open the "Blue Top" product from the listing
    And I add the product to the cart
    And I continue shopping from the modal
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 row
    And the quantity for "Blue Top" should be "2"

  @regression @cart
  # JIRA: SCRUM-127 (hash: 38e2df4c)
  Scenario: Cart contents persist across refresh and navigation
    When I open the "Blue Top" product from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 row
    When I reload the cart page
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 row
    And the quantity for "Blue Top" should be "1"
    When I navigate away to the products page and back to the cart
    Then the cart should contain the product "Blue Top"
    And the cart should contain exactly 1 row
    And the quantity for "Blue Top" should be "1"
