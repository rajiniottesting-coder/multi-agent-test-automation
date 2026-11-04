@testcases
Feature: Automation Exercise Test Cases listing and search
  As a visitor
  I want to browse and search the Test Cases page
  So that I can quickly find the test case I am interested in

  Background:
    Given I am on the Test Cases page

  @smoke @testcases
  # JIRA: SCRUM-320 (hash: e7c20533) owner: SCRUM-294
  Scenario: Test Cases page lists each test case title as a clickable link
    Then the full list of test case titles is displayed
    And the test case title "successful login with valid credentials" is shown as a link
    And the test case title "add a single product to the cart from its product details page" is shown as a link

  @positive @testcases
  # JIRA: SCRUM-321 (hash: 3d4571e9) owner: SCRUM-294
  Scenario: Typing a keyword shows only matching test case titles
    Then the full list of test case titles is displayed
    When I search the test cases for "login"
    Then every shown test case title contains "login"
    And the test case title "searching for an existing product returns only matching products" should not be shown

  @negative @testcases
  # JIRA: SCRUM-322 (hash: 8b926011) owner: SCRUM-294
  Scenario: Searching for a keyword that matches no test case title shows no results
    Then the full list of test case titles is displayed
    When I search the test cases for "Zznonexistentkeyword999"
    Then no test case titles are shown

  @edge @testcases
  # JIRA: SCRUM-323 (hash: 4c0b07cc) owner: SCRUM-294
  Scenario: Clearing the search box after filtering restores the full list
    Then the full list of test case titles is displayed
    When I search the test cases for "login"
    Then every shown test case title contains "login"
    And the test case title "visitor subscribes to the newsletter with a valid email address" should not be shown
    When I clear the test case search box
    Then the test case title "visitor subscribes to the newsletter with a valid email address" is shown
    And the test case title "successful login with valid credentials" is shown
