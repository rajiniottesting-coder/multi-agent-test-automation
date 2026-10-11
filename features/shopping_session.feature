@shopping
Feature: Shopping session
  As a registered shopper
  I want to sign in, search, manage my cart and sign out
  So that I can complete a full shopping session reliably

  Background:
    Given I am on the signup and login page

  @edge @negative @shopping
  # JIRA: SCRUM-226 (hash: d3e85679) owner: SCRUM-187
  Scenario: Signed-in shopper searches for a product that does not exist
    When I log in as a "registered" user
    Then I should be logged in
    When I go to the products page
    And I search for "Zznonexistentproduct999"
    Then the search should run
    And no product result cards should be shown

  @negative @shopping
  # JIRA: SCRUM-225 (hash: a2dc9ab4) owner: SCRUM-187
  Scenario: Sign in with incorrect credentials is rejected
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page
    And I should not be logged in

  @smoke @shopping
  # JIRA: SCRUM-224 (hash: 1e2c0e9f) owner: SCRUM-187
  Scenario: Complete shopping session: sign in, search, add to cart, remove product, sign out
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation
    When I go to the products page
    And I search for "Blue Top"
    Then I should see the product "Blue Top" in the results
    When I open the product "Blue Top"
    Then I should see the product name "Blue Top" on the detail page
    And I should see the product price "Rs. 500" on the detail page
    When I add the product to the cart
    Then I should see the add to cart confirmation modal
    When I view the cart from the modal
    Then the cart should contain "Blue Top"
    When I remove "Blue Top" from the cart
    Then "Blue Top" should no longer be in the cart
    When I log out
    Then I should not be logged in
    And I should remain on the login page
