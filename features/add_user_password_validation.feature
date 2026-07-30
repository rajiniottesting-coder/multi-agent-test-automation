@add_user_password_validation
Feature: Add User password and confirm-password inline validation
  As an HR admin
  I want to see inline validation messages for password fields on the Add User form
  So that I can correct password policy violations before submitting

  Background:
    Given I am on the OrangeHRM login page
    And I log in as "admin"
    And I am on the Add User form

  @negative @validation @add_user_password_validation
  # JIRA: SCRUM-93 (hash: e5b02d72)
  Scenario: Password policy inline validation for invalid passwords
    When I enter password "abc12" on the Add User form
    And I click outside the password field
    Then I should see the password field error "Should have at least 7 characters"
    When I clear the password field on the Add User form
    And I enter password "abcdefgh" on the Add User form
    And I click outside the password field
    Then I should see the password field error "Your password must contain minimum 1 number"
    When I clear the password field on the Add User form
    And I enter password "ABCDEF123" on the Add User form
    And I click outside the password field
    Then I should see the password field error "Your password must contain minimum 1 lower-case letter"
    When I clear the password field on the Add User form
    And I enter password "abc 1234" on the Add User form
    And I click outside the password field
    Then I should see the password field error "Your password should not contain spaces"

  @positive @add_user_password_validation
  # JIRA: SCRUM-94 (hash: 90e22438)
  Scenario: Valid password shows no validation message
    When I enter password "Str0ngPass1" on the Add User form
    And I click outside the password field
    Then I should not see a password field error

  @negative @add_user_password_validation
  # JIRA: SCRUM-95 (hash: f7ce6dd2)
  Scenario: Confirm Password mismatch shows error
    When I enter password "Str0ngPass1" on the Add User form
    And I enter confirm password "DifferentPass9" on the Add User form
    And I click outside the confirm password field
    Then I should see the confirm password field error "Passwords do not match"

  @positive @add_user_password_validation
  # JIRA: SCRUM-96 (hash: bc182236)
  Scenario: Matching Confirm Password shows no error
    When I enter password "Str0ngPass1" on the Add User form
    And I enter confirm password "Str0ngPass1" on the Add User form
    And I click outside the confirm password field
    Then I should not see a confirm password field error

  @edge @add_user_password_validation
  # JIRA: SCRUM-97 (hash: 5ca6203a)
  Scenario: Password exactly at the 7-character minimum boundary
    When I enter password "Abcd1x" on the Add User form
    And I click outside the password field
    Then I should see the password field error "Should have at least 7 characters"
    When I clear the password field on the Add User form
    And I enter password "Abcde1x" on the Add User form
    And I click outside the password field
    Then I should not see a password field error

  @negative @validation @add_user_password_validation
  # JIRA: SCRUM-98 (hash: 412aff63)
  Scenario: Password and Confirm Password required field validation
    When I click into the password field and click away
    Then I should see the password field error "Required"
    When I click into the confirm password field and click away
    Then I should see the confirm password field error "Required"
