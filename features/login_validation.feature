Feature: Login Field Validation
  As a user of SauceDemo
  I want to see clear validation errors when I submit invalid login data
  So that I understand what corrections are needed

  Background:
    Given I am on the SauceDemo login page

  @negative @login-validation
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

  @negative @login-validation
  Scenario: Invalid or locked-out credentials show appropriate error messages
    When I log in with username "standard_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the credential fields
    And I log in with username "invalid_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the credential fields
    When I log in as "locked_out"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."
    When I dismiss the error message
    Then no error message should be displayed

  @edge @login-validation
  Scenario: Whitespace-only username and password are treated as empty
    When I log in with username "   " and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the credential fields
    And I log in with username "standard_user" and password "   "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
