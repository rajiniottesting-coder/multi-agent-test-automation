Feature: Login Edge Cases and Validation
  As a user of SauceDemo
  I want the login form to validate my input correctly
  So that I receive clear feedback when credentials are missing, invalid, or malformed

  Background:
    Given I am on the SauceDemo login page

  @positive @login
  # JIRA: SCRUM-51 (hash: 512f7f08)
  Scenario: Successful login with valid credentials redirects to inventory page
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"

  @negative @login
  # JIRA: SCRUM-52 (hash: bb01ac5a)
  Scenario: Login with invalid credentials and locked-out user displays appropriate error messages
    When I log in with username "invalid_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "standard_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "locked_out_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."

  @negative @validation @login
  # JIRA: SCRUM-53 (hash: dd71ca8e)
  Scenario: Login form field validation for empty username and/or password
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @edge @login
  # JIRA: SCRUM-54 (hash: 238b7da4)
  Scenario: Login with credentials containing leading/trailing spaces and special characters
    When I log in with username " standard_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "standard_user" and password "secret_sauce "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    And I clear the login form
    And I log in with username "<script>alert(1)</script>" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
