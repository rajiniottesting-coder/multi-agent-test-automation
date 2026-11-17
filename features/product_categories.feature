@products
Feature: Product category browsing
  As a shopper
  I want to browse products by category
  So that I can find items grouped by what I am looking for

  @smoke @products
  # JIRA: SCRUM-459 (hash: 74ba709d) owner: SCRUM-453
  Scenario: Opening Women > Dress shows the category page with a heading and at least one product
    Given I am on the products page
    When I open the "Women" category and select the "Dress" subcategory
    Then I should be on a category products page
    And the category heading should be "Women - Dress Products"
    And at least one product card should be displayed

  @negative @products
  # JIRA: SCRUM-460 (hash: 9d363ee5) owner: SCRUM-453
  Scenario: A nonexistent category URL lists no products
    Given I am on the category page for category id "999999"
    Then no product cards should be displayed
