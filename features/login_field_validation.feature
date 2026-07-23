Feature: Login Field Validation
  As a user of SauceDemo
  I want to see clear validation errors when I submit the login form with empty or whitespace-only fields
  So that I understand which fields are required

  Background:
    Given I am on the SauceDemo login page

  @negative @login-field-validation
  # JIRA: SCRUM-86 (hash: cfbd0e5e)
  Scenario: Empty username or password fields display required-field errors
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    And I clear the credential fields
    And I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    And I clear the credential fields
    And I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"

  @edge @login-field-validation
  # JIRA: SCRUM-87 (hash: e5f6g7h8)
  Scenario: Whitespace-only username and password are treated as empty
    When I log in with username "   " and password "secret_sauce"
    Then I should see a login error
    When I dismiss the error message
    And I clear the credential fields
    And I log in with username "standard_user" and password "   "
    Then I should see a login error
