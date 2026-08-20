@cart
Feature: Automation Exercise cart add and remove
  As a shopper
  I want to add and remove products in my cart
  So that my cart reflects exactly what I intend to buy

  @smoke @cart
  Scenario: Add two different products to the cart as separate line items
    Given I have an empty cart
    When I add the product "Blue Top" to the cart and continue shopping
    And I add the product "Men Tshirt" to the cart and view the cart
    Then the cart should contain 2 products
    And the cart should contain the product "Blue Top"
    And the cart should contain the product "Men Tshirt"

  @cart
  # JIRA: SCRUM-123 (hash: 677339aa)
  Scenario: Remove products from a two-item cart until it is empty
    Given I have an empty cart
    When I add the product "Blue Top" to the cart and continue shopping
    And I add the product "Men Tshirt" to the cart and view the cart
    Then the cart should contain 2 products
    When I remove the product "Blue Top" from the cart
    Then the cart should contain 1 product
    And the cart should contain the product "Men Tshirt"
    And the cart should not contain the product "Blue Top"
    When I remove the product "Men Tshirt" from the cart
    Then the cart should be empty

  @edge @cart
  Scenario: Viewing the cart with no products added shows an empty cart
    Given I have an empty cart
    When I view the cart
    Then the cart should be empty
