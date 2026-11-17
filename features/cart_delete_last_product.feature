@cart
Feature: Delete the only product from the cart
  As a shopper
  I want to remove the last product from my cart
  So that I can see a clear empty-cart message with no leftover rows

  @smoke @cart
  # JIRA: SCRUM-452 (hash: 04fe72d7) owner: SCRUM-449
  Scenario: Deleting the only product from the cart shows the empty-cart message and leaves no row
    Given I am on the products page
    When I open the product details for "Blue Top"
    And I add the product to the cart from the product details page
    And I view the cart from the confirmation modal
    Then I should see the product "Blue Top" in the cart
    When I delete the product "Blue Top" from the cart
    Then the product "Blue Top" should not be shown in the cart
    And the cart should show the empty-cart message
