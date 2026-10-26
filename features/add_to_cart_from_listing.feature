@products
Feature: Add to cart from the all-products listing
  As a shopper
  I want to add a product to my cart from its card on the listing
  So that I can add items without opening each product's detail page

  Background:
    Given I am on the all-products page

  @smoke @products
  # JIRA: SCRUM-259 (hash: 2d722efb) owner: SCRUM-206
  Scenario: Add a product to the cart from its card on the listing
    Then I should see "Blue Top" in the product listing
    When I add "Blue Top" to the cart from its product card
    Then I should see the product added confirmation modal
    And I should remain on the all-products page
    When I click View Cart in the confirmation modal
    Then I should be on the cart page
    And the cart should contain "Blue Top" with quantity 1
