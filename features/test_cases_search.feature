@testcases
Feature: Test Cases page search
  As a visitor
  I want to search the list of test cases
  So that I can quickly find the ones that interest me

  Background:
    Given I am on the Test Cases page

  @smoke @testcases
  # JIRA: SCRUM-340 (hash: 2f22a94d) owner: SCRUM-332
  Scenario: Search box is displayed above the list of test cases
    Then the Test Cases page should be headed "Test Cases"
    And the test case search box should be displayed

  @testcases
  # JIRA: SCRUM-341 (hash: bae241c3) owner: SCRUM-332
  Scenario: Typing a word into the search box filters the list to only matching titles
    When I note a distinctive word from the first test case title
    And I note a test case title that does not contain that word
    And I type that word into the test case search box
    Then every test case title shown should contain that word
    And the originally noted title should still be shown
    And the non-matching title should not be shown on the Test Cases page
