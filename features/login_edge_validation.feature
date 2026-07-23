Feature: Login Edge Validation
  As a user of SauceDemo
  I want the login form to validate empty and whitespace-only inputs
  So that I receive clear feedback and can still log in with valid credentials

  Background:
    Given I am on the SauceDemo login page

  @negative @login-edge-validation
  # JIRA: SCRUM-66 (hash: 33a77251)
  Scenario: Login form field validation — empty username, empty password, both empty
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    And I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @edge @login-edge-validation
  # JIRA: SCRUM-67 (hash: e5f6g7h8)
  Scenario: Login with whitespace-only inputs and performance_glitch_user
    When I log in with username "   " and password "   "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "performance_glitch_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"
