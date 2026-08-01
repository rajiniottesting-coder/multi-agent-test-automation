# GOLD STANDARD reference feature. Agent 2 copies this style.
#
# Conventions it demonstrates:
#   - one Scenario per behaviour, not per input value
#   - real logins go through a ROLE ("I log in as"); credentials never appear here
#   - INVALID data stays literal — empty strings and wrong passwords are test
#     data, not secrets
#   - tags are lowercase single words, so `pytest -m negative` works
@login
Feature: Automation Exercise login
  As a shopper
  I want to log in to my account
  So that I can use my cart and order history

  Background:
    Given I am on the signup and login page

  @smoke @login
  Scenario: Successful login with valid credentials
    When I log in as "registered"
    Then I should be logged in
    And I should see my account name in the navigation

  @negative @login
  Scenario: Login fails with an incorrect password
    When I log in as "registered" with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page

  @negative @login
  Scenario: Login fails with an unknown email address
    When I log in with email "no.such.user@example.com" and password "whatever123"
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page

  @negative @validation @login
  Scenario: Submitting an empty form does not log the user in
    When I log in with email "" and password ""
    Then I should not be logged in
    And I should remain on the login page

  @login
  Scenario: A failed login can be cleared and retried
    When I log in with email "no.such.user@example.com" and password "whatever123"
    Then I should see the error message "Your email or password is incorrect!"
    When I clear the credential fields
    And I log in as "registered"
    Then I should be logged in
