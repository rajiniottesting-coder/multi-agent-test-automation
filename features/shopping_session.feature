@shopping
Feature: Automation Exercise shopping session
  As a registered shopper
  I want to log in, search the catalogue, and manage my cart
  So that I can complete a full shopping session

  Background:
    Given I am on the signup and login page

  @smoke @shopping
  Scenario: Full session login search add to cart verify remove and logout
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should be shown
    And the product "Blue Top" should be listed with price "Rs. 500"
    When I open the product "Blue Top" from the results
    Then the product detail page should show "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain "Blue Top" with price "Rs. 500"
    When I remove "Blue Top" from the cart
    Then the cart should be empty
    When I log out
    Then I should not be logged in

  @edge @shopping
  # JIRA: SCRUM-120 (hash: fe5b11d1)
  Scenario: Searching for a non-existent product name returns no results
    When I log in as a "registered" user
    And I go to the products page
    And I search for "Zzxcvbnmqwerty404"
    Then the search results should be shown
    And no product cards should be displayed

  @edge @shopping
  Scenario: Case-insensitive partial search finds the known product Blue Top
    When I log in as a "registered" user
    And I go to the products page
    And I search for "top"
    Then the search results should be shown
    And the product "Blue Top" should be listed with price "Rs. 500"
