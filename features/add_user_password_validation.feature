@admin @add_user @password_validation
Feature: Add User password validation
  As an HR administrator
  I want the Add User form to validate passwords in real time
  So that only users with policy-compliant passwords are created

  Background:
    Given I am logged in as "admin"
    And I am on the Add User form

  @smoke @positive @password_validation
  # JIRA: SCRUM-99 (hash: 42f12c7a)
  Scenario: Password field shows the correct policy message as the user types
    When I enter the password "abc12"
    Then I should see the password field error "Should have at least 7 characters"
    When I clear the password field
    And I enter the password "abcdefg"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I clear the password field
    And I enter the password "abcdefgh"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I clear the password field
    And I enter the password "ABCDEF123"
    Then I should see the password field error "Your password must contain minimum 1 lower-case letter"
    When I clear the password field
    And I enter the password "abc 1234"
    Then I should see the password field error "Your password should not contain spaces"
    When I clear the password field
    And I enter the password "Str0ngPass1"
    Then I should not see a password field error

  @negative @password_validation
  # JIRA: SCRUM-100 (hash: f2dd54c6)
  Scenario: Confirm Password mismatch shows 'Passwords do not match'
    When I enter the password "Str0ngPass1"
    Then I should not see a password field error
    When I enter the confirm password "Str0ngPass2"
    Then I should see the confirm password field error "Passwords do not match"
    When I clear the confirm password field
    And I enter the confirm password "Str0ngPass1"
    Then I should not see a confirm password field error

  @edge @validation @password_validation
  # JIRA: SCRUM-101 (hash: f2821f06)
  Scenario: Empty and whitespace-only Password and Confirm Password show 'Required'
    When I focus and blur the password field without typing
    Then I should see the password field error "Required"
    When I clear the password field
    And I enter the password "   "
    And I focus and blur the password field without typing
    Then I should see the password field error "Required"
    When I clear the password field
    And I enter the password "Str0ngPass1"
    And I focus and blur the confirm password field without typing
    Then I should see the confirm password field error "Required"

  @negative @password_validation
  # JIRA: SCRUM-102 (hash: b6638429)
  Scenario: Save is blocked and no user is created when the password is invalid
    When I select the user role "ESS"
    Then the user role should show "ESS"
    When I enter an employee name and select the first suggestion
    Then the employee name field should be populated
    When I select the status "Enabled"
    Then the status should show "Enabled"
    When I enter the username "qa_pwtest01"
    Then I should not see a username field error
    When I enter the password "abcdefgh"
    And I enter the confirm password "abcdefgh"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I click the Save button
    Then I should remain on the Add User form
    And I should see the password field error "Your password must contain minimum 1 number"
    When I search the users list by username "qa_pwtest01"
    Then the search should return no records
