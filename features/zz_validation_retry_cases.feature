Feature: Throw-away validation checks (never merged)

  Scenario: A throw-away check whose first attempt meets an unreachable host
    Then the throw-away check reaches the home page on its second attempt

  Scenario: A throw-away check of a test case's steps
    Given I open the throw-away Test Cases page
    When I open the throw-away first test case
    Then the throw-away second test case's steps are shown
