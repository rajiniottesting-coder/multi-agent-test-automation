Feature: User Logout
  As a logged-in user of SauceDemo
  I want to log out securely
  So that my session is terminated and protected pages are inaccessible

  Background:
    Given I am logged in as "standard_user"

  @logout @positive @smoke
  Scenario: Successful logout from the inventory page
    When I open the burger menu
    And I click the "Logout" link
    Then I should be redirected to the login page

  @logout @positive
  Scenario: Burger menu and logout option are visible for a logged-in user
    Then the burger menu should be visible
    When I open the burger menu
    Then the side menu should be visible
    And the side menu should contain the "Logout" link

  @logout @positive
  Scenario: Login page fields are empty after logout
    When I log out
    Then I should be on the login page
    And the username input should be empty
    And the password input should be empty

  @logout @negative
  # JIRA: SCRUM-25 (hash: 737c516c)
  Scenario: Cannot access protected inventory page via URL after logout
    When I log out
    And I navigate directly to the inventory page
    Then I should be on the login page
    And I should see the error message "Epic sadface: You can only access '/inventory.html' when you are logged in."

  @logout @edge
  Scenario: Using the browser back button after logout does not re-authenticate
    When I log out
    And I press the browser back button
    Then I should remain on the login page
