@cart
Feature: Add and remove products in the cart
  As a shopper
  I want to add and remove products in my cart
  So that my cart reflects exactly what I intend to buy

  @smoke @cart
  # JIRA: SCRUM-212 (hash: a0135022) owner: SCRUM-111
  Scenario: Add a single product to the cart from its product details page
    Given I am on the products listing page
    When I open the product details page for "Blue Top"
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with quantity 1

  @cart
  # JIRA: SCRUM-213 (hash: a8208888) owner: SCRUM-111
  Scenario: Adding a second, different product keeps both products in the cart
    Given I am on the products listing page
    When I open the product details page for "Blue Top"
    And I add the product to the cart
    And I continue shopping from the modal
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with quantity 1
    And the cart should contain "Men Tshirt" with quantity 1

  @cart
  # JIRA: SCRUM-214 (hash: d1186ff5) owner: SCRUM-111
  Scenario: Removing one of two products takes it out of the cart and keeps the other
    Given I am on the products listing page
    When I open the product details page for "Blue Top"
    And I add the product to the cart
    And I continue shopping from the modal
    And I am on the products listing page
    And I open the product details page for "Men Tshirt"
    And I add the product to the cart
    And I view the cart from the modal
    And I remove "Men Tshirt" from the cart
    Then the cart should not contain "Men Tshirt"
    And the cart should contain "Blue Top" with quantity 1

  @cart @regression
  # JIRA: SCRUM-215 (hash: efe4088b) owner: SCRUM-111
  Scenario: Adding the same product twice shows its quantity increased to 2
    Given I am on the products listing page
    When I open the product details page for "Sleeveless Dress"
    And I add the product to the cart
    And I continue shopping from the modal
    And I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Sleeveless Dress" with quantity 2
