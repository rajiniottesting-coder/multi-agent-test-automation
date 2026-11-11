@testcases
Feature: Test Cases page navigation
  As a visitor
  I want to open the Test Cases page from the home page
  So that I can read the documented test cases

  Background:
    Given I am on the home page

  @smoke @testcases
  # JIRA: SCRUM-331 (hash: a9421d15) owner: SCRUM-330
  Scenario: Open the Test Cases page from the home page button
    When I click the Test Cases button on the home page
    Then I should be on the Test Cases page
    And the page should be headed "Test Cases"
    And a list of test case titles should be displayed
    And the feedback email address link should be shown
