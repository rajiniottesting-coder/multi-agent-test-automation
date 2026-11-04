@test_cases
Feature: Automation Exercise Test Cases page
  As a visitor
  I want to open the Test Cases page from the top menu
  So that I can read each test case and expand its steps

  Background:
    Given I am on the home page

  @smoke @test_cases
  # JIRA: SCRUM-312 (hash: 5e7948bc) owner: SCRUM-293
  Scenario: Open the Test Cases page from the top menu and verify its layout
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be displayed with the heading "Test Cases"
    And each test case title should be rendered as a link

  @test_cases
  # JIRA: SCRUM-313 (hash: 3f300ca1) owner: SCRUM-293
  Scenario: Clicking a test case title shows its steps underneath
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be displayed with the heading "Test Cases"
    When I click the first test case title
    Then the steps for that test case should be shown
    And I should remain on the Test Cases page
