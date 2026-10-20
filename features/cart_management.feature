@cart
Feature: Automation Exercise cart management
  As an anonymous shopper
  I want to add, remove and re-add products in my cart
  So that my cart reflects exactly the products I chose

  Background:
    Given I am on the products listing page

  @smoke @cart
  # JIRA: SCRUM-212 (hash: a0135022) owner: SCRUM-111
  Scenario: Add a single product to the cart from its product details page
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue to the cart
    Then the cart should contain "Blue Top" with quantity 1

  @cart
  # JIRA: SCRUM-213 (hash: 64be015e) owner: SCRUM-111 impacted-by: SCRUM-203
  Scenario: Adding a second, different product keeps both products in the cart
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue shopping
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart and continue to the cart
    Then the cart should contain "Blue Top" with quantity 1
    And the cart should contain "Men Tshirt" with quantity 1

  @cart
  # JIRA: SCRUM-214 (hash: d1186ff5) owner: SCRUM-111
  Scenario: Removing one of two products takes it out of the cart and keeps the other
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue shopping
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart and continue to the cart
    And I remove "Men Tshirt" from the cart
    Then the cart should not contain "Men Tshirt"
    And the cart should contain "Blue Top" with quantity 1

  @edge @cart
  # JIRA: SCRUM-215 (hash: 9aaa7e50) owner: SCRUM-111 impacted-by: SCRUM-203
  Scenario: Adding the same product twice shows its quantity increased to 2
    When I open the product details page for "Sleeveless Dress"
    And I add the product to the cart and continue shopping
    And I add the product to the cart and continue to the cart
    Then the cart should contain "Sleeveless Dress" with quantity 2
