@cart
Feature: Automation Exercise cart management
  As a shopper
  I want to add and remove products in my cart
  So that I can control what I intend to buy

  @edge @cart
  # JIRA: SCRUM-124 (hash: dd6f28b3)
  Scenario: Viewing the cart with no products added shows an empty cart
    Given I have an empty cart
    When I view the cart
    Then the cart should be empty
    And the cart should contain 0 products

  @smoke @cart
  Scenario: Add two different products to the cart as separate line items
    Given I have an empty cart
    When I open the product listing
    And I open the product "Blue Top" from the listing
    And I add the product to the cart
    And I continue shopping
    And I open the product listing
    And I open the product "Men Tshirt" from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain 2 products
    And the cart should contain the product "Blue Top"
    And the cart should contain the product "Men Tshirt"

  @cart
  Scenario: Removing products one by one leaves the cart empty
    Given I have an empty cart
    When I open the product listing
    And I open the product "Blue Top" from the listing
    And I add the product to the cart
    And I continue shopping
    And I open the product listing
    And I open the product "Men Tshirt" from the listing
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain 2 products
    When I remove the product "Blue Top" from the cart
    Then the cart should contain 1 product
    And the cart should contain the product "Men Tshirt"
    And the cart should not contain the product "Blue Top"
    When I remove the product "Men Tshirt" from the cart
    Then the cart should be empty
    And the cart should contain 0 products
