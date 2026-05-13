Feature: User Logout
  As a logged-in user of SauceDemo
  I want to log out securely
  So that my session is terminated and my account is protected

  Background:
    Given I am logged in as a standard user

  @smoke @logout
  Scenario: Successful logout from inventory page
    When I log out from the application
    Then I should be redirected to the login page

  @logout
  Scenario: Burger menu and logout option are visible
    Then the burger menu should be visible
    When I open the burger menu
    Then the logout link should be visible in the sidebar

  @logout
  Scenario: Login page is in a clean state after logout
    When I log out from the application
    Then I should be on the login page
    And the username field should be empty
    And the password field should be empty

  @negative @logout
  # JIRA: SCRUM-25 (hash: 737c516c)
  Scenario: Cannot access protected page via URL after logout
    When I log out from the application
    And I navigate directly to the inventory page
    Then I should be on the login page
    And I should see the error message "Epic sadface: You can only access '/inventory.html' when you are logged in."

  @edge @logout
  Scenario: Cannot access protected page via browser back button after logout
    When I log out from the application
    And I click the browser's back button
    Then I should remain on the login page
    And the inventory page should not be visible
