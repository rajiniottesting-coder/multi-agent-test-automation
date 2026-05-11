`gherkin
Feature: User Logout
  As a logged-in user of SauceDemo
  I want to log out of the application
  So that my session is securely terminated

  Background:
    Given I am logged in as a standard user

  @logout
  Scenario: Logged-in user can see the burger menu and logout option
    When I open the burger menu
    Then the logout link should be visible

  @smoke @logout
  Scenario: Successful logout from the inventory page
    When I click the logout link
    Then I should be redirected to the login page
    And the login form should be visible

  @negative @logout
  Scenario: User cannot access inventory page after logging out
    When I click the logout link
    And I navigate directly to the inventory page
    Then I should be redirected to the login page
    And I should see the error message "Epic sadface: You can only access '/inventory.html' when you are logged in."
