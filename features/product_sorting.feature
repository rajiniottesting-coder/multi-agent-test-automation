Feature: Product Sorting
  As a user of SauceDemo
  I want to sort products on the inventory page
  So that I can find items more easily based on name or price

  @positive @sorting @smoke
  Scenario: Verify default sort order is Name (A to Z)
    Given I am on the SauceDemo login page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And the product sort dropdown should show "Name (A to Z)"
    And the products should be sorted by "name" in "ascending" order

  @positive @sorting
  Scenario: Verify sorting by Name (Z to A)
    Given I am logged in as a "standard_user"
    When I sort the products by "Name (Z to A)"
    Then the product sort dropdown should show "Name (Z to A)"
    And the products should be sorted by "name" in "descending" order

  @positive @sorting
  # JIRA: SCRUM-32 (hash: fe5eabb4)
  Scenario: Verify sorting by Price (low to high)
    Given I am logged in as a "standard_user"
    When I sort the products by "Price (low to high)"
    Then the product sort dropdown should show "Price (low to high)"
    And the products should be sorted by "price" in "ascending" order

  @positive @sorting
  # JIRA: SCRUM-31 (hash: a982ceb9)
  Scenario: Verify sorting by Price (high to low)
    Given I am logged in as a "standard_user"
    When I sort the products by "Price (high to low)"
    Then the product sort dropdown should show "Price (high to low)"
    And the products should be sorted by "price" in "descending" order

  @edge @sorting
  Scenario: Verify sort order persists after navigating away and back
    Given I am logged in as a "standard_user"
    When I sort the products by "Price (high to low)"
    And I navigate to the cart page
    And I navigate back to the inventory page
    Then the product sort dropdown should show "Price (high to low)"
    And the products should be sorted by "price" in "descending" order

  @negative @sorting
  Scenario: Verify sorting functionality with a 'problem_user'
    Given I am logged in as a "problem_user"
    When I sort the products by "Price (low to high)"
    Then the product sort dropdown should show "Price (low to high)"
    And the products should be sorted by "price" in "ascending" order
