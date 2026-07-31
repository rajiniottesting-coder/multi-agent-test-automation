@admin
Feature: Admin system user lifecycle
  As an HR administrator
  I want to create, search and delete system users
  So that I can manage application access safely on a shared environment

  Background:
    Given I am logged in as "admin"
    And I am on the Users list page

  @smoke @admin
  # JIRA: SCRUM-107 (hash: 7df45137)
  Scenario: Create, search and delete a system user
    When I click the Add button on the Users list
    And I select "ESS" from the User Role dropdown
    And I select an employee whose name starts with "pet"
    And I select "Enabled" from the Status dropdown
    And I enter a run-unique username for user creation
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click Save on the Add User form
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should contain "(1) Record"
    And the result row username should equal the created username
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should appear
    When I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"

  @negative @admin
  # JIRA: SCRUM-108 (hash: 3b8d4208)
  Scenario: Searching for a non-existent username shows No Records Found
    When I search the Users list for username "zz_never_exists_9999999"
    Then the results summary should read "No Records Found"

  @regression @admin
  # JIRA: SCRUM-109 (hash: 8e53210d)
  Scenario: Cancelling the delete confirmation leaves the created user intact
    When I click the Add button on the Users list
    And I select "ESS" from the User Role dropdown
    And I select an employee whose name starts with "pet"
    And I select "Enabled" from the Status dropdown
    And I enter a run-unique username for user creation
    And I enter the password "Passw0rd1" and confirm password "Passw0rd1"
    And I click Save on the Add User form
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should contain "(1) Record"
    When I click the delete icon on the single result row
    Then the delete confirmation dialog should appear
    When I cancel the deletion
    Then no success toast should be shown
    When I search the Users list for the created username
    Then the results summary should contain "(1) Record"
    And the result row username should equal the created username
    When I click the delete icon on the single result row
    And I confirm the deletion
    Then I should see a success toast
    When I search the Users list for the created username
    Then the results summary should read "No Records Found"
