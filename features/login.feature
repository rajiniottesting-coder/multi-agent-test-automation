# GOLD STANDARD reference feature. Agent 2 copies this style.
#
# Conventions it demonstrates:
#   - one Scenario per behaviour, not per input value
#   - real logins go through a ROLE ("I log in as"); credentials never appear here
#   - INVALID data stays literal — empty strings and wrong passwords are test
#     data, not secrets
#   - tags mark category so `pytest -m negative` works
@login
Feature: OrangeHRM login
  As an HR user
  I want to log in to OrangeHRM
  So that I can reach my dashboard

  Background:
    Given I am on the OrangeHRM login page

  @smoke @login
  Scenario: Successful login with valid admin credentials
    When I log in as "admin"
    Then I should be redirected to the dashboard
    And I should see the page title "Dashboard"

  @negative @login
  Scenario: Login fails with an incorrect password
    When I log in as "admin" with an incorrect password
    Then I should see the error message "Invalid credentials"
    And I should remain on the login page

  @negative @login
  Scenario: Login fails with an unknown username
    When I log in with username "no.such.user" and password "whatever123"
    Then I should see the error message "Invalid credentials"
    And I should remain on the login page

  @negative @validation @login
  Scenario: Required-field validation on an empty form
    When I log in with username "" and password ""
    Then I should see the field error "Required"
    And I should remain on the login page

  @login
  Scenario: A failed login can be cleared and retried
    When I log in with username "no.such.user" and password "whatever123"
    Then I should see the error message "Invalid credentials"
    When I clear the credential fields
    And I log in as "admin"
    Then I should be redirected to the dashboard
