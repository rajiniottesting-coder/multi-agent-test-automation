@home
Feature: Home page footer and scroll-up arrow
  As a visitor
  I want the footer subscription controls and the scroll-up arrow to work
  So that I can subscribe to the newsletter and return to the top of the page

  Background:
    Given I am on the home page

  @smoke @home
  # JIRA: SCRUM-383 (hash: 69e4e454) owner: SCRUM-379
  Scenario: Home page footer shows newsletter subscription email field and subscribe button
    When I scroll down to the footer
    Then the Subscription heading should be shown in the footer
    And the newsletter email input should be shown in the footer
    And the subscribe button should be shown in the footer

  @home @regression
  # JIRA: SCRUM-384 (hash: 1b07bbe2) owner: SCRUM-379
  Scenario: Scroll-up arrow returns visitor to top of home page after reading to the bottom
    When I scroll down to the footer
    Then the Subscription heading should be shown in the footer
    When I click the scroll-up arrow
    Then the top of the home page should be displayed

  @home @regression
  # JIRA: SCRUM-385 (hash: 2a6fe1ed) owner: SCRUM-379
  Scenario: Scroll-up arrow returns to top of home page when clicked from a partial scroll position
    When I scroll down partway to the middle of the home page
    When I click the scroll-up arrow
    Then the top of the home page should be displayed
