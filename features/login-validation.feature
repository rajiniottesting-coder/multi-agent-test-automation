Feature: Login Validation and Error Handling
  As a user of SauceDemo
  I want to understand login validation and error messages
  So that I can correct my input or understand system limitations

  Background:
    Given I am on the SauceDemo login page

  @smoke @login @positive
  Scenario: Successful login with standard user credentials
    When I log in with username "standard_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"

  @negative @login
  Scenario: Login fails with invalid username and password
    When I log in with username "invalid_user" and password "wrong_password"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"

  @negative @login
  Scenario: Login fails for locked-out user
    When I log in with username "locked_out_user" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Sorry, this user has been locked out."

  @edge @login
  Scenario: Login validation error for empty username field
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @edge @login
  Scenario: Login validation error for empty password field
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"

  @edge @login
  Scenario: Login validation error for both empty username and password fields
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
