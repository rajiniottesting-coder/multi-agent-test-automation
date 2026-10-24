@cart
Feature: Add to cart from the product listing
  As a shopper
  I want to add a product straight from its listing card
  So that I can fill my cart without opening each product's detail page

  @smoke @cart
  # JIRA: SCRUM-255 (hash: 3c8212bc) owner: SCRUM-206
  Scenario: Adding a product from its listing card adds one item without opening the detail page
    Given I am on the products listing page
    When I add the product "Blue Top" to the cart from its listing card
    Then I should remain on the products listing page
    And I should see the added-to-cart confirmation modal
    When I view the cart from the confirmation modal
    Then I should be taken to the cart page
    And the cart should contain the product "Blue Top"
    And the cart row for "Blue Top" should show quantity 1
