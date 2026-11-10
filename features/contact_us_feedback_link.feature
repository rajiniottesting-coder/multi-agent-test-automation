@contact
Feature: Contact Us feedback email link
  As a visitor to the Contact Us page
  I want the feedback email link to show the email address
  So that I can write to the team as I always could, unaffected by the Test Cases page rename

  Background:
    Given I am on the home page

  @smoke @contact @regression
  # JIRA: SCRUM-366 (hash: c5727bef) owner: SCRUM-354
  Scenario: Feedback email link on the Contact Us page remains unaffected by the Test Cases page rename
    When I click the Contact Us link in the navigation
    Then the Contact Us page should be shown
    And the feedback email link should display the email address as its link text
    And the feedback email link should be a mailto link
