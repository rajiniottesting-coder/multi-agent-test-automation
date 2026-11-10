Feature: Throw-away validation checks (never merged)

  Scenario: A throw-away check whose first attempt meets an unreachable host
    Then the throw-away check reaches the home page on its second attempt

  Scenario: A throw-away check of the Test Cases heading
    Given I open the throw-away Test Cases page
    Then the throw-away Test Cases heading reads as expected
