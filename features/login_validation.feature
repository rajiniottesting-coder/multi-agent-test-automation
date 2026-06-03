Feature: Login Validation
  As a user of SauceDemo
  I want the login form to validate my input correctly
  So that I receive clear feedback when credentials are invalid, empty, or contain whitespace

  Background:
    Given I am on the SauceDemo login page

  @edge @login-validation
  # JIRA: SCRUM-50 (hash: 3a3b9cb1)
  Scenario: Login fails when credentials contain leading or trailing whitespace
    When I log in with username " standard_user " and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    Then the error message should not be visible
    When I log in with username "standard_user" and password " secret_sauce "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @negative @login-validation
  # JIRA: SCRUM-49 (hash: 9f7abd41)
  Scenario: Login form displays validation errors for empty fields
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @negative @login-validation
  # JIRA: SCRUM-48 (hash: 0d43120d)
  Scenario: Login fails with invalid credentials and locked-out user
    When I log in with username "invalid_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    When I log in with username "standard_user" and password "incorrect_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    When I log in with username "locked_out_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."

  @smoke @login-validation
  # JIRA: SCRUM-47 (hash: a8340aa2)
  Scenario: Successful login with valid credentials redirects to inventory page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"
