@admin @user-management
Feature: OrangeHRM Admin user management
  As an HR administrator
  I want to create, find and delete system users
  So that I can manage access to OrangeHRM

  Background:
    Given I am logged in as "admin"
    And I am on the Admin Users list

  @smoke @admin @positive
  # JIRA: SCRUM-104 (hash: 7088dc26)
  Scenario: Full lifecycle - create a system user, find it by exact username, then delete it
    When I click the Add button on the Users list
    And I select the user role "ESS"
    And I enter an employee name starting with "a"
    And I select the status "Enabled"
    And I enter a run-unique username
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I save the user
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    And the single result row should show the created username
    When I delete the created user and confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @admin @edge
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation dialog leaves the created user in place
    When I click the Add button on the Users list
    And I select the user role "ESS"
    And I enter an employee name starting with "a"
    And I select the status "Enabled"
    And I enter a run-unique username
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I save the user
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    When I delete the created user and cancel the deletion
    Then I should not see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    When I delete the created user and confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @admin @negative
  # JIRA: SCRUM-106 (hash: 121dea5c)
  Scenario: Searching for a username that was never created returns No Records Found
    When I search the Users list for username "zzz_nonexistent_9876543210"
    Then the results summary should read "No Records Found"
