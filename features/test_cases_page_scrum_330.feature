@test-cases
Feature: Test Cases page navigation
  As a visitor
  I want to open the Test Cases page from the home page
  So that I can read the documented test cases

  Background:
    Given I am on the home page

  @smoke @test-cases
  # JIRA: SCRUM-331 (hash: b82a86b0) owner: SCRUM-330 impacted-by: SCRUM-354
  Scenario: Open the Test Cases page from the home page button
    Given I am on the home page
    When I click the Test Cases button on the home page
    Then I should be on the Test Cases page
    And the page should be headed "Test Cases"
    And a list of test case titles should be displayed
    And the feedback section should be headed "Questions or suggestions?"
    And the heading "Feedback for Us" should not be shown
    And the feedback email link should read "Write to our QA team"
    And the link text "feedback@automationexercise.com" should not be shown
    And the feedback email link should point to "feedback@automationexercise.com"
