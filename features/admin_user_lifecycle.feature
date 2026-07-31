@admin
Feature: Admin user lifecycle
  As an HR administrator
  I want to create, find and delete system users
  So that I can manage access to OrangeHRM

  Background:
    Given I am logged in as "admin"
    And I am on the Users list page

  @smoke @admin
  Scenario: Full lifecycle - create a system user, find it by exact username, then delete it
    When I click the Add button on the Users list
    And I select the user role "ESS"
    And I enter the employee name starting with "a" and pick the first suggestion
    And I select the status "Enabled"
    And I enter a run-unique username
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click the Save button
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    And the single row username should match the created username
    When I click the delete icon on the matching row
    And I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @edge @admin
  # JIRA: SCRUM-105 (hash: 628f9cb7)
  Scenario: Cancelling the delete confirmation dialog leaves the created user in place
    Given I have created a run-unique system user with role "ESS" and status "Enabled" and password "Passw0rd1"
    And I am on the Users list page
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    And the single row username should match the created username
    When I click the delete icon on the matching row
    And I cancel the deletion
    Then I should not see a success toast
    When I search the Users list for the created username
    Then the results summary should read "(1) Records Found"
    When I click the delete icon on the matching row
    And I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @negative @admin
  Scenario: Searching for a username that was never created returns No Records Found
    When I search the Users list for username "zzz_nonexistent_9876543210"
    Then the results summary should read "No Records Found"
