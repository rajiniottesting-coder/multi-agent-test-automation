Feature: User Logout
  As a logged-in user of SauceDemo
  I want to log out of my session
  So that my account is secure and I am returned to the login page

  Background:
    Given I am logged in as a standard user

  @logout
  Scenario: Burger menu and logout option are visible
    # Corresponds to test case SCRUM-23
    When I open the burger menu
    Then the logout link should be visible

  @smoke @logout
  Scenario: Successful logout from the inventory page
    # Corresponds to test case SCRUM-21
    When I log out
    Then I should be redirected to the login page
    And the login form should be visible

  @negative @logout
  Scenario: Logout prevents direct access to protected pages
    # Corresponds to test case SCRUM-22
    When I log out
    And I attempt to navigate directly to the inventory page
    Then I should be redirected to the login page
    And I should see the error message "Epic sadface: You can only access '/inventory.html' when you are logged in."
