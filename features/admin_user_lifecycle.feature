@admin
Feature: Admin user lifecycle
  As an HR administrator
  I want to create, find and delete system users
  So that I can manage access with confidence that each action is honoured

  Background:
    Given I am logged in as "admin"
    And I am on the Users list page

  @smoke @admin
  # JIRA: SCRUM-104 (hash: 7088dc26)
  Scenario: Full lifecycle - create a system user, find it by exact username, then delete it
    When I click the Add button
    And I select the user role "ESS"
    And I select an employee from the autocomplete
    And I select the status "Enabled"
    And I enter a run-unique username
    And I enter the password "Passw0rd1"
    And I enter the confirm password "Passw0rd1"
    Then no field error should be shown on the add user form
    When I click the Save button
    Then I should see a success toast on the users list
    When I search for the created username
    Then the results summary should read "(1) Records Found"
    And the single result row should contain the created username
    When I click the delete icon on the matching row
    Then the delete confirmation dialog should be displayed
    When I confirm the deletion
    Then I should see a success toast on the users list
    When I search for the created username
    Then the results summary should read "No Records Found"

  @regression @admin
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation dialog leaves the created user in place
    Given a run-unique system user has been created
    When I search for the created username
    Then the results summary should read "(1) Records Found"
    And the single result row should contain the created username
    When I click the delete icon on the matching row
    Then the delete confirmation dialog should be displayed
    When I cancel the deletion
    Then no success toast should be shown on the users list
    When I search for the created username
    Then the results summary should read "(1) Records Found"
    When I click the delete icon on the matching row
    And I confirm the deletion
    Then I should see a success toast on the users list
    When I search for the created username
    Then the results summary should read "No Records Found"

  @negative @admin
  # JIRA: SCRUM-106 (hash: 121dea5c)
  Scenario: Searching for a username that was never created returns No Records Found
    When I search the users list for username "zzz_nonexistent_9876543210"
    Then the results summary should read "No Records Found"
