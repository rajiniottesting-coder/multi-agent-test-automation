@admin
Feature: Admin user lifecycle
  As an HR administrator
  I want to create, find and delete system users
  So that user accounts stay under my control

  Background:
    Given I am logged in as "admin"
    And I am on the Admin Users list

  @negative @admin
  # JIRA: SCRUM-106 (hash: 121dea5c)
  Scenario: Searching for a username that was never created returns no records
    When I search for the username "zzz_nonexistent_9876543210"
    Then the results summary should read "No Records Found"

  @regression @admin
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation leaves the created user in place
    Given I have created a run-unique system user with role "ESS" status "Enabled" and password "Passw0rd1"
    When I search for the created username
    Then the results summary should read "(1) Record"
    And the single result row should show the created username
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I cancel the delete confirmation dialog
    Then no success toast should be shown
    When I search for the created username
    Then the results summary should read "(1) Record"
    When I click the delete icon on the single result row
    And I confirm the delete
    Then a success toast should be shown
    When I search for the created username
    Then the results summary should read "No Records Found"

  @smoke @admin
  # JIRA: SCRUM-104 (hash: 7088dc26)
  Scenario: Full lifecycle create find and delete a system user
    When I click the Add button
    Then I should be on the Add User form
    When I select the user role "ESS"
    And I select an employee by typing "a"
    And I select the status "Enabled"
    And I enter a run-unique username
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click the Save button
    Then a success toast should be shown
    When I search for the created username
    Then the results summary should read "(1) Record"
    And the single result row should show the created username
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I confirm the delete
    Then a success toast should be shown
    When I search for the created username
    Then the results summary should read "No Records Found"
