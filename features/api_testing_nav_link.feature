@navigation
Feature: API Testing navigation link
  As a visitor
  I want an API Testing link in the top navigation
  So that I can reach the APIs list from the home and Contact Us pages

  # JIRA: SCRUM-387 (hash: 3dd10e78) owner: SCRUM-381
  @smoke @navigation
  Scenario: Home page top menu shows a working API Testing link next to Test Cases
    Given I am on the home page
    Then I should see the Test Cases link in the top navigation
    And I should see the API Testing link in the top navigation
    When I click the API Testing link
    Then I should be taken to the API testing page

  # JIRA: SCRUM-388 (hash: 4a53eed2) owner: SCRUM-381
  @navigation
  Scenario: Contact Us page top menu shows the same working API Testing link next to Test Cases
    Given I am on the home page
    When I navigate to the Contact Us page
    Then I should see the Test Cases link in the top navigation
    And I should see the API Testing link in the top navigation
    When I click the API Testing link
    Then I should be taken to the API testing page
