@admin @add_user @password_validation
Feature: Add User password and confirm-password validation
  As an OrangeHRM administrator
  I want the Add User form to validate the password and confirm-password fields
  So that only users with policy-compliant, matching passwords can be created

  Background:
    Given I am logged in as "admin"
    And I am on the Add User form

  @smoke @validation @password_validation
  # JIRA: SCRUM-99 (hash: 42f12c7a)
  Scenario: Password field shows the correct policy message as the user types
    When I enter the password "abc12"
    Then I should see the password field error "Should have at least 7 characters"
    When I enter the password "abcdefg"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I enter the password "abcdefgh"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I enter the password "ABCDEF123"
    Then I should see the password field error "Your password must contain minimum 1 lower-case letter"
    When I enter the password "abc 1234"
    Then I should see the password field error "Your password should not contain spaces"
    When I enter the password "Str0ngPass1"
    Then I should not see any password field error

  @negative @validation @password_validation
  # JIRA: SCRUM-100 (hash: f2dd54c6)
  Scenario: Confirm Password mismatch shows 'Passwords do not match'
    When I enter the password "Str0ngPass1"
    Then I should not see any password field error
    When I enter the confirm password "Str0ngPass2"
    Then I should see the confirm password field error "Passwords do not match"
    When I enter the confirm password "Str0ngPass1"
    Then I should not see any confirm password field error

  @edge @validation @password_validation
  # JIRA: SCRUM-101 (hash: f2821f06)
  Scenario: Empty and whitespace-only Password and Confirm Password fields show 'Required'
    When I focus and blur the password field without typing
    Then I should see the password field error "Required"
    When I enter the password "   "
    Then I should see the password field error "Required"
    When I enter the password "Str0ngPass1"
    And I focus and blur the confirm password field without typing
    Then I should see the confirm password field error "Required"

  @negative @validation @password_validation
  # JIRA: SCRUM-102 (hash: b6638429)
  Scenario: Save is blocked and no user is created when the password is invalid
    When I select the user role "ESS"
    And I select an employee from the autocomplete
    And I select the status "Enabled"
    And I enter the username "qa_pwtest01"
    And I enter the password "abcdefgh"
    And I enter the confirm password "abcdefgh"
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I click the Save button
    Then I should remain on the Add User form
    And I should see the password field error "Your password must contain minimum 1 number"
    When I search the users list for username "qa_pwtest01"
    Then the users search should return no records
