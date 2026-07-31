@admin
Feature: Admin user lifecycle
  As an HR administrator
  I want to create, find and delete system users
  So that I can manage access with confidence that only my own data is affected

  Background:
    Given I am logged in as "admin"
    And I am on the Admin Users list

  @negative @admin
  # JIRA: SCRUM-106 (hash: 121dea5c)
  Scenario: Searching for a username that was never created returns no records
    When I search the users list for a run-unique username that does not exist
    Then the users search results should show "No Records Found"

  @regression @admin
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation leaves the created user in place
    Given a run-unique system user has been created with role "ESS" status "Enabled" and password "Passw0rd1"
    When I search the users list for the created username
    Then the users search results should show "(1) Records Found"
    And the created username should be shown in the results row
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I cancel the delete confirmation dialog
    Then no success toast should be shown
    When I search the users list for the created username
    Then the users search results should show "(1) Records Found"
    When I click the delete icon on the single result row
    And I confirm the delete
    Then a success toast should be shown
    When I search the users list for the created username
    Then the users search results should show "No Records Found"

  @smoke @admin
  # JIRA: SCRUM-104 (hash: 7088dc26)
  Scenario: Full lifecycle create find and delete a system user
    When I click the Add button on the users list
    Then the Add User form should be displayed
    When I select the user role "ESS"
    And I select the first employee suggestion for the letter "a"
    And I select the status "Enabled"
    And I enter a run-unique username in the Add User form
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click the Save button
    Then a success toast should be shown
    When I search the users list for the created username
    Then the users search results should show "(1) Records Found"
    And the created username should be shown in the results row
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should be displayed
    When I confirm the delete
    Then a success toast should be shown
    When I search the users list for the created username
    Then the users search results should show "No Records Found"
