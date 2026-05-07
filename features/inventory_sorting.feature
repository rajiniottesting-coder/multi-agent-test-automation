Feature: Inventory Sorting
  As a user of SauceDemo
  I want to sort the inventory items
  So that I can find products more easily

  Background:
    Given I am on the SauceDemo login page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page

  @smoke @inventory @sorting
  Scenario: Default sort order is Name (A to Z)
    Then I should see the page title "Products"
    And the inventory items should be sorted by name ascending

  @inventory @sorting
  Scenario: Verify sorting by Price (low to high)
    Given the inventory items are sorted by name ascending
    When I select the sort option "Price (low to high)"
    Then the inventory items should be sorted by price ascending

  @inventory @sorting
  Scenario: Verify sorting by Price (high to low)
    Given the inventory items are sorted by name ascending
    When I select the sort option "Price (high to low)"
    Then the inventory items should be sorted by price descending

  @inventory @sorting
  Scenario: Verify sorting by Name (Z to A)
    Given the inventory items are sorted by name ascending
    When I select the sort option "Name (Z to A)"
    Then the inventory items should be sorted by name descending

  @inventory @sorting @persistence
  Scenario: Sort selection persists after page refresh
    Given the inventory items are sorted by price descending
    When I refresh the inventory page
    Then the inventory items should still be sorted by price descending

  @inventory @sorting @persistence
  Scenario: Sort selection persists after navigating to cart and back
    Given the inventory items are sorted by name descending
    And I have added at least one item to the cart
    When I navigate to the cart page
    And I navigate back to the inventory page
    Then the inventory items should still be sorted by name descending

  @inventory @sorting @persistence
  Scenario: Sort selection persists after navigating to product detail and back
    Given the inventory items are sorted by price ascending
    When I click on the first product name
    And I navigate back to the inventory page
    Then the inventory items should still be sorted by price ascending
