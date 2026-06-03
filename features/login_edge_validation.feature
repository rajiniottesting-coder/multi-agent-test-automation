Feature: Login Edge Validation
  As a user of SauceDemo
  I want the login form to properly validate edge cases
  So that whitespace credentials are rejected and empty fields show appropriate errors

  Background:
    Given I am on the SauceDemo login page

  @edge @login
  # JIRA: SCRUM-50 (hash: 3a3b9cb1)
  Scenario: Login fails with leading and trailing whitespace in credentials
    When I log in with username " standard_user " and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    And I should remain on the login page
    When I dismiss the error message
    Then the error message should not be visible
    When I log in with username "standard_user" and password " secret_sauce "
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
    And I should remain on the login page

  @negative @login
  # JIRA: SCRUM-49 (hash: 9f7abd41)
  Scenario: Login form field validation for empty username and empty password
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    And I should remain on the login page
    When I dismiss the error message
    When I log in with username "standard_user" and password ""
    Then I should see the error message "Epic sadface: Password is required"
    And I should remain on the login page
    When I dismiss the error message
    When I log in with username "" and password "secret_sauce"
    Then I should see the error message "Epic sadface: Username is required"
    And I should remain on the login page
