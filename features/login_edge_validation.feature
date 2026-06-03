Feature: Login Edge Validation
  As a user of SauceDemo
  I want the login form to handle edge cases properly
  So that whitespace credentials are rejected and empty field errors are shown

  Background:
    Given I am on the SauceDemo login page

  @edge @login
  # JIRA: SCRUM-50 (hash: 3a3b9cb1)
  Scenario: Login with whitespace credentials shows error and error can be dismissed
    When I log in with username " standard_user " and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    Then the error message should not be visible
    When I clear the credentials and log in with username "standard_user" and password " secret_sauce "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @negative @login
  # JIRA: SCRUM-49 (hash: 9f7abd41)
  Scenario: Login form field validation for empty username and empty password
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"
