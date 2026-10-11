@products
Feature: Product detail display and add-to-cart quantity
  As a shopper
  I want to see full product details and control the quantity I add
  So that my cart accurately reflects what I chose

  Background:
    Given I am on the products page

  @smoke @products
  # JIRA: SCRUM-219 (hash: bc72dfb1) owner: SCRUM-201
  Scenario: Product details page shows name, price, availability, condition and brand
    When I view the product "Blue Top"
    Then the product detail page should show the name "Blue Top"
    And the product detail page should show the price "Rs. 500"
    And the product detail page should show the availability label
    And the product detail page should show the condition label
    And the product detail page should show the brand label

  @smoke @products
  # JIRA: SCRUM-220 (hash: ec665267) owner: SCRUM-201
  Scenario: Choose a quantity and add product to cart, then view cart to confirm quantity
    When I view the product "Men Tshirt"
    Then the product detail page should show the name "Men Tshirt"
    And the product detail page should show the price "Rs. 400"
    When I set the quantity to 3
    And I add the product to the cart
    And I click View Cart in the confirmation modal
    Then the cart should contain "Men Tshirt" with quantity 3

  @products
  # JIRA: SCRUM-221 (hash: a6105dc1) owner: SCRUM-201
  Scenario: Add product to cart and continue shopping, then verify it is in the cart
    When I view the product "Blue Top"
    Then the product detail page should show the name "Blue Top"
    And the product detail page should show the price "Rs. 500"
    When I set the quantity to 2
    And I add the product to the cart
    And I click Continue Shopping in the confirmation modal
    Then I should remain on the "Blue Top" product detail page
    When I go to the cart via the navigation
    Then the cart should contain "Blue Top" with quantity 2

  @products
  # JIRA: SCRUM-222 (hash: 216020c2) owner: SCRUM-201
  Scenario: Add a large boundary quantity of a product and verify the cart reflects it accurately
    When I view the product "Sleeveless Dress"
    Then the product detail page should show the name "Sleeveless Dress"
    And the product detail page should show the price "Rs. 1000"
    When I set the quantity to 50
    And I add the product to the cart
    And I click View Cart in the confirmation modal
    Then the cart should contain "Sleeveless Dress" with quantity 50
