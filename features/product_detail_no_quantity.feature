@product
Feature: Product detail page has no quantity input field
  As a shopper
  I want each add-to-cart to place exactly one item
  So that I do not need to set a quantity on the product detail page

  @smoke @product
  # JIRA: SCRUM-232 (hash: eb0d46aa) owner: SCRUM-206
  Scenario: Product detail page no longer offers a quantity input field
    Given I am on the all products page
    When I open the product detail page for "Blue Top"
    Then I should see the product name "Blue Top"
    And I should see the product price "500"
    And I should not see a quantity input field
