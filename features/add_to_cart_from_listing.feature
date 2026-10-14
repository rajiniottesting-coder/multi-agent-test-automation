@cart
Feature: Add to cart from the product listing
  As a shopper
  I want to add a product to my cart directly from its listing card
  So that I can buy it without opening its detail page

  Background:
    Given I am on the products listing page

  @smoke @cart
  # JIRA: SCRUM-237
  # JIRA: SCRUM-237 (hash: b31e396a) owner: SCRUM-206
  Scenario: Add a product to the cart from its listing card
    When I add "Blue Top" to the cart from its listing card
    Then I should see the product added confirmation modal
    When I view the cart from the confirmation modal
    Then I should be on the cart page
    And the cart should contain "Blue Top" with quantity 1
