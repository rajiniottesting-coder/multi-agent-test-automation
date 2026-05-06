Feature: Login Validation
  As a user of SauceDemo
  I want to see validation messages when I attempt to log in with invalid or incomplete credentials
  So that I understand why my login attempt failed

  Background:
    Given I am on the SauceDemo login page

  @login @negative @SCRUM-7
  Scenario: Login fails with invalid username and password
    When I log in with username "invalid_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @login @negative @SCRUM-8
  Scenario: Login fails for locked-out user
    When I log in with username "locked_out_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."

  @login @edge @SCRUM-9
  Scenario: Login fails with empty username field
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @login @edge @SCRUM-10
  Scenario: Login fails with empty password field
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"

  @login @edge @SCRUM-11
  Scenario: Login fails with both empty username and password fields
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
