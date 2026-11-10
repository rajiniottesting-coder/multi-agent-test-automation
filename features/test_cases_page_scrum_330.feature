@test-cases
Feature: Test Cases page navigation
  As a visitor
  I want to open the Test Cases page from the home page
  So that I can read the documented test cases

  Background:
    Given I am on the home page

  @smoke @test-cases
  # JIRA: SCRUM-331 (hash: 5dc9540f) owner: SCRUM-330 impacted-by: SCRUM-360
  Scenario: Open the Test Cases page from the home page button
    Given I am on the home page
    When I click the Test Cases button on the home page
    Then I should be on the Test Cases page
    And the page should be headed "Test Cases"
    And a list of test case titles should be displayed
    And the feedback email link should not be shown
    When I click the feedback Contact us link
    Then I should be on the Contact Us page
    And the Contact Us form should be shown
    And a new browser tab should not be opened
