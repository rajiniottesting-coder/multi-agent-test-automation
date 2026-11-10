@test_cases
Feature: Test Cases page keyword search
  As a visitor exploring the documented test cases
  I want to filter the list by keyword
  So that I can quickly find the test cases I care about

  Background:
    Given I am on the Test Cases page

  @smoke @test_cases
  # JIRA: SCRUM-335 (hash: e0be46de) owner: SCRUM-334
  Scenario: Typing a word filters the list to only matching titles
    When I search the test cases for a distinctive word from the first title
    Then every displayed test case title should contain that word
    And a title lacking that word should not be shown on the Test Cases page
    And the first title should still be displayed among the results

  @negative @test_cases
  # JIRA: SCRUM-336 (hash: 6d5ef875) owner: SCRUM-334
  Scenario: A keyword matching no title leaves no test cases displayed
    When I search the test cases for "Zznonexistentproduct999"
    Then no test case titles should be displayed

  @edge @test_cases
  # JIRA: SCRUM-337 (hash: f0b690ae) owner: SCRUM-334
  Scenario: Clearing the keyword restores the full list of titles
    When I search the test cases for a distinctive word from the first title
    And I clear the keyword and search the test cases again
    Then the full baseline list of test case titles should be displayed
