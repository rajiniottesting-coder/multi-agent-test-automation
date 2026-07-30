@admin @password_validation
Feature: Admin Add User password validation
  As an HR admin
  I want inline password validation on the Add User form
  So that I am guided to create a password that meets policy rules

  Background:
    Given I am on the OrangeHRM login page
    And I log in as "admin"
    And I navigate to the Admin Add User page

  @negative @validation @password_validation
  # JIRA: SCRUM-93 (hash: e5b02d72)
  Scenario: Password policy inline validation for invalid passwords
    When I enter password "abc12" in the add user form
    And I click outside the password field
    Then I should see the password validation message "Should have at least 7 characters"
    When I clear the password field in the add user form
    And I enter password "abcdefgh" in the add user form
    And I click outside the password field
    Then I should see the password validation message "Your password must contain minimum 1 number"
    When I clear the password field in the add user form
    And I enter password "ABCDEF123" in the add user form
    And I click outside the password field
    Then I should see the password validation message "Your password must contain minimum 1 lower-case letter"
    When I clear the password field in the add user form
    And I enter password "abc 1234" in the add user form
    And I click outside the password field
    Then I should see the password validation message "Your password should not contain spaces"

  @positive @password_validation
  # JIRA: SCRUM-94 (hash: 90e22438)
  Scenario: Valid password shows no validation message
    When I enter password "Str0ngPass1" in the add user form
    And I click outside the password field
    Then I should not see any password validation message

  @negative @password_validation
  # JIRA: SCRUM-95 (hash: f7ce6dd2)
  Scenario: Confirm Password mismatch shows error
    When I enter password "Str0ngPass1" in the add user form
    And I enter confirm password "DifferentPass9" in the add user form
    And I click outside the confirm password field
    Then I should see the password validation message "Passwords do not match"

  @positive @password_validation
  # JIRA: SCRUM-96 (hash: bc182236)
  Scenario: Matching Confirm Password shows no error
    When I enter password "Str0ngPass1" in the add user form
    And I enter confirm password "Str0ngPass1" in the add user form
    And I click outside the confirm password field
    Then I should not see any password validation message

  @edge @password_validation
  # JIRA: SCRUM-97 (hash: 5ca6203a)
  Scenario: Password exactly at the 7-character minimum boundary
    When I enter password "Abcd1x" in the add user form
    And I click outside the password field
    Then I should see the password validation message "Should have at least 7 characters"
    When I clear the password field in the add user form
    And I enter password "Abcde1x" in the add user form
    And I click outside the password field
    Then I should not see any password validation message

  @negative @validation @password_validation
  # JIRA: SCRUM-98 (hash: 412aff63)
  Scenario: Password and Confirm Password required field validation
    When I click into the password field and click away
    Then I should see the password validation message "Required"
    When I click into the confirm password field and click away
    Then I should see the password validation message "Required"
