@shopper
Feature: Registered shopper session
  As a registered shopper
  I want to sign in, browse, search and manage my cart
  So that I can complete a shopping session reliably

  Background:
    Given I am on the signup and login page

  @smoke @shopper
  # JIRA: SCRUM-240
  # JIRA: SCRUM-240 (hash: 0c5ba6d5) owner: SCRUM-187
  Scenario: Registered shopper completes a full session
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then the search results should include "Blue Top"
    When I view the product "Blue Top" from the search results
    Then I should be on the product detail page for "Blue Top"
    And the product price should be "Rs. 500"
    When I add the product to the cart
    And I view the cart from the added-to-cart modal
    Then the cart should contain a row for "Blue Top"
    When I remove "Blue Top" from the cart
    Then the cart should no longer contain a row for "Blue Top"
    When I log out
    Then I should not be logged in

  @negative @login @shopper
  # JIRA: SCRUM-241
  # JIRA: SCRUM-241 (hash: d152513d) owner: SCRUM-187
  Scenario: Invalid login attempts are rejected
    When I log in with email "wrong.user@example.com" and password "WrongPass123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should not be logged in
    When I clear the credential fields
    And I log in with email "" and password ""
    Then I should not be logged in
    When I clear the credential fields
    And I log in with email "not-an-email" and password "SomePass1"
    Then I should not be logged in

  @negative @search @shopper
  # JIRA: SCRUM-242
  # JIRA: SCRUM-242 (hash: 9b724a9f) owner: SCRUM-187
  Scenario: Searching for a non-existent product returns no result cards
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zznonexistentproduct999"
    Then no product result cards should be displayed

  @search @shopper
  # JIRA: SCRUM-243
  # JIRA: SCRUM-243 (hash: aae333c7) owner: SCRUM-187
  Scenario: An empty search returns the full catalogue
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I submit the search with no term
    Then the unsearched products heading should remain
    And the search results should include "Blue Top"
