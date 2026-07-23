Feature: Login Edge Validation
  As a user of SauceDemo
  I want the login form to properly validate edge-case inputs
  So that invalid or empty credentials are rejected with clear error messages

  Background:
    Given I am on the SauceDemo login page

  @negative @login-edge-validation
  # JIRA: SCRUM-74 (hash: de8bdc7c)
  Scenario: Login form field validation — empty username, empty password, both empty
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    Then no error message should be displayed
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    Then no error message should be displayed
    When I clear the credential fields
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"

  @edge @login-edge-validation
  # JIRA: SCRUM-75 (hash: 45c8a531)
  Scenario: Login with whitespace-only fields is rejected
    When I log in with username "   " and password "   "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    When I dismiss the error message
    Then no error message should be displayed
    When I clear the credential fields
    When I log in with username "standard_user" and password "   "
    Then I should see an error message containing "Epic sadface:"
    And I should remain on the login page

  @edge @login-edge-validation
  # JIRA: SCRUM-76 (hash: aa0ce564)
  Scenario: Login with performance_glitch_user succeeds despite delay
    When I log in with username "performance_glitch_user" and password "secret_sauce"
    Then I should be redirected to the inventory page
    And I should see the page title "Products"
    And I should see 6 inventory items
