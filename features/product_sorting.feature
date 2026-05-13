Feature: Product Sorting
  As a user of SauceDemo
  I want to sort products on the inventory page
  So that I can find items more easily

  Background:
    Given I am logged in as the "standard_user"

  @sorting @positive @smoke
  Scenario: Verify default sort order is Name (A to Z)
    Then the sort dropdown should show "Name (A to Z)"
    And the products should be sorted by "name" in "ascending" order

  @sorting @positive
  Scenario: Verify sorting by Name (Z to A)
    When I sort the products by "Name (Z to A)"
    Then the products should be sorted by "name" in "descending" order

  @sorting @positive
  # JIRA: SCRUM-32 (hash: fe5eabb4)
  Scenario: Verify sorting by Price (low to high)
    When I sort the products by "Price (low to high)"
    Then the products should be sorted by "price" in "ascending" order

  @sorting @positive
  # JIRA: SCRUM-31 (hash: a982ceb9)
  Scenario: Verify sorting by Price (high to low)
    When I sort the products by "Price (high to low)"
    Then the products should be sorted by "price" in "descending" order

  @sorting @edge
  Scenario: Verify sort order persists after navigating away and back
    When I sort the products by "Price (high to low)"
    And I navigate to the cart page
    And I navigate back to the inventory page
    Then the sort dropdown should show "Price (high to low)"
    And the products should be sorted by "price" in "descending" order

  @sorting @negative
  Scenario: Verify sorting functionality with a problem user
    Given I am logged in as the "problem_user"
    When I sort the products by "Price (low to high)"
    Then the sort dropdown should show "Price (low to high)"
    And the products should be sorted by "price" in "ascending" order
