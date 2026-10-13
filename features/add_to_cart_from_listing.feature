@cart
Feature: Add to cart from the all-products listing
  As a shopper
  I want to add a product straight from its listing card
  So that I can fill my cart without opening every product page

  Background:
    Given I am on the products listing page

  @smoke @cart
  # JIRA: SCRUM-235 (hash: e15641b7) owner: SCRUM-206
  Scenario: Add a product to the cart from its listing card
    When I add "Men Tshirt" to the cart from its listing card
    Then I should see the product added confirmation modal
    When I click View Cart in the modal
    Then I should be on the cart page
    And the cart should contain "Men Tshirt" with quantity 1
