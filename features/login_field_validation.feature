Feature: Login Field Validation
  As a user of SauceDemo
  I want to see clear validation errors when I submit empty or whitespace-only credentials
  So that I know which fields are required

  Background:
    Given I am on the SauceDemo login page

  @negative @login @validation
  # JIRA: SCRUM-91 (hash: 949a2d48)
  Scenario: Empty and whitespace-only username/password show correct validation errors
    When I log in with username "" and password "Password123"
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    And I clear the credential fields
    When I log in as "standard" with an empty password
    Then I should see the error message "Epic sadface: Password is required"
    When I dismiss the error message
    And I clear the credential fields
    When I log in with username "" and password ""
    Then I should see the error message "Epic sadface: Username is required"
    When I dismiss the error message
    And I clear the credential fields
    When I log in with username " " and password "Password123"
    Then I should see the error message "Epic sadface: Username and password do not match any user in this service"
