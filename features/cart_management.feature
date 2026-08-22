@cart
Feature: Cart management
  As a shopper
  I want to add and remove products in my cart
  So that I can control what I intend to buy

  Background:
    Given I am on the products page

  @smoke @cart
  # JIRA: SCRUM-125 (hash: 21fadcc5)
  Scenario: Full cart lifecycle: add, add second, remove one, remove all
    When I open the product "Blue Top" from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Blue Top"
    When I open the product "Men Tshirt" from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain exactly 2 products
    And the cart should contain the product "Blue Top"
    And the cart should contain the product "Men Tshirt"
    When I remove the product "Blue Top" from the cart
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Men Tshirt"
    When I remove the product "Men Tshirt" from the cart
    Then the cart should be empty

  @cart
  # JIRA: SCRUM-126 (hash: 4bdc92a2)
  Scenario: Adding the same product twice increases its quantity
    When I open the product "Blue Top" from the listing
    And I add the product to the cart
    And I continue shopping from the modal
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Blue Top"
    And the quantity for "Blue Top" should be 2

  @cart
  # JIRA: SCRUM-127 (hash: 38e2df4c)
  Scenario: Cart contents persist across page refresh and navigation
    When I open the product "Blue Top" from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Blue Top"
    When I reload the cart page
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Blue Top"
    When I navigate away to the products page and back to the cart
    Then the cart should contain exactly 1 product
    And the cart should contain the product "Blue Top"
