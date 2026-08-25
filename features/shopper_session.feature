@shopper
Feature: Automation Exercise shopper session
  As a registered shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a shopping session reliably

  @smoke @shopper
  # JIRA: SCRUM-161 (hash: 57f84699)
  Scenario: Registered shopper completes a full session
    Given I am on the signup and login page
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I open the product "Blue Top" from the search results
    Then I should be on the product detail page for "Blue Top"
    When I add the product to the cart
    And I view the cart from the modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should not contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @shopper
  # JIRA: SCRUM-162 (hash: b5b77a51)
  Scenario: Login fails with an incorrect password
    Given I am on the signup and login page
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @edge @shopper
  # JIRA: SCRUM-163 (hash: a8774850)
  Scenario: Searching for a nonexistent product returns no result cards
    Given I am on the products page
    When I search for "Zzzznonexistentproduct123"
    Then the search should return no product cards
