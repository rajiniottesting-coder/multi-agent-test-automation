Feature: User Logout
  As a logged-in user of SauceDemo
  I want to securely log out
  So that my session is cleared and I am returned to the login page

  Background:
    Given I am on the SauceDemo login page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page

  @smoke @logout @positive
  Scenario: Verify burger menu and Logout option are present on inventory page
    When I open the burger menu
    Then I should see the "Logout" option in the burger menu

  @smoke @logout @positive
  Scenario: Successful logout from inventory page
    When I open the burger menu
    And I click the "Logout" option
    Then I should be redirected to the login page
    And I should see the username and password input fields

  @negative @logout
  Scenario: Logout clears session and prevents direct access to inventory page
    When I open the burger menu
    And I click the "Logout" option
    And I attempt to navigate directly to the inventory page
    Then I should be redirected to the login page
    And I should see the error message "Epic sadface: Username is required"
