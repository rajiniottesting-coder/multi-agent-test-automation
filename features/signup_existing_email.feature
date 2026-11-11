@signup
Feature: Signup with an already-registered email
  As a returning shopper who forgot I already have an account
  I want the signup form to refuse an email that is already registered
  So that I am told to log in instead of creating a duplicate account

  Background:
    Given I am on the signup and login page

  @negative @signup
  # JIRA: SCRUM-409 (hash: b33f39fe) owner: SCRUM-408
  Scenario: Signup with an already-registered email is refused and the Login form remains available
    When I sign up with name "Demo Visitor" and the email of a "registered" user
    Then I should see the signup error message "Email Address already exist!"
    And I should remain on the signup and login page
    And the login form should still be displayed
