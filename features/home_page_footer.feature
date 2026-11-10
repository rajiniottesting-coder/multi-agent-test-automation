@home
Feature: Home page footer newsletter subscription
  As a visitor
  I want to see the newsletter subscription controls in the home page footer
  So that I can sign up for updates

  Background:
    Given I am on the home page

  @smoke @home
  # JIRA: SCRUM-383 (hash: 69e4e454) owner: SCRUM-379
  Scenario: Footer shows the subscription email field and subscribe button
    Then I should see the Subscription heading in the footer
    And I should see the subscription email field in the footer
    And I should see the subscribe button in the footer
