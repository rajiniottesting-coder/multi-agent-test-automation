@products
Feature: Add to cart from the product listing
  As a shopper
  I want to add a product to my cart directly from its card on the listing
  So that I do not have to open the product detail page first

  @smoke @products
  # JIRA: SCRUM-264 (hash: b33b4043) owner: SCRUM-206
  Scenario: Add Blue Top to the cart from its listing card
    Given I am on the products listing page
    When I add "Blue Top" to the cart from its product card
    Then I should see the product-added confirmation modal
    And I should remain on the products listing page
    When I view the cart from the confirmation modal
    Then I should be on the cart page
    And the cart should contain "Blue Top" with quantity 1
