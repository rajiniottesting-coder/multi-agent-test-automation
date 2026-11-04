@test_cases
Feature: Automation Exercise Test Cases page
  As a visitor
  I want to open the Test Cases page and reveal each test case's steps
  So that I can read the documented test scenarios without leaving the page

  Background:
    Given I am on the home page

  @smoke @test_cases
  # JIRA: SCRUM-312 (hash: f97f1aa6) owner: SCRUM-293
  Scenario: Open the Test Cases page from the top menu and verify its layout
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be headed "Test Cases"
    And each test case title should be shown as a link
    And a "Feedback for Us" section should display an email address link

  @smoke @test_cases
  # JIRA: SCRUM-313 (hash: 3f300ca1) owner: SCRUM-293
  Scenario: Clicking a test case's title shows its steps underneath
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be headed "Test Cases"
    When I click the title of the first test case
    Then the steps for the first test case should be shown
    And I should remain on the Test Cases page

  @test_cases
  Scenario: Each test case title independently reveals its own steps
    When I click "Test Cases" in the top navigation menu
    Then the Test Cases page should be headed "Test Cases"
    When I click the title of the first test case
    Then the steps for the first test case should be shown
    When I click the title of the second test case
    Then the steps for the second test case should be shown
    And I should remain on the Test Cases page
