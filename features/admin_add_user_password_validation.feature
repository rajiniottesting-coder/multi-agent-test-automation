@admin @add_user @validation
Feature: Admin Add User password validation
  As an HR administrator
  I want inline validation on the Add User password fields
  So that I create users with policy-compliant, matching passwords

  Background:
    Given I am logged in as "admin"
    And I am on the Add User page

  @negative @validation
  # JIRA: SCRUM-98 (hash: 412aff63)
  Scenario: Password and Confirm Password required field validation
    When I enter the password ""
    Then the password field error should be "Required"
    When I clear the password fields
    And I enter the confirm password ""
    Then the confirm password field error should be "Required"

  @edge @validation
  # JIRA: SCRUM-97 (hash: 5ca6203a)
  Scenario: Password exactly at the 7-character minimum boundary
    When I enter the password "Abcd1x"
    Then the password field error should be "Should have at least 7 characters"
    When I clear the password fields
    And I enter the password "Abcde1x"
    Then no password field error should be shown

  @positive @validation
  # JIRA: SCRUM-96 (hash: bc182236)
  Scenario: Matching Confirm Password shows no error
    When I enter the password "Str0ngPass1"
    And I enter the confirm password "Str0ngPass1"
    Then no password field error should be shown
    And no confirm password field error should be shown

  @negative @validation
  # JIRA: SCRUM-95 (hash: f7ce6dd2)
  Scenario: Confirm Password mismatch shows error
    When I enter the password "Str0ngPass1"
    And I enter the confirm password "DifferentPass9"
    Then the confirm password field error should be "Passwords do not match"

  @positive @validation
  # JIRA: SCRUM-94 (hash: 90e22438)
  Scenario: Valid password shows no validation message
    When I enter the password "Str0ngPass1"
    Then no password field error should be shown

  @negative @validation
  # JIRA: SCRUM-93 (hash: e5b02d72)
  Scenario: Password policy inline validation for invalid passwords
    When I enter the password "abc12"
    Then the password field error should be "Should have at least 7 characters"
    When I clear the password fields
    And I enter the password "abcdefgh"
    Then the password field error should be "Your password must contain minimum 1 number"
    When I clear the password fields
    And I enter the password "ABCDEF123"
    Then the password field error should be "Your password must contain minimum 1 lower-case letter"
    When I clear the password fields
    And I enter the password "abc 1234"
    Then the password field error should be "Your password should not contain spaces"
