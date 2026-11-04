@cart
Feature: Automation Exercise cart management
  As an anonymous shopper
  I want to add, remove and re-add products in my cart
  So that my cart reflects exactly the products I chose

  Background:
    Given I am on the products listing page

  @smoke @cart
  # JIRA: SCRUM-212 (hash: 4ec26326) owner: SCRUM-111 impacted-by: SCRUM-296
  Scenario: Add a single product to the cart from its product details page
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue to the cart
    Then the cart should contain "Blue Top" with quantity 1

  @cart
  # JIRA: SCRUM-213 (hash: 450e13e8) owner: SCRUM-111 impacted-by: SCRUM-296
  Scenario: Adding a second, different product keeps both products in the cart
    Given I am on the products listing page
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue shopping
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart and continue to the cart
    Then the cart should contain "Blue Top" with quantity 1
    And the cart should contain "Men Tshirt" with quantity 1

  @cart
  # JIRA: SCRUM-214 (hash: f8de86a0) owner: SCRUM-111 impacted-by: SCRUM-296
  Scenario: Removing one of two products takes it out of the cart and keeps the other
    When I open the product details page for "Blue Top"
    And I add the product to the cart and continue shopping
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart and continue to the cart
    And I remove "Men Tshirt" from the cart
    Then the cart should not contain "Men Tshirt"
    And the cart should contain "Blue Top" with quantity 1
