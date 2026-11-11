@testcases
Feature: Automation Exercise Test Cases page
  As a visitor
  I want to open the Test Cases page from the top menu
  So that I can read the documented test cases and their steps

  Background:
    Given I am on the home page

  @smoke @testcases
  # JIRA: SCRUM-312 (hash: f97f1aa6) owner: SCRUM-293
  Scenario: Open the Test Cases page from the top menu and verify its layout
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be headed "Test Cases"
    And each test case title should be shown as a link
    And the Feedback for Us section should show an email address link

  @testcases
  # JIRA: SCRUM-313 (hash: 3f300ca1) owner: SCRUM-293
  Scenario: Clicking a test case's title shows its steps underneath
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be headed "Test Cases"
    When I click the title of the first test case
    Then the steps of that test case should be displayed
    And I should remain on the Test Cases page
