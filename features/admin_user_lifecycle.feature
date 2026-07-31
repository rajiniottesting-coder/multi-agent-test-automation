@admin
Feature: Admin system-user lifecycle
  As an HR administrator
  I want to create, find and delete system users
  So that I can manage access without leaving residual data

  Background:
    Given I am logged in as "admin"
    And I am on the Users list page

  @smoke @admin
  Scenario: Full lifecycle - create a system user, find it by exact username, then delete it
    When I click the Add button on the Users list
    And I select the User Role "ESS"
    And I enter the employee name prefix "a" and pick the first suggestion
    And I select the Status "Enabled"
    And I enter a run-unique username in the Username field
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click the Save button
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Record"
    And the single result row should contain the created username
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @edge @admin
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation dialog leaves the created user in place
    When I click the Add button on the Users list
    And I select the User Role "ESS"
    And I enter the employee name prefix "a" and pick the first suggestion
    And I select the Status "Enabled"
    And I enter a run-unique username in the Username field
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click the Save button
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Record"
    And the single result row should contain the created username
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I cancel the deletion
    When I search the Users list for the created username
    Then the results summary should read "(1) Record"
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @negative @admin
  Scenario: Searching for a username that was never created returns No Records Found
    When I search the Users list for the username "zzz_nonexistent_9876543210"
    Then the results summary should read "No Records Found"
    And no result rows should be displayed
