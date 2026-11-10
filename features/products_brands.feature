@products
Feature: Products brands sidebar and brand-filtered navigation
  As a shopper
  I want to browse products by brand
  So that I can see only the products from a brand I care about

  Background:
    Given I am on the products page

  @smoke @products
  # JIRA: SCRUM-399 (hash: c2506392) owner: SCRUM-398
  Scenario: Products page sidebar lists brands with product counts
    Then the brands sidebar should be visible
    And the brands sidebar should list the following brands with counts
      | brand                      |
      | Polo (6)                   |
      | H&M (5)                    |
      | Madame (5)                 |
      | Mast & Harbour (3)         |
      | Babyhug (4)                |
      | Allen Solly Junior (3)     |
      | Kookie Kids (3)            |
      | Biba (5)                   |

  @products
  # JIRA: SCRUM-400 (hash: a2884de4) owner: SCRUM-398
  Scenario: Clicking a brand shows only that brand's products and View Product opens matching details
    When I click the brand "Polo" in the sidebar
    Then the brand products page title should contain "Polo"
    And the brand products page should list 6 products
    When I view the first product on the brand page
    Then the product details page should show a product name and price
    And the product details page should show the brand "Polo"

  @products @edge
  # JIRA: SCRUM-401 (hash: fb5c1600) owner: SCRUM-398
  Scenario: Brand name containing a special character navigates and displays correctly
    When I click the brand "Mast & Harbour" in the sidebar
    Then the brand products page title should contain "Mast & Harbour"
    And the brand products page should list 3 products
    When I view the first product on the brand page
    Then the product details page should show a product name and price
    And the product details page should show the brand "Mast & Harbour"
