@products
Feature: Automation Exercise product search
  As a shopper
  I want to search the product catalogue by name
  So that I can quickly find the products I am interested in

  Background:
    Given I am on the products page

  @smoke @products
  # JIRA: SCRUM-216 (hash: 8d03173c) owner: SCRUM-200
  Scenario: Searching for an existing product returns only matching products
    When I search for "Blue Top"
    Then the search results heading should be shown
    And the search results should include "Blue Top"
    And every product in the results should match "Blue Top"

  @negative @products
  # JIRA: SCRUM-217 (hash: 3d5bb907) owner: SCRUM-200
  Scenario: Searching for a non-existent product shows no products
    When I search for "Zznonexistentproduct999"
    Then no product cards should be shown

  @edge @products
  # JIRA: SCRUM-218 (hash: 89eff3b4) owner: SCRUM-200
  Scenario: Submitting an empty search query returns the whole catalogue
    When I search for ""
    Then the full product listing heading should be shown
    And the search results should include "Blue Top"
    And the search results should include "Men Tshirt"
