Feature: Login Validation Edge Cases
  As a user of SauceDemo
  I want to receive clear validation messages for incomplete login attempts
  So that I can correct my input and successfully log in

  Background:
    Given I am on the SauceDemo login page

  @negative @login @validation @SCRUM-11
  Scenario: Login fails with empty username and empty password
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"

  @negative @login @validation @SCRUM-10
  Scenario: Login fails with empty password
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"

  @negative @login @validation @SCRUM-9
  Scenario: Login fails with empty username
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"
